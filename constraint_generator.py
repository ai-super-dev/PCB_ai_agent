"""
Constraint Generator - Intelligent Design Rule Inference

This module generates design constraints/rules from schematic analysis:
- Net class definitions
- Clearance rules
- Track width rules
- Via rules
- Differential pair rules
- High-speed signal constraints

Generates rules that can be exported to Altium.
"""
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class RuleType(Enum):
    """Design rule types"""
    CLEARANCE = "clearance"
    WIDTH = "width"
    VIA = "via"
    DIFFERENTIAL_PAIR = "differential_pair"
    LENGTH_MATCH = "length_match"
    NET_CLASS = "net_class"
    COMPONENT_CLEARANCE = "component_clearance"
    PLANE_CLEARANCE = "plane_clearance"
    SOLDER_MASK = "solder_mask"


class NetClassType(Enum):
    """Net class types for automatic classification"""
    POWER = "Power"
    GROUND = "Ground"
    HIGH_SPEED = "HighSpeed"
    DIFFERENTIAL = "Differential"
    ANALOG = "Analog"
    CLOCK = "Clock"
    RESET = "Reset"
    DEFAULT = "Default"


@dataclass
class DesignRule:
    """Represents a design rule"""
    name: str
    rule_type: RuleType
    enabled: bool = True
    priority: int = 1
    scope: str = "All"  # All, InNetClass, InNet, etc.
    properties: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.properties is None:
            self.properties = {}
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.rule_type.value,
            "enabled": self.enabled,
            "priority": self.priority,
            "scope": self.scope,
            "properties": self.properties
        }


@dataclass
class NetClass:
    """Represents a net class definition"""
    name: str
    nets: List[str]
    properties: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.properties is None:
            self.properties = {}
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "nets": self.nets,
            "properties": self.properties
        }


