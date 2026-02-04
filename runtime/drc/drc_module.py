"""
DRC Module
Integrated with artifact store for DRC operations

Per Week 1 Task 9: Integrate DRC with Artifact Store
"""
from typing import List, Optional, Dict, Any
from core.artifacts.store import ArtifactStore
from core.artifacts.models import Artifact, ArtifactType, ArtifactMeta, SourceEngine, CreatedBy
from core.ir.gir import GeometryIR
from core.ir.cir import ConstraintIR
import json
import subprocess
from pathlib import Path


class DRCModule:
    """
    DRC module integrated with artifact store
    
    Reads board and constraint artifacts, runs DRC, and stores violations.
    """
    
    def __init__(self, artifact_store: Optional[ArtifactStore] = None):
        """
        Initialize DRC module
        
        Args:
            artifact_store: Artifact store instance (creates new if None)
        """
        self.store = artifact_store or ArtifactStore()
    
    def get_board_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Get board artifact from store"""
        artifact = self.store.read(artifact_id)
        if artifact and artifact.type == ArtifactType.PCB_BOARD:
            return artifact
        return None
    
    def get_constraint_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Get constraint artifact from store"""
        artifact = self.store.read(artifact_id)
        if artifact and artifact.type == ArtifactType.CONSTRAINT_RULESET:
            return artifact
        return None
    
    def get_gir_from_artifact(self, artifact_id: str) -> Optional[GeometryIR]:
        """Extract G-IR from board artifact"""
        artifact = self.get_board_artifact(artifact_id)
        if not artifact:
            return None
        
        try:
            data = artifact.data
            if isinstance(data, dict):
                return GeometryIR(**data)
            return None
        except Exception as e:
            print(f"Error converting artifact to G-IR: {e}")
            return None
    
    def get_cir_from_artifact(self, artifact_id: str) -> Optional[ConstraintIR]:
        """Extract C-IR from constraint artifact"""
        artifact = self.get_constraint_artifact(artifact_id)
        if not artifact:
            return None
        
        try:
            data = artifact.data
            if isinstance(data, dict):
                from core.ir.cir import ConstraintIR
                return ConstraintIR(**data)
            return None
        except Exception as e:
            print(f"Error converting artifact to C-IR: {e}")
            return None
    
    def run_drc(self, board_artifact_id: str, constraint_artifact_id: str) -> Optional[Artifact]:
        """
        Run DRC on board using constraints
        
        Args:
            board_artifact_id: Board artifact ID
            constraint_artifact_id: Constraint artifact ID
            
        Returns:
            Violations artifact or None if DRC fails
        """
        # Get artifacts
        board_artifact = self.get_board_artifact(board_artifact_id)
        constraint_artifact = self.get_constraint_artifact(constraint_artifact_id)
        
        if not board_artifact or not constraint_artifact:
            print("Error: Board or constraint artifact not found")
            return None
        
        # Export to temporary files for Altium DRC script
        from adapters.altium.exporter import AltiumExporter
        exporter = AltiumExporter()
        
        gir = self.get_gir_from_artifact(board_artifact_id)
        cir = self.get_cir_from_artifact(constraint_artifact_id)
        
        if not gir or not cir:
            print("Error: Could not extract G-IR or C-IR from artifacts")
            return None
        
        # Export to temporary files
        temp_dir = Path("temp_drc")
        temp_dir.mkdir(exist_ok=True)
        
        pcb_info_path = str(temp_dir / "pcb_info.json")
        design_rules_path = str(temp_dir / "design_rules.json")
        
        exporter.export_pcb_info(gir, pcb_info_path)
        exporter.export_design_rules(cir, design_rules_path)
        
        # Run Altium DRC script
        # Note: This assumes Altium script is available
        # For MVP, we'll create a mock DRC result
        violations = self._run_altium_drc(pcb_info_path, design_rules_path)
        
        # Create violations artifact
        violations_artifact = self.create_violations_artifact(
            violations=violations,
            board_artifact_id=board_artifact_id,
            constraint_artifact_id=constraint_artifact_id
        )
        
        # Store violations artifact
        stored = self.store.create(violations_artifact)
        
        return stored
    
    def create_violations_artifact(self, violations: List[Dict[str, Any]], 
                                   board_artifact_id: str, 
                                   constraint_artifact_id: str) -> Artifact:
        """
        Create violations artifact from parsed violations
        
        Args:
            violations: List of violation dicts
            board_artifact_id: Board artifact ID
            constraint_artifact_id: Constraint artifact ID
            
        Returns:
            Violations artifact
        """
        from datetime import datetime
        
        return Artifact(
            type=ArtifactType.CONSTRAINT_VIOLATIONS,
            data={
                "violations": violations,
                "board_artifact_id": board_artifact_id,
                "constraint_artifact_id": constraint_artifact_id,
                "drc_run_timestamp": datetime.utcnow().isoformat(),
                "violation_count": len(violations)
            },
            meta=ArtifactMeta(
                source_engine=SourceEngine.ALTIUM,
                created_by=CreatedBy.ENGINE
            ),
            relations=[
                {"role": "checks", "target_id": board_artifact_id},
                {"role": "uses", "target_id": constraint_artifact_id}
            ]
        )
    
    def _run_altium_drc(self, pcb_info_path: str, design_rules_path: str) -> List[Dict[str, Any]]:
        """
        Run geometric DRC based on actual PCB data and design rules.
        
        This is REAL DRC - no mock violations. Only reports actual issues found.
        
        Args:
            pcb_info_path: Path to pcb_info.json
            design_rules_path: Path to design_rules.json
            
        Returns:
            List of violation dicts (empty if no violations found)
        """
        import math
        
        violations = []
        
        # Load actual PCB data and rules
        try:
            with open(pcb_info_path, 'r') as f:
                pcb_data = json.load(f)
            with open(design_rules_path, 'r') as f:
                rules_data = json.load(f)
        except Exception as e:
            print(f"Error loading DRC input files: {e}")
            return []
        
        # Extract design rules
        min_clearance_mm = 0.2  # Default
        min_track_width_mm = 0.15  # Default
        min_via_drill_mm = 0.2  # Default
        
        for rule in rules_data.get('rules', []):
            if rule.get('type') == 'clearance':
                min_clearance_mm = rule.get('clearance_mm', min_clearance_mm)
            elif rule.get('type') == 'width':
                min_track_width_mm = rule.get('min_width_mm', min_track_width_mm)
            elif rule.get('type') == 'via':
                min_via_drill_mm = rule.get('min_hole_mm', min_via_drill_mm)
        
        # Get PCB elements
        tracks = pcb_data.get('tracks', [])
        vias = pcb_data.get('vias', [])
        pads = pcb_data.get('pads', [])
        nets = pcb_data.get('nets', [])
        components = pcb_data.get('components', [])
        
        violation_id = 0
        
        # CHECK 1: Track width violations
        for track in tracks:
            width = track.get('width_mm', 0)
            if width > 0 and width < min_track_width_mm:
                violation_id += 1
                violations.append({
                    "id": f"violation-{violation_id}",
                    "type": "track_width",
                    "severity": "error",
                    "message": f"Track width {width:.3f}mm is below minimum {min_track_width_mm}mm",
                    "location": {
                        "layer": track.get('layer', 'unknown')
                    },
                    "rule_id": "min-track-width",
                    "actual_mm": width,
                    "required_mm": min_track_width_mm
                })
        
        # CHECK 2: Via drill violations
        for via in vias:
            drill = via.get('hole_size_mm', 0)
            if drill > 0 and drill < min_via_drill_mm:
                violation_id += 1
                loc = via.get('location', {})
                violations.append({
                    "id": f"violation-{violation_id}",
                    "type": "via_drill",
                    "severity": "error",
                    "message": f"Via drill {drill:.3f}mm is below minimum {min_via_drill_mm}mm",
                    "location": {
                        "x_mm": loc.get('x_mm', 0),
                        "y_mm": loc.get('y_mm', 0)
                    },
                    "rule_id": "min-via-drill",
                    "actual_mm": drill,
                    "required_mm": min_via_drill_mm
                })
        
        # CHECK 3: Unrouted nets (nets with no tracks)
        track_nets = set()
        for track in tracks:
            net = track.get('net', '')
            if net:
                track_nets.add(net)
        
        for net in nets:
            net_name = net.get('name', '')
            if net_name and net_name not in track_nets and net_name != 'No Net':
                violation_id += 1
                severity = "warning"
                # Power/ground nets unrouted = error
                if 'GND' in net_name.upper() or 'VCC' in net_name.upper() or 'VDD' in net_name.upper():
                    severity = "error"
                violations.append({
                    "id": f"violation-{violation_id}",
                    "type": "unrouted_net",
                    "severity": severity,
                    "message": f"Net '{net_name}' has no routed tracks",
                    "net_name": net_name,
                    "rule_id": "connectivity"
                })
        
        # CHECK 4: Clearance check between pads (simplified geometric check)
        for i, pad1 in enumerate(pads):
            loc1 = pad1.get('location', {})
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            size1 = max(pad1.get('size_x_mm', 0), pad1.get('size_y_mm', 0)) / 2
            
            for pad2 in pads[i+1:]:
                # Skip if same net
                if pad1.get('net') == pad2.get('net') and pad1.get('net'):
                    continue
                    
                loc2 = pad2.get('location', {})
                x2 = loc2.get('x_mm', 0)
                y2 = loc2.get('y_mm', 0)
                size2 = max(pad2.get('size_x_mm', 0), pad2.get('size_y_mm', 0)) / 2
                
                if x1 == 0 and y1 == 0:
                    continue
                if x2 == 0 and y2 == 0:
                    continue
                
                # Calculate edge-to-edge distance
                distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                clearance = distance - size1 - size2
                
                if clearance > 0 and clearance < min_clearance_mm:
                    violation_id += 1
                    violations.append({
                        "id": f"violation-{violation_id}",
                        "type": "clearance",
                        "severity": "error",
                        "message": f"Clearance violation between pads: {clearance:.3f}mm < {min_clearance_mm}mm",
                        "location": {
                            "x_mm": (x1 + x2) / 2,
                            "y_mm": (y1 + y2) / 2
                        },
                        "objects": [pad1.get('name', 'pad1'), pad2.get('name', 'pad2')],
                        "rule_id": "min-clearance",
                        "actual_clearance_mm": round(clearance, 3),
                        "required_clearance_mm": min_clearance_mm
                    })
        
        return violations
    
    def parse_drc_output(self, drc_output_path: str) -> List[Dict[str, Any]]:
        """
        Parse Altium DRC output file
        
        Args:
            drc_output_path: Path to DRC output JSON file
            
        Returns:
            List of violation dicts
        """
        try:
            with open(drc_output_path, 'r', encoding='utf-8') as f:
                drc_data = json.load(f)
        except Exception as e:
            print(f"Error reading DRC output: {e}")
            return []
        
        violations = []
        
        # Parse DRC output format
        # Expected format from Altium script:
        # {
        #   "violations": [
        #     {
        #       "type": "clearance",
        #       "message": "...",
        #       "location": {"x_mm": ..., "y_mm": ..., "layer": "..."},
        #       "rule": "...",
        #       "actual": ...,
        #       "required": ...
        #     }
        #   ]
        # }
        
        drc_violations = drc_data.get("violations", [])
        
        for i, viol_data in enumerate(drc_violations):
            violation = {
                "id": f"violation-{i+1}",
                "type": viol_data.get("type", "unknown"),
                "severity": viol_data.get("severity", "error"),
                "message": viol_data.get("message", ""),
                "location": viol_data.get("location", {}),
                "rule_id": viol_data.get("rule", ""),
                "actual_clearance_mm": viol_data.get("actual"),
                "required_clearance_mm": viol_data.get("required")
            }
            violations.append(violation)
        
        return violations
    
    def get_violations(self, violations_artifact_id: str) -> List[Dict[str, Any]]:
        """
        Get violations from violations artifact
        
        Args:
            violations_artifact_id: Violations artifact ID
            
        Returns:
            List of violation dicts
        """
        artifact = self.store.read(violations_artifact_id)
        if not artifact or artifact.type != ArtifactType.CONSTRAINT_VIOLATIONS:
            return []
        
        return artifact.data.get("violations", [])
