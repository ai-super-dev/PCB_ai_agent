"""
Automatic DRC Rule Generator
Automatically creates and updates DRC rules based on PCB design analysis

Features:
- Analyzes PCB design (nets, components, layers)
- Generates appropriate rules based on design characteristics
- Updates rules automatically when design changes
- Learns from DRC violations to refine rules
"""
from typing import List, Dict, Any, Optional
from core.ir.gir import GeometryIR
from core.ir.cir import ConstraintIR, Rule, RuleType, RuleScope, RuleParams, Netclass, NetclassDefaults
import sys
from pathlib import Path
# Import core modules
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from enum import Enum

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import json

# Define NetClassType locally since constraint_generator was removed
class NetClassType(Enum):
    POWER = "power"
    GROUND = "ground" 
    SIGNAL = "signal"
    CLOCK = "clock"
    DIFFERENTIAL = "differential"


class AutoDRCRuleGenerator:
    """
    Automatically generates DRC rules based on PCB design analysis
    
    This class:
    1. Analyzes the PCB design to understand requirements
    2. Generates appropriate design rules
    3. Updates rules when design changes
    4. Learns from violations to improve rules
    """
    
    def __init__(self):
        self.rule_history = []  # Track rule changes for learning
        
    def generate_rules_from_pcb(self, gir: GeometryIR, 
                                existing_rules: Optional[ConstraintIR] = None) -> ConstraintIR:
        """
        Automatically generate DRC rules from PCB design
        
        Args:
            gir: Geometry IR of the PCB
            existing_rules: Optional existing rules to merge/update
            
        Returns:
            ConstraintIR with generated rules
        """
        # Create basic constraint IR with default rules
        constraint_ir = ConstraintIR()
        
        # Add basic clearance rules
        clearance_rule = Rule(
            name="Basic_Clearance",
            rule_type=RuleType.CLEARANCE,
            scope=RuleScope(),
            parameters={"clearance_mm": 0.2}
        )
        constraint_ir.rules.append(clearance_rule)
        
        # Add basic width rules
        width_rule = Rule(
            name="Basic_Width", 
            rule_type=RuleType.WIDTH,
            scope=RuleScope(),
            parameters={"min_width_mm": 0.254, "max_width_mm": 15.0, "preferred_width_mm": 0.838}
        )
        constraint_ir.rules.append(width_rule)
        
        return constraint_ir
        
        # Step 4: Convert to C-IR format
        rules = []
        netclasses = []
        
        # Convert net classes
        for nc in net_classes:
            # Map net names to net IDs
            net_ids = []
            for net in gir.nets:
                if net.name in nc.nets:
                    net_ids.append(net.id)
            
            netclass = Netclass(
                id=f"nc-{nc.name.lower()}",
                name=nc.name,
                nets=net_ids,
                defaults=NetclassDefaults(
                    trace_width_mm=nc.properties.get("track_width", 0.25),
                    clearance_mm=nc.properties.get("clearance", 0.2)
                )
            )
            netclasses.append(netclass)
        
        # Convert basic rules (simplified since constraint_generator was removed)
        # Add the basic rules we created earlier
        for rule in constraint_ir.rules:
            # Convert to C-IR format
            if rule.rule_type == RuleType.CLEARANCE:
                c_rule = Rule(
                    name=rule.name,
                    rule_type=RuleType.CLEARANCE,
                    scope=RuleScope(),
                    parameters=rule.parameters
                )
                constraint_ir.rules.append(c_rule)
            elif rule.rule_type == RuleType.WIDTH:
                c_rule = Rule(
                    name=rule.name,
                    rule_type=RuleType.WIDTH,
                    scope=RuleScope(),
                    parameters=rule.parameters
                )
                constraint_ir.rules.append(c_rule)
            
            # Convert rule type
            rule_type_map = {
                "clearance": RuleType.CLEARANCE,
                "width": RuleType.TRACE_WIDTH,
                "via": RuleType.VIA,
                "differential_pair": RuleType.DIFFERENTIAL_PAIR,
            }
            cir_rule_type = rule_type_map.get(rule.rule_type.value, RuleType.CLEARANCE)
            
            # Create rule params
            params = RuleParams()
            if rule.rule_type.value == "clearance":
                params.min_clearance_mm = rule.properties.get("min_clearance_mm", 0.2)
            elif rule.rule_type.value == "width":
                params.min_width_mm = rule.properties.get("min_width_mm", 0.25)
                params.preferred_width_mm = rule.properties.get("preferred_width_mm", 0.25)
            elif rule.rule_type.value == "via":
                params.min_drill_mm = rule.properties.get("hole_size_mm", 0.3)
            
            cir_rule = Rule(
                id=f"auto-{rule.name.lower().replace(' ', '-')}",
                type=cir_rule_type,
                scope=scope,
                params=params,
                enabled=rule.enabled,
                priority=rule.priority
            )
            rules.append(cir_rule)
        
        # Step 5: Analyze board characteristics for additional rules
        additional_rules = self._analyze_board_characteristics(gir, classified_nets)
        rules.extend(additional_rules)
        
        # Step 6: Merge with existing rules if provided
        if existing_rules:
            rules, netclasses = self._merge_rules(existing_rules, rules, netclasses)
        
        return ConstraintIR(rules=rules, netclasses=netclasses)
    
    def _analyze_board_characteristics(self, gir: GeometryIR, 
                                       classified_nets: Dict[str, List[str]]) -> List[Rule]:
        """
        Analyze board characteristics and generate additional rules
        
        Args:
            gir: Geometry IR
            classified_nets: Classified nets dictionary
            
        Returns:
            List of additional rules
        """
        additional_rules = []
        
        # Analyze board size
        if gir.board.outline and gir.board.outline.polygon:
            outline = gir.board.outline.polygon
            x_coords = [p[0] for p in outline]
            y_coords = [p[1] for p in outline]
            board_width = max(x_coords) - min(x_coords)
            board_height = max(y_coords) - min(y_coords)
            board_area = board_width * board_height
            
            # Larger boards may need stricter rules
            if board_area > 10000:  # > 100 cm²
                # Add stricter clearance for large boards
                additional_rules.append(Rule(
                    id="auto-large-board-clearance",
                    type=RuleType.CLEARANCE,
                    scope=RuleScope(),
                    params=RuleParams(min_clearance_mm=0.25),
                    enabled=True,
                    priority=1
                ))
        
        # Analyze layer count
        layer_count = len(gir.board.layers)
        if layer_count >= 4:
            # Multi-layer boards may need via rules
            additional_rules.append(Rule(
                id="auto-multilayer-via",
                type=RuleType.VIA,
                scope=RuleScope(),
                params=RuleParams(
                    min_drill_mm=0.2,
                    max_drill_mm=0.5
                ),
                enabled=True,
                priority=1
            ))
        
        # Analyze component density
        component_count = len(gir.footprints)
        track_count = len(gir.tracks)
        if component_count > 50 and track_count > 100:
            # High density board - stricter rules
            additional_rules.append(Rule(
                id="auto-high-density-clearance",
                type=RuleType.CLEARANCE,
                scope=RuleScope(),
                params=RuleParams(min_clearance_mm=0.15),
                enabled=True,
                priority=2
            ))
        
        # Analyze for high-speed signals
        if classified_nets.get(NetClassType.HIGH_SPEED.value):
            # Add crosstalk rules for high-speed nets
            high_speed_nets = classified_nets[NetClassType.HIGH_SPEED.value]
            scope = RuleScope()
            scope.nets = [f"net-{n.lower().replace(' ', '-')}" for n in high_speed_nets]
            
            additional_rules.append(Rule(
                id="auto-highspeed-crosstalk",
                type=RuleType.CROSSTALK,
                scope=scope,
                params=RuleParams(min_spacing_mm=0.3),
                enabled=True,
                priority=3
            ))
        
        return additional_rules
    
    def _merge_rules(self, existing: ConstraintIR, new_rules: List[Rule], 
                    new_netclasses: List[Netclass]) -> tuple:
        """
        Merge new rules with existing rules, avoiding duplicates
        
        Args:
            existing: Existing ConstraintIR
            new_rules: New rules to merge
            new_netclasses: New net classes to merge
            
        Returns:
            Tuple of (merged_rules, merged_netclasses)
        """
        # Start with existing rules
        merged_rules = list(existing.rules)
        merged_netclasses = list(existing.netclasses)
        
        # Add new rules, avoiding duplicates by ID
        existing_ids = {r.id for r in merged_rules}
        for rule in new_rules:
            if rule.id not in existing_ids:
                merged_rules.append(rule)
                existing_ids.add(rule.id)
        
        # Add new net classes, avoiding duplicates by name
        existing_nc_names = {nc.name for nc in merged_netclasses}
        for nc in new_netclasses:
            if nc.name not in existing_nc_names:
                merged_netclasses.append(nc)
                existing_nc_names.add(nc.name)
        
        return merged_rules, merged_netclasses
    
    def update_rules_from_violations(self, rules: ConstraintIR, 
                                    violations: List[Dict[str, Any]]) -> ConstraintIR:
        """
        Learn from DRC violations and update rules
        
        Args:
            rules: Current rules
            violations: List of DRC violations
            
        Returns:
            Updated ConstraintIR with refined rules
        """
        # Group violations by type
        violations_by_type = {}
        for violation in violations:
            v_type = violation.get("type", "unknown")
            if v_type not in violations_by_type:
                violations_by_type[v_type] = []
            violations_by_type[v_type].append(violation)
        
        # Update rules based on violations
        updated_rules = list(rules.rules)
        
        # If we have many clearance violations, we might need stricter clearance
        if "clearance" in violations_by_type:
            clearance_violations = violations_by_type["clearance"]
            if len(clearance_violations) > 5:
                # Find clearance rules and increase minimum
                for rule in updated_rules:
                    if rule.type == RuleType.CLEARANCE and rule.scope.netclass is None:
                        # Increase clearance by 10%
                        current = rule.params.min_clearance_mm or 0.2
                        rule.params.min_clearance_mm = current * 1.1
        
        # If we have track width violations, adjust width rules
        if "track_width" in violations_by_type:
            width_violations = violations_by_type["track_width"]
            if len(width_violations) > 3:
                # Find width rules and adjust
                for rule in updated_rules:
                    if rule.type == RuleType.TRACE_WIDTH:
                        # Check if violations suggest we need larger minimum
                        avg_actual = sum(v.get("actual_mm", 0) for v in width_violations) / len(width_violations)
                        if avg_actual < (rule.params.min_width_mm or 0.25):
                            # Rules are too strict, but violations exist - might need better routing
                            pass  # Don't lower standards, but could add suggestions
        
        return ConstraintIR(rules=updated_rules, netclasses=rules.netclasses)
    
    def get_rule_suggestions(self, gir: GeometryIR, 
                            violations: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Get suggestions for rule improvements
        
        Args:
            gir: Geometry IR
            violations: Optional list of violations
            
        Returns:
            List of suggestion dictionaries
        """
        suggestions = []
        
        # Simple analysis - look for power/ground nets by name
        power_nets = [net for net in gir.nets if any(keyword in net.name.upper() 
                     for keyword in ['VCC', 'VDD', 'POWER', '+3V', '+5V', '+12V'])]
        ground_nets = [net for net in gir.nets if any(keyword in net.name.upper() 
                      for keyword in ['GND', 'GROUND', 'VSS'])]
        
        # Suggest power net class if we have power nets
        if power_nets:
            suggestions.append({
                "type": "net_class",
                "priority": "high",
                "message": f"Found {len(power_nets)} power nets. Consider creating a Power net class with wider trace width rules.",
                "action": "create_power_netclass"
            })
        
        # Suggest ground net class if we have ground nets
        if ground_nets:
            suggestions.append({
                "type": "net_class", 
                "priority": "high",
                "message": f"Found {len(ground_nets)} ground nets. Consider creating a Ground net class with wider trace width rules.",
                "action": "create_ground_netclass"
            })
        
        # Suggest high-speed rules if we have high-speed nets
        if classified_nets.get(NetClassType.HIGH_SPEED.value):
            suggestions.append({
                "type": "rule",
                "priority": "high",
                "message": f"Found {len(classified_nets[NetClassType.HIGH_SPEED.value])} high-speed nets. Consider adding crosstalk and length matching rules.",
                "action": "add_highspeed_rules"
            })
        
        # Analyze violations for suggestions
        if violations:
            violation_types = {}
            for v in violations:
                v_type = v.get("type", "unknown")
                violation_types[v_type] = violation_types.get(v_type, 0) + 1
            
            # Suggest rule adjustments based on violation patterns
            if violation_types.get("clearance", 0) > 10:
                suggestions.append({
                    "type": "rule_adjustment",
                    "priority": "medium",
                    "message": f"Found {violation_types['clearance']} clearance violations. Consider increasing minimum clearance or reviewing component placement.",
                    "action": "increase_clearance"
                })
            
            if violation_types.get("track_width", 0) > 5:
                suggestions.append({
                    "type": "rule_adjustment",
                    "priority": "medium",
                    "message": f"Found {violation_types['track_width']} track width violations. Review routing and ensure tracks meet minimum width requirements.",
                    "action": "review_track_widths"
                })
        
        return suggestions
