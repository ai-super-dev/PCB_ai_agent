"""
Altium Exporter
Maps canonical G-IR and C-IR artifacts to Altium JSON format
Per Architecture Spec §8.1
"""
from typing import Dict, Any, Optional
from pathlib import Path

from core.ir.gir import GeometryIR
from core.ir.cir import ConstraintIR, RuleType
from core.artifacts.models import Artifact


class AltiumExporter:
    """Exports canonical IR artifacts to Altium JSON format"""
    
    def __init__(self):
        """Initialize exporter"""
        pass
    
    def export_pcb_info(self, gir: GeometryIR, output_path: str) -> bool:
        """
        Export G-IR to Altium pcb_info.json format
        
        Args:
            gir: Geometry IR
            output_path: Output file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract board dimensions from outline
            outline = gir.board.outline.polygon
            if outline:
                # Calculate bounding box
                x_coords = [p[0] for p in outline]
                y_coords = [p[1] for p in outline]
                width_mm = max(x_coords) - min(x_coords)
                height_mm = max(y_coords) - min(y_coords)
            else:
                width_mm = 100.0
                height_mm = 80.0
            
            # Build Altium-compatible format
            pcb_info = {
                "file_name": "exported_board",
                "board_size": {
                    "width_mm": width_mm,
                    "height_mm": height_mm
                },
                "board_thickness_mm": gir.board.stackup.thickness_mm,
                "layers": [layer.name for layer in gir.board.layers],
                "statistics": {
                    "component_count": len(gir.footprints),
                    "net_count": len(gir.nets),
                    "layer_count": len(gir.board.layers),
                    "via_count": len(gir.vias),
                    "track_count": len(gir.tracks)
                },
                "components": [],
                "nets": [],
                "tracks": [],
                "vias": []
            }
            
            # Export components (footprints)
            for fp in gir.footprints:
                pcb_info["components"].append({
                    "name": fp.ref,
                    "designator": fp.ref,
                    "location": {
                        "x_mm": fp.position[0],
                        "y_mm": fp.position[1]
                    },
                    "rotation_degrees": fp.rotation_deg,
                    "layer": next((l.name for l in gir.board.layers if l.id == fp.layer), "Top"),
                    "footprint": fp.footprint_name or ""
                })
            
            # Export nets
            for net in gir.nets:
                pcb_info["nets"].append({
                    "name": net.name
                })
            
            # Export tracks
            for track in gir.tracks:
                layer_name = next((l.name for l in gir.board.layers if l.id == track.layer_id), "Top")
                if track.segments:
                    seg = track.segments[0]  # Use first segment for MVP
                    pcb_info["tracks"].append({
                        "id": track.id,
                        "net": next((n.name for n in gir.nets if n.id == track.net_id), ""),
                        "layer": layer_name,
                        "width_mm": seg.width_mm,
                        "start": {
                            "x_mm": seg.from_pos[0],
                            "y_mm": seg.from_pos[1]
                        },
                        "end": {
                            "x_mm": seg.to_pos[0],
                            "y_mm": seg.to_pos[1]
                        }
                    })
            
            # Export vias
            for via in gir.vias:
                pcb_info["vias"].append({
                    "id": via.id,
                    "net": next((n.name for n in gir.nets if n.id == via.net_id), ""),
                    "x_mm": via.position[0],
                    "y_mm": via.position[1],
                    "drill_mm": via.drill_mm
                })
            
            # Write to file
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                import json
                json.dump(pcb_info, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error exporting pcb_info: {e}")
            return False
    
    def export_design_rules(self, cir: ConstraintIR, output_path: str) -> bool:
        """
        Export C-IR to Altium design_rules.json format
        
        Args:
            cir: Constraint IR
            output_path: Output file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            design_rules = {
                "statistics": {
                    "total_rules": len(cir.rules),
                    "clearance_rules": len([r for r in cir.rules if r.type == RuleType.CLEARANCE]),
                    "width_rules": len([r for r in cir.rules if r.type == RuleType.TRACE_WIDTH]),
                    "via_rules": len([r for r in cir.rules if r.type == RuleType.VIA])
                },
                "clearance_rules": [],
                "width_rules": [],
                "via_rules": [],
                "netclasses": []
            }
            
            # Export rules
            for rule in cir.rules:
                rule_data = {
                    "id": rule.id,
                    "enabled": rule.enabled,
                    "priority": rule.priority
                }
                
                if rule.type == RuleType.CLEARANCE:
                    rule_data["minimum_mm"] = rule.params.min_clearance_mm or 0.2
                    if rule.scope.netclass:
                        rule_data["net_class"] = rule.scope.netclass
                    elif rule.scope.nets:
                        rule_data["nets"] = [n.replace("net-", "") for n in rule.scope.nets]
                    design_rules["clearance_rules"].append(rule_data)
                
                elif rule.type == RuleType.TRACE_WIDTH:
                    rule_data["min_width_mm"] = rule.params.min_width_mm or 0.25
                    rule_data["preferred_width_mm"] = rule.params.preferred_width_mm or 0.3
                    if rule.scope.netclass:
                        rule_data["net_class"] = rule.scope.netclass
                    elif rule.scope.nets:
                        rule_data["nets"] = [n.replace("net-", "") for n in rule.scope.nets]
                    design_rules["width_rules"].append(rule_data)
                
                elif rule.type == RuleType.VIA:
                    if rule.params.min_drill_mm:
                        rule_data["min_drill_mm"] = rule.params.min_drill_mm
                    if rule.params.max_drill_mm:
                        rule_data["max_drill_mm"] = rule.params.max_drill_mm
                    design_rules["via_rules"].append(rule_data)
            
            # Export netclasses
            for nc in cir.netclasses:
                design_rules["netclasses"].append({
                    "name": nc.name,
                    "nets": [n.replace("net-", "") for n in nc.nets],
                    "default_width_mm": nc.defaults.trace_width_mm or 0.3,
                    "default_clearance_mm": nc.defaults.clearance_mm or 0.2
                })
            
            # Write to file
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                import json
                json.dump(design_rules, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error exporting design_rules: {e}")
            return False
