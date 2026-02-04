"""
Altium Importer
Maps Altium JSON exports to canonical G-IR and C-IR artifacts
Per Architecture Spec §8.1

Now supports DIRECT file reading (no Altium scripting needed!)
Uses tools/altium_file_reader.py to read .PcbDoc files directly.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from core.ir.gir import (
    GeometryIR, Board, BoardOutline, Layer, LayerKind, Stackup, Net, Track, TrackSegment,
    Via, Footprint, Pad
)
from core.ir.cir import ConstraintIR, Rule, RuleType, RuleScope, RuleParams, Netclass, NetclassDefaults
from core.artifacts.models import Artifact, ArtifactType, ArtifactMeta, SourceEngine, CreatedBy

# Try to import the direct file reader
try:
    from tools.altium_file_reader import AltiumFileReader
    DIRECT_READER_AVAILABLE = True
except ImportError:
    DIRECT_READER_AVAILABLE = False


class AltiumImporter:
    """Imports Altium data to canonical IR artifacts"""
    
    def __init__(self):
        """Initialize importer"""
        self.file_reader = AltiumFileReader() if DIRECT_READER_AVAILABLE else None
    
    def import_pcb_direct(self, pcb_file_path: str) -> Optional[GeometryIR]:
        """
        Import PCB directly from .PcbDoc file (NO Altium scripting needed!)
        
        This reads the Altium file directly using Python, avoiding memory issues.
        
        Args:
            pcb_file_path: Path to .PcbDoc file
            
        Returns:
            GeometryIR object or None if import fails
        """
        if not self.file_reader:
            print("ERROR: Direct file reader not available. Install olefile: pip install olefile")
            return None
        
        try:
            # Read PCB file directly
            pcb_data = self.file_reader.read_pcb(pcb_file_path)
            
            if 'error' in pcb_data:
                print(f"Error reading PCB file: {pcb_data['error']}")
                return None
            
            # Convert to same format as JSON import
            return self._convert_direct_data_to_gir(pcb_data)
        except Exception as e:
            print(f"Error importing PCB directly: {e}")
            return None
    
    def _convert_direct_data_to_gir(self, pcb_data: Dict[str, Any]) -> GeometryIR:
        """Convert direct file reader data to G-IR"""
        # Extract board information
        board_size = pcb_data.get('board_size', {})
        width_mm = board_size.get('width_mm', 100.0)
        height_mm = board_size.get('height_mm', 80.0)
        
        # Create board outline
        outline = BoardOutline(
            polygon=[[0, 0], [width_mm, 0], [width_mm, height_mm], [0, height_mm]]
        )
        
        # Create default layers
        layers = [
            Layer(id="L1", name="Top", kind=LayerKind.SIGNAL, index=1),
            Layer(id="L2", name="GND", kind=LayerKind.GROUND, index=2),
            Layer(id="L3", name="VCC", kind=LayerKind.POWER, index=3),
            Layer(id="L4", name="Bottom", kind=LayerKind.SIGNAL, index=4),
        ]
        
        # Create stackup
        stackup = Stackup(
            layers=[layer.id for layer in layers],
            thickness_mm=1.6,
            dielectrics=[]
        )
        
        board = Board(outline=outline, layers=layers, stackup=stackup)
        
        # Extract components
        footprints = []
        for comp in pcb_data.get('components', []):
            if isinstance(comp, dict):
                footprints.append(Footprint(
                    id=f"fp-{comp.get('designitemid', 'unknown')}",
                    ref=comp.get('designitemid', 'U?'),
                    position=[comp.get('x_mm', 0), comp.get('y_mm', 0)],
                    rotation_deg=0,
                    layer="L1",
                    pads=[],
                    footprint_name=comp.get('pattern', '')
                ))
        
        # Extract nets
        nets = []
        for net in pcb_data.get('nets', []):
            if isinstance(net, dict):
                net_name = net.get('name', 'Unknown')
                nets.append(Net(id=f"net-{net_name.lower()}", name=net_name))
        
        # Statistics for empty arrays
        stats = pcb_data.get('statistics', {})
        
        return GeometryIR(
            board=board,
            nets=nets,
            tracks=[],  # Detailed tracks not extracted yet
            vias=[],    # Detailed vias not extracted yet
            footprints=footprints
        )
    
    def import_pcb_info(self, pcb_info_path: str) -> Optional[GeometryIR]:
        """
        Import PCB info from Altium JSON to G-IR
        
        Args:
            pcb_info_path: Path to pcb_info.json file
            
        Returns:
            GeometryIR object or None if import fails
        """
        try:
            with open(pcb_info_path, 'r', encoding='utf-8') as f:
                pcb_data = json.load(f)
        except Exception as e:
            print(f"Error reading pcb_info.json: {e}")
            return None
        
        # Extract board information
        board_size = pcb_data.get('board_size', {})
        width_mm = board_size.get('width_mm', 100.0)
        height_mm = board_size.get('height_mm', 80.0)
        
        # Create board outline (simple rectangle for MVP)
        outline = BoardOutline(
            polygon=[[0, 0], [width_mm, 0], [width_mm, height_mm], [0, height_mm]]
        )
        
        # Extract layers (handle both old format and new comprehensive format)
        layers_data = pcb_data.get('layers', [])
        layers = []
        for i, layer_item in enumerate(layers_data):
            if isinstance(layer_item, dict):
                # New comprehensive format
                layer_id = layer_item.get('id', f"L{i+1}")
                layer_name = layer_item.get('name', f'Layer {i+1}')
                kind_str = layer_item.get('kind', 'signal')
                # Map string to enum
                kind_map = {
                    'signal': LayerKind.SIGNAL,
                    'ground': LayerKind.GROUND,
                    'power': LayerKind.POWER,
                    'plane': LayerKind.PLANE
                }
                kind = kind_map.get(kind_str, LayerKind.SIGNAL)
                index = layer_item.get('index', i+1)
            else:
                # Old format (just name string)
                layer_name = str(layer_item)
                layer_id = f"L{i+1}"
                layer_name_lower = layer_name.lower()
                if 'gnd' in layer_name_lower or 'ground' in layer_name_lower:
                    kind = LayerKind.GROUND
                elif 'power' in layer_name_lower or 'vcc' in layer_name_lower:
                    kind = LayerKind.POWER
                else:
                    kind = LayerKind.SIGNAL
                index = i+1
            
            layers.append(Layer(
                id=layer_id,
                name=layer_name,
                kind=kind,
                index=index
            ))
        
        # Create stackup
        stackup = Stackup(
            layers=[layer.id for layer in layers],
            thickness_mm=pcb_data.get('board_thickness_mm', 1.6),
            dielectrics=[]
        )
        
        board = Board(
            outline=outline,
            layers=layers,
            stackup=stackup
        )
        
        # Extract nets
        nets_data = pcb_data.get('nets', [])
        nets = []
        for net_data in nets_data:
            if isinstance(net_data, dict):
                net_name = net_data.get('name', '')
                net_id = f"net-{net_name.lower().replace(' ', '-')}"
            else:
                net_name = str(net_data)
                net_id = f"net-{net_name.lower().replace(' ', '-')}"
            
            nets.append(Net(id=net_id, name=net_name))
        
        # Extract tracks
        tracks_data = pcb_data.get('tracks', [])
        tracks = []
        for i, track_data in enumerate(tracks_data):
            track_id = track_data.get('id', f"trk-{i+1}")
            net_name = track_data.get('net', '')
            net_id = f"net-{net_name.lower().replace(' ', '-')}" if net_name else None
            
            # Create net if it doesn't exist
            if net_name and net_id not in [n.id for n in nets]:
                nets.append(Net(id=net_id, name=net_name))
            
            layer_name = track_data.get('layer', layers[0].name if layers else 'Top')
            layer_id = next((l.id for l in layers if l.name == layer_name), layers[0].id if layers else 'L1')
            
            # Extract segments
            segments = []
            width_mm = track_data.get('width_mm', 0.25)
            
            # Handle new Altium export format (x1_mm, y1_mm, x2_mm, y2_mm)
            if 'x1_mm' in track_data and 'y1_mm' in track_data:
                segments.append(TrackSegment(
                    from_pos=[track_data.get('x1_mm', 0), track_data.get('y1_mm', 0)],
                    to_pos=[track_data.get('x2_mm', 0), track_data.get('y2_mm', 0)],
                    width_mm=width_mm
                ))
            # Handle old format (start/end)
            elif 'start' in track_data and 'end' in track_data:
                segments.append(TrackSegment(
                    from_pos=[track_data['start'].get('x_mm', 0), track_data['start'].get('y_mm', 0)],
                    to_pos=[track_data['end'].get('x_mm', 0), track_data['end'].get('y_mm', 0)],
                    width_mm=width_mm
                ))
            # Handle segments array
            elif 'segments' in track_data:
                for seg in track_data['segments']:
                    segments.append(TrackSegment(
                        from_pos=[seg.get('from', {}).get('x', 0), seg.get('from', {}).get('y', 0)],
                        to_pos=[seg.get('to', {}).get('x', 0), seg.get('to', {}).get('y', 0)],
                        width_mm=width_mm
                    ))
            
            if segments:
                tracks.append(Track(
                    id=track_id,
                    net_id=net_id or '',
                    layer_id=layer_id,
                    segments=segments
                ))
        
        # Extract vias
        vias_data = pcb_data.get('vias', [])
        vias = []
        for i, via_data in enumerate(vias_data):
            via_id = via_data.get('id', f"via-{i+1}")
            net_name = via_data.get('net', '')
            net_id = f"net-{net_name.lower().replace(' ', '-')}" if net_name else None
            
            # Create net if it doesn't exist
            if net_name and net_id and net_id not in [n.id for n in nets]:
                nets.append(Net(id=net_id, name=net_name))
            
            position = [
                via_data.get('x_mm', via_data.get('position', {}).get('x', 0)),
                via_data.get('y_mm', via_data.get('position', {}).get('y', 0))
            ]
            drill_mm = via_data.get('hole_size_mm', via_data.get('drill_mm', via_data.get('drill_size_mm', 0.3)))
            
            # Determine layers from new format (low_layer, high_layer)
            via_layers = []
            if 'low_layer' in via_data and 'high_layer' in via_data:
                low_layer_name = via_data.get('low_layer', '')
                high_layer_name = via_data.get('high_layer', '')
                # Find layer IDs
                for layer in layers:
                    if layer.name == low_layer_name or layer.name == high_layer_name:
                        if layer.id not in via_layers:
                            via_layers.append(layer.id)
            else:
                # Fallback: all signal layers
                via_layers = [l.id for l in layers if l.kind == LayerKind.SIGNAL]
            
            if not via_layers:
                via_layers = [layers[0].id] if layers else []
            
            vias.append(Via(
                id=via_id,
                net_id=net_id or '',
                position=position,
                drill_mm=drill_mm,
                layers=via_layers
            ))
        
        # Extract footprints (components) with pads
        components_data = pcb_data.get('components', [])
        footprints = []
        for comp_data in components_data:
            if isinstance(comp_data, dict):
                comp_name = comp_data.get('designator', comp_data.get('name', ''))
                comp_id = f"fp-{comp_name.lower()}"
                
                # Position (handle both formats)
                if 'x_mm' in comp_data:
                    position = [comp_data.get('x_mm', 0), comp_data.get('y_mm', 0)]
                else:
                    location = comp_data.get('location', {})
                    position = [
                        location.get('x_mm', location.get('x', 0)),
                        location.get('y_mm', location.get('y', 0))
                    ]
                
                rotation = comp_data.get('rotation', comp_data.get('rotation_degrees', 0))
                layer_name = comp_data.get('layer', layers[0].name if layers else 'Top')
                layer_id = next((l.id for l in layers if l.name == layer_name), layers[0].id if layers else 'L1')
                
                # Extract pads from comprehensive export
                pads = []
                pads_data = comp_data.get('pads', [])
                for pad_data in pads_data:
                    if isinstance(pad_data, dict):
                        pad_net_name = pad_data.get('net', '')
                        pad_net_id = f"net-{pad_net_name.lower().replace(' ', '-')}" if pad_net_name else None
                        
                        # Create net if it doesn't exist
                        if pad_net_name and pad_net_id and pad_net_id not in [n.id for n in nets]:
                            nets.append(Net(id=pad_net_id, name=pad_net_name))
                        
                        # Pad position relative to component
                        pad_x = pad_data.get('x_mm', 0) - position[0]
                        pad_y = pad_data.get('y_mm', 0) - position[1]
                        
                        pads.append(Pad(
                            id=f"pad-{pad_data.get('name', 'unknown')}",
                            net_id=pad_net_id,
                            shape="round",  # Default, could be extracted from pad data
                            size_mm=[pad_data.get('size_x_mm', 1.0), pad_data.get('size_y_mm', 1.0)],
                            position=[pad_x, pad_y],
                            layer=pad_data.get('layer', layer_id)
                        ))
                
                footprints.append(Footprint(
                    id=comp_id,
                    ref=comp_name,
                    position=position,
                    rotation_deg=rotation,
                    layer=layer_id,
                    pads=pads,
                    footprint_name=comp_data.get('footprint', comp_data.get('pattern', ''))
                ))
        
        return GeometryIR(
            board=board,
            nets=nets,
            tracks=tracks,
            vias=vias,
            footprints=footprints
        )
    
    def import_design_rules_from_file_reader(self, rules_data: List[Dict[str, Any]]) -> Optional[ConstraintIR]:
        """
        Import design rules directly from file reader data (from Rules6/Data stream).
        
        Args:
            rules_data: List of rule dicts from file reader (pcb_data['rules'])
            
        Returns:
            ConstraintIR object or None if import fails
        """
        if not rules_data:
            return None
        
        rules = []
        netclasses = []
        
        for rule_data in rules_data:
            if not isinstance(rule_data, dict):
                continue
            
            # Skip disabled rules
            if not rule_data.get('enabled', True):
                continue
            
            rule_type_str = rule_data.get('type', '').lower()
            rule_kind = rule_data.get('kind', '')
            rule_name = rule_data.get('name', '')
            
            if not rule_name:
                continue
            
            rule_id = f"rule-{rule_name.lower().replace(' ', '-')}"
            scope = RuleScope()
            
            # Parse scope if available
            scope_expr = rule_data.get('scope', '')
            if scope_expr:
                # Try to extract net class or net names from scope expression
                if 'NetClass' in scope_expr:
                    # Extract net class name
                    import re
                    match = re.search(r'NetClass\(([^)]+)\)', scope_expr)
                    if match:
                        scope.netclass = match.group(1)
            
            # Convert based on rule type
            if rule_type_str == 'clearance' or 'CLEARANCE' in rule_kind.upper():
                clearance_mm = rule_data.get('clearance_mm', 0.2)
                if clearance_mm <= 0:
                    continue  # Skip invalid rules
                
                rules.append(Rule(
                    id=rule_id,
                    type=RuleType.CLEARANCE,
                    scope=scope,
                    params=RuleParams(min_clearance_mm=clearance_mm),
                    enabled=True
                ))
            
            elif rule_type_str == 'width' or 'WIDTH' in rule_kind.upper():
                min_width = rule_data.get('min_width_mm', 0.15)
                preferred_width = rule_data.get('preferred_width_mm', rule_data.get('min_width_mm', 0.25))
                max_width = rule_data.get('max_width_mm', 0)
                
                if min_width <= 0:
                    continue  # Skip invalid rules
                
                params = RuleParams(min_width_mm=min_width, preferred_width_mm=preferred_width)
                if max_width > 0:
                    params.max_width_mm = max_width
                
                rules.append(Rule(
                    id=rule_id,
                    type=RuleType.TRACE_WIDTH,
                    scope=scope,
                    params=params,
                    enabled=True
                ))
            
            elif rule_type_str == 'via' or 'VIA' in rule_kind.upper():
                min_hole = rule_data.get('min_hole_mm', 0.2)
                max_hole = rule_data.get('max_hole_mm', 0)
                
                if min_hole <= 0:
                    continue  # Skip invalid rules
                
                params = RuleParams(min_via_drill_mm=min_hole)
                if max_hole > 0:
                    params.max_via_drill_mm = max_hole
                
                rules.append(Rule(
                    id=rule_id,
                    type=RuleType.VIA,
                    scope=scope,
                    params=params,
                    enabled=True
                ))
        
        # If no rules found, return None
        if not rules:
            return None
        
        return ConstraintIR(rules=rules, netclasses=netclasses)
    
    def import_design_rules(self, design_rules_path: str) -> Optional[ConstraintIR]:
        """
        Import design rules from Altium JSON to C-IR
        
        Args:
            design_rules_path: Path to design_rules.json file
            
        Returns:
            ConstraintIR object or None if import fails
        """
        try:
            with open(design_rules_path, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
        except Exception as e:
            print(f"Error reading design_rules.json: {e}")
            return None
        
        rules = []
        netclasses = []
        
        # Import clearance rules
        clearance_rules = rules_data.get('clearance_rules', [])
        for rule_data in clearance_rules:
            if not rule_data.get('enabled', True):
                continue
            
            rule_id = rule_data.get('id', f"rule-clearance-{len(rules)}")
            min_clearance = rule_data.get('minimum_mm', rule_data.get('min_clearance_mm', 0.2))
            
            # Determine scope
            scope = RuleScope()
            if 'net_class' in rule_data:
                scope.netclass = rule_data['net_class']
            elif 'nets' in rule_data:
                scope.nets = [f"net-{n.lower().replace(' ', '-')}" for n in rule_data['nets']]
            
            rules.append(Rule(
                id=rule_id,
                type=RuleType.CLEARANCE,
                scope=scope,
                params=RuleParams(min_clearance_mm=min_clearance),
                enabled=True
            ))
        
        # Import width rules
        width_rules = rules_data.get('width_rules', [])
        for rule_data in width_rules:
            if not rule_data.get('enabled', True):
                continue
            
            rule_id = rule_data.get('id', f"rule-width-{len(rules)}")
            min_width = rule_data.get('min_width_mm', 0.25)
            preferred_width = rule_data.get('preferred_width_mm', rule_data.get('default_width_mm', 0.3))
            
            scope = RuleScope()
            if 'net_class' in rule_data:
                scope.netclass = rule_data['net_class']
            elif 'nets' in rule_data:
                scope.nets = [f"net-{n.lower().replace(' ', '-')}" for n in rule_data['nets']]
            
            rules.append(Rule(
                id=rule_id,
                type=RuleType.TRACE_WIDTH,
                scope=scope,
                params=RuleParams(
                    min_width_mm=min_width,
                    preferred_width_mm=preferred_width
                ),
                enabled=True
            ))
        
        # Import netclasses
        netclasses_data = rules_data.get('netclasses', [])
        for nc_data in netclasses_data:
            nc_id = f"nc-{nc_data.get('name', '').lower().replace(' ', '-')}"
            nc_name = nc_data.get('name', '')
            nc_nets = [f"net-{n.lower().replace(' ', '-')}" for n in nc_data.get('nets', [])]
            
            defaults = NetclassDefaults(
                trace_width_mm=nc_data.get('default_width_mm', 0.3),
                clearance_mm=nc_data.get('default_clearance_mm', 0.2)
            )
            
            netclasses.append(Netclass(
                id=nc_id,
                name=nc_name,
                nets=nc_nets,
                defaults=defaults
            ))
        
        return ConstraintIR(rules=rules, netclasses=netclasses)
    
    def create_pcb_board_artifact(self, gir: GeometryIR, pcb_info_path: str) -> Artifact:
        """
        Create pcb.board artifact from G-IR
        
        Args:
            gir: Geometry IR
            pcb_info_path: Source file path (for metadata)
            
        Returns:
            Artifact object
        """
        return Artifact(
            type=ArtifactType.PCB_BOARD,
            data=gir.model_dump(),
            meta=ArtifactMeta(
                source_engine=SourceEngine.ALTIUM,
                created_by=CreatedBy.ENGINE
            )
        )
    
    def create_constraint_ruleset_artifact(self, cir: ConstraintIR, design_rules_path: str) -> Artifact:
        """
        Create constraint.ruleSet artifact from C-IR
        
        Args:
            cir: Constraint IR
            design_rules_path: Source file path (for metadata)
            
        Returns:
            Artifact object
        """
        return Artifact(
            type=ArtifactType.CONSTRAINT_RULESET,
            data=cir.model_dump(),
            meta=ArtifactMeta(
                source_engine=SourceEngine.ALTIUM,
                created_by=CreatedBy.ENGINE
            )
        )
