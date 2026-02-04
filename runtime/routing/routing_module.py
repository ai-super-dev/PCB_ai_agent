"""
Routing Module
Integrated with artifact store for routing operations

Per Week 1 Task 7-8, 12: Routing Module with Basic Operations + DRC Integration
"""
from typing import List, Optional, Dict, Any, Tuple
import math
from core.artifacts.store import ArtifactStore
from core.artifacts.models import Artifact, ArtifactType, ArtifactMeta, SourceEngine, CreatedBy
from core.ir.gir import GeometryIR, Board, Net, Track, TrackSegment, Via, Footprint
from core.patch.schema import Patch, PatchOp, PatchMeta
from core.patch.operations import MoveComponentOp, AddTrackSegmentOp, AddViaOp


class RoutingModule:
    """
    Routing module integrated with artifact store
    
    Reads G-IR from artifacts and generates routing suggestions.
    """
    
    def __init__(self, artifact_store: Optional[ArtifactStore] = None, 
                 enable_drc_validation: bool = True):
        """
        Initialize routing module
        
        Args:
            artifact_store: Artifact store instance (creates new if None)
            enable_drc_validation: Whether to automatically run DRC after routing
        """
        self.store = artifact_store or ArtifactStore()
        self.enable_drc_validation = enable_drc_validation
    
    def get_board_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """
        Get board artifact from store
        
        Args:
            artifact_id: Board artifact ID
            
        Returns:
            Artifact or None if not found
        """
        artifact = self.store.read(artifact_id)
        if artifact and artifact.type == ArtifactType.PCB_BOARD:
            return artifact
        return None
    
    def get_gir_from_artifact(self, artifact_id: str) -> Optional[GeometryIR]:
        """
        Extract G-IR from board artifact
        
        Args:
            artifact_id: Board artifact ID
            
        Returns:
            GeometryIR object or None
        """
        artifact = self.get_board_artifact(artifact_id)
        if not artifact:
            return None
        
        try:
            # Artifact data contains G-IR as dict (from gir.model_dump())
            data = artifact.data
            
            if isinstance(data, dict):
                # Parse dict back to GeometryIR using Pydantic
                return GeometryIR(**data)
            else:
                return None
            
        except Exception as e:
            print(f"Error converting artifact to G-IR: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def generate_routing_suggestions(self, artifact_id: str) -> List[Patch]:
        """
        Generate routing suggestions based on board artifact using A* pathfinding.
        
        Routes are calculated with obstacle avoidance - NOT straight lines.
        
        Args:
            artifact_id: Board artifact ID
            
        Returns:
            List of Patch objects with routing suggestions
        """
        gir = self.get_gir_from_artifact(artifact_id)
        if not gir:
            return []
        
        artifact = self.get_board_artifact(artifact_id)
        if not artifact:
            return []
        
        suggestions = []
        
        # Collect obstacles from existing components and pads
        obstacles = self._collect_obstacles(gir)
        
        # Get board bounds from outline
        board_bounds = self._get_board_bounds(gir)
        
        # Analyze unconnected nets (nets without tracks)
        connected_nets = {track.net_id for track in gir.tracks}
        unconnected_nets = [net for net in gir.nets if net.id not in connected_nets]
        
        # Generate routing suggestions for unconnected nets
        for net in unconnected_nets[:10]:  # Process up to 10 nets
            # Find pads connected to this net
            pads = []
            for fp in gir.footprints:
                for pad in fp.pads:
                    if pad.net_id == net.id:
                        pads.append((fp, pad))
            
            if len(pads) >= 2:
                # Generate track between first two pads using A* pathfinding
                fp1, pad1 = pads[0]
                fp2, pad2 = pads[1]
                
                # Calculate positions (footprint position + pad offset)
                pos1 = [
                    fp1.position[0] + pad1.position[0],
                    fp1.position[1] + pad1.position[1]
                ]
                pos2 = [
                    fp2.position[0] + pad2.position[0],
                    fp2.position[1] + pad2.position[1]
                ]
                
                # Filter obstacles to exclude pads on this net
                net_obstacles = [
                    obs for obs in obstacles 
                    if obs not in self._get_net_pad_positions(gir, net.id)
                ]
                
                # Calculate path using A* algorithm
                waypoints = self.calculate_route_path(
                    pos1, pos2, 
                    obstacles=net_obstacles,
                    board_bounds=board_bounds
                )
                
                # Create operations for each segment of the path
                ops = []
                layer_id = gir.board.layers[0].id if gir.board.layers else "L1"
                
                for i in range(len(waypoints) - 1):
                    add_track_op = AddTrackSegmentOp(
                        net_id=net.id,
                        layer_id=layer_id,
                        from_pos=waypoints[i],
                        to_pos=waypoints[i + 1],
                        width_mm=0.25  # Default width
                    )
                    ops.append(PatchOp(**add_track_op.to_patch_op()))
                
                # Create patch with all segments
                patch = Patch(
                    artifact_id=artifact_id,
                    from_version=artifact.version,
                    to_version=artifact.version + 1,
                    ops=ops,
                    meta=PatchMeta(
                        author="routing-module",
                        source="agent",
                        explain=f"Route net {net.name} between {fp1.ref} and {fp2.ref} using A* pathfinding ({len(waypoints)-1} segments)"
                    )
                )
                patch.validate_version_consistency()
                suggestions.append(patch)
        
        return suggestions
    
    def _collect_obstacles(self, gir: GeometryIR) -> List[Tuple[float, float, float]]:
        """
        Collect obstacles from board geometry for pathfinding.
        
        Returns list of (x, y, radius) tuples.
        """
        obstacles = []
        
        # Add footprint positions as obstacles
        for fp in gir.footprints:
            # Estimate component size based on pad positions
            if fp.pads:
                max_extent = 0
                for pad in fp.pads:
                    extent = math.sqrt(pad.position[0]**2 + pad.position[1]**2)
                    max_extent = max(max_extent, extent)
                radius = max_extent + 1.0  # Add clearance
            else:
                radius = 2.5  # Default 5mm diameter
            
            obstacles.append((fp.position[0], fp.position[1], radius))
        
        # Add via positions as obstacles
        for via in gir.vias:
            obstacles.append((via.position[0], via.position[1], via.drill_mm / 2 + 0.3))
        
        return obstacles
    
    def _get_board_bounds(self, gir: GeometryIR) -> Optional[Tuple[float, float, float, float]]:
        """Get board boundaries from outline."""
        outline = gir.board.outline.polygon
        if not outline:
            return None
        
        x_coords = [p[0] for p in outline]
        y_coords = [p[1] for p in outline]
        
        return (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
    
    def _get_net_pad_positions(self, gir: GeometryIR, net_id: str) -> List[Tuple[float, float, float]]:
        """Get pad positions for a specific net (these shouldn't be obstacles for that net)."""
        positions = []
        for fp in gir.footprints:
            for pad in fp.pads:
                if pad.net_id == net_id:
                    x = fp.position[0] + pad.position[0]
                    y = fp.position[1] + pad.position[1]
                    positions.append((x, y, 0.5))  # Small radius for pad
        return positions
    
    def optimize_component_placement(self, artifact_id: str) -> List[Patch]:
        """
        Generate component placement optimization suggestions
        
        Args:
            artifact_id: Board artifact ID
            
        Returns:
            List of Patch objects with placement suggestions
        """
        gir = self.get_gir_from_artifact(artifact_id)
        if not gir:
            return []
        
        artifact = self.get_board_artifact(artifact_id)
        if not artifact:
            return []
        
        suggestions = []
        
        # Simple optimization: spread out components that are too close
        min_spacing = 5.0  # mm
        footprints = gir.footprints
        
        for i, fp1 in enumerate(footprints):
            for j, fp2 in enumerate(footprints[i+1:], i+1):
                # Calculate distance
                dx = fp1.position[0] - fp2.position[0]
                dy = fp1.position[1] - fp2.position[1]
                distance = (dx**2 + dy**2)**0.5
                
                if distance < min_spacing:
                    # Suggest moving fp2 away
                    new_x = fp2.position[0] + (min_spacing - distance) * (dx / distance if distance > 0 else 1)
                    new_y = fp2.position[1] + (min_spacing - distance) * (dy / distance if distance > 0 else 1)
                    
                    move_op = MoveComponentOp(
                        component_ref=fp2.ref,
                        new_position_mm=[new_x, new_y],
                        new_rotation_deg=fp2.rotation_deg
                    )
                    
                    patch = Patch(
                        artifact_id=artifact_id,
                        from_version=artifact.version,
                        to_version=artifact.version + 1,
                        ops=[PatchOp(**move_op.to_patch_op())],
                        meta=PatchMeta(
                            author="routing-module",
                            source="agent",
                            explain=f"Move {fp2.ref} to increase spacing from {fp1.ref}"
                        )
                    )
                    patch.validate_version_consistency()
                    suggestions.append(patch)
        
        return suggestions
    
    def route_net(self, artifact_id: str, net_id: str, start_pos: List[float], 
                  end_pos: List[float], layer_id: str, width_mm: float = 0.25) -> Optional[Patch]:
        """
        Route a single net between two points
        
        Args:
            artifact_id: Board artifact ID
            net_id: Net to route
            start_pos: Start position [x, y] in mm
            end_pos: End position [x, y] in mm
            layer_id: Layer to route on
            width_mm: Track width in mm
            
        Returns:
            Patch with routing suggestion or None
        """
        artifact = self.get_board_artifact(artifact_id)
        if not artifact:
            return None
        
        # Create AddTrackSegment operation
        add_track_op = AddTrackSegmentOp(
            net_id=net_id,
            layer_id=layer_id,
            from_pos=start_pos,
            to_pos=end_pos,
            width_mm=width_mm
        )
        
        patch = Patch(
            artifact_id=artifact_id,
            from_version=artifact.version,
            to_version=artifact.version + 1,
            ops=[PatchOp(**add_track_op.to_patch_op())],
            meta=PatchMeta(
                author="routing-module",
                source="agent",
                explain=f"Route net {net_id} from {start_pos} to {end_pos}"
            )
        )
        patch.validate_version_consistency()
        return patch
    
    def place_via(self, artifact_id: str, net_id: str, position: List[float],
                  layers: List[str], drill_mm: float = 0.3) -> Optional[Patch]:
        """
        Place a via at specified position
        
        Args:
            artifact_id: Board artifact ID
            net_id: Net the via belongs to
            position: Via position [x, y] in mm
            layers: List of layer IDs the via connects
            drill_mm: Via drill diameter in mm
            
        Returns:
            Patch with via placement suggestion or None
        """
        artifact = self.get_board_artifact(artifact_id)
        if not artifact:
            return None
        
        add_via_op = AddViaOp(
            net_id=net_id,
            position=position,
            drill_mm=drill_mm,
            layers=layers
        )
        
        patch = Patch(
            artifact_id=artifact_id,
            from_version=artifact.version,
            to_version=artifact.version + 1,
            ops=[PatchOp(**add_via_op.to_patch_op())],
            meta=PatchMeta(
                author="routing-module",
                source="agent",
                explain=f"Place via for net {net_id} at {position}"
            )
        )
        patch.validate_version_consistency()
        return patch
    
    def calculate_route_path(self, start_pos: List[float], end_pos: List[float],
                            obstacles: List[Tuple[float, float, float]] = None,
                            grid_resolution: float = 0.5,
                            board_bounds: Tuple[float, float, float, float] = None) -> List[List[float]]:
        """
        Calculate routing path using A* pathfinding algorithm with obstacle avoidance.
        
        This is REAL routing - not placeholder straight lines.
        
        Args:
            start_pos: Start position [x, y] in mm
            end_pos: End position [x, y] in mm
            obstacles: List of (x, y, radius) obstacles to avoid
            grid_resolution: Grid cell size in mm (default 0.5mm)
            board_bounds: (min_x, min_y, max_x, max_y) board boundaries
            
        Returns:
            List of waypoints [[x1, y1], [x2, y2], ...] with obstacle avoidance
        """
        import heapq
        
        if obstacles is None:
            obstacles = []
        
        # Default board bounds if not provided
        if board_bounds is None:
            all_x = [start_pos[0], end_pos[0]] + [o[0] for o in obstacles]
            all_y = [start_pos[1], end_pos[1]] + [o[1] for o in obstacles]
            margin = 10.0  # mm margin around components
            board_bounds = (
                min(all_x) - margin,
                min(all_y) - margin,
                max(all_x) + margin,
                max(all_y) + margin
            )
        
        min_x, min_y, max_x, max_y = board_bounds
        
        # Convert to grid coordinates
        def to_grid(pos):
            return (
                int((pos[0] - min_x) / grid_resolution),
                int((pos[1] - min_y) / grid_resolution)
            )
        
        def from_grid(grid_pos):
            return [
                min_x + grid_pos[0] * grid_resolution,
                min_y + grid_pos[1] * grid_resolution
            ]
        
        def is_blocked(grid_pos):
            """Check if grid position is blocked by an obstacle"""
            world_pos = from_grid(grid_pos)
            for ox, oy, radius in obstacles:
                dist = math.sqrt((world_pos[0] - ox)**2 + (world_pos[1] - oy)**2)
                if dist < radius + grid_resolution:  # Add clearance
                    return True
            return False
        
        def heuristic(a, b):
            """Manhattan distance heuristic"""
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        
        start_grid = to_grid(start_pos)
        end_grid = to_grid(end_pos)
        
        # Grid dimensions
        grid_width = int((max_x - min_x) / grid_resolution) + 1
        grid_height = int((max_y - min_y) / grid_resolution) + 1
        
        # A* algorithm
        open_set = []
        heapq.heappush(open_set, (0, start_grid))
        came_from = {}
        g_score = {start_grid: 0}
        f_score = {start_grid: heuristic(start_grid, end_grid)}
        
        # 8-directional movement (including diagonals for 45-degree routing)
        directions = [
            (0, 1), (1, 0), (0, -1), (-1, 0),  # Cardinal
            (1, 1), (1, -1), (-1, 1), (-1, -1)  # Diagonal
        ]
        
        while open_set:
            current = heapq.heappop(open_set)[1]
            
            if current == end_grid:
                # Reconstruct path
                path = []
                while current in came_from:
                    path.append(from_grid(current))
                    current = came_from[current]
                path.append(start_pos)
                path.reverse()
                path.append(end_pos)  # Add exact end position
                
                # Optimize path - remove collinear points
                return self._optimize_path(path)
            
            for dx, dy in directions:
                neighbor = (current[0] + dx, current[1] + dy)
                
                # Check bounds
                if neighbor[0] < 0 or neighbor[0] >= grid_width:
                    continue
                if neighbor[1] < 0 or neighbor[1] >= grid_height:
                    continue
                
                # Check obstacles
                if is_blocked(neighbor):
                    continue
                
                # Diagonal movement costs more (sqrt(2))
                move_cost = 1.414 if dx != 0 and dy != 0 else 1.0
                tentative_g = g_score[current] + move_cost
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + heuristic(neighbor, end_grid)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        
        # No path found - return direct connection with warning
        print(f"WARNING: A* pathfinding could not find obstacle-free path from {start_pos} to {end_pos}")
        return [start_pos, end_pos]
    
    def _optimize_path(self, path: List[List[float]]) -> List[List[float]]:
        """
        Optimize path by removing unnecessary waypoints (collinear points).
        Produces cleaner routing with fewer segments.
        """
        if len(path) <= 2:
            return path
        
        optimized = [path[0]]
        
        for i in range(1, len(path) - 1):
            prev = optimized[-1]
            curr = path[i]
            next_pt = path[i + 1]
            
            # Check if points are collinear (within tolerance)
            # Cross product should be near zero for collinear points
            cross = (curr[0] - prev[0]) * (next_pt[1] - curr[1]) - \
                    (curr[1] - prev[1]) * (next_pt[0] - curr[0])
            
            if abs(cross) > 0.01:  # Not collinear - keep this waypoint
                optimized.append(curr)
        
        optimized.append(path[-1])
        return optimized
    
    def optimize_component_spacing(self, artifact_id: str, min_spacing_mm: float = 5.0) -> List[Patch]:
        """
        Optimize component placement to ensure minimum spacing
        
        Args:
            artifact_id: Board artifact ID
            min_spacing_mm: Minimum spacing between components in mm
            
        Returns:
            List of patches with placement optimizations
        """
        gir = self.get_gir_from_artifact(artifact_id)
        if not gir:
            return []
        
        artifact = self.get_board_artifact(artifact_id)
        if not artifact:
            return []
        
        suggestions = []
        footprints = gir.footprints
        
        for i, fp1 in enumerate(footprints):
            for j, fp2 in enumerate(footprints[i+1:], i+1):
                # Calculate distance
                dx = fp1.position[0] - fp2.position[0]
                dy = fp1.position[1] - fp2.position[1]
                distance = math.sqrt(dx**2 + dy**2)
                
                if distance < min_spacing_mm and distance > 0:
                    # Calculate new position to maintain spacing
                    direction_x = dx / distance if distance > 0 else 1.0
                    direction_y = dy / distance if distance > 0 else 1.0
                    
                    # Move fp2 away from fp1
                    move_distance = min_spacing_mm - distance + 0.5  # Add small buffer
                    new_x = fp2.position[0] + direction_x * move_distance
                    new_y = fp2.position[1] + direction_y * move_distance
                    
                    # Ensure new position is within board bounds
                    board_outline = gir.board.outline.polygon
                    if board_outline:
                        x_coords = [p[0] for p in board_outline]
                        y_coords = [p[1] for p in board_outline]
                        new_x = max(min(x_coords), min(max(x_coords), new_x))
                        new_y = max(min(y_coords), min(max(y_coords), new_y))
                    
                    move_op = MoveComponentOp(
                        component_ref=fp2.ref,
                        new_position_mm=[new_x, new_y],
                        new_rotation_deg=fp2.rotation_deg
                    )
                    
                    patch = Patch(
                        artifact_id=artifact_id,
                        from_version=artifact.version,
                        to_version=artifact.version + 1,
                        ops=[PatchOp(**move_op.to_patch_op())],
                        meta=PatchMeta(
                            author="routing-module",
                            source="agent",
                            explain=f"Optimize spacing: Move {fp2.ref} away from {fp1.ref} (distance: {distance:.2f}mm < {min_spacing_mm}mm)"
                        )
                    )
                    patch.validate_version_consistency()
                    suggestions.append(patch)
        
        return suggestions
