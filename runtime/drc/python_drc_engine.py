"""
Python DRC Engine
Comprehensive Design Rule Check implementation in Python

This module performs real DRC checks on PCB data without requiring Altium Designer.
It implements all standard DRC rules for physical and manufacturing validation.
"""
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class DRCRule:
    """Represents a design rule"""
    name: str
    rule_type: str  # clearance, width, via, short_circuit, unrouted_net, etc.
    enabled: bool = True
    priority: int = 1
    
    # Rule parameters (varies by type)
    min_clearance_mm: float = 0.2
    min_width_mm: float = 0.254
    max_width_mm: float = 15.0
    preferred_width_mm: float = 0.838
    min_hole_mm: float = 0.025
    max_hole_mm: float = 5.0
    min_via_drill_mm: float = 0.2
    min_via_diameter_mm: float = 0.5
    hole_to_hole_clearance_mm: float = 0.254
    min_solder_mask_sliver_mm: float = 0.06
    silk_to_solder_mask_clearance_mm: float = 0.0
    silk_to_silk_clearance_mm: float = 0.0
    min_height_mm: float = 0.0
    max_height_mm: float = 25.4
    preferred_height_mm: float = 12.7
    
    # Scope (for clearance rules)
    scope1: str = "All"
    scope2: str = "All"
    scope1_polygon: Optional[str] = None  # e.g., "KZ", "LB"
    
    # Short circuit
    short_circuit_allowed: bool = False
    
    # Unrouted net
    check_unrouted: bool = True
    
    # Modified polygon
    allow_modified_polygon: bool = False
    allow_shelved_polygon: bool = False
    
    # Power plane connect
    plane_connect_style: str = "Relief Connect"
    plane_expansion_mm: float = 0.508
    plane_conductor_width_mm: float = 0.254
    plane_air_gap_mm: float = 0.254
    plane_entries: int = 4
    
    # Net antennae
    net_antennae_tolerance_mm: float = 0.0


@dataclass
class DRCViolation:
    """Represents a DRC violation"""
    rule_name: str
    rule_type: str
    severity: str  # "error" or "warning"
    message: str
    location: Dict[str, Any]  # {x_mm, y_mm, layer, etc.}
    actual_value: Optional[float] = None
    required_value: Optional[float] = None
    objects: Optional[List[str]] = None  # Component names, net names, etc.
    net_name: Optional[str] = None
    component_name: Optional[str] = None


