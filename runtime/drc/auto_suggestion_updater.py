"""
Automatic DRC Suggestion Updater
Automatically generates and updates suggestions based on DRC violations

Features:
- Monitors DRC violations
- Generates actionable suggestions
- Updates suggestions automatically when violations change
- Provides prioritized recommendations
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from core.ir.gir import GeometryIR
from core.ir.cir import ConstraintIR
import json


class AutoSuggestionUpdater:
    """
    Automatically generates and updates DRC suggestions
    
    This class:
    1. Analyzes DRC violations
    2. Generates actionable suggestions
    3. Updates suggestions when violations change
    4. Prioritizes suggestions by severity and impact
    """
    
    def __init__(self):
        self.suggestion_cache = {}  # Cache suggestions by violation set hash
        self.last_update_time = None
        
    def generate_suggestions(self, violations: List[Dict[str, Any]], 
                           gir: Optional[GeometryIR] = None,
                           rules: Optional[ConstraintIR] = None) -> List[Dict[str, Any]]:
        """
        Generate suggestions from DRC violations
        
        Args:
            violations: List of DRC violations
            gir: Optional Geometry IR for context
            rules: Optional Constraint IR for context
            
        Returns:
            List of suggestion dictionaries with priority and actions
        """
        suggestions = []
        
        if not violations:
            return [{
                "type": "success",
                "priority": "low",
                "message": "No DRC violations found. Design passes all checks!",
                "action": None,
                "timestamp": datetime.utcnow().isoformat()
            }]
        
        # Group violations by type
        violations_by_type = self._group_violations_by_type(violations)
        
        # Generate suggestions for each violation type
        for v_type, v_list in violations_by_type.items():
            type_suggestions = self._generate_type_suggestions(v_type, v_list, gir, rules)
            suggestions.extend(type_suggestions)
        
        # Add general suggestions
        general_suggestions = self._generate_general_suggestions(violations, gir)
        suggestions.extend(general_suggestions)
        
        # Prioritize and sort suggestions
        suggestions = self._prioritize_suggestions(suggestions)
        
        return suggestions
    
    def _group_violations_by_type(self, violations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group violations by type"""
        grouped = {}
        for violation in violations:
            v_type = violation.get("type", "unknown")
            if v_type not in grouped:
                grouped[v_type] = []
            grouped[v_type].append(violation)
        return grouped
    
    def _generate_type_suggestions(self, v_type: str, violations: List[Dict[str, Any]],
                                  gir: Optional[GeometryIR], 
                                  rules: Optional[ConstraintIR]) -> List[Dict[str, Any]]:
        """Generate suggestions for a specific violation type"""
        suggestions = []
        count = len(violations)
        
        if v_type == "clearance":
            # Analyze clearance violations
            min_clearance = min(v.get("actual_clearance_mm", 0) for v in violations if v.get("actual_clearance_mm"))
            required_clearance = violations[0].get("required_clearance_mm", 0.2) if violations else 0.2
            
            if count > 10:
                suggestions.append({
                    "type": "clearance",
                    "priority": "high",
                    "message": f"Found {count} clearance violations. Minimum clearance is {required_clearance}mm, but some objects are as close as {min_clearance:.3f}mm.",
                    "action": "increase_clearance_rule",
                    "details": {
                        "violation_count": count,
                        "min_actual_mm": min_clearance,
                        "required_mm": required_clearance,
                        "suggested_clearance_mm": max(required_clearance, min_clearance * 1.2)
                    },
                    "fixes": [
                        "Increase minimum clearance rule",
                        "Review component placement",
                        "Adjust routing to maintain clearance"
                    ],
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                suggestions.append({
                    "type": "clearance",
                    "priority": "medium",
                    "message": f"Found {count} clearance violation(s). Review component placement and routing.",
                    "action": "review_clearance",
                    "details": {
                        "violation_count": count,
                        "locations": [v.get("location", {}) for v in violations[:5]]
                    },
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        elif v_type == "track_width":
            # Analyze track width violations
            min_width = min(v.get("actual_mm", 0) for v in violations if v.get("actual_mm"))
            required_width = violations[0].get("required_mm", 0.25) if violations else 0.25
            
            suggestions.append({
                "type": "track_width",
                "priority": "high" if count > 5 else "medium",
                "message": f"Found {count} track width violation(s). Some tracks are {min_width:.3f}mm, but minimum is {required_width}mm.",
                "action": "fix_track_widths",
                "details": {
                    "violation_count": count,
                    "min_actual_mm": min_width,
                    "required_mm": required_width
                },
                "fixes": [
                    "Increase track width to meet minimum",
                    "Review routing constraints",
                    "Check if minimum width rule is appropriate"
                ],
                "timestamp": datetime.utcnow().isoformat()
            })
        
        elif v_type == "via_drill":
            # Analyze via drill violations
            min_drill = min(v.get("actual_mm", 0) for v in violations if v.get("actual_mm"))
            required_drill = violations[0].get("required_mm", 0.2) if violations else 0.2
            
            suggestions.append({
                "type": "via_drill",
                "priority": "high",
                "message": f"Found {count} via drill violation(s). Some vias have {min_drill:.3f}mm drill, but minimum is {required_drill}mm.",
                "action": "fix_via_drills",
                "details": {
                    "violation_count": count,
                    "min_actual_mm": min_drill,
                    "required_mm": required_drill
                },
                "fixes": [
                    "Increase via drill size",
                    "Replace vias with larger drill size",
                    "Review via size rules"
                ],
                "timestamp": datetime.utcnow().isoformat()
            })
        
        elif v_type == "unrouted_net":
            # Analyze unrouted nets
            power_nets = [v for v in violations if any(p in v.get("net_name", "").upper() 
                                                       for p in ["VCC", "VDD", "GND", "POWER"])]
            
            if power_nets:
                suggestions.append({
                    "type": "unrouted_net",
                    "priority": "critical",
                    "message": f"Found {len(power_nets)} unrouted power/ground net(s) and {count - len(power_nets)} other unrouted net(s). Power nets must be routed!",
                    "action": "route_power_nets",
                    "details": {
                        "total_unrouted": count,
                        "power_nets": [v.get("net_name") for v in power_nets],
                        "other_nets": [v.get("net_name") for v in violations if v not in power_nets]
                    },
                    "fixes": [
                        "Route power and ground nets immediately",
                        "Use power planes if appropriate",
                        "Ensure adequate trace width for current capacity"
                    ],
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                suggestions.append({
                    "type": "unrouted_net",
                    "priority": "high",
                    "message": f"Found {count} unrouted net(s). These nets need routing to complete the design.",
                    "action": "route_nets",
                    "details": {
                        "unrouted_nets": [v.get("net_name") for v in violations[:10]]
                    },
                    "fixes": [
                        "Route all unrouted nets",
                        "Check for missing connections",
                        "Verify net connectivity"
                    ],
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        else:
            # Generic suggestion for other violation types
            suggestions.append({
                "type": v_type,
                "priority": "medium",
                "message": f"Found {count} {v_type} violation(s). Review and fix these issues.",
                "action": f"fix_{v_type}",
                "details": {
                    "violation_count": count,
                    "violations": violations[:5]  # First 5 for reference
                },
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return suggestions
    
    def _generate_general_suggestions(self, violations: List[Dict[str, Any]],
                                     gir: Optional[GeometryIR]) -> List[Dict[str, Any]]:
        """Generate general suggestions based on overall violation patterns"""
        suggestions = []
        
        total_violations = len(violations)
        error_count = sum(1 for v in violations if v.get("severity") == "error")
        warning_count = sum(1 for v in violations if v.get("severity") == "warning")
        
        # Overall health suggestion
        if total_violations == 0:
            suggestions.append({
                "type": "design_health",
                "priority": "low",
                "message": "Design passes all DRC checks! No violations found.",
                "action": None,
                "timestamp": datetime.utcnow().isoformat()
            })
        elif error_count == 0 and warning_count > 0:
            suggestions.append({
                "type": "design_health",
                "priority": "low",
                "message": f"Design has {warning_count} warning(s) but no errors. Review warnings for potential improvements.",
                "action": "review_warnings",
                "timestamp": datetime.utcnow().isoformat()
            })
        elif error_count > 0:
            suggestions.append({
                "type": "design_health",
                "priority": "high",
                "message": f"Design has {error_count} error(s) and {warning_count} warning(s). Fix errors before manufacturing.",
                "action": "fix_errors",
                "details": {
                    "error_count": error_count,
                    "warning_count": warning_count,
                    "total_violations": total_violations
                },
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Suggestion for rule review if many violations
        if total_violations > 20:
            suggestions.append({
                "type": "rule_review",
                "priority": "medium",
                "message": f"Found {total_violations} violations. Consider reviewing design rules - they may be too strict or the design needs adjustment.",
                "action": "review_design_rules",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return suggestions
    
    def _prioritize_suggestions(self, suggestions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prioritize suggestions by importance"""
        priority_order = {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3
        }
        
        # Sort by priority, then by violation count if available
        suggestions.sort(key=lambda s: (
            priority_order.get(s.get("priority", "medium"), 2),
            -s.get("details", {}).get("violation_count", 0)
        ))
        
        return suggestions
    
    def update_suggestions(self, old_violations: List[Dict[str, Any]],
                          new_violations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare old and new violations and return update information
        
        Args:
            old_violations: Previous violations
            new_violations: Current violations
            
        Returns:
            Dictionary with update information
        """
        old_count = len(old_violations)
        new_count = len(new_violations)
        
        # Create violation sets for comparison
        old_set = {self._violation_key(v) for v in old_violations}
        new_set = {self._violation_key(v) for v in new_violations}
        
        fixed = old_set - new_set
        new_issues = new_set - old_set
        
        return {
            "updated": True,
            "timestamp": datetime.utcnow().isoformat(),
            "old_count": old_count,
            "new_count": new_count,
            "fixed_count": len(fixed),
            "new_issues_count": len(new_issues),
            "improvement": new_count < old_count,
            "message": self._generate_update_message(old_count, new_count, len(fixed), len(new_issues))
        }
    
    def _violation_key(self, violation: Dict[str, Any]) -> str:
        """Create a unique key for a violation for comparison"""
        v_type = violation.get("type", "unknown")
        location = violation.get("location", {})
        if isinstance(location, dict):
            loc_str = f"{location.get('x_mm', 0):.2f},{location.get('y_mm', 0):.2f}"
        else:
            loc_str = str(location)
        return f"{v_type}:{loc_str}:{violation.get('message', '')[:50]}"
    
    def _generate_update_message(self, old_count: int, new_count: int, 
                                fixed: int, new_issues: int) -> str:
        """Generate human-readable update message"""
        if new_count == 0 and old_count > 0:
            return f"🎉 All violations fixed! Design now passes DRC."
        elif new_count < old_count:
            return f"✅ Improved: {fixed} violation(s) fixed, {new_issues} new issue(s). {new_count} violation(s) remaining."
        elif new_count > old_count:
            return f"⚠️  {new_issues} new violation(s) found. {fixed} previous issue(s) fixed. {new_count} total violation(s)."
        else:
            return f"📊 No change: {new_count} violation(s) remain."
    
    def get_suggestion_summary(self, suggestions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get a summary of suggestions"""
        if not suggestions:
            return {
                "total": 0,
                "by_priority": {},
                "by_type": {},
                "status": "no_suggestions"
            }
        
        by_priority = {}
        by_type = {}
        
        for s in suggestions:
            priority = s.get("priority", "medium")
            s_type = s.get("type", "unknown")
            
            by_priority[priority] = by_priority.get(priority, 0) + 1
            by_type[s_type] = by_type.get(s_type, 0) + 1
        
        return {
            "total": len(suggestions),
            "by_priority": by_priority,
            "by_type": by_type,
            "status": "active" if any(s.get("priority") in ["critical", "high"] for s in suggestions) else "normal"
        }