class ConstraintGenerator:
    """
    Generates design constraints from schematic/PCB analysis.
    
    Capabilities:
    - Infer net classes from net names
    - Generate clearance rules
    - Generate track width rules
    - Generate differential pair rules
    - Generate high-speed constraints
    """
    
    def __init__(self):
        self.net_classes: List[NetClass] = []
        self.rules: List[DesignRule] = []
        
        # Default rule values (in mm)
        self.defaults = {
            "clearance": 0.2,
            "track_width": 0.25,
            "power_track_width": 0.5,
            "ground_track_width": 0.5,
            "highspeed_clearance": 0.3,
            "via_hole": 0.3,
            "via_diameter": 0.6,
            "diff_pair_gap": 0.15,
            "diff_pair_width": 0.2,
        }
    
    def analyze_nets(self, nets: List[Dict]) -> Dict[str, List[str]]:
        """
        Analyze nets and classify them by type.
        Returns dict of net class type -> list of net names.
        """
        classified = {nc.value: [] for nc in NetClassType}
        
        for net in nets:
            net_name = net.get("name", "") or net.get("net_name", "")
            if not net_name:
                continue
            
            net_upper = net_name.upper()
            
            # Classify by name patterns
            if any(p in net_upper for p in ["VCC", "VDD", "3V3", "5V", "12V", "VBAT", "+V", "VIN", "VOUT"]):
                classified[NetClassType.POWER.value].append(net_name)
            elif any(p in net_upper for p in ["GND", "VSS", "GROUND", "AGND", "DGND", "PGND"]):
                classified[NetClassType.GROUND.value].append(net_name)
            elif any(p in net_upper for p in ["CLK", "CLOCK", "XTAL"]):
                classified[NetClassType.CLOCK.value].append(net_name)
            elif any(p in net_upper for p in ["USB", "ETH", "HDMI", "PCIE", "LVDS", "MIPI"]):
                classified[NetClassType.HIGH_SPEED.value].append(net_name)
            elif net_name.endswith("_P") or net_name.endswith("_N") or net_name.endswith("+") or net_name.endswith("-"):
                classified[NetClassType.DIFFERENTIAL.value].append(net_name)
            elif any(p in net_upper for p in ["RST", "RESET", "NRST"]):
                classified[NetClassType.RESET.value].append(net_name)
            elif any(p in net_upper for p in ["AIN", "AOUT", "VREF", "SENSE", "ANALOG"]):
                classified[NetClassType.ANALOG.value].append(net_name)
            else:
                classified[NetClassType.DEFAULT.value].append(net_name)
        
        return classified
    
    def generate_net_classes(self, classified_nets: Dict[str, List[str]]) -> List[NetClass]:
        """Generate net class definitions from classified nets"""
        self.net_classes = []
        
        for class_name, nets in classified_nets.items():
            if nets:  # Only create class if there are nets
                self.net_classes.append(NetClass(
                    name=class_name,
                    nets=nets,
                    properties=self._get_class_properties(class_name)
                ))
        
        return self.net_classes
    
    def _get_class_properties(self, class_name: str) -> Dict[str, Any]:
        """Get default properties for a net class"""
        props = {
            NetClassType.POWER.value: {
                "track_width": self.defaults["power_track_width"],
                "clearance": self.defaults["clearance"],
                "color": "#FF0000"  # Red
            },
            NetClassType.GROUND.value: {
                "track_width": self.defaults["ground_track_width"],
                "clearance": self.defaults["clearance"],
                "color": "#000000"  # Black
            },
            NetClassType.HIGH_SPEED.value: {
                "track_width": self.defaults["diff_pair_width"],
                "clearance": self.defaults["highspeed_clearance"],
                "length_matching": True,
                "color": "#0000FF"  # Blue
            },
            NetClassType.DIFFERENTIAL.value: {
                "track_width": self.defaults["diff_pair_width"],
                "clearance": self.defaults["highspeed_clearance"],
                "differential_pair": True,
                "pair_gap": self.defaults["diff_pair_gap"],
                "color": "#FF00FF"  # Magenta
            },
            NetClassType.CLOCK.value: {
                "track_width": self.defaults["track_width"],
                "clearance": self.defaults["highspeed_clearance"],
                "short_trace": True,
                "color": "#FFFF00"  # Yellow
            },
            NetClassType.ANALOG.value: {
                "track_width": self.defaults["track_width"],
                "clearance": self.defaults["highspeed_clearance"],
                "guard_ring": True,
                "color": "#00FF00"  # Green
            },
        }
        return props.get(class_name, {"track_width": self.defaults["track_width"]})
    
    def generate_rules(self, classified_nets: Dict[str, List[str]] = None) -> List[DesignRule]:
        """Generate design rules"""
        self.rules = []
        
        # === Default Rules ===
        self.rules.append(DesignRule(
            name="Clearance_Default",
            rule_type=RuleType.CLEARANCE,
            priority=1,
            scope="All",
            properties={
                "min_clearance_mm": self.defaults["clearance"],
                "description": "Default clearance between all objects"
            }
        ))
        
        self.rules.append(DesignRule(
            name="Width_Default",
            rule_type=RuleType.WIDTH,
            priority=1,
            scope="All",
            properties={
                "min_width_mm": self.defaults["track_width"],
                "preferred_width_mm": self.defaults["track_width"],
                "max_width_mm": 2.0,
                "description": "Default track width"
            }
        ))
        
        self.rules.append(DesignRule(
            name="Via_Default",
            rule_type=RuleType.VIA,
            priority=1,
            scope="All",
            properties={
                "hole_size_mm": self.defaults["via_hole"],
                "via_diameter_mm": self.defaults["via_diameter"],
                "description": "Default via size"
            }
        ))
        
        # === Net Class Specific Rules ===
        if classified_nets:
            # Power track width
            if classified_nets.get(NetClassType.POWER.value):
                self.rules.append(DesignRule(
                    name="Width_Power",
                    rule_type=RuleType.WIDTH,
                    priority=2,
                    scope=f"InNetClass('{NetClassType.POWER.value}')",
                    properties={
                        "min_width_mm": self.defaults["power_track_width"],
                        "preferred_width_mm": self.defaults["power_track_width"],
                        "description": "Power net track width - wider for current capacity"
                    }
                ))
            
            # Ground track width
            if classified_nets.get(NetClassType.GROUND.value):
                self.rules.append(DesignRule(
                    name="Width_Ground",
                    rule_type=RuleType.WIDTH,
                    priority=2,
                    scope=f"InNetClass('{NetClassType.GROUND.value}')",
                    properties={
                        "min_width_mm": self.defaults["ground_track_width"],
                        "preferred_width_mm": self.defaults["ground_track_width"],
                        "description": "Ground net track width"
                    }
                ))
            
            # High-speed clearance
            if classified_nets.get(NetClassType.HIGH_SPEED.value):
                self.rules.append(DesignRule(
                    name="Clearance_HighSpeed",
                    rule_type=RuleType.CLEARANCE,
                    priority=2,
                    scope=f"InNetClass('{NetClassType.HIGH_SPEED.value}')",
                    properties={
                        "min_clearance_mm": self.defaults["highspeed_clearance"],
                        "description": "High-speed signal clearance for signal integrity"
                    }
                ))
            
            # Differential pairs
            if classified_nets.get(NetClassType.DIFFERENTIAL.value):
                self.rules.append(DesignRule(
                    name="DiffPair_Rule",
                    rule_type=RuleType.DIFFERENTIAL_PAIR,
                    priority=2,
                    scope=f"InNetClass('{NetClassType.DIFFERENTIAL.value}')",
                    properties={
                        "track_width_mm": self.defaults["diff_pair_width"],
                        "gap_mm": self.defaults["diff_pair_gap"],
                        "coupled_length": True,
                        "description": "Differential pair routing rules"
                    }
                ))
        
        return self.rules
    
    def generate_altium_rules_script(self) -> str:
        """Generate DelphiScript to create rules in Altium"""
        script_lines = [
            "{ Auto-generated design rules script }",
            "{ Generated by EagilinsED Constraint Generator }",
            "",
            "Procedure CreateDesignRules;",
            "Var",
            "    Board : IPCB_Board;",
            "    Rule : IPCB_Rule;",
            "Begin",
            "    Board := PCBServer.GetCurrentPCBBoard;",
            "    If Board = Nil Then Exit;",
            "",
            "    PCBServer.PreProcess;",
            "",
        ]
        
        for rule in self.rules:
            if rule.rule_type == RuleType.CLEARANCE:
                clearance = rule.properties.get("min_clearance_mm", 0.2)
                clearance_mils = clearance * 39.3701
                script_lines.extend([
                    f"    {{ {rule.name} }}",
                    "    Rule := PCBServer.PCBRuleFactory(eRule_Clearance);",
                    f"    Rule.Name := '{rule.name}';",
                    f"    Rule.MinimumGap := MilsToCoord({clearance_mils:.2f});",
                    "    Board.AddPCBObject(Rule);",
                    "",
                ])
            
            elif rule.rule_type == RuleType.WIDTH:
                min_w = rule.properties.get("min_width_mm", 0.25)
                pref_w = rule.properties.get("preferred_width_mm", 0.25)
                min_w_mils = min_w * 39.3701
                pref_w_mils = pref_w * 39.3701
                script_lines.extend([
                    f"    {{ {rule.name} }}",
                    "    Rule := PCBServer.PCBRuleFactory(eRule_Width);",
                    f"    Rule.Name := '{rule.name}';",
                    f"    Rule.MinWidth := MilsToCoord({min_w_mils:.2f});",
                    f"    Rule.PreferedWidth := MilsToCoord({pref_w_mils:.2f});",
                    "    Board.AddPCBObject(Rule);",
                    "",
                ])
        
        script_lines.extend([
            "    PCBServer.PostProcess;",
            "    Board.GraphicallyInvalidate;",
            "    ShowMessage('Design rules created successfully.');",
            "End;",
        ])
        
        return "\n".join(script_lines)
    
    def export_rules_json(self) -> str:
        """Export rules to JSON format"""
        data = {
            "net_classes": [nc.to_dict() for nc in self.net_classes],
            "rules": [r.to_dict() for r in self.rules]
        }
        return json.dumps(data, indent=2)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of generated constraints"""
        return {
            "net_classes": len(self.net_classes),
            "rules": len(self.rules),
            "rules_by_type": {
                rt.value: len([r for r in self.rules if r.rule_type == rt])
                for rt in RuleType
            }
        }


def generate_constraints_from_design(schematic_data: Dict, 
                                     pcb_data: Dict = None) -> Dict[str, Any]:
    """
    Convenience function to generate all constraints from design data.
    
    Args:
        schematic_data: Schematic data with components and nets
        pcb_data: Optional PCB data
        
    Returns:
        Dict with net_classes, rules, and scripts
    """
    generator = ConstraintGenerator()
    
    # Get nets from schematic or PCB
    nets = schematic_data.get("nets", []) or schematic_data.get("wires", [])
    if not nets and pcb_data:
        nets = pcb_data.get("nets", [])
    
    # Analyze and generate
    classified = generator.analyze_nets(nets)
    generator.generate_net_classes(classified)
    generator.generate_rules(classified)
    
    return {
        "net_classes": generator.net_classes,
        "rules": generator.rules,
        "script": generator.generate_altium_rules_script(),
        "json": generator.export_rules_json(),
        "summary": generator.get_summary()
    }

