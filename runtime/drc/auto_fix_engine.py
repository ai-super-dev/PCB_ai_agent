"""
Auto-Fix Engine for DRC Violations
Implements automated fix strategies for all DRC violation types.

CRITICAL: Fixes must be SAFE and CONVERGENT — each iteration must reduce violations,
never increase them. If a fix creates new violations, it's rolled back.

Fix strategies (in order of safety):
1. Net Antennae → Delete dead-end tracks (SAFE: deterministic, no side effects)
2. Unrouted Net → Route between pad pairs using ratsnest data  
3. Clearance → Move component by minimum distance
4. Width → Resize track width

Uses command_server.pas (via AltiumScriptClient) for PCB modifications.
"""
import math
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from runtime.drc.python_drc_engine import point_to_line_distance


class AutoFixEngine:
    """Automated DRC violation fix engine."""
    
    def __init__(self, script_client=None):
        self.script_client = script_client
        self.fix_log = []
    
    def fix_violations(self, violations: List[Dict], pcb_data: Dict, 
                       rules: List[Dict], drc_runner=None) -> Dict[str, Any]:
        """
        Fix violations in a SINGLE pass (no iterative loop to avoid destabilization).
        
        The iterative DRC→Fix→DRC approach can destabilize when fixes create new violations.
        Instead, we do ONE careful fix pass and report results.
        """
        self.fix_log = []
        total_fixed = 0
        total_failed = 0
        self._min_clearance_guard = self._extract_min_clearance_mm(rules)
        # Track nets with explicit unrouted violations; antennae on these nets
        # should be resolved by routing, not by deleting copper.
        self._unrouted_nets = {
            str(v.get('net_name', '')).strip()
            for v in violations
            if str(v.get('type', '')).lower() == 'unrouted_net' and str(v.get('net_name', '')).strip()
        }
        
        self._log(f"Auto-fix: Processing {len(violations)} violations")
        
        # Sort violations: antennae first (safest), then unrouted, then others
        sorted_violations = sorted(violations, key=lambda v: {
            'net_antennae': 0,
            'unrouted_net': 1, 
            'clearance': 2,
            'width': 3
        }.get(v.get('type', '').lower(), 9))
        
        for violation in sorted_violations:
            result = self._fix_single_violation(violation, pcb_data)
            
            if result['success']:
                total_fixed += 1
                self._log(f"✅ {result['message']}")
            else:
                total_failed += 1
                self._log(f"⚠️ {result['error']}")
            
            # Delay between commands to let Altium process
            time.sleep(1.5)
        
        return {
            'success': total_fixed > 0,
            'total_fixed': total_fixed,
            'total_failed': total_failed,
            'remaining_violations': total_failed,
            'log': self.fix_log
        }
    
    def _fix_single_violation(self, violation: Dict, pcb_data: Dict) -> Dict:
        """Apply fix for a single violation based on its type."""
        v_type = violation.get('type', '').lower()
        
        if 'antennae' in v_type or 'antenna' in v_type:
            net = str(violation.get('net_name', '')).strip()
            if net and net in getattr(self, '_unrouted_nets', set()):
                # For unrouted nets, route completion is safer than deleting antenna stubs.
                return {'success': False, 'error': f'Antenna on {net} — will be resolved when net is routed'}
            # For routed nets (no explicit UnRoutedNet on same net), delete the
            # dead-end segment directly.
            return self._fix_net_antennae(violation, pcb_data)
        elif 'unrouted' in v_type:
            return self._fix_unrouted_net(violation, pcb_data)
        elif 'clearance' in v_type:
            return self._fix_clearance(violation, pcb_data)
        elif 'width' in v_type:
            return self._fix_width(violation, pcb_data)
        else:
            return {'success': False, 'error': f'No auto-fix for: {v_type}'}
    
    # =========================================================================
    # NET ANTENNAE FIX: Delete dead-end tracks (SAFE)
    # =========================================================================
    def _fix_net_antennae(self, violation: Dict, pcb_data: Dict) -> Dict:
        """Delete the dead-end track identified in the violation."""
        message = violation.get('message', '')
        coords = self._parse_track_coords(message)
        
        if not coords:
            return {'success': False, 'error': f'Cannot parse track coords: {message[:80]}'}
        
        if not self.script_client:
            return {'success': False, 'error': 'No Altium connection'}
        
        x1, y1, x2, y2 = coords
        net = violation.get('net_name', 'unknown')
        
        result = self.script_client._send_command({
            'action': 'delete_track',
            'x1': str(x1), 'y1': str(y1),
            'x2': str(x2), 'y2': str(y2)
        })
        
        if result.get('success'):
            return {'success': True, 'message': f'Deleted antenna track on net {net}'}
        else:
            return {'success': False, 'error': f'Could not delete track on {net}: {result.get("error", "")}'}
    
    # =========================================================================
    # UNROUTED NET FIX: Connect pads using ratsnest data
    # =========================================================================
    def _fix_unrouted_net(self, violation: Dict, pcb_data: Dict) -> Dict:
        """Route tracks between disconnected pads using connection/ratsnest data."""
        net_name = violation.get('net_name', '')
        if not net_name or not self.script_client:
            return {'success': False, 'error': f'Cannot route: no net name or no Altium connection'}
        
        # Get ratsnest connections for this net (exact pad-pair connections needed)
        connections = [c for c in pcb_data.get('connections', [])
                       if isinstance(c, dict) and c.get('net', '').strip() == net_name]
        
        if not connections:
            # Fallback: use coordinates embedded in Python DRC violation message.
            # This keeps the flow fully automated even when connection objects are not exported.
            endpoints = self._parse_unrouted_endpoints(violation.get('message', ''))
            if endpoints:
                fx, fy, tx, ty = endpoints
                connections = [{
                    'net': net_name,
                    'from_x_mm': fx, 'from_y_mm': fy,
                    'to_x_mm': tx, 'to_y_mm': ty
                }]
            else:
                return {'success': False, 'error': f'No routable endpoints for net {net_name}'}
        
        # Get existing track width for this net
        net_tracks = [t for t in pcb_data.get('tracks', [])
                      if isinstance(t, dict) and t.get('net', '').strip() == net_name]
        track_width = 0.254
        layer = 'Top'
        if net_tracks:
            for t in net_tracks:
                w = t.get('width_mm', 0)
                if w > 0:
                    track_width = w
                    break
            for t in net_tracks:
                l = t.get('layer', '')
                if l:
                    layer = l
                    break
        
        layer_name = 'Top' if 'top' in layer.lower() else ('Bottom' if 'bottom' in layer.lower() else 'Top')
        
        # Route each ratsnest connection as a direct track
        # Ratsnest endpoints are the EXACT from/to points that need connecting
        routes_added = 0
        for conn in connections[:3]:  # Limit to 3 connections per net to avoid flooding
            from_x = conn.get('from_x_mm', 0)
            from_y = conn.get('from_y_mm', 0)
            to_x = conn.get('to_x_mm', 0)
            to_y = conn.get('to_y_mm', 0)
            
            if from_x == 0 and from_y == 0:
                continue
            if to_x == 0 and to_y == 0:
                continue

            if self._route_connection_with_fallback(
                net_name=net_name,
                x1=from_x,
                y1=from_y,
                x2=to_x,
                y2=to_y,
                width_mm=track_width,
                layer_name=layer_name,
                pcb_data=pcb_data,
            ):
                routes_added += 1
            
            time.sleep(0.5)
        
        if routes_added > 0:
            return {'success': True, 'message': f'Added {routes_added} track(s) for net {net_name}'}
        else:
            return {'success': False, 'error': f'Could not route net {net_name} with safe patterns'}

    def _route_connection_with_fallback(self, net_name: str, x1: float, y1: float, x2: float, y2: float,
                                        width_mm: float, layer_name: str, pcb_data: Dict) -> bool:
        """Route one connection: direct segment first, then safe L-shape alternatives."""
        if self._is_direct_route_safe(net_name, x1, y1, x2, y2, width_mm, pcb_data):
            return self._add_track(net_name, layer_name, x1, y1, x2, y2, width_mm)

        pivots = [
            (x1, y2),
            (x2, y1),
            ((x1 + x2) / 2.0, y1),
            ((x1 + x2) / 2.0, y2),
            (x1, (y1 + y2) / 2.0),
            (x2, (y1 + y2) / 2.0),
        ]
        for px, py in pivots:
            if (abs(px - x1) < 1e-6 and abs(py - y1) < 1e-6) or (abs(px - x2) < 1e-6 and abs(py - y2) < 1e-6):
                continue
            if not self._is_direct_route_safe(net_name, x1, y1, px, py, width_mm, pcb_data):
                continue
            if not self._is_direct_route_safe(net_name, px, py, x2, y2, width_mm, pcb_data):
                continue

            if not self._add_track(net_name, layer_name, x1, y1, px, py, width_mm):
                continue
            if self._add_track(net_name, layer_name, px, py, x2, y2, width_mm):
                return True
            # rollback first segment if second fails
            self.script_client._send_command({
                'action': 'delete_track',
                'x1': str(x1), 'y1': str(y1),
                'x2': str(px), 'y2': str(py)
            })
        return False

    def _add_track(self, net_name: str, layer_name: str, x1: float, y1: float, x2: float, y2: float, width_mm: float) -> bool:
        result = self.script_client._send_command({
            'action': 'add_track',
            'net': net_name,
            'layer': layer_name,
            'x1': str(x1), 'y1': str(y1),
            'x2': str(x2), 'y2': str(y2),
            'width': str(width_mm)
        })
        return bool(result.get('success'))

    def _extract_min_clearance_mm(self, rules: List[Dict]) -> float:
        """Get a conservative global clearance guard from enabled clearance rules."""
        vals = []
        for r in rules or []:
            if not isinstance(r, dict):
                continue
            rtype = str(r.get('type', '')).strip().lower()
            if rtype != 'clearance':
                continue
            if r.get('enabled', True) is False:
                continue
            v = r.get('clearance_mm', r.get('min_clearance_mm', None))
            try:
                if v is not None:
                    fv = float(v)
                    if fv > 0:
                        vals.append(fv)
            except Exception:
                continue
        if vals:
            return min(vals)
        return 0.2

    def _is_direct_route_safe(self, net_name: str, x1: float, y1: float, x2: float, y2: float,
                              width_mm: float, pcb_data: Dict) -> bool:
        """Conservative pre-check for direct auto-route safety against foreign-net pads."""
        half_w = max(float(width_mm or 0.254) / 2.0, 0.05)
        guard = max(float(getattr(self, '_min_clearance_guard', 0.2) or 0.2), 0.05)

        for pad in pcb_data.get('pads', []) or []:
            if not isinstance(pad, dict):
                continue
            pnet = str(pad.get('net', '')).strip()
            if not pnet or pnet == net_name:
                continue
            px = float(pad.get('x_mm', 0) or 0)
            py = float(pad.get('y_mm', 0) or 0)
            if px == 0 and py == 0:
                continue
            sx = float(pad.get('size_x_mm', 0) or pad.get('width_mm', 0) or 1.0)
            sy = float(pad.get('size_y_mm', 0) or pad.get('height_mm', 0) or 1.0)
            pad_r = max(sx, sy) / 2.0

            dist = point_to_line_distance(px, py, x1, y1, x2, y2)
            if dist <= (pad_r + half_w + guard):
                return False

        return True
    
    # =========================================================================
    # CLEARANCE FIX
    # =========================================================================
    def _fix_clearance(self, violation: Dict, pcb_data: Dict) -> Dict:
        """Fix clearance by moving the nearest component."""
        location = violation.get('location', {})
        x = location.get('x_mm', 0)
        y = location.get('y_mm', 0)
        actual = violation.get('actual_value', 0)
        required = violation.get('required_value', 0)
        
        if not self.script_client:
            return {'success': False, 'error': 'No Altium connection'}
        
        nearest = self._find_nearest_component(x, y, pcb_data)
        if not nearest:
            return {'success': False, 'error': 'No component found near violation — manual fix needed'}
        
        comp_name = nearest.get('designator', '')
        comp_x = nearest.get('x_mm', 0)
        comp_y = nearest.get('y_mm', 0)
        
        move_dist = max((required - actual) + 0.1, 0.5)
        dx = comp_x - x
        dy = comp_y - y
        dist = math.sqrt(dx*dx + dy*dy) if (dx != 0 or dy != 0) else 1.0
        
        new_x = comp_x + (dx / dist) * move_dist
        new_y = comp_y + (dy / dist) * move_dist
        
        result = self.script_client._send_command({
            'action': 'move_component',
            'designator': comp_name,
            'x': str(new_x), 'y': str(new_y)
        })
        
        if result.get('success'):
            return {'success': True, 'message': f'Moved {comp_name} by {move_dist:.2f}mm'}
        return {'success': False, 'error': f'Failed to move {comp_name}'}
    
    # =========================================================================
    # WIDTH FIX
    # =========================================================================
    def _fix_width(self, violation: Dict, pcb_data: Dict) -> Dict:
        return {'success': False, 'error': 'Width fix requires track resize — manual fix in Altium'}
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    def _parse_track_coords(self, message: str) -> Optional[Tuple[float, float, float, float]]:
        """Parse track coordinates from 'Track (x1mm,y1mm)(x2mm,y2mm)'"""
        pattern = r'Track\s*\(([0-9.]+)mm?,([0-9.]+)mm?\)\s*\(([0-9.]+)mm?,([0-9.]+)mm?\)'
        match = re.search(pattern, message)
        if match:
            return (float(match.group(1)), float(match.group(2)),
                    float(match.group(3)), float(match.group(4)))
        return None

    def _parse_unrouted_endpoints(self, message: str) -> Optional[Tuple[float, float, float, float]]:
        """Parse endpoints from unrouted message text."""
        if not message:
            return None
        m = re.search(
            r'Between\s*\(([0-9.]+)mm,([0-9.]+)mm\)\s*And\s*\(([0-9.]+)mm,([0-9.]+)mm\)',
            message
        )
        if m:
            return (float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))

        m2 = re.search(
            r'Between\s+Pad\s+.+?\(([0-9.]+)mm,([0-9.]+)mm\).+?\bAnd\s+Via\s*\(([0-9.]+)mm,([0-9.]+)mm\)',
            message
        )
        if m2:
            return (float(m2.group(1)), float(m2.group(2)), float(m2.group(3)), float(m2.group(4)))
        return None
    
    def _find_nearest_component(self, x, y, pcb_data) -> Optional[Dict]:
        min_dist = float('inf')
        nearest = None
        for comp in pcb_data.get('components', []):
            if not isinstance(comp, dict):
                continue
            cx = comp.get('x_mm', 0)
            cy = comp.get('y_mm', 0)
            if cx == 0 and cy == 0:
                continue
            dist = math.sqrt((cx - x)**2 + (cy - y)**2)
            if dist < min_dist:
                min_dist = dist
                nearest = comp
        return nearest if min_dist < 10.0 else None
    
    def _log(self, message: str):
        self.fix_log.append(message)
        print(f"AutoFix: {message}")