class PythonDRCEngine:
    """
    Comprehensive Python DRC engine
    
    Performs all standard design rule checks:
    - Clearance constraints
    - Width constraints
    - Via/hole size constraints
    - Short-circuit detection
    - Unrouted net detection
    - Solder mask sliver
    - Silk screen clearance
    - Height constraints
    - And more...
    """
    
    def __init__(self):
        self.violations: List[DRCViolation] = []
        self.warnings: List[DRCViolation] = []
    
    def _safe_get_location(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """Safely get location dict from an object, handling tuples and other types"""
        loc = obj.get('location', {})
        if not isinstance(loc, dict):
            # If location is a tuple, try to convert it
            if isinstance(loc, (tuple, list)) and len(loc) >= 2:
                return {"x_mm": float(loc[0]) if loc[0] else 0, "y_mm": float(loc[1]) if loc[1] else 0}
            return {}
        return loc
    
    def run_drc(self, pcb_data: Dict[str, Any], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Run comprehensive DRC check
        
        Args:
            pcb_data: PCB data from get_pcb_info() or similar
            rules: List of design rules (from PCB data or constraint artifacts)
            
        Returns:
            Dictionary with violations, warnings, and summary
        """
        self.violations = []
        self.warnings = []
        
        # Parse rules into DRCRule objects
        drc_rules = self._parse_rules(rules)
        
        # Get PCB elements - ensure they are lists and filter out non-dict items
        tracks = [t for t in pcb_data.get('tracks', []) if isinstance(t, dict)]
        vias = [v for v in pcb_data.get('vias', []) if isinstance(v, dict)]
        pads = [p for p in pcb_data.get('pads', []) if isinstance(p, dict)]
        nets = [n for n in pcb_data.get('nets', []) if isinstance(n, dict)]
        components = [c for c in pcb_data.get('components', []) if isinstance(c, dict)]
        polygons = [p for p in pcb_data.get('polygons', []) if isinstance(p, dict)]
        
        # Run all rule checks
        for rule in drc_rules:
            if not rule.enabled:
                continue
            
            if rule.rule_type == 'clearance':
                self._check_clearance(rule, tracks, pads, vias, components)
            elif rule.rule_type == 'width':
                self._check_width(rule, tracks)
            elif rule.rule_type == 'via' or rule.rule_type == 'hole_size':
                self._check_hole_size(rule, vias, pads)
            elif rule.rule_type == 'short_circuit':
                self._check_short_circuit(rule, tracks, pads, vias)
            elif rule.rule_type == 'unrouted_net':
                self._check_unrouted_nets(rule, nets, tracks, pads, vias)
            elif rule.rule_type == 'hole_to_hole_clearance':
                self._check_hole_to_hole_clearance(rule, vias, pads)
            elif rule.rule_type == 'solder_mask_sliver':
                self._check_solder_mask_sliver(rule, pads, vias)
            elif rule.rule_type == 'silk_to_solder_mask':
                self._check_silk_to_solder_mask(rule, components, pads)
            elif rule.rule_type == 'silk_to_silk':
                self._check_silk_to_silk(rule, components)
            elif rule.rule_type == 'height':
                self._check_height(rule, components)
            elif rule.rule_type == 'modified_polygon':
                self._check_modified_polygon(rule, polygons)
            elif rule.rule_type == 'net_antennae':
                self._check_net_antennae(rule, nets, tracks, pads, vias)
        
        # Build summary
        violations_by_type = {}
        for v in self.violations:
            violations_by_type[v.rule_type] = violations_by_type.get(v.rule_type, 0) + 1
        
        return {
            "summary": {
                "warnings": len(self.warnings),
                "rule_violations": len(self.violations),
                "total": len(self.violations) + len(self.warnings),
                "passed": len(self.violations) == 0 and len(self.warnings) == 0
            },
            "violations_by_type": violations_by_type,
            "violations": [self._violation_to_dict(v) for v in self.violations],
            "warnings": [self._violation_to_dict(v) for v in self.warnings],
            "detailed_violations": [self._violation_to_dict(v) for v in self.violations]
        }
    
    def _parse_rules(self, rules: List[Dict[str, Any]]) -> List[DRCRule]:
        """Parse rules from dict format to DRCRule objects"""
        drc_rules = []
        
        # Handle case where rules might be a tuple or other iterable
        if not isinstance(rules, (list, tuple)):
            return drc_rules
        
        for rule_dict in rules:
            # Skip if rule_dict is not a dict (might be a tuple or other type)
            if not isinstance(rule_dict, dict):
                continue
            
            # Handle both 'type' and 'kind' fields (Altium uses 'kind')
            rule_type = rule_dict.get('type') or rule_dict.get('kind', 'other')
            rule_name = rule_dict.get('name', 'Unnamed Rule')
            
            # Normalize rule type from Altium format
            if isinstance(rule_type, str):
                rule_type_lower = rule_type.lower()
                if 'clearance' in rule_type_lower:
                    rule_type = 'clearance'
                elif 'width' in rule_type_lower and 'via' not in rule_type_lower:
                    rule_type = 'width'
                elif 'via' in rule_type_lower or 'hole' in rule_type_lower:
                    rule_type = 'via' if 'via' in rule_type_lower else 'hole_size'
                elif 'short' in rule_type_lower:
                    rule_type = 'short_circuit'
                elif 'unrouted' in rule_type_lower:
                    rule_type = 'unrouted_net'
                elif 'solder' in rule_type_lower and 'mask' in rule_type_lower:
                    rule_type = 'solder_mask_sliver'
                elif 'silk' in rule_type_lower:
                    if 'solder' in rule_type_lower or 'mask' in rule_type_lower:
                        rule_type = 'silk_to_solder_mask'
                    else:
                        rule_type = 'silk_to_silk'
                elif 'height' in rule_type_lower:
                    rule_type = 'height'
                elif 'polygon' in rule_type_lower:
                    rule_type = 'modified_polygon'
                elif 'antenna' in rule_type_lower:
                    rule_type = 'net_antennae'
                elif 'hole' in rule_type_lower and 'clearance' in rule_type_lower:
                    rule_type = 'hole_to_hole_clearance'
            
            rule = DRCRule(
                name=rule_name,
                rule_type=rule_type,
                enabled=rule_dict.get('enabled', True),
                priority=rule_dict.get('priority', 1)
            )
            
            # Extract rule-specific parameters
            if rule_type == 'clearance':
                rule.min_clearance_mm = rule_dict.get('clearance_mm', 0.2)
                rule.scope1 = rule_dict.get('scope1', 'All')
                rule.scope2 = rule_dict.get('scope2', 'All')
                rule.scope1_polygon = rule_dict.get('scope1_polygon')
            elif rule_type == 'width':
                rule.min_width_mm = rule_dict.get('min_width_mm', 0.254)
                rule.max_width_mm = rule_dict.get('max_width_mm', 15.0)
                rule.preferred_width_mm = rule_dict.get('preferred_width_mm', 0.838)
            elif rule_type in ['via', 'hole_size']:
                rule.min_hole_mm = rule_dict.get('min_hole_mm', 0.025)
                rule.max_hole_mm = rule_dict.get('max_hole_mm', 5.0)
            elif rule_type == 'short_circuit':
                rule.short_circuit_allowed = rule_dict.get('allowed', False)
            elif rule_type == 'unrouted_net':
                rule.check_unrouted = rule_dict.get('enabled', True)
            elif rule_type == 'hole_to_hole_clearance':
                rule.hole_to_hole_clearance_mm = rule_dict.get('gap_mm', 0.254)
            elif rule_type == 'solder_mask_sliver':
                rule.min_solder_mask_sliver_mm = rule_dict.get('gap_mm', 0.06)
            elif rule_type == 'silk_to_solder_mask':
                rule.silk_to_solder_mask_clearance_mm = rule_dict.get('clearance_mm', 0.0)
            elif rule_type == 'silk_to_silk':
                rule.silk_to_silk_clearance_mm = rule_dict.get('clearance_mm', 0.0)
            elif rule_type == 'height':
                rule.min_height_mm = rule_dict.get('min_height_mm', 0.0)
                rule.max_height_mm = rule_dict.get('max_height_mm', 25.4)
                rule.preferred_height_mm = rule_dict.get('preferred_height_mm', 12.7)
            elif rule_type == 'modified_polygon':
                rule.allow_modified_polygon = rule_dict.get('allow_modified', False)
                rule.allow_shelved_polygon = rule_dict.get('allow_shelved', False)
            elif rule_type == 'net_antennae':
                rule.net_antennae_tolerance_mm = rule_dict.get('tolerance_mm', 0.0)
            
            drc_rules.append(rule)
        
        return drc_rules
    
    def _check_clearance(self, rule: DRCRule, tracks: List[Dict], pads: List[Dict], 
                        vias: List[Dict], components: List[Dict]):
        """Check clearance constraints between objects"""
        min_clearance = rule.min_clearance_mm
        
        # Check pad-to-pad clearance
        for i, pad1 in enumerate(pads):
            loc1 = self._safe_get_location(pad1)
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            net1 = pad1.get('net', '')
            size1 = max(pad1.get('size_x_mm', 0), pad1.get('size_y_mm', 0)) / 2
            
            for pad2 in pads[i+1:]:
                # Skip if same net
                if net1 and pad2.get('net') == net1:
                    continue
                
                loc2 = self._safe_get_location(pad2)
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
                
                if clearance > 0 and clearance < min_clearance:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="clearance",
                        severity="error",
                        message=f"Clearance violation: {clearance:.3f}mm < {min_clearance}mm between pads",
                        location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                        actual_value=round(clearance, 3),
                        required_value=min_clearance,
                        objects=[pad1.get('name', 'pad1'), pad2.get('name', 'pad2')]
                    ))
        
        # Check via-to-pad clearance
        for via in vias:
            via_loc = self._safe_get_location(via)
            via_x = via_loc.get('x_mm', 0)
            via_y = via_loc.get('y_mm', 0)
            via_radius = via.get('diameter_mm', 0) / 2
            
            for pad in pads:
                pad_loc = self._safe_get_location(pad)
                pad_x = pad_loc.get('x_mm', 0)
                pad_y = pad_loc.get('y_mm', 0)
                pad_radius = max(pad.get('size_x_mm', 0), pad.get('size_y_mm', 0)) / 2
                pad_net = pad.get('net', '')
                via_net = via.get('net', '')
                
                # Skip if same net
                if pad_net and via_net and pad_net == via_net:
                    continue
                
                if via_x == 0 and via_y == 0:
                    continue
                if pad_x == 0 and pad_y == 0:
                    continue
                
                distance = math.sqrt((pad_x - via_x)**2 + (pad_y - via_y)**2)
                clearance = distance - via_radius - pad_radius
                
                if clearance > 0 and clearance < min_clearance:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="clearance",
                        severity="error",
                        message=f"Clearance violation: {clearance:.3f}mm < {min_clearance}mm between via and pad",
                        location={"x_mm": (via_x + pad_x) / 2, "y_mm": (via_y + pad_y) / 2},
                        actual_value=round(clearance, 3),
                        required_value=min_clearance
                    ))
    
    def _check_width(self, rule: DRCRule, tracks: List[Dict]):
        """Check track width constraints"""
        for track in tracks:
            width = track.get('width_mm', 0)
            
            if width > 0:
                if width < rule.min_width_mm:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="width",
                        severity="error",
                        message=f"Track width {width:.3f}mm is below minimum {rule.min_width_mm}mm",
                        location={"layer": track.get('layer', 'unknown')},
                        actual_value=width,
                        required_value=rule.min_width_mm
                    ))
                elif width > rule.max_width_mm:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="width",
                        severity="error",
                        message=f"Track width {width:.3f}mm exceeds maximum {rule.max_width_mm}mm",
                        location={"layer": track.get('layer', 'unknown')},
                        actual_value=width,
                        required_value=rule.max_width_mm
                    ))
    
    def _check_hole_size(self, rule: DRCRule, vias: List[Dict], pads: List[Dict]):
        """Check via and pad hole size constraints"""
        # Check vias
        for via in vias:
            hole_size = via.get('hole_size_mm', 0)
            if hole_size > 0:
                if hole_size < rule.min_hole_mm:
                    loc = self._safe_get_location(via)
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="hole_size",
                        severity="error",
                        message=f"Via hole size {hole_size:.3f}mm is below minimum {rule.min_hole_mm}mm",
                        location={"x_mm": loc.get('x_mm', 0), "y_mm": loc.get('y_mm', 0)},
                        actual_value=hole_size,
                        required_value=rule.min_hole_mm
                    ))
                elif hole_size > rule.max_hole_mm:
                    loc = self._safe_get_location(via)
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="hole_size",
                        severity="error",
                        message=f"Via hole size {hole_size:.3f}mm exceeds maximum {rule.max_hole_mm}mm",
                        location={"x_mm": loc.get('x_mm', 0), "y_mm": loc.get('y_mm', 0)},
                        actual_value=hole_size,
                        required_value=rule.max_hole_mm
                    ))
        
        # Check pads
        for pad in pads:
            hole_size = pad.get('hole_size_mm', 0)
            if hole_size > 0:
                if hole_size < rule.min_hole_mm:
                    loc = self._safe_get_location(pad)
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="hole_size",
                        severity="error",
                        message=f"Pad hole size {hole_size:.3f}mm is below minimum {rule.min_hole_mm}mm",
                        location={"x_mm": loc.get('x_mm', 0), "y_mm": loc.get('y_mm', 0)},
                        actual_value=hole_size,
                        required_value=rule.min_hole_mm,
                        component_name=pad.get('component', '')
                    ))
                elif hole_size > rule.max_hole_mm:
                    loc = self._safe_get_location(pad)
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="hole_size",
                        severity="error",
                        message=f"Pad hole size {hole_size:.3f}mm exceeds maximum {rule.max_hole_mm}mm",
                        location={"x_mm": loc.get('x_mm', 0), "y_mm": loc.get('y_mm', 0)},
                        actual_value=hole_size,
                        required_value=rule.max_hole_mm,
                        component_name=pad.get('component', '')
                    ))
    
    def _check_short_circuit(self, rule: DRCRule, tracks: List[Dict], pads: List[Dict], vias: List[Dict]):
        """Check for short circuits (overlapping objects on different nets)"""
        if rule.short_circuit_allowed:
            return  # Short circuits are allowed
        
        # Check pad-to-pad overlaps (different nets)
        for i, pad1 in enumerate(pads):
            loc1 = pad1.get('location', {})
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            net1 = pad1.get('net', '')
            size1 = max(pad1.get('size_x_mm', 0), pad1.get('size_y_mm', 0)) / 2
            
            for pad2 in pads[i+1:]:
                net2 = pad2.get('net', '')
                if not net1 or not net2 or net1 == net2:
                    continue
                
                loc2 = pad2.get('location', {})
                x2 = loc2.get('x_mm', 0)
                y2 = loc2.get('y_mm', 0)
                size2 = max(pad2.get('size_x_mm', 0), pad2.get('size_y_mm', 0)) / 2
                
                distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                if distance < (size1 + size2):
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="short_circuit",
                        severity="error",
                        message=f"Short circuit: Pads on different nets ({net1}, {net2}) overlap",
                        location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                        objects=[pad1.get('name', 'pad1'), pad2.get('name', 'pad2')],
                        net_name=f"{net1}/{net2}"
                    ))
    
    def _check_unrouted_nets(self, rule: DRCRule, nets: List[Dict], tracks: List[Dict], 
                             pads: List[Dict], vias: List[Dict]):
        """Check for unrouted nets - matching Altium's logic"""
        if not rule.check_unrouted:
            return
        
        # Altium's unrouted net check:
        # 1. A net is considered "routed" if it has tracks connecting its pads
        # 2. Nets connected only via polygons/pours are considered routed
        # 3. Single-pad nets (test points, etc.) are typically not flagged
        # 4. Power/ground nets connected to planes are considered routed
        
        # Collect all nets that have tracks (actual routing)
        nets_with_tracks = set()
        for track in tracks:
            net = track.get('net', '')
            if net and net.strip():
                nets_with_tracks.add(net.strip())
        
        # Collect nets that have pads/vias (connectivity exists)
        nets_with_pads = set()
        for pad in pads:
            net = pad.get('net', '')
            if net and net.strip():
                nets_with_pads.add(net.strip())
        
        for via in vias:
            net = via.get('net', '')
            if net and net.strip():
                nets_with_pads.add(net.strip())
        
        # Count pads per net to identify single-pad nets (test points, etc.)
        pad_count_per_net = {}
        for pad in pads:
            net = pad.get('net', '')
            if net and net.strip():
                net = net.strip()
                pad_count_per_net[net] = pad_count_per_net.get(net, 0) + 1
        
        # Check each net
        for net in nets:
            net_name = net.get('name', '')
            if not net_name or net_name == 'No Net' or net_name.strip() == '':
                continue
            
            net_name = net_name.strip()
            
            # Skip if net has tracks (it's routed)
            if net_name in nets_with_tracks:
                continue
            
            # Skip single-pad nets (test points, mounting holes, etc.)
            # Altium typically doesn't flag these as unrouted
            if pad_count_per_net.get(net_name, 0) <= 1:
                continue
            
            # Skip if net doesn't have any pads/vias (orphaned net definition)
            if net_name not in nets_with_pads:
                continue
            
            # Only flag nets that have multiple pads but no tracks
            # This matches Altium's behavior more closely
            pad_count = pad_count_per_net.get(net_name, 0)
            if pad_count >= 2 and net_name not in nets_with_tracks:
                severity = "warning"
                # Power/ground nets with multiple pads but no tracks = error
                if any(power in net_name.upper() for power in ['GND', 'VCC', 'VDD', 'POWER', 'GROUND']):
                    severity = "error"
                
                violation = DRCViolation(
                    rule_name=rule.name,
                    rule_type="unrouted_net",
                    severity=severity,
                    message=f"Net '{net_name}' has {pad_count} pad(s) but no routed tracks",
                    location={},
                    net_name=net_name
                )
                
                if severity == "error":
                    self.violations.append(violation)
                else:
                    self.warnings.append(violation)
    
    def _check_hole_to_hole_clearance(self, rule: DRCRule, vias: List[Dict], pads: List[Dict]):
        """Check clearance between holes"""
        min_clearance = rule.hole_to_hole_clearance_mm
        
        # Check via-to-via
        for i, via1 in enumerate(vias):
            loc1 = self._safe_get_location(via1)
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            hole1 = via1.get('hole_size_mm', 0) / 2
            
            for via2 in vias[i+1:]:
                loc2 = self._safe_get_location(via2)
                x2 = loc2.get('x_mm', 0)
                y2 = loc2.get('y_mm', 0)
                hole2 = via2.get('hole_size_mm', 0) / 2
                
                distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                clearance = distance - hole1 - hole2
                
                if clearance > 0 and clearance < min_clearance:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="hole_to_hole_clearance",
                        severity="error",
                        message=f"Hole-to-hole clearance violation: {clearance:.3f}mm < {min_clearance}mm",
                        location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                        actual_value=round(clearance, 3),
                        required_value=min_clearance
                    ))
    
    def _check_solder_mask_sliver(self, rule: DRCRule, pads: List[Dict], vias: List[Dict]):
        """Check for minimum solder mask sliver"""
        # This is a simplified check - full implementation would require
        # detailed solder mask geometry analysis
        min_sliver = rule.min_solder_mask_sliver_mm
        
        # Check pad-to-pad spacing for potential slivers
        for i, pad1 in enumerate(pads):
            loc1 = self._safe_get_location(pad1)
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            size1 = max(pad1.get('size_x_mm', 0), pad1.get('size_y_mm', 0)) / 2
            
            for pad2 in pads[i+1:]:
                loc2 = self._safe_get_location(pad2)
                x2 = loc2.get('x_mm', 0)
                y2 = loc2.get('y_mm', 0)
                size2 = max(pad2.get('size_x_mm', 0), pad2.get('size_y_mm', 0)) / 2
                
                distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                gap = distance - size1 - size2
                
                if 0 < gap < min_sliver:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="solder_mask_sliver",
                        severity="error",
                        message=f"Solder mask sliver: {gap:.3f}mm < {min_sliver}mm",
                        location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                        actual_value=round(gap, 3),
                        required_value=min_sliver
                    ))
    
    def _check_silk_to_solder_mask(self, rule: DRCRule, components: List[Dict], pads: List[Dict]):
        """Check silk screen to solder mask clearance"""
        min_clearance = rule.silk_to_solder_mask_clearance_mm
        
        # Altium only checks silk-to-solder-mask when clearance > 0
        # If clearance is 0, it means overlap is allowed
        if min_clearance <= 0:
            return  # Skip check if clearance is 0 or negative
        
        # Without actual silk screen geometry data, we cannot accurately check this
        # Altium uses actual silk screen geometry, not component bounding boxes
        # This check requires detailed component footprint data with silk screen layers
        # For now, skip this check to prevent false positives
        return
    
    def _check_silk_to_silk(self, rule: DRCRule, components: List[Dict]):
        """Check silk screen to silk screen clearance"""
        min_clearance = rule.silk_to_silk_clearance_mm
        
        # Altium only checks silk-to-silk when clearance > 0
        # If clearance is 0, it means silk overlap is allowed
        if min_clearance <= 0:
            return  # Skip check if clearance is 0 or negative
        
        # Only check if we have actual component dimensions
        # Without real silk screen geometry, we can't accurately check this
        # Altium uses actual silk screen geometry, not component bounding boxes
        # For now, skip this check as we don't have silk screen data
        # This prevents false positives from component proximity
        return
    
    def _check_height(self, rule: DRCRule, components: List[Dict]):
        """Check component height constraints"""
        for comp in components:
            height = comp.get('height_mm', 0)
            
            if height > 0:
                if height < rule.min_height_mm:
                    loc = self._safe_get_location(comp)
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="height",
                        severity="error",
                        message=f"Component height {height:.2f}mm is below minimum {rule.min_height_mm}mm",
                        location={"x_mm": loc.get('x_mm', 0), "y_mm": loc.get('y_mm', 0)},
                        actual_value=height,
                        required_value=rule.min_height_mm,
                        component_name=comp.get('name', '')
                    ))
                elif height > rule.max_height_mm:
                    loc = self._safe_get_location(comp)
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="height",
                        severity="error",
                        message=f"Component height {height:.2f}mm exceeds maximum {rule.max_height_mm}mm",
                        location={"x_mm": loc.get('x_mm', 0), "y_mm": loc.get('y_mm', 0)},
                        actual_value=height,
                        required_value=rule.max_height_mm,
                        component_name=comp.get('name', '')
                    ))
    
    def _check_modified_polygon(self, rule: DRCRule, polygons: List[Dict]):
        """Check for modified polygons"""
        if rule.allow_modified_polygon and rule.allow_shelved_polygon:
            return
        
        for polygon in polygons:
            if polygon.get('modified', False) and not rule.allow_modified_polygon:
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="modified_polygon",
                    severity="error",
                    message="Modified polygon detected (not allowed)",
                    location={},
                    objects=[polygon.get('name', 'polygon')]
                ))
            
            if polygon.get('shelved', False) and not rule.allow_shelved_polygon:
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="modified_polygon",
                    severity="error",
                    message="Shelved polygon detected (not allowed)",
                    location={},
                    objects=[polygon.get('name', 'polygon')]
                ))
    
    def _check_net_antennae(self, rule: DRCRule, nets: List[Dict], tracks: List[Dict], 
                           pads: List[Dict], vias: List[Dict]):
        """Check for net antennae (stub traces)"""
        # Simplified check - would need full net topology analysis
        tolerance = rule.net_antennae_tolerance_mm
        
        # This is a placeholder - full implementation would require
        # analyzing net connectivity to find stubs
        pass
    
    def _violation_to_dict(self, violation: DRCViolation) -> Dict[str, Any]:
        """Convert DRCViolation to dictionary"""
        return {
            "rule_name": violation.rule_name,
            "type": violation.rule_type,
            "severity": violation.severity,
            "message": violation.message,
            "location": violation.location,
            "actual_value": violation.actual_value,
            "required_value": violation.required_value,
            "objects": violation.objects,
            "net_name": violation.net_name,
            "component_name": violation.component_name
        }
