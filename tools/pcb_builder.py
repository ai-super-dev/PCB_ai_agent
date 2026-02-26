"""
PCB Builder - Fully Automated Schematic to PCB Conversion
Generates complete PCB layout from schematic data without Altium API limitations
"""
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class Component:
    """Component with placement info"""
    designator: str
    footprint: str
    value: str
    lib_reference: str
    x: float = 0.0  # mm
    y: float = 0.0  # mm
    rotation: float = 0.0  # degrees
    layer: str = "Top"
    pins: List[Dict[str, Any]] = field(default_factory=list)
    width: float = 5.0  # mm (estimated)
    height: float = 5.0  # mm (estimated)


@dataclass
class Net:
    """Net with connections"""
    name: str
    pins: List[Tuple[str, str]]  # [(component, pin), ...]
    is_power: bool = False
    is_ground: bool = False
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    vias: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class PCBLayout:
    """Complete PCB layout data"""
    board_width: float = 100.0  # mm
    board_height: float = 80.0  # mm
    components: List[Component] = field(default_factory=list)
    nets: List[Net] = field(default_factory=list)
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    vias: List[Dict[str, Any]] = field(default_factory=list)
    pads: List[Dict[str, Any]] = field(default_factory=list)


class PCBBuilder:
    """Builds complete PCB layout from schematic data"""
    
    def __init__(self):
        self.layout = PCBLayout()
        self.component_map: Dict[str, Component] = {}
        self.net_map: Dict[str, Net] = {}
        
    def load_schematic(self, schematic_data: Dict[str, Any]) -> bool:
        """Load schematic data and prepare for PCB generation"""
        try:
            # Extract components
            for comp_data in schematic_data.get('components', []):
                comp = Component(
                    designator=comp_data.get('designator', ''),
                    footprint=comp_data.get('footprint', ''),
                    value=comp_data.get('value', ''),
                    lib_reference=comp_data.get('lib_reference', ''),
                    pins=comp_data.get('pins', [])
                )
                
                # Estimate component size from footprint name
                comp.width, comp.height = self._estimate_component_size(comp.footprint)
                
                self.layout.components.append(comp)
                self.component_map[comp.designator] = comp
            
            # Extract nets
            for net_data in schematic_data.get('nets', []):
                net_name = net_data.get('name', '')
                pins = []
                
                for pin_data in net_data.get('pins', []):
                    comp_desig = pin_data.get('component', '')
                    pin_num = pin_data.get('pin', '')
                    if comp_desig and pin_num:
                        pins.append((comp_desig, pin_num))
                
                net = Net(
                    name=net_name,
                    pins=pins,
                    is_power=self._is_power_net(net_name),
                    is_ground=self._is_ground_net(net_name)
                )
                
                self.layout.nets.append(net)
                self.net_map[net_name] = net
            
            print(f"[PCB Builder] Loaded {len(self.layout.components)} components, {len(self.layout.nets)} nets")
            return True
            
        except Exception as e:
            print(f"[PCB Builder] Error loading schematic: {e}")
            return False
    
    def _estimate_component_size(self, footprint: str) -> Tuple[float, float]:
        """Estimate component size from footprint name"""
        footprint_upper = footprint.upper()
        
        # Common footprint patterns
        if 'SOT23' in footprint_upper or 'SOT-23' in footprint_upper:
            return (3.0, 3.0)
        elif 'SOIC' in footprint_upper:
            if '8' in footprint_upper:
                return (5.0, 4.0)
            elif '14' in footprint_upper or '16' in footprint_upper:
                return (9.0, 4.0)
            return (7.0, 4.0)
        elif 'QFP' in footprint_upper or 'TQFP' in footprint_upper:
            if '32' in footprint_upper:
                return (7.0, 7.0)
            elif '44' in footprint_upper:
                return (10.0, 10.0)
            elif '64' in footprint_upper:
                return (12.0, 12.0)
            return (10.0, 10.0)
        elif '0805' in footprint_upper:
            return (2.0, 1.25)
        elif '0603' in footprint_upper:
            return (1.6, 0.8)
        elif '0402' in footprint_upper:
            return (1.0, 0.5)
        elif '1206' in footprint_upper:
            return (3.2, 1.6)
        elif 'DIP' in footprint_upper:
            if '8' in footprint_upper:
                return (10.0, 8.0)
            elif '14' in footprint_upper:
                return (18.0, 8.0)
            elif '16' in footprint_upper:
                return (20.0, 8.0)
            return (15.0, 8.0)
        elif 'TO-220' in footprint_upper or 'TO220' in footprint_upper:
            return (10.0, 9.0)
        
        # Default size
        return (5.0, 5.0)
    
    def _is_power_net(self, net_name: str) -> bool:
        """Check if net is a power net"""
        net_upper = net_name.upper()
        power_keywords = ['VCC', 'VDD', 'VIN', 'VOUT', '+', 'PWR', 'POWER', 'V+']
        return any(kw in net_upper for kw in power_keywords)
    
    def _is_ground_net(self, net_name: str) -> bool:
        """Check if net is a ground net"""
        net_upper = net_name.upper()
        ground_keywords = ['GND', 'GROUND', 'VSS', 'AGND', 'DGND', 'V-']
        return any(kw in net_upper for kw in ground_keywords)
    
    def auto_place_components(self) -> bool:
        """Automatically place components on the PCB"""
        try:
            print(f"[PCB Builder] Auto-placing {len(self.layout.components)} components...")
            
            # Calculate board size based on components
            total_area = sum(c.width * c.height for c in self.layout.components)
            estimated_area = total_area * 3.0  # 3x spacing factor
            
            # Use square board or adjust to fit
            side = math.sqrt(estimated_area)
            self.layout.board_width = max(100.0, min(200.0, side))
            self.layout.board_height = max(80.0, min(160.0, side))
            
            # Grid-based placement
            margin = 10.0  # mm from edge
            spacing = 5.0  # mm between components
            
            x = margin
            y = margin
            row_height = 0.0
            
            for comp in self.layout.components:
                # Check if component fits in current row
                if x + comp.width + margin > self.layout.board_width:
                    # Move to next row
                    x = margin
                    y += row_height + spacing
                    row_height = 0.0
                
                # Place component
                comp.x = x + comp.width / 2
                comp.y = y + comp.height / 2
                comp.layer = "Top"
                comp.rotation = 0.0
                
                # Update position for next component
                x += comp.width + spacing
                row_height = max(row_height, comp.height)
            
            print(f"[PCB Builder] Placement complete. Board size: {self.layout.board_width}x{self.layout.board_height}mm")
            return True
            
        except Exception as e:
            print(f"[PCB Builder] Error in auto-placement: {e}")
            return False
    
    def auto_route_nets(self) -> bool:
        """Automatically route all nets"""
        try:
            print(f"[PCB Builder] Auto-routing {len(self.layout.nets)} nets...")
            
            routed_count = 0
            
            for net in self.layout.nets:
                if len(net.pins) < 2:
                    continue
                
                # Get component positions for this net
                pin_positions = []
                for comp_desig, pin_num in net.pins:
                    comp = self.component_map.get(comp_desig)
                    if comp:
                        # Approximate pin position (center of component for now)
                        pin_positions.append((comp.x, comp.y, comp_desig, pin_num))
                
                if len(pin_positions) < 2:
                    continue
                
                # Simple star routing from first pin to all others
                first_pos = pin_positions[0]
                
                for i in range(1, len(pin_positions)):
                    target_pos = pin_positions[i]
                    
                    # Manhattan routing (L-shaped)
                    # Horizontal segment
                    track1 = {
                        'net': net.name,
                        'x1_mm': first_pos[0],
                        'y1_mm': first_pos[1],
                        'x2_mm': target_pos[0],
                        'y2_mm': first_pos[1],
                        'width_mm': 0.25 if not (net.is_power or net.is_ground) else 0.5,
                        'layer': 'Top'
                    }
                    
                    # Vertical segment
                    track2 = {
                        'net': net.name,
                        'x1_mm': target_pos[0],
                        'y1_mm': first_pos[1],
                        'x2_mm': target_pos[0],
                        'y2_mm': target_pos[1],
                        'width_mm': 0.25 if not (net.is_power or net.is_ground) else 0.5,
                        'layer': 'Top'
                    }
                    
                    net.tracks.append(track1)
                    net.tracks.append(track2)
                    self.layout.tracks.append(track1)
                    self.layout.tracks.append(track2)
                
                routed_count += 1
            
            print(f"[PCB Builder] Routed {routed_count} nets with {len(self.layout.tracks)} tracks")
            return True
            
        except Exception as e:
            print(f"[PCB Builder] Error in auto-routing: {e}")
            return False
    
    def generate_pads(self) -> bool:
        """Generate pad data for all components"""
        try:
            print(f"[PCB Builder] Generating pads for {len(self.layout.components)} components...")
            
            pad_count = 0
            
            for comp in self.layout.components:
                # Generate pads based on component pins
                for pin_data in comp.pins:
                    pin_name = pin_data.get('name', '')
                    pin_desig = pin_data.get('designator', '')
                    
                    # Simple pad generation (circular, 1.5mm diameter)
                    pad = {
                        'component': comp.designator,
                        'pin': pin_desig or pin_name,
                        'x_mm': comp.x,  # Offset from component center in real implementation
                        'y_mm': comp.y,
                        'diameter_mm': 1.5,
                        'hole_mm': 0.8 if 'DIP' in comp.footprint.upper() else 0.0,
                        'layer': comp.layer,
                        'shape': 'round'
                    }
                    
                    # Find net for this pad
                    for net in self.layout.nets:
                        for net_comp, net_pin in net.pins:
                            if net_comp == comp.designator and net_pin == (pin_desig or pin_name):
                                pad['net'] = net.name
                                break
                    
                    self.layout.pads.append(pad)
                    pad_count += 1
            
            print(f"[PCB Builder] Generated {pad_count} pads")
            return True
            
        except Exception as e:
            print(f"[PCB Builder] Error generating pads: {e}")
            return False
    
    def build(self) -> PCBLayout:
        """Build complete PCB layout"""
        print("[PCB Builder] Starting PCB build process...")
        
        # Step 1: Auto-place components
        if not self.auto_place_components():
            print("[PCB Builder] Auto-placement failed")
            return None
        
        # Step 2: Generate pads
        if not self.generate_pads():
            print("[PCB Builder] Pad generation failed")
            return None
        
        # Step 3: Auto-route nets
        if not self.auto_route_nets():
            print("[PCB Builder] Auto-routing failed")
            return None
        
        print("[PCB Builder] PCB build complete!")
        return self.layout
    
    def export_to_json(self, output_path: str) -> bool:
        """Export PCB layout to JSON format"""
        try:
            data = {
                'board_size': {
                    'width_mm': self.layout.board_width,
                    'height_mm': self.layout.board_height
                },
                'components': [
                    {
                        'designator': c.designator,
                        'footprint': c.footprint,
                        'value': c.value,
                        'x_mm': c.x,
                        'y_mm': c.y,
                        'rotation': c.rotation,
                        'layer': c.layer
                    }
                    for c in self.layout.components
                ],
                'nets': [
                    {
                        'name': n.name,
                        'pins': [{'component': c, 'pin': p} for c, p in n.pins],
                        'is_power': n.is_power,
                        'is_ground': n.is_ground
                    }
                    for n in self.layout.nets
                ],
                'tracks': self.layout.tracks,
                'vias': self.layout.vias,
                'pads': self.layout.pads,
                'statistics': {
                    'component_count': len(self.layout.components),
                    'net_count': len(self.layout.nets),
                    'track_count': len(self.layout.tracks),
                    'via_count': len(self.layout.vias),
                    'pad_count': len(self.layout.pads)
                }
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            print(f"[PCB Builder] Exported PCB layout to {output_path}")
            return True
            
        except Exception as e:
            print(f"[PCB Builder] Error exporting to JSON: {e}")
            return False


def build_pcb_from_schematic(schematic_json_path: str, output_json_path: str) -> Optional[PCBLayout]:
    """
    Main entry point: Build PCB from schematic JSON
    
    Args:
        schematic_json_path: Path to schematic_info.json
        output_json_path: Path to save generated PCB layout JSON
        
    Returns:
        PCBLayout object or None if failed
    """
    try:
        # Load schematic data
        with open(schematic_json_path, 'r', encoding='utf-8') as f:
            schematic_data = json.load(f)
        
        # Create builder and build PCB
        builder = PCBBuilder()
        
        if not builder.load_schematic(schematic_data):
            return None
        
        layout = builder.build()
        
        if layout:
            builder.export_to_json(output_json_path)
        
        return layout
        
    except Exception as e:
        print(f"[PCB Builder] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == '__main__':
    # Test with example schematic
    import sys
    
    if len(sys.argv) > 1:
        schematic_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else 'pcb_layout.json'
        
        layout = build_pcb_from_schematic(schematic_path, output_path)
        
        if layout:
            print(f"\n✅ PCB built successfully!")
            print(f"   Board: {layout.board_width}x{layout.board_height}mm")
            print(f"   Components: {len(layout.components)}")
            print(f"   Nets: {len(layout.nets)}")
            print(f"   Tracks: {len(layout.tracks)}")
        else:
            print("\n❌ PCB build failed")
            sys.exit(1)
    else:
        print("Usage: python pcb_builder.py <schematic_info.json> [output.json]")
