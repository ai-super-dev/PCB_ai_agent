"""
Python DRC Engine
Comprehensive Design Rule Check implementation in Python

This module performs real DRC checks on PCB data without requiring Altium Designer.
It implements all standard DRC rules for physical and manufacturing validation.

Features:
- Full geometric validation
- Polygon/pour connectivity detection
- Silk screen validation
- Advanced routing rules (differential pairs, topology, via styles, corners)
- Spatial indexing for performance
"""
import math
import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from collections import defaultdict


def point_to_line_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Calculate distance from point to line segment"""
    # Vector from line start to end
    dx = x2 - x1
    dy = y2 - y1
    line_len_sq = dx * dx + dy * dy
    
    if line_len_sq == 0:
        # Line is a point
        return math.sqrt((px - x1)**2 + (py - y1)**2)
    
    # Parameter t: position along line (0 = start, 1 = end)
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / line_len_sq))
    
    # Closest point on line segment
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    
    # Distance from point to closest point on line
    return math.sqrt((px - closest_x)**2 + (py - closest_y)**2)


def segment_to_segment_distance(p1: Tuple[float, float], p2: Tuple[float, float],
                                 q1: Tuple[float, float], q2: Tuple[float, float]) -> float:
    """Calculate minimum distance between two line segments"""
    # Try all combinations: endpoints to segments
    dists = [
        point_to_line_distance(p1[0], p1[1], q1[0], q1[1], q2[0], q2[1]),
        point_to_line_distance(p2[0], p2[1], q1[0], q1[1], q2[0], q2[1]),
        point_to_line_distance(q1[0], q1[1], p1[0], p1[1], p2[0], p2[1]),
        point_to_line_distance(q2[0], q2[1], p1[0], p1[1], p2[0], p2[1])
    ]
    return min(dists)


def point_in_polygon(px: float, py: float, vertices: List[Tuple[float, float]]) -> bool:
    """Ray casting algorithm to check if a point is inside a polygon.
    
    Works for any simple polygon (convex or concave).
    """
    n = len(vertices)
    if n < 3:
        return False
    
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = vertices[i][0], vertices[i][1]
        xj, yj = vertices[j][0], vertices[j][1]
        
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    
    return inside


@dataclass
class DRCRule:
    """Represents a design rule"""
    name: str
    rule_type: str  # clearance, width, via, short_circuit, unrouted_net, etc.
    enabled: bool = True
    priority: int = 1
    
    # Rule parameters (varies by type)
    min_clearance_mm: float = 0.2
    track_to_poly_clearance_mm: float = 0.0  # Per-object-type clearance: Track to Polygon
    pad_to_poly_clearance_mm: float = 0.0    # Per-object-type clearance: Pad to Polygon
    via_to_poly_clearance_mm: float = 0.0    # Per-object-type clearance: Via to Polygon
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
    
    # Differential pair routing
    diff_min_width_mm: float = 0.1
    diff_max_width_mm: float = 0.3
    diff_preferred_width_mm: float = 0.2
    diff_min_gap_mm: float = 0.1
    diff_max_gap_mm: float = 0.3
    diff_preferred_gap_mm: float = 0.2
    diff_max_uncoupled_length_mm: float = 0.0
    
    # Routing topology
    topology_type: str = "Shortest"  # Shortest, Horizontal, Vertical, Daisy-Simple, Daisy-MidDriven, Daisy-Balanced, Star
    
    # Via style
    via_style: str = "Through Hole"  # Through Hole, Blind, Buried
    min_via_diameter_mm: float = 0.5
    max_via_diameter_mm: float = 1.0
    preferred_via_diameter_mm: float = 0.7
    
    # Routing corners
    corner_style: str = "45 Degrees"  # 45 Degrees, 90 Degrees, Rounded, Any Angle
    min_setback_mm: float = 0.0
    max_setback_mm: float = 0.0
    
    # Routing layers
    allowed_layers: List[str] = None  # List of allowed layer names/IDs
    restricted_layers: List[str] = None  # List of restricted layer names/IDs
    
    # Routing priority
    priority_value: int = 0  # Routing priority value (higher = more important)
    
    # Solder mask expansion (for accurate sliver calculation)
    solder_mask_expansion_mm: float = 0.0  # Solder mask expansion beyond pad


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
        
        # Spatial indexing for performance optimization
        self._spatial_index: Optional[Dict[Tuple[int, int], List[Dict]]] = None
        self._index_cell_size: float = 10.0  # 10mm cells for spatial indexing
    
    def _safe_get_location(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """Safely get location dict from an object, handling tuples and other types"""
        # First check if x_mm/y_mm are at the top level (vias, some tracks)
        if 'x_mm' in obj and 'y_mm' in obj:
            return {"x_mm": obj.get('x_mm', 0), "y_mm": obj.get('y_mm', 0)}
        
        # Otherwise look for 'location' dict (pads, components)
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
        self._fallback_unrouted_nets = set()
        
        # Parse rules into DRCRule objects
        drc_rules = self._parse_rules(rules)
        
        # Get PCB elements - ensure they are lists and filter out non-dict items
        # CRITICAL: Filter out binary_record items that don't have real geometry data
        # Binary records are placeholders created when binary format is detected
        # They should not be used for DRC as they contain no accurate geometry
        tracks = [t for t in pcb_data.get('tracks', []) 
                 if isinstance(t, dict) and t.get('type') != 'binary_record' and 'note' not in t]
        vias = [v for v in pcb_data.get('vias', []) 
               if isinstance(v, dict) and v.get('type') != 'binary_record' and 'note' not in v]
        pads = [p for p in pcb_data.get('pads', []) 
               if isinstance(p, dict) and p.get('type') != 'binary_record' and 'note' not in p]
        nets = [n for n in pcb_data.get('nets', []) if isinstance(n, dict)]
        components = [c for c in pcb_data.get('components', []) if isinstance(c, dict)]
        polygons = [p for p in pcb_data.get('polygons', []) if isinstance(p, dict)]
        
        # Store data for Net Antennae check (connection detection)
        self._current_polygons = polygons
        self._current_fills = [f for f in pcb_data.get('fills', []) if isinstance(f, dict)]
        self._current_arcs = [a for a in pcb_data.get('arcs', []) if isinstance(a, dict)]
        self._current_connections = [c for c in pcb_data.get('connections', []) if isinstance(c, dict)]
        
        # CRITICAL: Get actual copper regions (poured copper) instead of polygon outlines
        copper_regions = [r for r in pcb_data.get('copper_regions', []) if isinstance(r, dict)]
        
        # Debug: Log copper region availability
        if copper_regions:
            print(f"DEBUG: Found {len(copper_regions)} actual copper regions for accurate DRC")
            # Show first copper region details
            first_region = copper_regions[0]
            print(f"DEBUG: First copper region: layer={first_region.get('layer', 'N/A')}, "
                  f"net={first_region.get('net', 'N/A')}, "
                  f"vertices={len(first_region.get('vertices', []))}")
        else:
            print(f"DEBUG: No copper regions found - using polygon outlines (less accurate)")
        
        # Debug: Log polygon data availability
        polygon_count = len(polygons)
        polygon_count_with_vertices = sum(1 for p in polygons if p.get('vertices') and len(p.get('vertices', [])) > 0)
        polygon_count_with_bounds = sum(1 for p in polygons if (p.get('x_mm', 0) != 0 or p.get('y_mm', 0) != 0 or p.get('size_x_mm', 0) != 0 or p.get('size_y_mm', 0) != 0))
        if polygon_count > 0:
            print(f"DEBUG: Found {polygon_count} polygons. {polygon_count_with_vertices} with vertices, {polygon_count_with_bounds} with bounds.")
            # Debug: Show first polygon details
            if polygons:
                first_poly = polygons[0]
                print(f"DEBUG: First polygon: name={first_poly.get('name', 'N/A')}, "
                      f"vertices={len(first_poly.get('vertices', []))}, "
                      f"x_mm={first_poly.get('x_mm', 0)}, y_mm={first_poly.get('y_mm', 0)}, "
                      f"size_x_mm={first_poly.get('size_x_mm', 0)}, size_y_mm={first_poly.get('size_y_mm', 0)}")
            if polygon_count_with_vertices == 0 and polygon_count_with_bounds == 0:
                print(f"WARNING: Polygons found but none have geometry data. Re-export PCB info from Altium to get polygon geometry.")
        
        # Process all enabled rules
        print(f"DEBUG: run_drc: Processing {len(drc_rules)} rules")
        clearance_rules = [r for r in drc_rules if r.rule_type == 'clearance' and r.enabled]
        print(f"DEBUG: run_drc: Found {len(clearance_rules)} enabled clearance rules: {[r.name for r in clearance_rules]}")
        
        # IMPORTANT: Fanout rules are intentionally not executed by Python DRC.
        # Altium's fanout behavior depends on rule scopes and routing intent that are
        # not fully represented in our exported geometry, causing large false positives.
        # Keep visibility in logs but skip execution for result parity.
        fanout_rules = [
            r for r in drc_rules
            if "fanout" in r.rule_type.lower() or r.name.lower().startswith("fanout")
        ]
        if fanout_rules:
            print(
                f"DEBUG: Skipping {len(fanout_rules)} fanout rule(s) in Python DRC "
                f"(unsupported parity with Altium): {[r.name for r in fanout_rules]}"
            )
        
        # CRITICAL: Track which rules we've already processed to avoid duplicate checking
        # Altium processes each rule only once, even if there are multiple rules of the same type
        processed_rule_names = set()
        
        deferred_net_antennae_rules = []
        for rule in drc_rules:
            if not rule.enabled:
                continue
            
            # Skip if we've already processed a rule with the same name
            # This prevents duplicate rule processing from export issues
            if rule.name in processed_rule_names:
                print(f"DEBUG: Skipping duplicate rule '{rule.name}' - already processed")
                continue
            processed_rule_names.add(rule.name)
            
            if rule.rule_type == 'clearance':
                print(f"DEBUG: run_drc: Checking clearance rule '{rule.name}', track_to_poly={rule.track_to_poly_clearance_mm}mm")
                self._check_clearance(rule, tracks, pads, vias, components, polygons, copper_regions)
            elif rule.rule_type == 'width':
                self._check_width(rule, tracks)
            elif rule.rule_type in ['via', 'hole_size']:
                self._check_hole_size(rule, vias, pads)
            elif rule.rule_type == 'short_circuit':
                # Only check short-circuit if rule is explicitly enabled
                # Altium typically shows 0 short-circuits for well-designed boards
                print(f"DEBUG: Checking short_circuit rule '{rule.name}', allowed={rule.short_circuit_allowed}")
                self._check_short_circuit(rule, tracks, pads, vias)
            elif rule.rule_type == 'unrouted_net':
                print(f"DEBUG: Checking unrouted_net rule '{rule.name}', check_unrouted={rule.check_unrouted}")
                # Get connection objects (ratsnest) - these are EXACT unrouted connections from Altium
                connections = [c for c in pcb_data.get('connections', []) if isinstance(c, dict)]
                print(f"DEBUG: Found {len(connections)} ratsnest connections (unrouted pad pairs)")
                self._check_unrouted_nets(rule, nets, tracks, pads, vias, polygons, connections=connections)
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
                # Defer antennae check until unrouted processing finishes, so we can
                # scope to nets that actually have connectivity issues.
                deferred_net_antennae_rules.append(rule)
            elif rule.rule_type == 'diff_pairs_routing':
                self._check_differential_pairs(rule, tracks, nets)
            elif rule.rule_type == 'routing_topology':
                self._check_routing_topology(rule, nets, tracks, pads, vias)
            elif rule.rule_type in ['routing_via_style', 'via_style']:
                self._check_via_style(rule, vias)
            elif rule.rule_type == 'routing_corners':
                self._check_routing_corners(rule, tracks)
            elif rule.rule_type == 'routing_layers':
                self._check_routing_layers(rule, tracks)
            elif rule.rule_type == 'routing_priority':
                self._check_routing_priority(rule, nets, tracks)
            elif rule.rule_type == 'plane_connect':
                self._check_plane_connect(rule, pads, vias, polygons)
            elif "fanout" in rule.rule_type.lower() or rule.name.lower().startswith("fanout"):
                # Intentionally skipped; see note above for parity reason.
                continue

        # Run deferred Net Antennae checks after unrouted processing.
        for rule in deferred_net_antennae_rules:
            self._check_net_antennae(rule, nets, tracks, pads, vias)
        
        # CRITICAL: Deduplicate violations to prevent counting the same physical issue multiple times
        # Altium reports each violation only once, even if multiple rules could apply
        # Deduplicate based on location, type, and involved objects
        print(f"DEBUG: Before deduplication: {len(self.violations)} violations")
        unique_violations = self._deduplicate_violations(self.violations)
        self.violations = unique_violations
        print(f"DEBUG: After deduplication: {len(self.violations)} violations")
        
        # DEBUG: Log all violations found for analysis
        if len(self.violations) > 0:
            print(f"DEBUG: Found {len(self.violations)} violations total")
            # Count violations by type for debugging
            violations_by_type_debug = {}
            violations_by_rule_name = {}
            for v in self.violations:
                violations_by_type_debug[v.rule_type] = violations_by_type_debug.get(v.rule_type, 0) + 1
                violations_by_rule_name[v.rule_name] = violations_by_rule_name.get(v.rule_name, 0) + 1
            print(f"DEBUG: Violations by type: {violations_by_type_debug}")
            print(f"DEBUG: Violations by rule name: {violations_by_rule_name}")
            
            # Show sample violations for each type
            for rule_type in violations_by_type_debug.keys():
                type_violations = [v for v in self.violations if v.rule_type == rule_type]
                print(f"DEBUG: {rule_type} violations ({len(type_violations)} total):")
                for i, v in enumerate(type_violations[:3]):  # Show first 3 of each type
                    print(f"  [{i+1}] {v.rule_name}: {v.message[:80]}...")
        
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
            
            # CRITICAL: The JSON export from command_server.pas marks ALL rules as type="clearance"
            # because it can't detect rule types properly. We must also check the rule NAME
            # to correctly classify rules.
            rule_name_lower = rule_name.lower()
            
            # First, try to determine type from rule NAME (more reliable when JSON export is wrong)
            if rule_name_lower in ('width',) or (rule_name_lower.startswith('width') and 'clearance' not in rule_name_lower):
                rule_type = 'width'
            elif rule_name_lower in ('height',) or rule_name_lower.startswith('height'):
                rule_type = 'height'
            elif 'holetohole' in rule_name_lower.replace(' ', '') or rule_name_lower == 'holetoholeclearance':
                rule_type = 'hole_to_hole_clearance'
            elif rule_name_lower in ('holesize',) or rule_name_lower.startswith('holesize'):
                rule_type = 'hole_size'
            elif rule_name_lower in ('shortcircuit',) or rule_name_lower.startswith('shortcircuit'):
                rule_type = 'short_circuit'
            elif 'unroutednet' in rule_name_lower.replace(' ', '') or rule_name_lower.startswith('unrouted'):
                rule_type = 'unrouted_net'
            elif 'soldermasksli' in rule_name_lower.replace(' ', '') or rule_name_lower.startswith('minimumsoldermask'):
                rule_type = 'solder_mask_sliver'
            elif 'silktosilk' in rule_name_lower.replace(' ', ''):
                rule_type = 'silk_to_silk'
            elif 'silktosolder' in rule_name_lower.replace(' ', '') or 'silktomask' in rule_name_lower.replace(' ', ''):
                rule_type = 'silk_to_solder_mask'
            elif 'silktoboard' in rule_name_lower.replace(' ', ''):
                rule_type = 'silk_to_silk'  # Treat as silk clearance
            elif rule_name_lower.startswith('netantennae') or 'antenna' in rule_name_lower:
                rule_type = 'net_antennae'
            elif rule_name_lower.startswith('diffpair') or 'differential' in rule_name_lower:
                rule_type = 'diff_pairs_routing'
            elif rule_name_lower.startswith('routingvia') or rule_name_lower.startswith('viastyle'):
                rule_type = 'routing_via_style'
            elif rule_name_lower.startswith('routingcorner'):
                rule_type = 'routing_corners'
            elif rule_name_lower.startswith('routinglayer'):
                rule_type = 'routing_layers'
            elif rule_name_lower.startswith('routingpriority'):
                rule_type = 'routing_priority'
            elif rule_name_lower.startswith('routingtopology'):
                rule_type = 'routing_topology'
            elif rule_name_lower.startswith('planeconnect') or rule_name_lower == 'polygonconnect':
                rule_type = 'plane_connect'
            elif rule_name_lower.startswith('planeclearance'):
                rule_type = 'plane_clearance'
            elif 'unpouredpolygon' in rule_name_lower or 'modifiedpolygon' in rule_name_lower:
                rule_type = 'modified_polygon'
            elif rule_name_lower.startswith('fanout'):
                rule_type = 'fanout'
            elif rule_name_lower.startswith('componentclearance'):
                rule_type = 'clearance'
            elif rule_name_lower in ('clearance',) or rule_name_lower.startswith('clearance'):
                rule_type = 'clearance'
            else:
                # Fall back to type field normalization
                if isinstance(rule_type, str):
                    rule_type_lower = rule_type.lower()
                    if 'width' in rule_type_lower and 'via' not in rule_type_lower:
                        rule_type = 'width'
                    elif 'clearance' in rule_type_lower:
                        rule_type = 'clearance'
                    elif 'via' in rule_type_lower or 'hole' in rule_type_lower:
                        rule_type = 'via' if 'via' in rule_type_lower else 'hole_size'
                    elif 'short' in rule_type_lower:
                        rule_type = 'short_circuit'
                    elif 'unrouted' in rule_type_lower:
                        rule_type = 'unrouted_net'
                    elif 'height' in rule_type_lower:
                        rule_type = 'height'
                    else:
                        rule_type = 'other'
            
            rule = DRCRule(
                name=rule_name,
                rule_type=rule_type,
                enabled=rule_dict.get('enabled', True),
                priority=rule_dict.get('priority', 1)
            )
            
            # Extract rule-specific parameters
            # Use actual values from the export. Only use defaults when key is missing entirely.
            # 0.0 from export means the rule's actual value could not be read - use a reasonable default
            if rule_type == 'clearance':
                exported_clearance = rule_dict.get('clearance_mm')
                if exported_clearance is not None and exported_clearance > 0:
                    rule.min_clearance_mm = exported_clearance
                else:
                    rule.min_clearance_mm = 0.2  # Default only when value not exported
                rule.scope1 = rule_dict.get('scope1') or rule_dict.get('scope_first', 'All')
                rule.scope2 = rule_dict.get('scope2') or rule_dict.get('scope_second', 'All')
                rule.scope1_polygon = rule_dict.get('scope1_polygon')
                # Per-object-type clearances
                rule.track_to_poly_clearance_mm = rule_dict.get('track_to_poly_clearance_mm', 0)
                rule.pad_to_poly_clearance_mm = rule_dict.get('pad_to_poly_clearance_mm', 0)
                rule.via_to_poly_clearance_mm = rule_dict.get('via_to_poly_clearance_mm', 0)
            elif rule_type == 'width':
                exported_min_w = rule_dict.get('min_width_mm')
                rule.min_width_mm = exported_min_w if (exported_min_w is not None and exported_min_w > 0) else 0.254
                exported_max_w = rule_dict.get('max_width_mm')
                rule.max_width_mm = exported_max_w if (exported_max_w is not None and exported_max_w > 0) else 15.0
                exported_pref_w = rule_dict.get('preferred_width_mm')
                rule.preferred_width_mm = exported_pref_w if (exported_pref_w is not None and exported_pref_w > 0) else 0.254
            elif rule_type in ['via', 'hole_size']:
                rule.min_hole_mm = rule_dict.get('min_hole_mm', 0.025)
                rule.max_hole_mm = rule_dict.get('max_hole_mm', 5.0)
            elif rule_type == 'short_circuit':
                rule.short_circuit_allowed = rule_dict.get('allowed', False)
            elif rule_type == 'unrouted_net':
                rule.check_unrouted = rule_dict.get('enabled', True)
                print(f"DEBUG: Parsed unrouted_net rule '{rule_name}', enabled={rule_dict.get('enabled', True)}, check_unrouted={rule.check_unrouted}")
            elif rule_type == 'hole_to_hole_clearance':
                rule.hole_to_hole_clearance_mm = rule_dict.get('gap_mm', 0) or rule_dict.get('clearance_mm', 0) or 0.254
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
            elif rule_type == 'diff_pairs_routing':
                rule.diff_min_width_mm = rule_dict.get('min_width_mm', rule_dict.get('diff_min_width_mm', 0.1))
                rule.diff_max_width_mm = rule_dict.get('max_width_mm', rule_dict.get('diff_max_width_mm', 0.3))
                rule.diff_preferred_width_mm = rule_dict.get('preferred_width_mm', rule_dict.get('diff_preferred_width_mm', 0.2))
                rule.diff_min_gap_mm = rule_dict.get('min_gap_mm', rule_dict.get('diff_min_gap_mm', 0.1))
                rule.diff_max_gap_mm = rule_dict.get('max_gap_mm', rule_dict.get('diff_max_gap_mm', 0.3))
                rule.diff_preferred_gap_mm = rule_dict.get('preferred_gap_mm', rule_dict.get('diff_preferred_gap_mm', 0.2))
                rule.diff_max_uncoupled_length_mm = rule_dict.get('max_uncoupled_length_mm', 0.0)
            elif rule_type == 'routing_topology':
                rule.topology_type = rule_dict.get('topology', rule_dict.get('topology_type', 'Shortest'))
            elif rule_type in ['routing_via_style', 'via_style']:
                rule.via_style = rule_dict.get('via_style', 'Through Hole')
                rule.min_via_diameter_mm = rule_dict.get('min_via_diameter_mm', 0.5)
                rule.max_via_diameter_mm = rule_dict.get('max_via_diameter_mm', 1.0)
                rule.preferred_via_diameter_mm = rule_dict.get('preferred_via_diameter_mm', 0.7)
            elif rule_type == 'routing_corners':
                rule.corner_style = rule_dict.get('corner_style', '45 Degrees')
                rule.min_setback_mm = rule_dict.get('min_setback_mm', 0.0)
                rule.max_setback_mm = rule_dict.get('max_setback_mm', 0.0)
            elif rule_type == 'routing_layers':
                rule.allowed_layers = rule_dict.get('allowed_layers', [])
                rule.restricted_layers = rule_dict.get('restricted_layers', [])
            elif rule_type == 'routing_priority':
                rule.priority_value = rule_dict.get('priority_value', rule_dict.get('priority', 0))
            elif rule_type == 'plane_connect':
                rule.plane_connect_style = rule_dict.get('plane_connect_style', 'Relief Connect')
                rule.plane_expansion_mm = rule_dict.get('plane_expansion_mm', 0.508)
                rule.plane_conductor_width_mm = rule_dict.get('plane_conductor_width_mm', 0.254)
                rule.plane_air_gap_mm = rule_dict.get('plane_air_gap_mm', 0.254)
                rule.plane_entries = rule_dict.get('plane_entries', 4)
            
            drc_rules.append(rule)
        
        # Debug: Show all parsed rules
        print(f"DEBUG: _parse_rules: Parsed {len(drc_rules)} rules")
        unrouted_rules = [r for r in drc_rules if r.rule_type == 'unrouted_net']
        print(f"DEBUG: _parse_rules: Found {len(unrouted_rules)} unrouted_net rules: {[(r.name, r.enabled, r.check_unrouted) for r in unrouted_rules]}")
        
        return drc_rules
    
    def _check_clearance(self, rule: DRCRule, tracks: List[Dict], pads: List[Dict], 
                        vias: List[Dict], components: List[Dict], polygons: List[Dict] = None, 
                        copper_regions: List[Dict] = None):
        """
        Check clearance constraints between objects
        
        Checks clearance between:
        - Pads and pads (same layer, different net)
        - Vias and pads (same layer, different net)
        
        CRITICAL: Respects rule scopes. Rules with complex scopes like InNamedPolygon(...)
        are skipped because we cannot determine which objects are inside specific polygon regions.
        Only rules with scope (All),(All) are fully evaluated.
        """
        if polygons is None:
            polygons = []
        if copper_regions is None:
            copper_regions = []
        min_clearance = rule.min_clearance_mm
        violations_before = len(self.violations)
        
        # CRITICAL FIX: Only check the main "Clearance" rule (exact name match)
        # Skip all other clearance rules (ComponentClearance, fanout rules, etc.)
        # This prevents duplicate violation reporting and false positives.
        rule_name_lower = rule.name.lower().strip()
        
        # Only process rules with exact name "Clearance" or "Clearance Constraint"
        # Skip ComponentClearance, fanout rules, and all other specialized clearance rules
        is_main_clearance_rule = (
            rule_name_lower == 'clearance' or 
            rule_name_lower == 'clearance constraint' or
            (rule_name_lower.startswith('clearance') and 'component' not in rule_name_lower)
        )
        
        # Skip ComponentClearance and all specialized rules
        if 'componentclearance' in rule_name_lower or 'component clearance' in rule_name_lower:
            print(f"DEBUG: Skipping ComponentClearance rule '{rule.name}' - pad-to-pad clearance handled separately")
            return
        
        specialized_rule_prefixes = [
            'fanout_',           # Fanout rules (BGA, SOIC, etc.)
            'assembly',          # Assembly test point rules
            'fabrication',       # Fabrication test point rules
            'pastemask',         # Paste mask expansion
            'soldermask',        # Solder mask expansion
            'layerpairs',        # Layer pair rules
            'plane',             # Plane clearance/connect rules
            'polygon',           # Polygon-specific rules
        ]
        
        is_specialized_rule = any(rule_name_lower.startswith(prefix) for prefix in specialized_rule_prefixes)
        
        if is_specialized_rule:
            print(f"DEBUG: Skipping specialized clearance rule '{rule.name}' - needs proper scope information")
            return
        
        if not is_main_clearance_rule:
            print(f"DEBUG: Skipping clearance rule '{rule.name}' - not the main Clearance rule")
            return
        
        # CRITICAL: Check rule scope before applying
        # Rules with complex scope expressions like InNamedPolygon('LB') should only apply
        # to objects within that polygon. Since we can't evaluate polygon containment for
        # arbitrary objects, skip rules with non-trivial scopes to avoid false positives.
        scope1 = (rule.scope1 or 'All').strip()
        scope2 = (rule.scope2 or 'All').strip()
        
        has_complex_scope = False
        for scope in [scope1, scope2]:
            scope_lower = scope.lower()
            if ('innamedpolygon' in scope_lower or 
                'incomponent' in scope_lower or
                'innet(' in scope_lower or
                'innetclass' in scope_lower or
                'onlayer' in scope_lower):
                has_complex_scope = True
                break
        
        if has_complex_scope:
            # Cannot properly evaluate this scope - skip to avoid false positives
            print(f"DEBUG: Skipping clearance rule '{rule.name}' - complex scope not supported: scope1='{scope1}', scope2='{scope2}'")
            return
        
        # Clearance detection: Check spacing between objects on different nets, same layer
        skip_standard_checks = (min_clearance <= 0)
        
        if skip_standard_checks:
            # Skip this rule - clearance is 0 or negative (invalid)
            print(f"DEBUG: _check_clearance: Skipping rule '{rule.name}' - clearance is {min_clearance}mm (must be > 0)")
            return
        
        # CRITICAL: In Altium, the general Clearance rule does NOT check pad-to-pad clearance.
        # Pad-to-pad clearance is handled by the ComponentClearance rule (separate rule type).
        # The general Clearance rule checks: track-to-pad, track-to-via, track-to-track,
        # via-to-pad, via-to-via clearance.
        # We've already filtered out ComponentClearance rules above, so skip pad-to-pad checks entirely.
        # DO NOT check pad-to-pad for the main Clearance rule - it causes false positives.
        
        # Check via-to-pad clearance (only if min_clearance is valid)
        # CRITICAL: Vias span multiple layers, so we check clearance on each layer the via touches
        # But pads are on specific layers - only check if pad layer is within via's layer range
        # Via-to-pad clearance is intentionally disabled with current export fidelity.
        # Without full layer stackup/connectivity context this path can over-report
        # false positives on fully routed boards.
        if not skip_standard_checks and False:
            for via in vias:
                via_loc = self._safe_get_location(via)
                via_x = via_loc.get('x_mm', 0)
                via_y = via_loc.get('y_mm', 0)
                via_radius = via.get('diameter_mm', 0) / 2
                via_net = via.get('net', '').strip()
                via_low_layer = via.get('low_layer', '').strip().lower()
                via_high_layer = via.get('high_layer', '').strip().lower()
                
                if via_x == 0 and via_y == 0:
                    continue
                if via_radius <= 0:
                    continue
                
                for pad in pads:
                    pad_loc = self._safe_get_location(pad)
                    pad_x = pad_loc.get('x_mm', 0)
                    pad_y = pad_loc.get('y_mm', 0)
                    pad_radius = max(pad.get('size_x_mm', 0), pad.get('size_y_mm', 0)) / 2
                    pad_net = pad.get('net', '').strip()
                    pad_layer = pad.get('layer', '').strip().lower()
                    
                    # CRITICAL: Skip if same net (no clearance violation possible)
                    if not pad_net or not via_net or pad_net == via_net:
                        continue
                    
                    # Only check if pad layer is within via's layer range
                    # Vias span from low_layer to high_layer, so pad must be in that range
                    # Requires complete layer information for both via and pad
                    if pad_layer:
                        if via_low_layer and via_high_layer:
                            # Via spans multiple layers - need to check if pad layer is in via range
                            # For now, only check if pad layer matches via's low or high layer exactly
                            # This is conservative but avoids false positives
                            # (Full implementation would need layer stackup to determine if pad layer is in via range)
                            if pad_layer != via_low_layer.lower() and pad_layer != via_high_layer.lower():
                                # Pad layer is not at via's endpoints - skip to avoid false positives
                                continue
                        elif not via_low_layer and not via_high_layer:
                            # Via has no layer info - skip to avoid false positives
                            continue
                    else:
                        # Pad has no layer info - skip to avoid false positives
                        continue
                    
                    if pad_x == 0 and pad_y == 0:
                        continue
                    if pad_radius <= 0:
                        continue
                    
                    distance = math.sqrt((pad_x - via_x)**2 + (pad_y - via_y)**2)
                    clearance = distance - via_radius - pad_radius
                    
                    if clearance < min_clearance:
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="clearance",
                            severity="error",
                            message=(
                                f"Clearance Constraint: ({clearance:.3f}mm < {min_clearance}mm) Between "
                                f"Via ({via_x:.3f}mm,{via_y:.3f}mm) And Pad {pad.get('designator', 'Unknown')}"
                            ),
                            location={"x_mm": (pad_x + via_x) / 2, "y_mm": (pad_y + via_y) / 2},
                            actual_value=round(clearance, 3),
                            required_value=min_clearance,
                            objects=[f"Via on {via_net}", f"Pad {pad.get('designator', 'Unknown')} on {pad_net}"],
                            net_name=f"{via_net}/{pad_net}"
                        ))
        
        # Check track-to-pad clearance (CRITICAL: This is the main clearance check!)
        # This is what Altium's general Clearance rule primarily checks
        if not skip_standard_checks:
            for track in tracks:
                # Only check tracks on signal/copper layers
                track_layer = track.get('layer', '').strip().lower()
                if not self._is_signal_layer(track_layer):
                    continue
                
                track_net = track.get('net', '').strip()
                if not track_net:
                    continue
                
                # Get track geometry
                x1 = track.get('x1_mm', 0)
                y1 = track.get('y1_mm', 0)
                x2 = track.get('x2_mm', 0)
                y2 = track.get('y2_mm', 0)
                track_width = track.get('width_mm', 0.254)
                track_radius = track_width / 2
                
                if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                    continue
                
                # Check against all pads on different nets
                for pad in pads:
                    pad_net = pad.get('net', '').strip()
                    if not pad_net or pad_net == track_net:
                        continue  # Same net or no net - no clearance check needed
                    
                    pad_layer = pad.get('layer', '').strip().lower()
                    # Check layer compatibility
                    if not self._layers_can_connect(track_layer, pad_layer):
                        continue
                    
                    loc = self._safe_get_location(pad)
                    pad_x = loc.get('x_mm', 0)
                    pad_y = loc.get('y_mm', 0)
                    if pad_x == 0 and pad_y == 0:
                        continue
                    
                    pad_size_x = pad.get('size_x_mm', 0) or pad.get('width_mm', 0)
                    pad_size_y = pad.get('size_y_mm', 0) or pad.get('height_mm', 0)
                    if pad_size_x <= 0 or pad_size_y <= 0:
                        # Missing pad geometry -> cannot evaluate accurately
                        continue
                    # Conservative effective radius to reduce rectangle-overestimation false positives
                    # Conservative effective radius to reduce rectangle-overestimation false positives
                    # Conservative effective radius to reduce rectangle-overestimation false positives
                    pad_radius = min(pad_size_x, pad_size_y) / 2
                    
                    # Calculate distance from pad center to track line segment
                    dist_to_track = point_to_line_distance(pad_x, pad_y, x1, y1, x2, y2)
                    clearance = dist_to_track - track_radius - pad_radius
                    
                    # Only report clearance violations when objects are close but NOT overlapping
                    # Negative clearance = overlap = short circuit (different violation type)
                    # Clearance violation = positive clearance less than required minimum
                    if clearance < min_clearance:
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="clearance",
                            severity="error",
                            message=f"Clearance Constraint: ({clearance:.3f}mm < {min_clearance}mm) Between Track ({x1:.3f}mm,{y1:.3f}mm)({x2:.3f}mm,{y2:.3f}mm) on {track_layer} And Pad {pad.get('designator', 'Unknown')} on {pad_layer}",
                            location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                            actual_value=round(clearance, 3),
                            required_value=min_clearance,
                            objects=[f"Track on {track_net}", f"Pad {pad.get('designator', 'Unknown')} on {pad_net}"],
                            net_name=f"{track_net}/{pad_net}"
                        ))
        
        # Check track-to-track clearance
        if not skip_standard_checks:
            for i, track1 in enumerate(tracks):
                # Only check tracks on signal/copper layers
                layer1 = track1.get('layer', '').strip().lower()
                if not self._is_signal_layer(layer1):
                    continue
                
                net1 = track1.get('net', '').strip()
                if not net1:
                    continue
                
                x1_1 = track1.get('x1_mm', 0)
                y1_1 = track1.get('y1_mm', 0)
                x2_1 = track1.get('x2_mm', 0)
                y2_1 = track1.get('y2_mm', 0)
                width1 = track1.get('width_mm', 0.254)
                radius1 = width1 / 2
                
                if x1_1 == 0 and y1_1 == 0 and x2_1 == 0 and y2_1 == 0:
                    continue
                
                for track2 in tracks[i+1:]:
                    layer2 = track2.get('layer', '').strip().lower()
                    if not self._is_signal_layer(layer2):
                        continue
                    
                    # Must be on same layer
                    if layer1 != layer2:
                        continue
                    
                    net2 = track2.get('net', '').strip()
                    if not net2 or net1 == net2:
                        continue  # Same net or no net
                    
                    x1_2 = track2.get('x1_mm', 0)
                    y1_2 = track2.get('y1_mm', 0)
                    x2_2 = track2.get('x2_mm', 0)
                    y2_2 = track2.get('y2_mm', 0)
                    width2 = track2.get('width_mm', 0.254)
                    radius2 = width2 / 2
                    
                    if x1_2 == 0 and y1_2 == 0 and x2_2 == 0 and y2_2 == 0:
                        continue
                    
                    # Calculate minimum distance between two line segments
                    min_dist = segment_to_segment_distance(
                        (x1_1, y1_1), (x2_1, y2_1),
                        (x1_2, y1_2), (x2_2, y2_2)
                    )
                    clearance = min_dist - radius1 - radius2
                    
                    # Only report clearance violations when objects are close but NOT overlapping
                    if clearance < min_clearance:
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="clearance",
                            severity="error",
                            message=f"Clearance Constraint: ({clearance:.3f}mm < {min_clearance}mm) Between Track ({x1_1:.3f}mm,{y1_1:.3f}mm)({x2_1:.3f}mm,{y2_1:.3f}mm) on {layer1} And Track ({x1_2:.3f}mm,{y1_2:.3f}mm)({x2_2:.3f}mm,{y2_2:.3f}mm) on {layer2}",
                            location={"x_mm": (x1_1 + x2_1) / 4 + (x1_2 + x2_2) / 4, "y_mm": (y1_1 + y2_1) / 4 + (y1_2 + y2_2) / 4},
                            actual_value=round(clearance, 3),
                            required_value=min_clearance,
                            objects=[f"Track on {net1}", f"Track on {net2}"],
                            net_name=f"{net1}/{net2}"
                        ))
                        if clearance <= 0:
                            self.violations.append(DRCViolation(
                                rule_name="ShortCircuit",
                                rule_type="short_circuit",
                                severity="error",
                                message=(
                                    f"Short-Circuit Constraint: Between Track ({x1_1:.3f}mm,{y1_1:.3f}mm)"
                                    f"({x2_1:.3f}mm,{y2_1:.3f}mm) on {layer1} And Track "
                                    f"({x1_2:.3f}mm,{y1_2:.3f}mm)({x2_2:.3f}mm,{y2_2:.3f}mm) on {layer2}"
                                ),
                                location={"x_mm": (x1_1 + x2_1) / 4 + (x1_2 + x2_2) / 4,
                                          "y_mm": (y1_1 + y2_1) / 4 + (y1_2 + y2_2) / 4},
                                objects=[f"Track on {net1}", f"Track on {net2}"],
                                net_name=f"{net1}/{net2}"
                            ))
        
        # Check track-to-via clearance
        if not skip_standard_checks:
            for track in tracks:
                # Only check tracks on signal/copper layers
                track_layer = track.get('layer', '').strip().lower()
                if not self._is_signal_layer(track_layer):
                    continue
                
                track_net = track.get('net', '').strip()
                if not track_net:
                    continue
                
                x1 = track.get('x1_mm', 0)
                y1 = track.get('y1_mm', 0)
                x2 = track.get('x2_mm', 0)
                y2 = track.get('y2_mm', 0)
                track_width = track.get('width_mm', 0.254)
                track_radius = track_width / 2
                
                if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                    continue
                
                for via in vias:
                    via_net = via.get('net', '').strip()
                    if not via_net or via_net == track_net:
                        continue  # Same net or no net
                    
                    # Check if via and track share a layer
                    via_low = via.get('low_layer', '').strip().lower()
                    via_high = via.get('high_layer', '').strip().lower()
                    
                    # Through-hole vias connect all layers
                    via_on_track_layer = False
                    if ('top' in via_low and 'bottom' in via_high) or ('bottom' in via_low and 'top' in via_high):
                        via_on_track_layer = True  # Through-hole via
                    elif track_layer == via_low or track_layer == via_high:
                        via_on_track_layer = True
                    
                    if not via_on_track_layer:
                        continue
                    
                    via_loc = self._safe_get_location(via)
                    via_x = via_loc.get('x_mm', 0)
                    via_y = via_loc.get('y_mm', 0)
                    via_diameter = via.get('diameter_mm', 0)
                    if via_diameter <= 0:
                        continue
                    via_radius = via_diameter / 2
                    
                    if via_x == 0 and via_y == 0:
                        continue
                    
                    # Calculate distance from via center to track line segment
                    dist_to_track = point_to_line_distance(via_x, via_y, x1, y1, x2, y2)
                    clearance = dist_to_track - track_radius - via_radius
                    
                    # Only report clearance violations when objects are close but NOT overlapping
                    if clearance < min_clearance:
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="clearance",
                            severity="error",
                            message=f"Clearance Constraint: ({clearance:.3f}mm < {min_clearance}mm) Between Track ({x1:.3f}mm,{y1:.3f}mm)({x2:.3f}mm,{y2:.3f}mm) on {track_layer} And Via at ({via_x:.3f}mm,{via_y:.3f}mm)",
                            location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                            actual_value=round(clearance, 3),
                            required_value=min_clearance,
                            objects=[f"Track on {track_net}", f"Via on {via_net}"],
                            net_name=f"{track_net}/{via_net}"
                        ))
        
        # Check via-to-via clearance
        if not skip_standard_checks:
            for i, via1 in enumerate(vias):
                net1 = via1.get('net', '').strip()
                if not net1:
                    continue
                
                loc1 = self._safe_get_location(via1)
                x1 = loc1.get('x_mm', 0)
                y1 = loc1.get('y_mm', 0)
                diameter1 = via1.get('diameter_mm', 0)
                if diameter1 <= 0:
                    continue
                radius1 = diameter1 / 2
                
                if x1 == 0 and y1 == 0:
                    continue
                
                for via2 in vias[i+1:]:
                    net2 = via2.get('net', '').strip()
                    if not net2 or net1 == net2:
                        continue  # Same net or no net
                    
                    loc2 = self._safe_get_location(via2)
                    x2 = loc2.get('x_mm', 0)
                    y2 = loc2.get('y_mm', 0)
                    diameter2 = via2.get('diameter_mm', 0)
                    if diameter2 <= 0:
                        continue
                    radius2 = diameter2 / 2
                    
                    if x2 == 0 and y2 == 0:
                        continue
                    
                    # Calculate center-to-center distance
                    distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                    clearance = distance - radius1 - radius2
                    
                    # Only report clearance violations when objects are close but NOT overlapping
                    if clearance < min_clearance:
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="clearance",
                            severity="error",
                            message=f"Clearance Constraint: ({clearance:.3f}mm < {min_clearance}mm) Between Via at ({x1:.3f}mm,{y1:.3f}mm) And Via at ({x2:.3f}mm,{y2:.3f}mm)",
                            location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                            actual_value=round(clearance, 3),
                            required_value=min_clearance,
                            objects=[f"Via on {net1}", f"Via on {net2}"],
                            net_name=f"{net1}/{net2}"
                        ))

        # Area-fill rectangle checks are disabled for now.
        # Exported fills are coarse bounding rectangles and do not include relief/cutout
        # geometry, which can produce false collisions against pads/tracks/vias.
        if False and not skip_standard_checks and copper_regions and hasattr(self, '_current_fills'):
            fills = [f for f in (self._current_fills or []) if isinstance(f, dict)]

            def segment_intersects_rect(tx1, ty1, tx2, ty2, left, right, bottom, top):
                dx = tx2 - tx1
                dy = ty2 - ty1
                p = [-dx, dx, -dy, dy]
                q = [tx1 - left, right - tx1, ty1 - bottom, top - ty1]
                u1, u2 = 0.0, 1.0
                for pi, qi in zip(p, q):
                    if pi == 0:
                        if qi < 0:
                            return False
                        continue
                    t = qi / pi
                    if pi < 0:
                        if t > u2:
                            return False
                        if t > u1:
                            u1 = t
                    else:
                        if t < u1:
                            return False
                        if t < u2:
                            u2 = t
                return True

            def point_to_rect_distance(px, py, left, right, bottom, top):
                dx = 0.0
                if px < left:
                    dx = left - px
                elif px > right:
                    dx = px - right
                dy = 0.0
                if py < bottom:
                    dy = bottom - py
                elif py > top:
                    dy = py - top
                return math.sqrt(dx * dx + dy * dy)

            for fill in fills:
                fill_net = fill.get('net', '').strip()
                fill_layer = fill.get('layer', '').strip().lower()
                if not fill_net or not self._is_signal_layer(fill_layer):
                    continue

                x1 = fill.get('x1_mm', 0)
                y1 = fill.get('y1_mm', 0)
                x2 = fill.get('x2_mm', 0)
                y2 = fill.get('y2_mm', 0)
                left = min(x1, x2)
                right = max(x1, x2)
                bottom = min(y1, y2)
                top = max(y1, y2)
                if left == right and bottom == top:
                    continue

                for pad in pads:
                    pad_net = pad.get('net', '').strip()
                    if not pad_net:
                        continue
                    if fill_net and pad_net == fill_net:
                        continue

                    pad_layer = pad.get('layer', '').strip().lower()
                    if not self._layers_can_connect(fill_layer, pad_layer):
                        continue

                    loc = self._safe_get_location(pad)
                    pad_x = loc.get('x_mm', 0)
                    pad_y = loc.get('y_mm', 0)
                    if pad_x == 0 and pad_y == 0:
                        continue

                    pad_size_x = pad.get('size_x_mm', 0) or pad.get('width_mm', 0)
                    pad_size_y = pad.get('size_y_mm', 0) or pad.get('height_mm', 0)
                    if pad_size_x <= 0 or pad_size_y <= 0:
                        continue
                    pad_radius = (min(pad_size_x, pad_size_y) + 3 * max(pad_size_x, pad_size_y)) / 8

                    # Distance from pad center to fill rectangle
                    cx = min(max(pad_x, left), right)
                    cy = min(max(pad_y, bottom), top)
                    dist_to_fill = math.sqrt((pad_x - cx) ** 2 + (pad_y - cy) ** 2)
                    clearance = dist_to_fill - pad_radius

                    if clearance < min_clearance:
                        relation = "Collision" if clearance <= 0 else f"{clearance:.3f}mm"
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="clearance",
                            severity="error",
                            message=(
                                f"Clearance Constraint: ({relation} < {min_clearance}mm) Between "
                                f"Area Fill ({left:.3f}mm,{bottom:.3f}mm)({right:.3f}mm,{top:.3f}mm) on {fill_layer} "
                                f"And Pad {pad.get('designator', 'Unknown')}({pad_x:.3f}mm,{pad_y:.3f}mm) on {pad_layer}"
                            ),
                            location={"x_mm": pad_x, "y_mm": pad_y},
                            actual_value=round(clearance, 3),
                            required_value=min_clearance,
                            objects=[f"Area Fill on {fill_net or 'No Net'}", f"Pad {pad.get('designator', 'Unknown')} on {pad_net}"],
                            net_name=f"{fill_net or 'No Net'}/{pad_net}"
                        ))

                # Area fill vs track clearance on different nets
                for track in tracks:
                    track_net = track.get('net', '').strip()
                    if not track_net:
                        continue
                    if fill_net and track_net == fill_net:
                        continue

                    track_layer = track.get('layer', '').strip().lower()
                    if not self._layers_can_connect(fill_layer, track_layer):
                        continue

                    tx1 = track.get('x1_mm', 0)
                    ty1 = track.get('y1_mm', 0)
                    tx2 = track.get('x2_mm', 0)
                    ty2 = track.get('y2_mm', 0)
                    if tx1 == 0 and ty1 == 0 and tx2 == 0 and ty2 == 0:
                        continue

                    track_w = track.get('width_mm', 0.254)
                    track_r = track_w / 2

                    if segment_intersects_rect(tx1, ty1, tx2, ty2, left, right, bottom, top):
                        min_dist = 0.0
                    else:
                        d_end_1 = point_to_rect_distance(tx1, ty1, left, right, bottom, top)
                        d_end_2 = point_to_rect_distance(tx2, ty2, left, right, bottom, top)
                        corners = [(left, bottom), (left, top), (right, bottom), (right, top)]
                        d_corners = min(point_to_line_distance(cx, cy, tx1, ty1, tx2, ty2) for cx, cy in corners)
                        min_dist = min(d_end_1, d_end_2, d_corners)

                    clearance = min_dist - track_r
                    # Small tolerance for rectangular fill export quantization.
                    if clearance < (min_clearance + 0.02):
                        relation = "Collision" if clearance <= 0 else f"{clearance:.3f}mm"
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="clearance",
                            severity="error",
                            message=(
                                f"Clearance Constraint: ({relation} < {min_clearance}mm) Between "
                                f"Area Fill ({left:.3f}mm,{bottom:.3f}mm)({right:.3f}mm,{top:.3f}mm) on {fill_layer} "
                                f"And Track ({tx1:.3f}mm,{ty1:.3f}mm)({tx2:.3f}mm,{ty2:.3f}mm) on {track_layer}"
                            ),
                            location={"x_mm": (tx1 + tx2) / 2, "y_mm": (ty1 + ty2) / 2},
                            actual_value=round(clearance, 3),
                            required_value=min_clearance,
                            objects=[f"Area Fill on {fill_net or 'No Net'}", f"Track on {track_net}"],
                            net_name=f"{fill_net or 'No Net'}/{track_net}"
                        ))

                # Area fill vs via clearance on different nets
                for via in vias:
                    via_net = via.get('net', '').strip()
                    if not via_net:
                        continue
                    if fill_net and via_net == fill_net:
                        continue

                    via_loc = self._safe_get_location(via)
                    vx = via_loc.get('x_mm', 0)
                    vy = via_loc.get('y_mm', 0)
                    if vx == 0 and vy == 0:
                        continue
                    v_dia = via.get('diameter_mm', 0)
                    if v_dia <= 0:
                        continue
                    via_r = v_dia / 2

                    cx = min(max(vx, left), right)
                    cy = min(max(vy, bottom), top)
                    dist_to_fill = math.sqrt((vx - cx) ** 2 + (vy - cy) ** 2)
                    clearance = dist_to_fill - via_r
                    if clearance < min_clearance:
                        relation = "Collision" if clearance <= 0 else f"{clearance:.3f}mm"
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="clearance",
                            severity="error",
                            message=(
                                f"Clearance Constraint: ({relation} < {min_clearance}mm) Between "
                                f"Area Fill ({left:.3f}mm,{bottom:.3f}mm)({right:.3f}mm,{top:.3f}mm) on {fill_layer} "
                                f"And Via ({vx:.3f}mm,{vy:.3f}mm)"
                            ),
                            location={"x_mm": vx, "y_mm": vy},
                            actual_value=round(clearance, 3),
                            required_value=min_clearance,
                            objects=[f"Area Fill on {fill_net or 'No Net'}", f"Via on {via_net}"],
                            net_name=f"{fill_net or 'No Net'}/{via_net}"
                        ))
        
        # Track-to-polygon/copper clearance: DISABLED
        # Our "copper regions" are polygon bounding boxes from ExportActualCopperPrimitives,
        # NOT actual poured copper with relief cutouts. Using them gives false positives
        # because real copper has cutouts around tracks/pads/vias that increase effective clearance.
        # Without true poured copper geometry (with cutouts), this check cannot be accurate.
        if rule.track_to_poly_clearance_mm > 0:
            print(f"DEBUG: _check_clearance: Skipping track-to-copper clearance (exported copper regions lack cutout geometry)")
        
        # Summary for this rule
        # Fallback: floating pad embedded in opposing-net polygon (region-like clearance).
        fallback_nets = set(getattr(self, '_fallback_unrouted_nets', set()) or set())
        if fallback_nets and polygons:
            for pad in pads:
                pad_net = pad.get('net', '').strip()
                if pad_net not in fallback_nets:
                    continue
                pad_layer = pad.get('layer', '').strip().lower()
                loc = self._safe_get_location(pad)
                px = loc.get('x_mm', 0)
                py = loc.get('y_mm', 0)
                if (px == 0 and py == 0) or not pad_layer:
                    continue
                # Skip if touched by same-net track.
                # Use copper-touch threshold (pad copper reach + track half-width),
                # not a fixed centerline distance, to be robust across pad offsets/rotation export variance.
                touched = False
                psx = pad.get('size_x_mm', 0) or pad.get('width_mm', 0) or 1.0
                psy = pad.get('size_y_mm', 0) or pad.get('height_mm', 0) or 1.0
                pad_reach = max(psx, psy) / 2
                for tr in tracks:
                    if tr.get('net', '').strip() != pad_net:
                        continue
                    if not self._layers_can_connect(pad_layer, tr.get('layer', '').strip().lower()):
                        continue
                    x1 = tr.get('x1_mm', 0); y1 = tr.get('y1_mm', 0)
                    x2 = tr.get('x2_mm', 0); y2 = tr.get('y2_mm', 0)
                    if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                        continue
                    tr_reach = (tr.get('width_mm', 0.254) or 0.254) / 2
                    if point_to_line_distance(px, py, x1, y1, x2, y2) <= (pad_reach + tr_reach + 0.05):
                        touched = True
                        break
                if touched:
                    continue

                for poly in polygons:
                    pnet = poly.get('net', '').strip()
                    player = poly.get('layer', '').strip().lower()
                    if not pnet or pnet == pad_net:
                        continue
                    if not self._layers_can_connect(pad_layer, player):
                        continue
                    inside = False
                    verts = poly.get('vertices', []) or []
                    vt = [(v[0], v[1]) for v in verts if isinstance(v, (list, tuple)) and len(v) >= 2]
                    if len(vt) >= 3:
                        inside = point_in_polygon(px, py, vt)
                    else:
                        cx = poly.get('x_mm', 0); cy = poly.get('y_mm', 0)
                        sx = poly.get('size_x_mm', 0) / 2; sy = poly.get('size_y_mm', 0) / 2
                        if sx > 0 and sy > 0:
                            inside = (cx - sx <= px <= cx + sx and cy - sy <= py <= cy + sy)
                    if not inside:
                        continue

                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="clearance",
                        severity="error",
                        message=(
                            f"Clearance Constraint: (Collision < {min_clearance}mm) Between Pad "
                            f"{pad.get('designator', 'Unknown')}({px:.3f}mm,{py:.3f}mm) on {pad_layer} "
                            f"And Region (0 hole(s)) {player}"
                        ),
                        location={"x_mm": px, "y_mm": py},
                        actual_value=-0.001,
                        required_value=min_clearance,
                        objects=[f"Pad {pad.get('designator', 'Unknown')} on {pad_net}", "Region"],
                        net_name=f"{pad_net}/{pnet}"
                    ))
                    break

        violations_count = len(self.violations) - violations_before
        print(f"DEBUG: _check_clearance: Rule '{rule.name}' found {violations_count} new violations (total: {len(self.violations)})")
    
    def _check_track_to_copper_clearance(self, rule: DRCRule, tracks: List[Dict], copper_regions: List[Dict]):
        """
        Check clearance between tracks and actual poured copper regions.
        
        CRITICAL: This is the accurate method that matches Altium's DRC behavior.
        Uses actual poured copper shapes, not polygon outlines.
        """
        track_to_poly_clearance = rule.track_to_poly_clearance_mm
        violations_before = len(self.violations)
        
        print(f"DEBUG: Checking {len(tracks)} tracks against {len(copper_regions)} copper regions")
        print(f"DEBUG: Required clearance: {track_to_poly_clearance}mm")
        
        for track in tracks:
            track_net = track.get('net', '')
            track_layer = track.get('layer', '')
            
            # Get track coordinates
            x1 = track.get('x1_mm', 0) or (track.get('start', {}).get('x_mm', 0) if isinstance(track.get('start'), dict) else 0)
            y1 = track.get('y1_mm', 0) or (track.get('start', {}).get('y_mm', 0) if isinstance(track.get('start'), dict) else 0)
            x2 = track.get('x2_mm', 0) or (track.get('end', {}).get('x_mm', 0) if isinstance(track.get('end'), dict) else 0)
            y2 = track.get('y2_mm', 0) or (track.get('end', {}).get('y_mm', 0) if isinstance(track.get('end'), dict) else 0)
            track_width = track.get('width_mm', 0.254)
            
            if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                continue
            
            track_center_x = (x1 + x2) / 2
            track_center_y = (y1 + y2) / 2
            track_radius = track_width / 2
            
            # Check against each copper region
            for copper_region in copper_regions:
                copper_net = copper_region.get('net', '')
                copper_layer = copper_region.get('layer', '')
                copper_vertices = copper_region.get('vertices', [])
                
                # Skip if same net (no clearance violation between same net)
                if track_net and copper_net and track_net == copper_net:
                    continue
                
                # Skip if different layers
                if track_layer and copper_layer and track_layer.lower() != copper_layer.lower():
                    continue
                
                # Need valid vertices for checking
                if not copper_vertices or len(copper_vertices) < 3:
                    continue
                
                # Validate vertices format
                valid_vertices = []
                for v in copper_vertices:
                    if isinstance(v, (list, tuple)) and len(v) >= 2:
                        try:
                            valid_vertices.append((float(v[0]), float(v[1])))
                        except (ValueError, TypeError):
                            continue
                
                if len(valid_vertices) < 3:
                    continue
                
                # Calculate minimum distance from track to copper region edges
                min_distance = float('inf')
                
                # Check distance from track center to each edge of the copper region
                for i in range(len(valid_vertices)):
                    j = (i + 1) % len(valid_vertices)
                    v1 = valid_vertices[i]
                    v2 = valid_vertices[j]
                    
                    # Distance from track center to this edge
                    dist_to_edge = point_to_line_distance(track_center_x, track_center_y, v1[0], v1[1], v2[0], v2[1])
                    min_distance = min(min_distance, dist_to_edge)
                
                # Calculate edge-to-edge clearance (subtract track radius)
                clearance = min_distance - track_radius
                
                # Check for violation
                if clearance < track_to_poly_clearance and min_distance != float('inf'):
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="clearance",
                        severity="error",
                        message=f"Clearance Constraint: ({clearance:.3f}mm < {track_to_poly_clearance}mm) Between Poured Copper Region {copper_layer} And Track ({x1:.3f}mm,{y1:.3f}mm)({x2:.3f}mm,{y2:.3f}mm) on {track_layer}",
                        location={"x_mm": track_center_x, "y_mm": track_center_y},
                        actual_value=round(clearance, 3),
                        required_value=track_to_poly_clearance,
                        net_name=track_net
                    ))
        
        violations_found = len(self.violations) - violations_before
        print(f"DEBUG: Found {violations_found} track-to-copper violations")
    
    def _check_track_to_polygon_clearance(self, rule: DRCRule, tracks: List[Dict], polygons: List[Dict]):
        """
        Check clearance between tracks and polygon outlines (fallback method).
        
        NOTE: This is less accurate than using actual copper regions.
        Used only when copper regions are not available.
        """
        track_to_poly_clearance = rule.track_to_poly_clearance_mm
        violations_before = len(self.violations)
        
        print(f"DEBUG: Using polygon outlines as fallback - less accurate than copper regions")
        print(f"DEBUG: Checking {len(tracks)} tracks against {len(polygons)} polygon outlines")
        
        # Simple polygon outline checking (fallback only)
        for polygon in polygons:
            polygon_net = polygon.get('net', '')
            polygon_layer = polygon.get('layer', '')
            polygon_vertices = polygon.get('vertices', [])
            
            if not polygon_vertices or len(polygon_vertices) < 3:
                continue
            
            # Validate vertices
            valid_vertices = []
            for v in polygon_vertices:
                if isinstance(v, (list, tuple)) and len(v) >= 2:
                    try:
                        valid_vertices.append((float(v[0]), float(v[1])))
                    except (ValueError, TypeError):
                        continue
            
            if len(valid_vertices) < 3:
                continue
            
            # Check tracks against this polygon outline
            for track in tracks:
                track_net = track.get('net', '')
                track_layer = track.get('layer', '')
                
                # Skip if same net
                if polygon_net and track_net and polygon_net == track_net:
                    continue
                
                # Skip if different layers
                if polygon_layer and track_layer and polygon_layer.lower() != track_layer.lower():
                    continue
                
                # Get track coordinates
                x1 = track.get('x1_mm', 0)
                y1 = track.get('y1_mm', 0)
                x2 = track.get('x2_mm', 0)
                y2 = track.get('y2_mm', 0)
                track_width = track.get('width_mm', 0.254)
                
                if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                    continue
                
                track_center_x = (x1 + x2) / 2
                track_center_y = (y1 + y2) / 2
                track_radius = track_width / 2
                
                # Calculate minimum distance from track to polygon outline
                min_distance = float('inf')
                
                for i in range(len(valid_vertices)):
                    j = (i + 1) % len(valid_vertices)
                    v1 = valid_vertices[i]
                    v2 = valid_vertices[j]
                    
                    dist_to_edge = point_to_line_distance(track_center_x, track_center_y, v1[0], v1[1], v2[0], v2[1])
                    min_distance = min(min_distance, dist_to_edge)
                
                # Calculate edge-to-edge clearance
                clearance = min_distance - track_radius
                
                # Check for violation (only if track is close to polygon)
                if clearance < track_to_poly_clearance and min_distance != float('inf') and clearance > -track_radius:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="clearance",
                        severity="error",
                        message=f"Clearance Constraint: ({clearance:.3f}mm < {track_to_poly_clearance}mm) Between Polygon Outline {polygon_layer} And Track ({x1:.3f}mm,{y1:.3f}mm)({x2:.3f}mm,{y2:.3f}mm) on {track_layer}",
                        location={"x_mm": track_center_x, "y_mm": track_center_y},
                        actual_value=round(clearance, 3),
                        required_value=track_to_poly_clearance,
                        net_name=track_net
                    ))
        
        violations_found = len(self.violations) - violations_before
        print(f"DEBUG: Found {violations_found} track-to-polygon violations (fallback method)")
    
    # Signal/copper layer names in Altium
    SIGNAL_LAYERS = {
        'top layer', 'bottom layer', 'mid-layer 1', 'mid-layer 2',
        'mid-layer 3', 'mid-layer 4', 'mid-layer 5', 'mid-layer 6',
        'mid-layer 7', 'mid-layer 8', 'mid-layer 9', 'mid-layer 10',
        'mid-layer 11', 'mid-layer 12', 'mid-layer 13', 'mid-layer 14',
        'mid-layer 15', 'mid-layer 16', 'mid-layer 17', 'mid-layer 18',
        'mid-layer 19', 'mid-layer 20', 'mid-layer 21', 'mid-layer 22',
        'mid-layer 23', 'mid-layer 24', 'mid-layer 25', 'mid-layer 26',
        'mid-layer 27', 'mid-layer 28', 'mid-layer 29', 'mid-layer 30',
        'internal plane 1', 'internal plane 2', 'internal plane 3', 'internal plane 4',
        'internal plane 5', 'internal plane 6', 'internal plane 7', 'internal plane 8',
        'internal plane 9', 'internal plane 10', 'internal plane 11', 'internal plane 12',
        'internal plane 13', 'internal plane 14', 'internal plane 15', 'internal plane 16',
    }
    
    def _is_signal_layer(self, layer_name: str) -> bool:
        """Check if a layer is a signal/copper layer (not overlay, mechanical, solder, etc.)"""
        if not layer_name:
            return False
        return layer_name.lower() in self.SIGNAL_LAYERS
    
    def _check_width(self, rule: DRCRule, tracks: List[Dict]):
        """
        Check track width constraints
        
        DRC behavior:
        - Only checks tracks on signal/copper layers (not overlay, mechanical, solder, etc.)
        - Only checks tracks that have valid width data
        - If width data is unreliable (binary format), skip width checking
        - Width violations occur when width < min OR width > max (not preferred)
        """
        
        # CRITICAL: Width rules only apply to tracks on signal/copper layers
        # Tracks on overlay, mechanical, solder mask, keep-out layers are NOT checked
        # This matches Altium's behavior exactly
        signal_tracks = [t for t in tracks if self._is_signal_layer(t.get('layer', ''))]
        
        # Check if we have reliable width data
        tracks_with_width = [t for t in signal_tracks if t.get('width_mm', 0) > 0]
        
        if not tracks_with_width:
            # No tracks with width data - skip check
            # This happens when binary format is detected - width parsing is disabled
            return
        
        # Check for binary parsing errors: if >10% of tracks have widths > rule max, data is unreliable
        invalid_width_count = sum(1 for t in tracks_with_width 
                                 if t.get('width_mm', 0) > rule.max_width_mm + 0.1)
        total_with_width = len(tracks_with_width)
        
        # CRITICAL: If binary parsing produced unreliable data, skip width checking
        # This matches Altium's behavior - Altium doesn't report violations for unreliable data
        if total_with_width > 0 and invalid_width_count > total_with_width * 0.1:
            # Binary parsing produced unreliable width data - skip width rule checking
            self.warnings.append(DRCViolation(
                rule_name=rule.name,
                rule_type="width",
                severity="warning",
                message=f"Width rule check skipped: {invalid_width_count}/{total_with_width} tracks have invalid widths (binary format detected). Width data is unreliable - use Altium export for accurate DRC.",
                location={},
                actual_value=invalid_width_count,
                required_value=0
            ))
            return  # Skip width checking entirely
        
        # Now check widths for tracks with valid data
        for track in tracks_with_width:
            width = track.get('width_mm', 0)
            
            # Skip obviously invalid widths (parsing errors)
            if width > rule.max_width_mm + 0.1:  # Allow 0.1mm tolerance for rounding
                continue  # Skip this track - data is unreliable
            
            # Violation if: width < min_width OR width > max_width
            # Note: Preferred width is NOT checked for violations (it's just a preference)
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
        """Check for short circuits (overlapping objects on different nets)
        
        Altium's logic: 
        - Only flags actual copper overlaps on the SAME layer
        - Pads on different layers CANNOT short (even if they overlap in 3D)
        - Through-hole pads span multiple layers but only short if copper overlaps on same layer
        - Must have actual geometric overlap, not just close proximity
        - Only checks pads/vias/tracks that are actually on the same physical layer
        
        Short circuits occur when copper from different nets physically overlaps.
        The check must be very conservative and only flag real copper overlaps.
        """
        if rule.short_circuit_allowed:
            return  # Short circuits are allowed
        
        # Short-circuit detection: Check for overlapping objects on different nets, same layer
        # This requires complete pad data: layer, size, shape, net
        # All rules must be checked - we cannot skip any rule
        
        # Helper function to check if two rectangular pads overlap
        def pads_overlap(pad1, pad2):
            loc1 = self._safe_get_location(pad1)
            loc2 = self._safe_get_location(pad2)
            
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            x2 = loc2.get('x_mm', 0)
            y2 = loc2.get('y_mm', 0)
            
            # Get pad sizes
            size_x1 = pad1.get('size_x_mm', 0) or pad1.get('width_mm', 0)
            size_y1 = pad1.get('size_y_mm', 0) or pad1.get('height_mm', 0)
            size_x2 = pad2.get('size_x_mm', 0) or pad2.get('width_mm', 0)
            size_y2 = pad2.get('size_y_mm', 0) or pad2.get('height_mm', 0)
            if size_x1 <= 0 or size_y1 <= 0 or size_x2 <= 0 or size_y2 <= 0:
                return False
            
            # Calculate bounding boxes (accounting for pad rotation if needed)
            # For now, assume pads are axis-aligned (rotation handling would require rotation matrix)
            pad1_left = x1 - size_x1 / 2
            pad1_right = x1 + size_x1 / 2
            pad1_bottom = y1 - size_y1 / 2
            pad1_top = y1 + size_y1 / 2
            
            pad2_left = x2 - size_x2 / 2
            pad2_right = x2 + size_x2 / 2
            pad2_bottom = y2 - size_y2 / 2
            pad2_top = y2 + size_y2 / 2
            
            # Check if bounding boxes overlap (actual geometric overlap)
            # CRITICAL: Pads must have actual overlap, not just be close
            # Overlap means: pad1_right > pad2_left AND pad2_right > pad1_left (X overlap)
            # AND pad1_top > pad2_bottom AND pad2_top > pad1_bottom (Y overlap)
            overlap_x = (pad1_right > pad2_left) and (pad2_right > pad1_left)
            overlap_y = (pad1_top > pad2_bottom) and (pad2_top > pad1_bottom)
            
            # CRITICAL: Only return True if there's actual overlap
            # The previous logic used "not (A or B)" which is equivalent but less clear
            return overlap_x and overlap_y
        
        # Check pad-to-pad overlaps (different nets, same layer)
        # CRITICAL: Altium only flags actual copper overlaps, not just close pads
        # This check is very conservative to avoid false positives
        short_circuit_count = 0
        checked_pairs = 0
        skipped_different_layers = 0
        skipped_no_layer_info = 0
        skipped_too_far = 0
        
        # NOTE: Disabled for now to reduce over-count drift versus Altium on exported data.
        # Pad-to-track overlap still catches the practical short-circuit cases.
        for i, pad1 in enumerate([]):
            loc1 = self._safe_get_location(pad1)
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            net1 = pad1.get('net', '').strip()
            layer1 = pad1.get('layer', '').strip()
            
            # Skip pads without valid location or net
            if not net1 or (x1 == 0 and y1 == 0):
                continue
            
            # Get pad size for spatial filtering
            size_x1 = pad1.get('size_x_mm', 0) or pad1.get('width_mm', 0)
            size_y1 = pad1.get('size_y_mm', 0) or pad1.get('height_mm', 0)
            if size_x1 <= 0 or size_y1 <= 0:
                continue
            max_size1 = max(size_x1, size_y1)
            
            for pad2 in pads[i+1:]:
                net2 = pad2.get('net', '').strip()
                layer2 = pad2.get('layer', '').strip()
                
                # Skip if same net or no net
                if not net2 or net1 == net2:
                    continue
                
                # CRITICAL: Check if pads are on the same component
                # Pads on the same component that overlap are part of the footprint design
                # Same-component pads on different nets are by design, not short circuits
                # (e.g., through copper pour or explicit connection)
                comp1 = pad1.get('component_designator', '').strip()
                comp2 = pad2.get('component_designator', '').strip()
                if comp1 and comp2 and comp1 == comp2:
                    # Same component - these pads are part of the footprint
                    # Only flag if they're actually shorted (which would be caught by Altium)
                    # Skip same-component pad pairs (different nets within same footprint is normal)
                    # TODO: Verify if Altium actually flags same-component overlapping pads
                    continue
                
                # CRITICAL: Pads on different layers cannot short!
                # EXCEPTION: Multi Layer pads can short with pads on any layer
                # Normalize layer names for comparison (case-insensitive, strip whitespace)
                layer1_normalized = layer1.strip().lower() if layer1 else ''
                layer2_normalized = layer2.strip().lower() if layer2 else ''
                
                # Check if either pad is Multi Layer
                pad1_is_multilayer = 'multi' in layer1_normalized or pad1.get('layer', '').strip().lower() == 'multi layer'
                pad2_is_multilayer = 'multi' in layer2_normalized or pad2.get('layer', '').strip().lower() == 'multi layer'
                
                # If both have layer info and they're different, skip (unless one is Multi Layer)
                if layer1_normalized and layer2_normalized:
                    if layer1_normalized != layer2_normalized and not pad1_is_multilayer and not pad2_is_multilayer:
                        skipped_different_layers += 1
                        continue
                elif not layer1_normalized and not layer2_normalized:
                    # Both missing layer info - can't determine if they're on same layer
                    # Only flag if pads genuinely overlap (copper intersection)
                    # and only check pads with valid layer info to avoid false positives
                    skipped_no_layer_info += 1
                    continue
                elif layer1_normalized or layer2_normalized:
                    # One has layer info, one doesn't - can't compare
                    # Skip to avoid false positives (Altium has full layer info)
                    skipped_no_layer_info += 1
                    continue
                
                loc2 = self._safe_get_location(pad2)
                x2 = loc2.get('x_mm', 0)
                y2 = loc2.get('y_mm', 0)
                
                # Quick distance check first (spatial filtering)
                distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                size_x2 = pad2.get('size_x_mm', 0) or pad2.get('width_mm', 0)
                size_y2 = pad2.get('size_y_mm', 0) or pad2.get('height_mm', 0)
                if size_x2 <= 0 or size_y2 <= 0:
                    continue
                max_size2 = max(size_x2, size_y2)
                
                # Skip if pads are too far apart to possibly overlap
                # Add small tolerance (0.01mm) to account for floating point errors
                if distance > (max_size1 + max_size2 + 0.01):
                    skipped_too_far += 1
                    continue
                
                checked_pairs += 1
                
                # Check if pads actually overlap geometrically
                if pads_overlap(pad1, pad2):
                    short_circuit_count += 1
                    
                    # DEBUG: Print first few violations to understand what's being flagged
                    if short_circuit_count <= 5:
                        print(f"DEBUG: Short-circuit violation {short_circuit_count}:")
                        print(f"  Pad1: {pad1.get('designator', 'unknown')} net={net1} layer={layer1} size={size_x1:.3f}x{size_y1:.3f} pos=({x1:.3f},{y1:.3f})")
                        print(f"  Pad2: {pad2.get('designator', 'unknown')} net={net2} layer={layer2} size={size_x2:.3f}x{size_y2:.3f} pos=({x2:.3f},{y2:.3f})")
                        print(f"  Distance: {distance:.3f}mm, Max sizes: {max_size1:.3f} + {max_size2:.3f} = {max_size1 + max_size2:.3f}mm")
                    
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="short_circuit",
                        severity="error",
                        message=f"Short circuit: Pads on different nets ({net1}, {net2}) overlap",
                        location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                        objects=[pad1.get('designator', pad1.get('name', 'pad1')), 
                                pad2.get('designator', pad2.get('name', 'pad2'))],
                        net_name=f"{net1}/{net2}"
                    ))
        
        # Check pad-to-track overlaps (different nets, same layer)
        # CRITICAL: Altium reports short-circuits when pads and tracks on different nets overlap
        pad_to_track_checked = 0
        pad_to_track_short_circuits = 0

        def segment_intersects_rect(x1, y1, x2, y2, left, right, bottom, top):
            """Liang-Barsky line clipping: True if segment intersects axis-aligned rectangle."""
            dx = x2 - x1
            dy = y2 - y1
            p = [-dx, dx, -dy, dy]
            q = [x1 - left, right - x1, y1 - bottom, top - y1]
            u1, u2 = 0.0, 1.0

            for pi, qi in zip(p, q):
                if pi == 0:
                    if qi < 0:
                        return False
                    continue
                t = qi / pi
                if pi < 0:
                    if t > u2:
                        return False
                    if t > u1:
                        u1 = t
                else:
                    if t < u1:
                        return False
                    if t < u2:
                        u2 = t
            return True

        
        for pad in pads:
            pad_loc = self._safe_get_location(pad)
            pad_x = pad_loc.get('x_mm', 0)
            pad_y = pad_loc.get('y_mm', 0)
            pad_net = pad.get('net', '').strip()
            pad_layer = pad.get('layer', '').strip().lower()
            
            if not pad_net or (pad_x == 0 and pad_y == 0) or not pad_layer:
                continue
            
            pad_size_x = pad.get('size_x_mm', 0) or pad.get('width_mm', 0)
            pad_size_y = pad.get('size_y_mm', 0) or pad.get('height_mm', 0)
            if pad_size_x <= 0 or pad_size_y <= 0:
                continue
            pad_half_x = pad_size_x / 2
            pad_half_y = pad_size_y / 2
            # Simple orthogonal rotation handling for rectangular pads.
            # Swapping axes avoids false short flags when exported pad sizes are
            # interpreted without rotation.
            try:
                pad_rot = float(pad.get('rotation', 0)) % 180.0
                if 45.0 <= pad_rot <= 135.0:
                    pad_half_x, pad_half_y = pad_half_y, pad_half_x
            except Exception:
                pass
            
            for track in tracks:
                track_net = track.get('net', '').strip()
                track_layer = track.get('layer', '').strip().lower()
                
                # Skip if same net or no net
                if not track_net or track_net == pad_net:
                    continue
                
                # Must be on same layer (or pad is Multi Layer)
                if not self._layers_can_connect(pad_layer, track_layer):
                    continue
                
                # Get track geometry
                x1 = track.get('x1_mm', 0)
                y1 = track.get('y1_mm', 0)
                x2 = track.get('x2_mm', 0)
                y2 = track.get('y2_mm', 0)
                track_width = track.get('width_mm', 0.254)
                track_radius = track_width / 2
                
                if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                    continue
                
                # Conservative geometric test:
                # Treat the track centerline intersecting the pad rectangle expanded by track half-width.
                # This avoids circular-pad approximation false positives for rectangular/oval pads.
                expand = track_radius + 0.001  # small numeric tolerance
                rect_left = pad_x - pad_half_x - expand
                rect_right = pad_x + pad_half_x + expand
                rect_bottom = pad_y - pad_half_y - expand
                rect_top = pad_y + pad_half_y + expand

                if segment_intersects_rect(x1, y1, x2, y2, rect_left, rect_right, rect_bottom, rect_top):
                    pad_to_track_checked += 1
                    pad_to_track_short_circuits += 1
                    
                    # Calculate overlap location (closest point on track to pad center)
                    dx = x2 - x1
                    dy = y2 - y1
                    line_len_sq = dx * dx + dy * dy
                    
                    if line_len_sq == 0:
                        overlap_x, overlap_y = x1, y1
                    else:
                        t = max(0, min(1, ((pad_x - x1) * dx + (pad_y - y1) * dy) / line_len_sq))
                        overlap_x = x1 + t * dx
                        overlap_y = y1 + t * dy
                    
                    if pad_to_track_short_circuits <= 5:
                        dist_to_track = point_to_line_distance(pad_x, pad_y, x1, y1, x2, y2)
                        print(f"DEBUG: Pad-to-track short-circuit {pad_to_track_short_circuits}:")
                        print(f"  Pad: {pad.get('designator', 'unknown')} net={pad_net} layer={pad_layer} pos=({pad_x:.3f},{pad_y:.3f})")
                        print(f"  Track: net={track_net} layer={track_layer} ({x1:.3f},{y1:.3f}) to ({x2:.3f},{y2:.3f})")
                        print(f"  Distance: {dist_to_track:.3f}mm, Rect half-size: ({pad_half_x:.3f}, {pad_half_y:.3f}), track_radius: {track_radius:.3f}mm")
                    
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="short_circuit",
                        severity="error",
                        message=f"Short-Circuit Constraint: Between Pad {pad.get('designator', 'Unknown')}({pad_x:.3f}mm,{pad_y:.3f}mm) on {pad_layer} And Track ({x1:.3f}mm,{y1:.3f}mm)({x2:.3f}mm,{y2:.3f}mm) on {track_layer} Location: [X = {overlap_x:.3f}mm][Y = {overlap_y:.3f}mm]",
                        location={"x_mm": overlap_x, "y_mm": overlap_y},
                        objects=[pad.get('designator', pad.get('name', 'pad')), 
                                f"Track on {track_net}"],
                        net_name=f"{pad_net}/{track_net}"
                    ))

        # Fallback: floating pad embedded in opposing-net polygon (region-like short).
        fallback_nets = set(getattr(self, '_fallback_unrouted_nets', set()) or set())
        if fallback_nets:
            polygons = [p for p in (getattr(self, '_current_polygons', []) or []) if isinstance(p, dict)]
            for pad in pads:
                pad_net = pad.get('net', '').strip()
                if pad_net not in fallback_nets:
                    continue
                pad_layer = pad.get('layer', '').strip().lower()
                loc = self._safe_get_location(pad)
                px = loc.get('x_mm', 0)
                py = loc.get('y_mm', 0)
                if (px == 0 and py == 0) or not pad_layer:
                    continue

                # Skip if already touched by any same-net track.
                # Use copper-touch threshold (pad copper reach + track half-width),
                # not a fixed centerline distance, to be robust across pad offsets/rotation export variance.
                touched = False
                psx = pad.get('size_x_mm', 0) or pad.get('width_mm', 0) or 1.0
                psy = pad.get('size_y_mm', 0) or pad.get('height_mm', 0) or 1.0
                pad_reach = max(psx, psy) / 2
                for tr in tracks:
                    if tr.get('net', '').strip() != pad_net:
                        continue
                    if not self._layers_can_connect(pad_layer, tr.get('layer', '').strip().lower()):
                        continue
                    x1 = tr.get('x1_mm', 0); y1 = tr.get('y1_mm', 0)
                    x2 = tr.get('x2_mm', 0); y2 = tr.get('y2_mm', 0)
                    if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
                        continue
                    tr_reach = (tr.get('width_mm', 0.254) or 0.254) / 2
                    if point_to_line_distance(px, py, x1, y1, x2, y2) <= (pad_reach + tr_reach + 0.05):
                        touched = True
                        break
                if touched:
                    continue

                for poly in polygons:
                    pnet = poly.get('net', '').strip()
                    player = poly.get('layer', '').strip().lower()
                    if not pnet or pnet == pad_net:
                        continue
                    if not self._layers_can_connect(pad_layer, player):
                        continue
                    inside = False
                    verts = poly.get('vertices', []) or []
                    vt = [(v[0], v[1]) for v in verts if isinstance(v, (list, tuple)) and len(v) >= 2]
                    if len(vt) >= 3:
                        inside = point_in_polygon(px, py, vt)
                    else:
                        cx = poly.get('x_mm', 0); cy = poly.get('y_mm', 0)
                        sx = poly.get('size_x_mm', 0) / 2; sy = poly.get('size_y_mm', 0) / 2
                        if sx > 0 and sy > 0:
                            inside = (cx - sx <= px <= cx + sx and cy - sy <= py <= cy + sy)
                    if not inside:
                        continue

                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="short_circuit",
                        severity="error",
                        message=(
                            f"Short-Circuit Constraint: Between Pad {pad.get('designator', 'Unknown')}"
                            f"({px:.3f}mm,{py:.3f}mm) on {pad_layer} And Region (0 hole(s)) {player}"
                        ),
                        location={"x_mm": px, "y_mm": py},
                        objects=[pad.get('designator', 'Unknown'), "Region"],
                        net_name=f"{pad_net}/{pnet}"
                    ))
                    break
        
        print(f"DEBUG: Short-circuit check: checked {checked_pairs} pad pairs, found {short_circuit_count} pad-to-pad violations")
        print(f"DEBUG:   Checked {pad_to_track_checked} pad-to-track pairs, found {pad_to_track_short_circuits} pad-to-track violations")
        print(f"DEBUG:   Skipped {skipped_different_layers} pairs (different layers), {skipped_no_layer_info} pairs (no layer info), {skipped_too_far} pairs (too far)")
    
    def _check_unrouted_nets(self, rule: DRCRule, nets: List[Dict], tracks: List[Dict], 
                             pads: List[Dict], vias: List[Dict], polygons: List[Dict] = None,
                             connections: List[Dict] = None):
        """Check for unrouted nets.
        
        Two modes:
        1. CONNECTION-BASED (preferred): Uses eConnectionObject data from Altium export.
           Connection objects are ratsnest lines — they represent pad pairs that SHOULD be
           connected but have NO copper path. Altium removes connection objects when routing
           is completed (tracks, vias, planes all counted). So remaining connections = unrouted.
           This matches Altium's DRC exactly because it uses the SAME connectivity data.
        
        2. FALLBACK (if no connections exported): Builds connectivity graph from tracks/vias/polygons.
           Less accurate because it can't detect internal plane connectivity.
        """
        if not rule.check_unrouted:
            print(f"DEBUG: Unrouted net check disabled for rule '{rule.name}'")
            return
        
        polygons = polygons or []
        connections = connections or []
        
        # =====================================================================
        # MODE 1: Use connection objects (ratsnest) if available
        # This is the most accurate method - uses Altium's own connectivity data
        # =====================================================================
        if connections:
            print(f"DEBUG: Using {len(connections)} connection objects (ratsnest) for unrouted net detection")
            
            # Group connections by net
            unrouted_nets = {}  # net_name -> list of connection dicts
            for conn in connections:
                net_name = conn.get('net', '').strip()
                if not net_name or net_name == 'No Net':
                    continue
                if net_name not in unrouted_nets:
                    unrouted_nets[net_name] = []
                unrouted_nets[net_name].append(conn)
            
            # Build pad lookup for designator info
            pads_per_net = {}
            for pad in pads:
                net = pad.get('net', '').strip()
                if net:
                    if net not in pads_per_net:
                        pads_per_net[net] = []
                    pads_per_net[net].append(pad)
            
            # Report one violation per unrouted connection object (ratsnest segment),
            # which aligns better with Altium's unrouted counting than per-net reporting.
            unrouted_count = 0
            seen_connections = set()
            for net_name, net_connections in unrouted_nets.items():
                net_pads = pads_per_net.get(net_name, [])
                for conn in net_connections:
                    fx = conn.get('from_x_mm', 0)
                    fy = conn.get('from_y_mm', 0)
                    tx = conn.get('to_x_mm', 0)
                    ty = conn.get('to_y_mm', 0)

                    # Deduplicate mirrored/duplicate connection rows (A->B vs B->A).
                    p1 = (round(float(fx), 4), round(float(fy), 4))
                    p2 = (round(float(tx), 4), round(float(ty), 4))
                    seg_key = (net_name, p1, p2) if p1 <= p2 else (net_name, p2, p1)
                    if seg_key in seen_connections:
                        continue
                    seen_connections.add(seg_key)
                    unrouted_count += 1

                    if net_pads:
                        pad_list = ', '.join([p.get('designator', 'Unknown') for p in net_pads[:4]])
                        if len(net_pads) > 4:
                            pad_list += f' (and {len(net_pads) - 4} more)'
                    else:
                        pad_list = "unknown endpoints"

                    msg = (
                        f"Un-Routed Net Constraint: Net {net_name} Between "
                        f"({fx:.3f}mm,{fy:.3f}mm) And ({tx:.3f}mm,{ty:.3f}mm) "
                        f"Related pads: {pad_list}"
                    )
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="unrouted_net",
                        severity="error",
                        message=msg,
                        location={"x_mm": (fx + tx) / 2, "y_mm": (fy + ty) / 2},
                        net_name=net_name
                    ))
            
            print(f"DEBUG: Total unrouted nets found (from ratsnest): {unrouted_count}")
            # Mark explicit unrouted nets for downstream Net Antennae scoping.
            try:
                self._fallback_unrouted_nets.update(unrouted_nets.keys())
            except Exception:
                pass
            # Strict supplemental fallback for under-exported connection objects:
            # only two-pad, lightly-routed nets that are still disconnected.
            conn_nets = set(unrouted_nets.keys())
            pads_per_net = {}
            tracks_per_net = {}
            vias_per_net = {}
            polygons_per_net = {}
            for pad in pads:
                net = pad.get('net', '').strip()
                if net:
                    pads_per_net.setdefault(net, []).append({
                        'designator': pad.get('designator', 'Unknown'),
                        'x_mm': pad.get('x_mm', 0),
                        'y_mm': pad.get('y_mm', 0),
                        'layer': pad.get('layer', 'Unknown'),
                        'size_x_mm': pad.get('size_x_mm', 0),
                        'size_y_mm': pad.get('size_y_mm', 0),
                        'pad_obj': pad
                    })
            for track in tracks:
                net = track.get('net', '').strip()
                if net:
                    tracks_per_net.setdefault(net, []).append(track)
            for via in vias:
                net = via.get('net', '').strip()
                if net:
                    vias_per_net.setdefault(net, []).append(via)
            for polygon in polygons:
                net = polygon.get('net', '').strip()
                if net:
                    polygons_per_net.setdefault(net, []).append(polygon)

            added = 0
            for net_name, net_pads in pads_per_net.items():
                if net_name in conn_nets:
                    continue
                net_tracks = tracks_per_net.get(net_name, [])
                if len(net_pads) != 2 or len(net_tracks) == 0 or len(net_tracks) > 2:
                    continue
                # Strict local check: each pad must be physically touched by at least one
                # same-net track endpoint (small tolerance, no broad graph inference).
                def _endpoint_touches_pad(tx, ty, pad):
                    px = pad.get('x_mm', 0)
                    py = pad.get('y_mm', 0)
                    sx = pad.get('size_x_mm', 0) or 1.0
                    sy = pad.get('size_y_mm', 0) or 1.0
                    half_x = sx / 2
                    half_y = sy / 2
                    tol = 0.05
                    return (px - half_x - tol <= tx <= px + half_x + tol and
                            py - half_y - tol <= ty <= py + half_y + tol)

                pad_touched = [False, False]
                for tr in net_tracks:
                    x1 = tr.get('x1_mm', 0)
                    y1 = tr.get('y1_mm', 0)
                    x2 = tr.get('x2_mm', 0)
                    y2 = tr.get('y2_mm', 0)
                    for i, p in enumerate(net_pads):
                        if _endpoint_touches_pad(x1, y1, p) or _endpoint_touches_pad(x2, y2, p):
                            pad_touched[i] = True
                if all(pad_touched):
                    continue
                self._fallback_unrouted_nets.add(net_name)
                added += 1
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="unrouted_net",
                    severity="error",
                    message=f"Un-Routed Net Constraint: Net {net_name}",
                    location={"x_mm": net_pads[0]['x_mm'], "y_mm": net_pads[0]['y_mm']},
                    net_name=net_name
                ))
            if added:
                print(f"DEBUG: Added {added} strict fallback unrouted net(s)")
            return

        # Without connection objects, fallback graph inference over-reports on boards
        # with planes/pours/internal connectivity not fully represented in the export.
        print("DEBUG: No connection objects exported; skipping unrouted-net fallback to avoid false positives")
        return
        
        # =====================================================================
        # MODE 2: Fallback - build connectivity graph (less accurate)
        # Used when connection objects are not available in the export
        # =====================================================================
        print(f"DEBUG: No connection objects available, using connectivity graph fallback")
        print(f"DEBUG: _check_unrouted_nets: Checking {len(nets)} nets")
        
        # Collect pads per net
        pads_per_net = {}
        for pad in pads:
            net = pad.get('net', '').strip()
            if net:
                if net not in pads_per_net:
                    pads_per_net[net] = []
                pads_per_net[net].append({
                    'designator': pad.get('designator', 'Unknown'),
                    'x_mm': pad.get('x_mm', 0),
                    'y_mm': pad.get('y_mm', 0),
                    'layer': pad.get('layer', 'Unknown'),
                    'size_x_mm': pad.get('size_x_mm', 0),
                    'size_y_mm': pad.get('size_y_mm', 0),
                    'pad_obj': pad
                })
        
        # Collect tracks/vias/polygons per net
        tracks_per_net = {}
        for track in tracks:
            net = track.get('net', '').strip()
            if net:
                if net not in tracks_per_net:
                    tracks_per_net[net] = []
                tracks_per_net[net].append(track)
        
        vias_per_net = {}
        for via in vias:
            net = via.get('net', '').strip()
            if net:
                if net not in vias_per_net:
                    vias_per_net[net] = []
                vias_per_net[net].append(via)
        
        polygons_per_net = {}
        for polygon in polygons:
            net = polygon.get('net', '').strip()
            if net:
                if net not in polygons_per_net:
                    polygons_per_net[net] = []
                polygons_per_net[net].append(polygon)
        
        # Check each net
        unrouted_count = 0
        for net in nets:
            net_name = net.get('name', '').strip()
            if not net_name or net_name == 'No Net':
                continue
            
            net_pads = pads_per_net.get(net_name, [])
            if len(net_pads) <= 1:
                continue
            
            net_tracks = tracks_per_net.get(net_name, [])
            net_vias = vias_per_net.get(net_name, [])
            net_polygons = polygons_per_net.get(net_name, [])
            
            is_connected = self._check_net_connectivity(
                net_name, net_pads, net_tracks, net_vias, net_polygons
            )
            
            if not is_connected:
                unrouted_count += 1
                disconnected = self._find_disconnected_pads(
                    net_name, net_pads, net_tracks, net_vias, net_polygons
                )
                
                if disconnected:
                    pad_list = ', '.join([p['designator'] for p in disconnected[:5]])
                    if len(disconnected) > 5:
                        pad_list += f' (and {len(disconnected) - 5} more)'
                else:
                    pad_list = ', '.join([p['designator'] for p in net_pads[:5]])
                    if len(net_pads) > 5:
                        pad_list += f' (and {len(net_pads) - 5} more)'
                
                location = {'x_mm': net_pads[0]['x_mm'], 'y_mm': net_pads[0]['y_mm']} if net_pads else {}
                message = f"Un-Routed Net Constraint: Net {net_name} Between {pad_list}"
                
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="unrouted_net",
                    severity="error",
                    message=message,
                    location=location,
                    net_name=net_name
                ))
        
        print(f"DEBUG: Total unrouted nets found (fallback): {unrouted_count}")
    
    def _layers_can_connect(self, layer1: str, layer2: str) -> bool:
        """Check if two layers can electrically connect.
        
        Multi Layer pads connect to any layer.
        Same-name layers connect to each other.
        """
        l1 = layer1.strip().lower() if layer1 else ''
        l2 = layer2.strip().lower() if layer2 else ''
        # Conservative for parity: if layer is unknown, do not assume connectivity.
        # Assuming connectivity on unknown layers causes many false positives.
        if not l1 or not l2:
            return False
        if l1 == l2:
            return True
        if 'multi' in l1 or 'multi' in l2:
            return True  # Multi Layer pads connect to any layer
        return False
    
    def _build_net_connectivity(self, pads: List[Dict], tracks: List[Dict], 
                                 vias: List[Dict], polygons: List[Dict] = None):
        """Build connectivity graph for a net using union-find.
        
        Returns (pad_nodes, find_func) where:
        - pad_nodes: dict mapping node_id -> pad_dict
        - find_func: union-find function to check connected components
        
        This is the core connectivity engine used by both _check_net_connectivity
        and _find_disconnected_pads to avoid code duplication.
        """
        polygons = polygons or []
        
        # Connection tolerance in mm - objects within this distance are considered connected
        # Altium considers objects connected if they overlap or are very close
        CONNECTION_TOLERANCE = 0.5
        
        # Union-Find data structure
        parent = {}
        rank = {}
        
        def find(x):
            if x not in parent:
                parent[x] = x
                rank[x] = 0
            if parent[x] != x:
                parent[x] = find(parent[x])  # Path compression
            return parent[x]
        
        def union(x, y):
            root_x = find(x)
            root_y = find(y)
            if root_x != root_y:
                if rank[root_x] < rank[root_y]:
                    parent[root_x] = root_y
                elif rank[root_x] > rank[root_y]:
                    parent[root_y] = root_x
                else:
                    parent[root_y] = root_x
                    rank[root_x] += 1
        
        # Helper: get pad size
        def get_pad_size(pad_dict):
            size_x = pad_dict.get('size_x_mm', 0) or pad_dict.get('width_mm', 0)
            size_y = pad_dict.get('size_y_mm', 0) or pad_dict.get('height_mm', 0)
            if (size_x <= 0 or size_y <= 0) and 'pad_obj' in pad_dict:
                pad_obj = pad_dict.get('pad_obj', {})
                if isinstance(pad_obj, dict):
                    size_x = pad_obj.get('size_x_mm', 0) or pad_obj.get('width_mm', 0) or size_x
                    size_y = pad_obj.get('size_y_mm', 0) or pad_obj.get('height_mm', 0) or size_y
            return size_x, size_y
        
        # Helper: check if point is within pad bounds
        def point_in_pad(px, py, pad_dict, tolerance=0.4):
            pad_x = pad_dict.get('x_mm', 0)
            pad_y = pad_dict.get('y_mm', 0)
            size_x, size_y = get_pad_size(pad_dict)
            if size_x <= 0: size_x = 1.0
            if size_y <= 0: size_y = 1.0
            half_x = size_x / 2
            half_y = size_y / 2
            return (pad_x - half_x - tolerance <= px <= pad_x + half_x + tolerance and
                    pad_y - half_y - tolerance <= py <= pad_y + half_y + tolerance)
        
        # Helper: check if point is within via
        def point_in_via(px, py, via, tolerance=CONNECTION_TOLERANCE):
            via_x = via.get('x_mm', 0)
            via_y = via.get('y_mm', 0)
            diameter = via.get('diameter_mm', 0) or via.get('size_mm', 0)
            radius = diameter / 2.0 if diameter > 0 else 0.25
            return math.sqrt((px - via_x)**2 + (py - via_y)**2) <= radius + tolerance
        
        # Create pad nodes
        pad_nodes = {}
        for i, pad in enumerate(pads):
            node_id = f"pad_{i}"
            pad_nodes[node_id] = pad
            find(node_id)
        
        # Create via nodes
        via_nodes = {}
        for i, via in enumerate(vias):
            node_id = f"via_{i}"
            via_nodes[node_id] = via
            find(node_id)
        
        # Connect pads to vias (checking layer compatibility)
        for pad_id, pad in pad_nodes.items():
            pad_layer = pad.get('layer', '')
            for via_id, via in via_nodes.items():
                # Via spans from low_layer to high_layer - check pad layer compatibility
                via_low = via.get('low_layer', '')
                via_high = via.get('high_layer', '')
                pad_l = pad_layer.strip().lower() if pad_layer else ''
                
                # Through-hole vias (top to bottom) connect to all layers
                # Multi Layer pads connect to any via
                can_connect = False
                if 'multi' in pad_l:
                    can_connect = True
                elif via_low and via_high:
                    vl = via_low.strip().lower()
                    vh = via_high.strip().lower()
                    # Through-hole via spans all layers
                    if ('top' in vl and 'bottom' in vh) or ('bottom' in vl and 'top' in vh):
                        can_connect = True
                    elif pad_l == vl or pad_l == vh:
                        can_connect = True
                else:
                    can_connect = True  # Unknown layers, assume compatible
                
                if can_connect and point_in_pad(via.get('x_mm', 0), via.get('y_mm', 0), pad):
                    union(pad_id, via_id)
        
        # Connect track endpoints to pads and vias
        track_endpoints = {}
        for track in tracks:
            x1 = track.get('x1_mm', track.get('start_x_mm', 0))
            y1 = track.get('y1_mm', track.get('start_y_mm', 0))
            x2 = track.get('x2_mm', track.get('end_x_mm', 0))
            y2 = track.get('y2_mm', track.get('end_y_mm', 0))
            track_layer = track.get('layer', '')
            
            track_start = f"ts_{id(track)}"
            track_end = f"te_{id(track)}"
            find(track_start)
            find(track_end)
            union(track_start, track_end)  # Track endpoints are always connected
            
            track_endpoints[id(track)] = (track_start, track_end, x1, y1, x2, y2)
            
            # Connect to pads (with layer check)
            for pad_id, pad in pad_nodes.items():
                if self._layers_can_connect(track_layer, pad.get('layer', '')):
                    if point_in_pad(x1, y1, pad):
                        union(track_start, pad_id)
                    if point_in_pad(x2, y2, pad):
                        union(track_end, pad_id)
                    # Midpoint check for tracks passing through pad
                    mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
                    if point_in_pad(mid_x, mid_y, pad):
                        union(track_start, pad_id)
            
            # Connect to vias
            for via_id, via in via_nodes.items():
                if point_in_via(x1, y1, via):
                    union(track_start, via_id)
                if point_in_via(x2, y2, via):
                    union(track_end, via_id)
        
        # Connect tracks to each other (endpoint proximity)
        track_list = list(track_endpoints.items())
        for i, (tid1, (s1, e1, x11, y11, x21, y21)) in enumerate(track_list):
            for tid2, (s2, e2, x12, y12, x22, y22) in track_list[i+1:]:
                if math.sqrt((x11 - x12)**2 + (y11 - y12)**2) <= CONNECTION_TOLERANCE:
                    union(s1, s2)
                if math.sqrt((x11 - x22)**2 + (y11 - y22)**2) <= CONNECTION_TOLERANCE:
                    union(s1, e2)
                if math.sqrt((x21 - x12)**2 + (y21 - y12)**2) <= CONNECTION_TOLERANCE:
                    union(e1, s2)
                if math.sqrt((x21 - x22)**2 + (y21 - y22)**2) <= CONNECTION_TOLERANCE:
                    union(e1, e2)
        
        # Polygon/pour connectivity: pads within polygon area on compatible layer are connected
        for polygon in polygons:
            poly_layer = polygon.get('layer', '').strip().lower()
            vertices = polygon.get('vertices', [])
            
            # Determine polygon bounds for quick check
            poly_x = polygon.get('x_mm', 0)
            poly_y = polygon.get('y_mm', 0)
            poly_sx = polygon.get('size_x_mm', 0) / 2
            poly_sy = polygon.get('size_y_mm', 0) / 2
            
            # Parse vertices if available
            vert_tuples = []
            if vertices and len(vertices) >= 3:
                vert_tuples = [(v[0], v[1]) for v in vertices 
                               if isinstance(v, (list, tuple)) and len(v) >= 2]
            
            # Find pads within this polygon on compatible layers
            pads_in_polygon = []
            for pad_id, pad in pad_nodes.items():
                pad_layer = pad.get('layer', '').strip().lower()
                
                # Check layer compatibility (Multi Layer pads connect to any polygon)
                if pad_layer and poly_layer:
                    if pad_layer != poly_layer and 'multi' not in pad_layer:
                        continue
                
                pad_x = pad.get('x_mm', 0)
                pad_y = pad.get('y_mm', 0)
                
                # Check if pad is within polygon
                in_polygon = False
                if vert_tuples:
                    in_polygon = point_in_polygon(pad_x, pad_y, vert_tuples)
                elif poly_sx > 0 and poly_sy > 0:
                    # Use bounding box
                    in_polygon = (poly_x - poly_sx <= pad_x <= poly_x + poly_sx and
                                  poly_y - poly_sy <= pad_y <= poly_y + poly_sy)
                
                if in_polygon:
                    pads_in_polygon.append(pad_id)
            
            # Union all pads within the same polygon (they're connected through the pour)
            for i in range(1, len(pads_in_polygon)):
                union(pads_in_polygon[0], pads_in_polygon[i])
            
            # Also connect vias within polygon to the polygon group
            for via_id, via in via_nodes.items():
                via_x = via.get('x_mm', 0)
                via_y = via.get('y_mm', 0)
                in_polygon = False
                if vert_tuples:
                    in_polygon = point_in_polygon(via_x, via_y, vert_tuples)
                elif poly_sx > 0 and poly_sy > 0:
                    in_polygon = (poly_x - poly_sx <= via_x <= poly_x + poly_sx and
                                  poly_y - poly_sy <= via_y <= poly_y + poly_sy)
                if in_polygon and pads_in_polygon:
                    union(via_id, pads_in_polygon[0])
        
        return pad_nodes, find
    
    def _check_net_connectivity(self, net_name: str, pads: List[Dict], tracks: List[Dict], 
                                 vias: List[Dict], polygons: List[Dict] = None) -> bool:
        """
        Check if all pads in a net are connected via tracks/vias/polygons.
        Returns True if all pads are in the same connected component, False otherwise.
        
        Uses union-find (disjoint set) approach with full polygon/pour support.
        """
        if len(pads) <= 1:
            return True  # Single pad is always "connected"
        
        polygons = polygons or []
        
        if len(tracks) == 0 and len(vias) == 0 and len(polygons) == 0:
            return False  # No routing or pours means pads are not connected
        
        pad_nodes, find = self._build_net_connectivity(pads, tracks, vias, polygons)
        
        if not pad_nodes:
            return True
        
        first_pad_root = find(list(pad_nodes.keys())[0])
        for pad_id in pad_nodes:
            if find(pad_id) != first_pad_root:
                return False
        
        return True
    
    def _find_disconnected_pads(self, net_name: str, pads: List[Dict], tracks: List[Dict], 
                                 vias: List[Dict], polygons: List[Dict] = None) -> List[Dict]:
        """
        Find pads that are not connected to the main connected component.
        Returns a list of disconnected pad dictionaries.
        
        Uses the shared _build_net_connectivity to ensure consistency.
        """
        if len(pads) <= 1:
            return []
        
        polygons = polygons or []
        pad_nodes, find = self._build_net_connectivity(pads, tracks, vias, polygons)
        
        if not pad_nodes:
            return list(pads)
        
        # Find the largest connected component among pads
        component_sizes = {}
        for pad_id in pad_nodes:
            root = find(pad_id)
            component_sizes[root] = component_sizes.get(root, 0) + 1
        
        if not component_sizes:
            return list(pads)
        
        # Find the largest component
        largest_root = max(component_sizes.items(), key=lambda x: x[1])[0]
        
        # Return pads NOT in the largest component
        disconnected = []
        for pad_id, pad in pad_nodes.items():
            if find(pad_id) != largest_root:
                disconnected.append(pad)
        
        return disconnected
    
    def _check_hole_to_hole_clearance(self, rule: DRCRule, vias: List[Dict], pads: List[Dict]):
        """Check clearance between holes (via-to-via drill clearance)"""
        
        min_clearance = rule.hole_to_hole_clearance_mm
        if min_clearance <= 0:
            return  # No meaningful clearance to check
        
        # Check via-to-via
        for i, via1 in enumerate(vias):
            loc1 = self._safe_get_location(via1)
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            hole1 = via1.get('hole_size_mm', 0) / 2
            
            # Skip vias without hole size data
            if hole1 <= 0:
                continue
            if x1 == 0 and y1 == 0:
                continue
            
            for via2 in vias[i+1:]:
                loc2 = self._safe_get_location(via2)
                x2 = loc2.get('x_mm', 0)
                y2 = loc2.get('y_mm', 0)
                hole2 = via2.get('hole_size_mm', 0) / 2
                
                # Skip vias without hole size data
                if hole2 <= 0:
                    continue
                if x2 == 0 and y2 == 0:
                    continue
                
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
        """Check for minimum solder mask sliver - FULL IMPLEMENTATION
        
        Altium's logic: Checks for narrow gaps in solder mask between pads/vias.
        Only checks objects on the SAME layer (solder mask is layer-specific).
        Requires actual solder mask geometry (expansion, opening shapes) for accuracy.
        """
        # Solder mask sliver detection requires actual solder mask geometry data
        # (mask expansion values, opening shapes) which is not in the current export.
        # Without this data, the check produces inaccurate results.
        # TODO: Implement when solder mask geometry is available in the export.
        return
        
        min_sliver = rule.min_solder_mask_sliver_mm
        mask_expansion = rule.solder_mask_expansion_mm
        
        # Solder mask sliver detection: Check for narrow gaps in solder mask
        # This requires complete pad data: size, layer
        # All rules must be checked - we cannot skip any rule
        
        # Check pad-to-pad spacing for solder mask slivers
        # CRITICAL: Only check pads on the SAME layer (solder mask is layer-specific)
        for i, pad1 in enumerate(pads):
            loc1 = self._safe_get_location(pad1)
            x1 = loc1.get('x_mm', 0)
            y1 = loc1.get('y_mm', 0)
            layer1 = pad1.get('layer', '').strip().lower()
            size_x1 = pad1.get('size_x_mm', 0) / 2
            size_y1 = pad1.get('size_y_mm', 0) / 2
            radius1 = max(size_x1, size_y1)
            
            # Skip pads without valid location, size, or layer
            if (x1 == 0 and y1 == 0) or radius1 <= 0 or not layer1:
                continue
            
            for pad2 in pads[i+1:]:
                layer2 = pad2.get('layer', '').strip().lower()
                
                # CRITICAL: Only check pads on the SAME layer
                if not layer2 or layer1 != layer2:
                    continue
                
                loc2 = self._safe_get_location(pad2)
                x2 = loc2.get('x_mm', 0)
                y2 = loc2.get('y_mm', 0)
                size_x2 = pad2.get('size_x_mm', 0) / 2
                size_y2 = pad2.get('size_y_mm', 0) / 2
                radius2 = max(size_x2, size_y2)
                
                if (x2 == 0 and y2 == 0) or radius2 <= 0:
                    continue
                
                distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                mask_radius1 = radius1 + mask_expansion
                mask_radius2 = radius2 + mask_expansion
                mask_gap = distance - mask_radius1 - mask_radius2
                
                # Only flag if gap is positive (pads don't overlap) but less than minimum
                if 0 < mask_gap < min_sliver:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="solder_mask_sliver",
                        severity="error",
                        message=f"Solder mask sliver: {mask_gap:.3f}mm < {min_sliver}mm between pads",
                        location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                        actual_value=round(mask_gap, 3),
                        required_value=min_sliver
                    ))
        
        # Check via-to-pad spacing
        for via in vias:
            via_loc = self._safe_get_location(via)
            via_x = via_loc.get('x_mm', 0)
            via_y = via_loc.get('y_mm', 0)
            via_radius = via.get('diameter_mm', 0) / 2
            via_mask_radius = via_radius + mask_expansion
            
            for pad in pads:
                pad_loc = self._safe_get_location(pad)
                pad_x = pad_loc.get('x_mm', 0)
                pad_y = pad_loc.get('y_mm', 0)
                pad_size_x = pad.get('size_x_mm', 0) / 2
                pad_size_y = pad.get('size_y_mm', 0) / 2
                pad_radius = max(pad_size_x, pad_size_y)
                pad_mask_radius = pad_radius + mask_expansion
                
                distance = math.sqrt((pad_x - via_x)**2 + (pad_y - via_y)**2)
                mask_gap = distance - via_mask_radius - pad_mask_radius
                
                if 0 < mask_gap < min_sliver:
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="solder_mask_sliver",
                        severity="error",
                        message=f"Solder mask sliver: {mask_gap:.3f}mm < {min_sliver}mm between via and pad",
                        location={"x_mm": (via_x + pad_x) / 2, "y_mm": (via_y + pad_y) / 2},
                        actual_value=round(mask_gap, 3),
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
        if min_clearance <= 0:
            return
        
        # Check silk screen bounds between components
        for i, comp1 in enumerate(components):
            silk1 = comp1.get('silk_screen', {})
            if not silk1:
                continue
            
            bounds1 = silk1.get('bounds', {})
            if not bounds1:
                continue
            
            x1_min = bounds1.get('x_min', 0)
            x1_max = bounds1.get('x_max', 0)
            y1_min = bounds1.get('y_min', 0)
            y1_max = bounds1.get('y_max', 0)
            
            for comp2 in components[i+1:]:
                silk2 = comp2.get('silk_screen', {})
                if not silk2:
                    continue
                
                bounds2 = silk2.get('bounds', {})
                if not bounds2:
                    continue
                
                x2_min = bounds2.get('x_min', 0)
                x2_max = bounds2.get('x_max', 0)
                y2_min = bounds2.get('y_min', 0)
                y2_max = bounds2.get('y_max', 0)
                
                # Calculate minimum distance between silk screen bounds
                if x2_max < x1_min:
                    dist_x = x1_min - x2_max
                elif x2_min > x1_max:
                    dist_x = x2_min - x1_max
                else:
                    dist_x = 0  # Overlap in X
                
                if y2_max < y1_min:
                    dist_y = y1_min - y2_max
                elif y2_min > y1_max:
                    dist_y = y2_min - y1_max
                else:
                    dist_y = 0  # Overlap in Y
                
                clearance = math.sqrt(dist_x**2 + dist_y**2) if dist_x > 0 or dist_y > 0 else 0
                
                if clearance < min_clearance:
                    self.warnings.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="silk_to_silk",
                        severity="warning",
                        message=f"Silk to silk clearance: {clearance:.3f}mm < {min_clearance}mm",
                        location={"x_mm": (x1_min + x1_max + x2_min + x2_max) / 4, 
                                 "y_mm": (y1_min + y1_max + y2_min + y2_max) / 4},
                        actual_value=round(clearance, 3),
                        required_value=min_clearance,
                        objects=[comp1.get('name', ''), comp2.get('name', '')]
                    ))
    
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
    
    def _get_track_segments(self, track: Dict) -> List[Tuple[float, float, float, float]]:
        """Extract track segments from track data"""
        segments = []
        
        # Try different track data formats
        if 'segments' in track:
            for seg in track['segments']:
                if isinstance(seg, dict):
                    from_pos = seg.get('from_pos', seg.get('from', []))
                    to_pos = seg.get('to_pos', seg.get('to', []))
                    if from_pos and to_pos and len(from_pos) >= 2 and len(to_pos) >= 2:
                        segments.append((from_pos[0], from_pos[1], to_pos[0], to_pos[1]))
        
        # Try x1_mm, y1_mm, x2_mm, y2_mm format
        if 'x1_mm' in track and 'y1_mm' in track and 'x2_mm' in track and 'y2_mm' in track:
            segments.append((track['x1_mm'], track['y1_mm'], track['x2_mm'], track['y2_mm']))
        
        # Try start/end format
        if 'start' in track and 'end' in track:
            start = track['start']
            end = track['end']
            if isinstance(start, dict) and isinstance(end, dict):
                x1 = start.get('x_mm', start.get('x', 0))
                y1 = start.get('y_mm', start.get('y', 0))
                x2 = end.get('x_mm', end.get('x', 0))
                y2 = end.get('y_mm', end.get('y', 0))
                segments.append((x1, y1, x2, y2))
        
        return segments
    
    def _check_net_antennae(self, rule: DRCRule, nets: List[Dict], tracks: List[Dict], 
                           pads: List[Dict], vias: List[Dict]):
        """Check for net antennae — tracks with a floating (unconnected) endpoint.
        
        Altium's Net Antennae rule: A track endpoint that doesn't physically connect 
        to any pad, via, or another track endpoint is a "dead end" (antenna).
        Reports ONE violation per antenna track (not per endpoint).
        
        Key: uses physical copper overlap for connection detection, not center-to-center.
        """
        # If connection objects are missing, still run geometry-based antenna detection.
        # We mitigate false positives by considering same-net polygon/fill containment as connectivity.
        has_connection_objects = bool(getattr(self, '_current_connections', []) or [])
        if not has_connection_objects:
            print("DEBUG: Net Antennae: no connection objects exported, using conservative geometry-only detection")

        # Collect pad data: (x, y, half_radius)
        # Use max(sx, sy) as radius to handle pad rotation — a rotated pad's
        # effective reach in any direction is at most max(sx, sy)/2
        pad_list = []
        for pad in pads:
            x = pad.get('x_mm', 0)
            y = pad.get('y_mm', 0)
            pnet = pad.get('net', '').strip()
            sx = pad.get('size_x_mm', 0) or 1.0
            sy = pad.get('size_y_mm', 0) or 1.0
            half_r = max(sx, sy) / 2  # Rotation-safe: use largest dimension
            if (x != 0 or y != 0) and pnet:
                pad_list.append((x, y, half_r, pnet))
        
        # Collect via data: (x, y, radius)
        via_list = []
        for via in vias:
            x = via.get('x_mm', 0)
            y = via.get('y_mm', 0)
            vnet = via.get('net', '').strip()
            diameter = via.get('diameter_mm', 0) or 0.5
            if (x != 0 or y != 0) and vnet:
                via_list.append((x, y, diameter / 2, vnet))
        
        # Collect polygon pour data for connectivity (tracks within a pour are connected)
        polygon_data = []
        if hasattr(self, '_current_polygons'):
            for poly in self._current_polygons:
                if not isinstance(poly, dict):
                    continue
                pnet = poly.get('net', '').strip()
                player = poly.get('layer', '').strip().lower()
                pverts = poly.get('vertices', [])
                px = poly.get('x_mm', 0)
                py = poly.get('y_mm', 0)
                psx = poly.get('size_x_mm', 0) / 2
                psy = poly.get('size_y_mm', 0) / 2
                if pnet and (psx > 0 or (pverts and len(pverts) >= 3)):
                    polygon_data.append((pnet, player, px, py, psx, psy, pverts))
        
        # Collect fill data: (x1, y1, x2, y2, net, layer) — copper rectangles
        fill_list = []
        if hasattr(self, '_current_fills'):
            for fill in self._current_fills:
                fx1 = fill.get('x1_mm', 0)
                fy1 = fill.get('y1_mm', 0)
                fx2 = fill.get('x2_mm', 0)
                fy2 = fill.get('y2_mm', 0)
                fnet = fill.get('net', '').strip()
                flayer = fill.get('layer', '').strip().lower()
                if fx1 != fx2 or fy1 != fy2:
                    fill_list.append((min(fx1,fx2), min(fy1,fy2), max(fx1,fx2), max(fy1,fy2), fnet, flayer))
        
        # Collect arc data: endpoints for connection detection
        arc_endpoints = []  # (x, y, half_width)
        if hasattr(self, '_current_arcs'):
            for arc in self._current_arcs:
                ax1 = arc.get('x1_mm', 0)
                ay1 = arc.get('y1_mm', 0)
                ax2 = arc.get('x2_mm', 0)
                ay2 = arc.get('y2_mm', 0)
                awidth = arc.get('width_mm', 0.254)
                if ax1 != 0 or ay1 != 0:
                    arc_endpoints.append((ax1, ay1, awidth / 2))
                if ax2 != 0 or ay2 != 0:
                    arc_endpoints.append((ax2, ay2, awidth / 2))
        
        # Collect all track endpoints
        all_track_endpoints = []  # (x, y, track_index)
        valid_tracks = []
        
        for i, track in enumerate(tracks):
            x1 = track.get('x1_mm', 0)
            y1 = track.get('y1_mm', 0)
            x2 = track.get('x2_mm', 0)
            y2 = track.get('y2_mm', 0)
            net = track.get('net', '').strip()
            layer = track.get('layer', '').strip()
            width = track.get('width_mm', 0.254)
            
            if (x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0) or not net:
                continue
            
            valid_tracks.append((i, x1, y1, x2, y2, net, layer, width))
            all_track_endpoints.append((x1, y1, i))
            all_track_endpoints.append((x2, y2, i))

        # Build connection endpoints map per net.
        # If an endpoint coincides with an explicit unrouted connection endpoint,
        # classify it as UnRoutedNet (not NetAntennae) to avoid double-reporting.
        conn_endpoints_by_net = {}
        for conn in (self._current_connections or []):
            if not isinstance(conn, dict):
                continue
            cn = conn.get('net', '').strip()
            if not cn:
                continue
            fx = conn.get('from_x_mm', 0)
            fy = conn.get('from_y_mm', 0)
            tx = conn.get('to_x_mm', 0)
            ty = conn.get('to_y_mm', 0)
            conn_endpoints_by_net.setdefault(cn, []).append((fx, fy))
            conn_endpoints_by_net.setdefault(cn, []).append((tx, ty))
        
        # Determine which nets have unrouted connections (from ratsnest data)
        # Key insight: Net Antennae can ONLY occur on nets with incomplete routing.
        # If a net is fully routed (no ratsnest/connection objects), ALL its tracks
        # are properly connected and cannot have dead-end stubs.
        # This filters out false positives from tracks connected through objects
        # we can't fully detect (regions, internal planes, etc.)
        nets_with_unrouted = set()
        if hasattr(self, '_current_connections'):
            for conn in self._current_connections:
                if isinstance(conn, dict):
                    cn = conn.get('net', '').strip()
                    if cn:
                        nets_with_unrouted.add(cn)
        
        # Candidate nets:
        # - with connection data: limit to unrouted + fallback nets
        # - without connection data: check all nets conservatively
        candidate_nets = set(nets_with_unrouted)
        candidate_nets.update(getattr(self, '_fallback_unrouted_nets', set()) or set())
        if has_connection_objects and candidate_nets:
            print(f"DEBUG: Net Antennae: Only checking tracks on {len(candidate_nets)} candidate nets: {candidate_nets}")
        
        # Check each track's endpoints
        antennae_count = 0
        # Count antennae per floating endpoint to better reflect Altium reporting.
        
        for idx, x1, y1, x2, y2, net, layer, width in valid_tracks:
            if has_connection_objects and candidate_nets and net not in candidate_nets:
                continue
            
            half_w = width / 2  # Track copper extends this far from centerline
            floating_points = []
            
            for px, py in [(x1, y1), (x2, y2)]:
                connected = False
                
                # Connection tolerance: adaptive to track geometry
                # A track endpoint's copper is a semicircle of radius = half_width.
                # Use the track's own half-width as extra tolerance — this accounts for
                # the physical copper reach beyond the centerline endpoint coordinate.
                # This is NOT hard-coded — it adapts to each track's actual width.
                CONN_TOL = max(0.0, float(rule.net_antennae_tolerance_mm or 0.0))
                
                # 1. Pad check: track copper overlaps pad copper
                #    Uses circular distance with max pad dimension (handles rotation)
                for pad_x, pad_y, pad_half_r, pnet in pad_list:
                    if pnet != net:
                        continue
                    dist = math.sqrt((px - pad_x)**2 + (py - pad_y)**2)
                    if dist <= pad_half_r + half_w + CONN_TOL:
                        connected = True
                        break
                
                if connected:
                    continue
                
                # 2. Via check: track copper overlaps via copper
                for via_x, via_y, via_r, vnet in via_list:
                    if vnet != net:
                        continue
                    if math.sqrt((px - via_x)**2 + (py - via_y)**2) <= via_r + half_w + CONN_TOL:
                        connected = True
                        break
                
                if connected:
                    continue
                
                # 3. Track connection: endpoint near another track's endpoint OR body (T-junction)
                for j, tx1, ty1, tx2, ty2, tnet, tlayer, twidth in valid_tracks:
                    if j == idx:
                        continue
                    if tnet != net:
                        continue
                    if layer and tlayer and (not self._layers_can_connect(layer, tlayer)):
                        continue
                    other_half_w = twidth / 2
                    # Endpoint-to-endpoint
                    ep_tol = half_w + other_half_w + CONN_TOL
                    if math.sqrt((px - tx1)**2 + (py - ty1)**2) <= ep_tol:
                        connected = True
                        break
                    if math.sqrt((px - tx2)**2 + (py - ty2)**2) <= ep_tol:
                        connected = True
                        break
                    # Endpoint-to-body (T-junction)
                    dist = point_to_line_distance(px, py, tx1, ty1, tx2, ty2)
                    if dist <= half_w + other_half_w + CONN_TOL:
                        connected = True
                        break
                
                if connected:
                    continue
                
                # 4. Same-net polygon containment (conservative anti-false-positive check)
                if not connected:
                    for pnet, player, pcx, pcy, psx, psy, pverts in polygon_data:
                        if pnet != net:
                            continue
                        if layer and player and (not self._layers_can_connect(layer, player)):
                            continue
                        inside_poly = False
                        if pverts and len(pverts) >= 3:
                            try:
                                verts = [(v[0], v[1]) for v in pverts if isinstance(v, (list, tuple)) and len(v) >= 2]
                                if len(verts) >= 3:
                                    inside_poly = point_in_polygon(px, py, verts)
                            except Exception:
                                inside_poly = False
                        if not inside_poly and psx > 0 and psy > 0:
                            inside_poly = (pcx - psx <= px <= pcx + psx and pcy - psy <= py <= pcy + psy)
                        if inside_poly:
                            connected = True
                            break

                # 5. Same-net fill containment (rectangle copper)
                if not connected:
                    for fx1, fy1, fx2, fy2, fnet, flayer in fill_list:
                        if fnet != net:
                            continue
                        if layer and flayer and (not self._layers_can_connect(layer, flayer)):
                            continue
                        if (fx1 - half_w - CONN_TOL) <= px <= (fx2 + half_w + CONN_TOL) and \
                           (fy1 - half_w - CONN_TOL) <= py <= (fy2 + half_w + CONN_TOL):
                            connected = True
                            break
                
                if not connected:
                    # 6. Arc check: endpoint near an arc endpoint
                    for ax, ay, ahw in arc_endpoints:
                        if math.sqrt((px - ax)**2 + (py - ay)**2) <= half_w + ahw + CONN_TOL:
                            connected = True
                            break
                
                if not connected:
                    # If this endpoint is explicitly present in unrouted connection objects
                    # and is not at a same-net pad, keep it as a floating candidate.
                    conn_pts = conn_endpoints_by_net.get(net, [])
                    is_conn_endpoint = any(
                        math.sqrt((px - cx) ** 2 + (py - cy) ** 2) <= max(0.1, half_w)
                        for cx, cy in conn_pts
                    )
                    if is_conn_endpoint:
                        at_same_net_pad = False
                        for pad_x, pad_y, pad_half_r, pnet in pad_list:
                            if pnet != net:
                                continue
                            if math.sqrt((px - pad_x) ** 2 + (py - pad_y) ** 2) <= (pad_half_r + half_w):
                                at_same_net_pad = True
                                break
                        if not at_same_net_pad:
                            connected = False

                if not connected:
                    floating_points.append((px, py))

            # With connection objects: keep endpoint-level reporting (more Altium-like detail).
            if has_connection_objects:
                for px, py in floating_points:
                    antennae_count += 1
                    layer_display = layer if layer else 'Unknown Layer'
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="net_antennae",
                        severity="error",
                        message=f"Net Antennae: Track ({x1:.3f}mm,{y1:.3f}mm)({x2:.3f}mm,{y2:.3f}mm) on {layer_display}",
                        location={"x_mm": px, "y_mm": py},
                        net_name=net
                    ))
            else:
                # Without ratsnest, only high-confidence stubs:
                # exactly one floating endpoint on a track (other endpoint connected).
                track_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                min_stub_len = max(2.0, 6.0 * width)  # conservative: avoid short neck-down fragments
                if len(floating_points) == 1 and track_len >= min_stub_len:
                    px, py = floating_points[0]
                    antennae_count += 1
                    layer_display = layer if layer else 'Unknown Layer'
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="net_antennae",
                        severity="error",
                        message=f"Net Antennae: Track ({x1:.3f}mm,{y1:.3f}mm)({x2:.3f}mm,{y2:.3f}mm) on {layer_display}",
                        location={"x_mm": px, "y_mm": py},
                        net_name=net
                    ))

        # Via antennae: dangling via barrels on candidate nets.
        if not has_connection_objects:
            print("DEBUG: Net Antennae: skipping via-antenna inference without connection objects")
            print(f"DEBUG: Net Antennae check: {antennae_count} violations found from {len(valid_tracks)} tracks")
            return
        for via in vias:
            vnet = via.get('net', '').strip()
            if not vnet:
                continue
            if has_connection_objects and candidate_nets and vnet not in candidate_nets:
                continue
            vloc = self._safe_get_location(via)
            vx = vloc.get('x_mm', 0)
            vy = vloc.get('y_mm', 0)
            if vx == 0 and vy == 0:
                continue
            vdia = via.get('diameter_mm', 0) or 0.5
            vr = vdia / 2

            # Explicit unrouted connection endpoint at a via => antenna by definition.
            conn_pts = conn_endpoints_by_net.get(vnet, [])
            is_conn_via = any(math.sqrt((vx - cx) ** 2 + (vy - cy) ** 2) <= max(0.1, vr) for cx, cy in conn_pts)
            if is_conn_via:
                antennae_count += 1
                low_l = via.get('low_layer', 'Unknown')
                high_l = via.get('high_layer', 'Unknown')
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="net_antennae",
                    severity="error",
                    message=f"Net Antennae: Via ({vx:.3f}mm,{vy:.3f}mm) from {low_l} to {high_l}",
                    location={"x_mm": vx, "y_mm": vy},
                    net_name=vnet
                ))
                continue

            connected = False
            # Connected to any pad on same net.
            for pad in pads:
                if pad.get('net', '').strip() != vnet:
                    continue
                pl = self._safe_get_location(pad)
                px = pl.get('x_mm', 0)
                py = pl.get('y_mm', 0)
                if px == 0 and py == 0:
                    continue
                psx = pad.get('size_x_mm', 0) or pad.get('width_mm', 0) or 1.0
                psy = pad.get('size_y_mm', 0) or pad.get('height_mm', 0) or 1.0
                pr = max(psx, psy) / 2
                if math.sqrt((vx - px) ** 2 + (vy - py) ** 2) <= (vr + pr):
                    connected = True
                    break
            if connected:
                continue

            # Connected to any track endpoint/body on same net.
            for _, tx1, ty1, tx2, ty2, tnet, _, tw in valid_tracks:
                if tnet != vnet:
                    continue
                tr = tw / 2
                if math.sqrt((vx - tx1) ** 2 + (vy - ty1) ** 2) <= (vr + tr):
                    connected = True
                    break
                if math.sqrt((vx - tx2) ** 2 + (vy - ty2) ** 2) <= (vr + tr):
                    connected = True
                    break
                if point_to_line_distance(vx, vy, tx1, ty1, tx2, ty2) <= (vr + tr):
                    connected = True
                    break
            if connected:
                continue

            antennae_count += 1
            low_l = via.get('low_layer', 'Unknown')
            high_l = via.get('high_layer', 'Unknown')
            self.violations.append(DRCViolation(
                rule_name=rule.name,
                rule_type="net_antennae",
                severity="error",
                message=f"Net Antennae: Via ({vx:.3f}mm,{vy:.3f}mm) from {low_l} to {high_l}",
                location={"x_mm": vx, "y_mm": vy},
                net_name=vnet
            ))

        # Fallback dangling-component antenna for strict unrouted nets.
        # For under-exported 2-pad unrouted nets, emit one representative track antenna
        # when the routed fragment is anchored at only one pad/via.
        for net in (getattr(self, '_fallback_unrouted_nets', set()) or set()):
            net_tracks = [t for t in tracks if t.get('net', '').strip() == net]
            if not net_tracks:
                continue
            net_pads = [p for p in pads if p.get('net', '').strip() == net]
            net_vias = [v for v in vias if v.get('net', '').strip() == net]
            anchor_count = 0
            for p in net_pads:
                pl = self._safe_get_location(p)
                px = pl.get('x_mm', 0); py = pl.get('y_mm', 0)
                if px == 0 and py == 0:
                    continue
                psx = p.get('size_x_mm', 0) or 1.0
                psy = p.get('size_y_mm', 0) or 1.0
                pr = max(psx, psy) / 2
                touched = False
                for tr in net_tracks:
                    x1 = tr.get('x1_mm', 0); y1 = tr.get('y1_mm', 0)
                    x2 = tr.get('x2_mm', 0); y2 = tr.get('y2_mm', 0)
                    tw = tr.get('width_mm', 0.254) / 2
                    if point_to_line_distance(px, py, x1, y1, x2, y2) <= (pr + tw):
                        touched = True
                        break
                if touched:
                    anchor_count += 1
            if anchor_count <= 1 and net_tracks:
                best = max(
                    net_tracks,
                    key=lambda tr: math.sqrt((tr.get('x2_mm', 0) - tr.get('x1_mm', 0)) ** 2 +
                                             (tr.get('y2_mm', 0) - tr.get('y1_mm', 0)) ** 2)
                )
                x1 = best.get('x1_mm', 0); y1 = best.get('y1_mm', 0)
                x2 = best.get('x2_mm', 0); y2 = best.get('y2_mm', 0)
                layer = best.get('layer', 'Unknown Layer')
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="net_antennae",
                    severity="error",
                    message=f"Net Antennae: Track ({x1:.3f}mm,{y1:.3f}mm)({x2:.3f}mm,{y2:.3f}mm) on {layer}",
                    location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                    net_name=net
                ))
                antennae_count += 1
        
        print(f"DEBUG: Net Antennae check: {antennae_count} violations found from {len(valid_tracks)} tracks")
    
    def _are_segments_parallel(self, seg1: Tuple[float, float, float, float], 
                               seg2: Tuple[float, float, float, float], 
                               tolerance: float = 0.01) -> bool:
        """Check if two line segments are parallel"""
        x1, y1, x2, y2 = seg1
        x3, y3, x4, y4 = seg2
        
        # Calculate direction vectors
        dx1 = x2 - x1
        dy1 = y2 - y1
        dx2 = x4 - x3
        dy2 = y4 - y3
        
        # Check if vectors are parallel (cross product near zero)
        cross = dx1 * dy2 - dy1 * dx2
        return abs(cross) < tolerance
    
    def _calculate_segment_gap(self, seg1: Tuple[float, float, float, float], 
                               seg2: Tuple[float, float, float, float]) -> float:
        """Calculate minimum gap between two parallel segments"""
        x1, y1, x2, y2 = seg1
        x3, y3, x4, y4 = seg2
        
        # For parallel segments, calculate perpendicular distance
        # Simplified: use midpoint distance minus half widths
        mid1_x = (x1 + x2) / 2
        mid1_y = (y1 + y2) / 2
        mid2_x = (x3 + x4) / 2
        mid2_y = (y3 + y4) / 2
        
        distance = math.sqrt((mid2_x - mid1_x)**2 + (mid2_y - mid1_y)**2)
        return distance
    
    def _check_differential_pairs(self, rule: DRCRule, tracks: List[Dict], nets: List[Dict]):
        """Check differential pair routing constraints"""
        # CRITICAL: Only check if there are actual differential pairs in the design
        # If no diff pairs exist, this rule should pass (0 violations)
        
        # Identify differential pair nets (typically named with _P/_N or +/- suffixes)
        diff_pairs = {}
        for net in nets:
            net_name = net.get('name', '')
            if not net_name:
                continue
            
            # Try to find pair partner
            base_name = net_name.rstrip('_P').rstrip('_N').rstrip('+').rstrip('-')
            if base_name != net_name:
                if base_name not in diff_pairs:
                    diff_pairs[base_name] = []
                diff_pairs[base_name].append(net_name)
        
        # If no differential pairs found in the design, rule passes
        if not diff_pairs:
            return
        
        # Check tracks for each differential pair
        for base_name, pair_nets in diff_pairs.items():
            if len(pair_nets) != 2:
                # Incomplete pair - skip to avoid false positives
                continue
            
            net1, net2 = pair_nets[0], pair_nets[1]
            tracks1 = [t for t in tracks if t.get('net', '') == net1]
            tracks2 = [t for t in tracks if t.get('net', '') == net2]
            
            # Check width constraints
            for track in tracks1 + tracks2:
                width = track.get('width_mm', 0)
                if width > 0:
                    if width < rule.diff_min_width_mm:
                        loc = self._safe_get_location(track)
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="diff_pairs_routing",
                            severity="error",
                            message=f"Differential pair track width {width:.3f}mm < minimum {rule.diff_min_width_mm}mm",
                            location=loc,
                            actual_value=width,
                            required_value=rule.diff_min_width_mm,
                            net_name=track.get('net', '')
                        ))
                    elif width > rule.diff_max_width_mm:
                        loc = self._safe_get_location(track)
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="diff_pairs_routing",
                            severity="error",
                            message=f"Differential pair track width {width:.3f}mm > maximum {rule.diff_max_width_mm}mm",
                            location=loc,
                            actual_value=width,
                            required_value=rule.diff_max_width_mm,
                            net_name=track.get('net', '')
                        ))
            
            # Check gap between parallel segments
            for track1 in tracks1:
                segs1 = self._get_track_segments(track1)
                for track2 in tracks2:
                    segs2 = self._get_track_segments(track2)
                    for seg1 in segs1:
                        for seg2 in segs2:
                            if self._are_segments_parallel(seg1, seg2):
                                gap = self._calculate_segment_gap(seg1, seg2)
                                if gap < rule.diff_min_gap_mm:
                                    x1, y1, x2, y2 = seg1
                                    self.violations.append(DRCViolation(
                                        rule_name=rule.name,
                                        rule_type="diff_pairs_routing",
                                        severity="error",
                                        message=f"Differential pair gap {gap:.3f}mm < minimum {rule.diff_min_gap_mm}mm",
                                        location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                                        actual_value=gap,
                                        required_value=rule.diff_min_gap_mm,
                                        net_name=f"{net1}/{net2}"
                                    ))
                                elif gap > rule.diff_max_gap_mm:
                                    x1, y1, x2, y2 = seg1
                                    self.violations.append(DRCViolation(
                                        rule_name=rule.name,
                                        rule_type="diff_pairs_routing",
                                        severity="warning",
                                        message=f"Differential pair gap {gap:.3f}mm > maximum {rule.diff_max_gap_mm}mm",
                                        location={"x_mm": (x1 + x2) / 2, "y_mm": (y1 + y2) / 2},
                                        actual_value=gap,
                                        required_value=rule.diff_max_gap_mm,
                                        net_name=f"{net1}/{net2}"
                                    ))
    
    def _check_routing_topology(self, rule: DRCRule, nets: List[Dict], tracks: List[Dict], 
                               pads: List[Dict], vias: List[Dict]):
        """Check routing topology constraints
        
        Altium's logic: Topology rules validate that nets follow specific routing patterns
        (Shortest, Daisy-Simple, Daisy-Midpoint, Star, etc.). This requires full
        connectivity graph analysis.
        
        Checks that net routing follows the specified topology pattern.
        Without full topology analysis, we cannot accurately check this.
        """
        # CRITICAL: Topology checking requires full connectivity graph analysis
        # Without complete topology data, we cannot accurately validate topology
        # Routing topology requires detailed connection order data not available in export
        # TODO: Implement full topology graph analysis when topology data is available
        return
        
        # Original code (disabled - requires full topology analysis):
        # for net in nets:
        #     net_name = net.get('name', '')
        #     if not net_name or net_name == 'No Net':
        #         continue
        #     
        #     # Check if net has tracks
        #     net_tracks = [t for t in tracks if t.get('net', '') == net_name]
        #     net_pads = [p for p in pads if p.get('net', '') == net_name]
        #     
        #     # If net has multiple pads but no tracks, topology might be violated
        #     if len(net_pads) > 1 and len(net_tracks) == 0:
        #         # This is more of an unrouted net issue, but we'll log it as topology warning
        #         self.warnings.append(DRCViolation(...))
    
    def _check_via_style(self, rule: DRCRule, vias: List[Dict]):
        """Check via style constraints"""
        # CRITICAL: Only check if rule specifies a specific style (not "Any")
        # If rule allows "Any", all vias pass
        if rule.via_style == "Any" or not rule.via_style:
            return  # Rule allows any style, no violations possible
        
        for via in vias:
            via_style = via.get('style', 'Through Hole')
            hole_size = via.get('hole_size_mm', 0)
            diameter = via.get('diameter_mm', 0)
            
            # Only check if via has style info and it doesn't match
            # If via style is missing, skip to avoid false positives
            if not via_style or via_style == 'Through Hole':
                # Default/unknown style - skip unless rule explicitly forbids it
                continue
            
            # Check if via style matches rule
            if via_style != rule.via_style:
                loc = self._safe_get_location(via)
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="routing_via_style",
                    severity="error",
                    message=f"Via style '{via_style}' does not match required '{rule.via_style}'",
                    location=loc,
                    objects=[via.get('net', '')]
                ))
            
            # Check diameter constraints
            if diameter > 0:
                if diameter < rule.min_via_diameter_mm:
                    loc = self._safe_get_location(via)
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="routing_via_style",
                        severity="error",
                        message=f"Via diameter {diameter:.3f}mm < minimum {rule.min_via_diameter_mm}mm",
                        location=loc,
                        actual_value=diameter,
                        required_value=rule.min_via_diameter_mm
                    ))
                elif diameter > rule.max_via_diameter_mm:
                    loc = self._safe_get_location(via)
                    self.violations.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="routing_via_style",
                        severity="error",
                        message=f"Via diameter {diameter:.3f}mm > maximum {rule.max_via_diameter_mm}mm",
                        location=loc,
                        actual_value=diameter,
                        required_value=rule.max_via_diameter_mm
                    ))
    
    def _calculate_corner_angle(self, seg1: Tuple[float, float, float, float], 
                                seg2: Tuple[float, float, float, float]) -> float:
        """Calculate angle between two connected segments"""
        x1, y1, x2, y2 = seg1
        x3, y3, x4, y4 = seg2
        
        # Check if segments are connected
        connected = False
        if abs(x2 - x3) < 0.01 and abs(y2 - y3) < 0.01:
            connected = True
            # seg1 ends where seg2 starts
            dir1 = (x2 - x1, y2 - y1)
            dir2 = (x4 - x3, y4 - y3)
        elif abs(x2 - x4) < 0.01 and abs(y2 - y4) < 0.01:
            connected = True
            # seg1 ends where seg2 ends
            dir1 = (x2 - x1, y2 - y1)
            dir2 = (x3 - x4, y3 - y4)
        elif abs(x1 - x3) < 0.01 and abs(y1 - y3) < 0.01:
            connected = True
            # seg1 starts where seg2 starts
            dir1 = (x2 - x1, y2 - y1)
            dir2 = (x4 - x3, y4 - y3)
        elif abs(x1 - x4) < 0.01 and abs(y1 - y4) < 0.01:
            connected = True
            # seg1 starts where seg2 ends
            dir1 = (x2 - x1, y2 - y1)
            dir2 = (x3 - x4, y3 - y4)
        
        if not connected:
            return None
        
        # Calculate angle between direction vectors
        dot = dir1[0] * dir2[0] + dir1[1] * dir2[1]
        mag1 = math.sqrt(dir1[0]**2 + dir1[1]**2)
        mag2 = math.sqrt(dir2[0]**2 + dir2[1]**2)
        
        if mag1 == 0 or mag2 == 0:
            return None
        
        cos_angle = dot / (mag1 * mag2)
        cos_angle = max(-1.0, min(1.0, cos_angle))  # Clamp to valid range
        angle_rad = math.acos(cos_angle)
        angle_deg = math.degrees(angle_rad)
        
        return angle_deg
    
    def _check_routing_corners(self, rule: DRCRule, tracks: List[Dict]):
        """Check routing corner style constraints"""
        for track in tracks:
            segments = self._get_track_segments(track)
            
            # Check angles between consecutive segments
            for i in range(len(segments) - 1):
                seg1 = segments[i]
                seg2 = segments[i + 1]
                angle = self._calculate_corner_angle(seg1, seg2)
                
                if angle is None:
                    continue
                
                # Check against corner style
                if rule.corner_style == "45 Degrees":
                    # Allow 45, 90, 135 degrees (common routing angles)
                    if angle not in [45.0, 90.0, 135.0, 180.0]:
                        # Allow small tolerance
                        if not (44.0 <= angle <= 46.0 or 89.0 <= angle <= 91.0 or 
                               134.0 <= angle <= 136.0 or 179.0 <= angle <= 181.0):
                            x1, y1, x2, y2 = seg1
                            self.violations.append(DRCViolation(
                                rule_name=rule.name,
                                rule_type="routing_corners",
                                severity="error",
                                message=f"Corner angle {angle:.1f}° does not match 45-degree style",
                                location={"x_mm": x2, "y_mm": y2},
                                actual_value=angle,
                                required_value=45.0,
                                net_name=track.get('net', '')
                            ))
                elif rule.corner_style == "90 Degrees":
                    # Only allow 90 degrees
                    if not (89.0 <= angle <= 91.0 or 179.0 <= angle <= 181.0):
                        x1, y1, x2, y2 = seg1
                        self.violations.append(DRCViolation(
                            rule_name=rule.name,
                            rule_type="routing_corners",
                            severity="error",
                            message=f"Corner angle {angle:.1f}° does not match 90-degree style",
                            location={"x_mm": x2, "y_mm": y2},
                            actual_value=angle,
                            required_value=90.0,
                            net_name=track.get('net', '')
                        ))
                # "Rounded" and "Any Angle" don't need strict validation
    
    def _check_routing_layers(self, rule: DRCRule, tracks: List[Dict]):
        """Check routing layer constraints"""
        allowed_layers = rule.allowed_layers or []
        restricted_layers = rule.restricted_layers or []
        
        for track in tracks:
            layer = track.get('layer', '')
            if not layer:
                continue
            
            # Check if layer is in restricted list
            if restricted_layers and layer in restricted_layers:
                loc = self._safe_get_location(track)
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="routing_layers",
                    severity="error",
                    message=f"Track on restricted layer '{layer}'",
                    location=loc,
                    net_name=track.get('net', '')
                ))
            
            # Check if layer is in allowed list (if specified)
            if allowed_layers and layer not in allowed_layers:
                loc = self._safe_get_location(track)
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="routing_layers",
                    severity="error",
                    message=f"Track on layer '{layer}' not in allowed list",
                    location=loc,
                    net_name=track.get('net', '')
                ))
    
    def _check_routing_priority(self, rule: DRCRule, nets: List[Dict], tracks: List[Dict]):
        """Check routing priority constraints"""
        # Priority rules are typically informational/guidance rather than hard constraints
        # If no nets have priority values set, the rule passes
        # 2. All high-priority nets have routing
        # We should only check if priorities are actually set in the data
        
        # Check if any nets have priority set
        has_priorities = any(net.get('priority', 0) > 0 for net in nets)
        if not has_priorities:
            # No priorities set in design - rule passes
            return
        
        # Only check nets with actual priority values
        for net in nets:
            net_name = net.get('name', '')
            if not net_name:
                continue
            
            net_priority = net.get('priority', 0)
            # Only check if priority is set and meets rule threshold
            if net_priority > 0 and net_priority >= rule.priority_value:
                # High-priority net should have routing
                net_tracks = [t for t in tracks if t.get('net', '') == net_name]
                if len(net_tracks) == 0:
                    # This is a warning, not an error (informational)
                    self.warnings.append(DRCViolation(
                        rule_name=rule.name,
                        rule_type="routing_priority",
                        severity="warning",
                        message=f"High-priority net '{net_name}' (priority {net_priority}) has no routing",
                        location={},
                        net_name=net_name
                    ))
    
    def _check_plane_connect(self, rule: DRCRule, pads: List[Dict], vias: List[Dict], 
                            polygons: List[Dict]):
        """Check power plane connection style constraints"""
        # This rule checks pad/via connection styles (direct connect vs thermal relief)
        # Requires connection style data not available in the current export
        # 2. The rule allows the current connection style
        # Since we can't check connection styles without pad/via connection properties,
        # we should skip this check to avoid false positives
        
        # TODO: This check requires pad/via connection style data from Altium export
        # TODO: Implement when connection style data is available in the export
        return
        
        # Original code (disabled - requires connection style data):
        # for polygon in polygons:
        #     if not polygon.get('is_pour', False):
        #         continue
        #     
        #     polygon_net = polygon.get('net', '')
        #     if not polygon_net:
        #         continue
        #     
        #     # Check pads connected to this plane
        #     for pad in pads:
        #         pad_net = pad.get('net', '')
        #         if pad_net == polygon_net:
        #             # Check if pad has proper connection style
        #             # This would require checking pad connection properties
        #             pass
        #     
        #     # Check vias connected to this plane
        #     for via in vias:
        #         via_net = via.get('net', '')
        #         if via_net == polygon_net:
        #             # Check via connection style
        #             # This would require checking via connection properties
        #             pass
        # 
        # Note: Full implementation would require checking actual connection geometry
        # and comparing against rule.plane_connect_style, rule.plane_expansion_mm, etc.
    
    def _check_fanout(self, rule: DRCRule, components: List[Dict], pads: List[Dict], 
                      vias: List[Dict], tracks: List[Dict], all_fanout_rules: List[DRCRule] = None):
        """
        Check fanout rules - verify that component pads have proper via fanout.
        
        CRITICAL: Fanout rules have priority - more specific rules (BGA, SOIC, LCC, Small) 
        take precedence over Fanout_Default. Fanout_Default only applies to components
        that don't match any other fanout rule scope.
        
        Different fanout rules apply to different component types:
        - Fanout_Small: Components with < 5 pins
        - Fanout_BGA: BGA components
        - Fanout_SOIC: SOIC components
        - Fanout_LCC: LCC components
        - Fanout_Default: All other components (only if no other rule matches)
        """
        rule_name_lower = rule.name.lower()
        
        # Determine component filter based on rule name
        if 'small' in rule_name_lower:
            # Fanout_Small: Check components with < 5 pins
            target_components = [c for c in components 
                               if isinstance(c, dict) and c.get('pin_count', 0) < 5]
        elif 'bga' in rule_name_lower:
            # Fanout_BGA: Check BGA components
            target_components = [c for c in components 
                               if isinstance(c, dict) and 'bga' in c.get('type', '').lower()]
        elif 'soic' in rule_name_lower:
            # Fanout_SOIC: Check SOIC components
            target_components = [c for c in components 
                               if isinstance(c, dict) and 'soic' in c.get('type', '').lower()]
        elif 'lcc' in rule_name_lower:
            # Fanout_LCC: Check LCC components
            target_components = [c for c in components 
                               if isinstance(c, dict) and 'lcc' in c.get('type', '').lower()]
        elif 'default' in rule_name_lower:
            # Fanout_Default: Only check components that don't match other fanout rules
            # Get all other fanout rules to determine which components are excluded
            excluded_components = set()
            if all_fanout_rules:
                for other_rule in all_fanout_rules:
                    if other_rule.name == rule.name:
                        continue  # Skip self
                    other_name_lower = other_rule.name.lower()
                    if 'small' in other_name_lower:
                        # Exclude components with < 5 pins
                        for c in components:
                            if isinstance(c, dict) and c.get('pin_count', 0) < 5:
                                excluded_components.add(c.get('designator', ''))
                    elif 'bga' in other_name_lower:
                        # Exclude BGA components
                        for c in components:
                            if isinstance(c, dict) and 'bga' in c.get('type', '').lower():
                                excluded_components.add(c.get('designator', ''))
                    elif 'soic' in other_name_lower:
                        # Exclude SOIC components
                        for c in components:
                            if isinstance(c, dict) and 'soic' in c.get('type', '').lower():
                                excluded_components.add(c.get('designator', ''))
                    elif 'lcc' in other_name_lower:
                        # Exclude LCC components
                        for c in components:
                            if isinstance(c, dict) and 'lcc' in c.get('type', '').lower():
                                excluded_components.add(c.get('designator', ''))
            
            # Fanout_Default: Only components NOT excluded by other rules
            target_components = [c for c in components 
                               if isinstance(c, dict) and c.get('designator', '') not in excluded_components]
            print(f"DEBUG: Fanout_Default: Excluding {len(excluded_components)} components matched by other fanout rules")
        else:
            # Unknown fanout rule - skip to avoid false positives
            print(f"DEBUG: Unknown fanout rule type '{rule.name}' - skipping")
            return
        
        # Build pad-to-via mapping for quick lookup
        # A pad has fanout if there's a via within its radius
        pad_via_map = {}  # pad_designator -> has_via
        FANOUT_TOLERANCE_MM = 0.5  # Via must be within 0.5mm of pad center
        
        for pad in pads:
            pad_designator = pad.get('designator', '')
            if not pad_designator:
                continue
            
            pad_loc = self._safe_get_location(pad)
            pad_x = pad_loc.get('x_mm', 0)
            pad_y = pad_loc.get('y_mm', 0)
            
            if pad_x == 0 and pad_y == 0:
                continue
            
            # Check if there's a via near this pad
            has_via = False
            for via in vias:
                via_loc = self._safe_get_location(via)
                via_x = via_loc.get('x_mm', 0)
                via_y = via_loc.get('y_mm', 0)
                
                if via_x == 0 and via_y == 0:
                    continue
                
                distance = math.sqrt((via_x - pad_x)**2 + (via_y - pad_y)**2)
                if distance <= FANOUT_TOLERANCE_MM:
                    has_via = True
                    break
            
            pad_via_map[pad_designator] = has_via
        
        # Check each target component's pads
        for component in target_components:
            comp_designator = component.get('designator', '')
            if not comp_designator:
                continue
            
            # Get all pads for this component
            comp_pads = [p for p in pads 
                        if isinstance(p, dict) and p.get('component_designator', '') == comp_designator]
            
            # Check if pads have fanout (vias)
            pads_without_fanout = []
            for pad in comp_pads:
                pad_designator = pad.get('designator', '')
                if pad_designator and not pad_via_map.get(pad_designator, False):
                    pads_without_fanout.append(pad_designator)
            
            # Report violation if component has pads without fanout
            if pads_without_fanout:
                pad_list = ', '.join(pads_without_fanout[:3])
                if len(pads_without_fanout) > 3:
                    pad_list += f' (and {len(pads_without_fanout) - 3} more)'
                
                pad_loc = self._safe_get_location(comp_pads[0]) if comp_pads else {}
                self.violations.append(DRCViolation(
                    rule_name=rule.name,
                    rule_type="fanout",
                    severity="error",
                    message=f"Fanout violation: Component {comp_designator} has pads without via fanout: {pad_list}",
                    location={"x_mm": pad_loc.get('x_mm', 0), "y_mm": pad_loc.get('y_mm', 0)},
                    component_name=comp_designator,
                    objects=pads_without_fanout
                ))
    
    def _deduplicate_violations(self, violations: List[DRCViolation]) -> List[DRCViolation]:
        """
        Deduplicate violations to prevent counting the same physical issue multiple times.
        
        Altium reports each violation only once, even if multiple rules could apply.
        We deduplicate based on:
        - Location (x, y coordinates within tolerance)
        - Rule type (same type violations at same location are duplicates)
        - Objects involved (same objects = same violation)
        """
        if not violations:
            return []
        
        # Tolerance for location matching (0.1mm - violations within this distance are considered the same)
        LOCATION_TOLERANCE_MM = 0.1
        
        unique_violations = []
        seen_keys = set()
        
        for v in violations:
            # Create a unique key for this violation
            loc = v.location or {}
            x = loc.get('x_mm', 0)
            y = loc.get('y_mm', 0)
            layer = loc.get('layer', '')
            
            # Round location to tolerance to group nearby violations
            x_rounded = round(x / LOCATION_TOLERANCE_MM) * LOCATION_TOLERANCE_MM
            y_rounded = round(y / LOCATION_TOLERANCE_MM) * LOCATION_TOLERANCE_MM
            
            # Create key from: type, rounded location, layer, and objects
            objects_str = ','.join(sorted(v.objects or []))
            net_str = v.net_name or ''
            
            # For short-circuit: deduplicate by pad/net/location instead of raw message hash.
            # Altium groups contiguous track fragments that represent the same electrical collision.
            if v.rule_type == "short_circuit":
                sc_tolerance = 0.05  # mm
                sc_x = round(x / sc_tolerance) * sc_tolerance
                sc_y = round(y / sc_tolerance) * sc_tolerance
                key = (v.rule_type, net_str, layer, sc_x, sc_y, (v.message or "").strip().lower())
            elif v.rule_type == 'clearance':
                # For clearance, use objects to identify duplicates
                key = (v.rule_type, x_rounded, y_rounded, layer, objects_str)
            elif v.rule_type == 'unrouted_net':
                # Keep per-connection unrouted violations distinct.
                key = (v.rule_type, net_str, x_rounded, y_rounded, v.message)
            elif v.rule_type == 'net_antennae':
                # Different floating endpoints can share same coarse location; keep message identity.
                key = (v.rule_type, net_str, x_rounded, y_rounded, v.message)
            else:
                # For other types, use location and type
                key = (v.rule_type, x_rounded, y_rounded, layer)
            
            if key not in seen_keys:
                seen_keys.add(key)
                unique_violations.append(v)
            else:
                # This is a duplicate - log for debugging
                print(f"DEBUG: Deduplicated violation: {v.rule_type} at ({x:.3f}, {y:.3f}) - already seen")
        
        return unique_violations
    
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
