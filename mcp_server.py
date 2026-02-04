"""
MCP Server for Altium Designer
Uses Python file reader for PCB data (NO Altium scripts needed for reading!)

Features:
- Direct PCB file reading (olefile)
- Routing module integration
- DRC module integration
- Artifact store for versioning
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs
import os
import time
import threading
from pathlib import Path

# Import our modules
from tools.altium_file_reader import AltiumFileReader
from adapters.altium.importer import AltiumImporter
from core.artifacts.store import ArtifactStore
from core.artifacts.models import Artifact, ArtifactType, ArtifactMeta, SourceEngine, CreatedBy
from core.ir.cir import ConstraintIR, Rule, RuleType, RuleScope, RuleParams
from runtime.routing.routing_module import RoutingModule
from runtime.drc.drc_module import DRCModule

# Try to import script client (for applying changes to Altium)
try:
    from tools.altium_script_client import AltiumScriptClient
    SCRIPT_CLIENT_AVAILABLE = True
except ImportError:
    SCRIPT_CLIENT_AVAILABLE = False


class AltiumMCPServer:
    """MCP Server with Python file reader and routing/DRC modules"""
    
    def __init__(self):
        self.store = ArtifactStore()
        self.reader = AltiumFileReader()
        self.importer = AltiumImporter()
        self.routing = RoutingModule(self.store, enable_drc_validation=True)
        self.drc = DRCModule(self.store)
        
        # Script client for applying changes to Altium (optional)
        self.script_client = None
        if SCRIPT_CLIENT_AVAILABLE:
            self.script_client = AltiumScriptClient()
        
        # Current loaded PCB
        self.current_pcb_path = None
        self.current_artifact_id = None
        self.current_gir = None
        self.current_design_rules = None
        
        # Default constraint artifact
        self.constraint_artifact_id = None
        self._create_default_constraints()
    
    def _create_default_constraints(self):
        """Create default design rule constraints"""
        cir = ConstraintIR(
            rules=[
                Rule(
                    id="rule-clearance",
                    type=RuleType.CLEARANCE,
                    scope=RuleScope(),
                    params=RuleParams(min_clearance_mm=0.2),
                    enabled=True
                ),
                Rule(
                    id="rule-trace-width",
                    type=RuleType.TRACE_WIDTH,
                    scope=RuleScope(),
                    params=RuleParams(min_width_mm=0.15, preferred_width_mm=0.25),
                    enabled=True
                ),
            ],
            netclasses=[]
        )
        
        constraint = Artifact(
            type=ArtifactType.CONSTRAINT_RULESET,
            data=cir.model_dump(),
            meta=ArtifactMeta(source_engine=SourceEngine.ALTIUM, created_by=CreatedBy.ENGINE)
        )
        constraint = self.store.create(constraint)
        self.constraint_artifact_id = constraint.id
    
    def load_pcb(self, pcb_path: str) -> dict:
        """Load a PCB file directly using Python file reader (includes design rules!)"""
        try:
            # Read PCB file (includes rules from Rules6/Data stream!)
            raw_data = self.reader.read_pcb(pcb_path)
            
            if 'error' in raw_data:
                return {"error": raw_data['error']}
            
            # Create G-IR
            gir = self.importer.import_pcb_direct(pcb_path)
            
            if not gir:
                return {"error": "Failed to create G-IR from PCB file"}
            
            # Create artifact
            board = self.importer.create_pcb_board_artifact(gir, pcb_path)
            board = self.store.create(board)
            
            # Extract and import design rules from file reader
            rules_from_file = raw_data.get('rules', [])
            design_rules = None
            if rules_from_file:
                cir = self.importer.import_design_rules_from_file_reader(rules_from_file)
                if cir:
                    # Create constraint artifact
                    constraint = self.importer.create_constraint_ruleset_artifact(cir, pcb_path)
                    constraint = self.store.create(constraint)
                    self.constraint_artifact_id = constraint.id
                    self.current_design_rules = cir
                    design_rules = {
                        "rule_count": len(cir.rules),
                        "clearance_rules": len([r for r in cir.rules if r.type == RuleType.CLEARANCE]),
                        "width_rules": len([r for r in cir.rules if r.type == RuleType.TRACE_WIDTH]),
                        "via_rules": len([r for r in cir.rules if r.type == RuleType.VIA])
                    }
            
            # Store current state
            self.current_pcb_path = pcb_path
            self.current_artifact_id = board.id
            self.current_gir = gir
            
            stats = raw_data.get('statistics', {})
            
            # Auto-analyze on load
            analysis = self._auto_analyze_pcb(gir, stats)
            
            result = {
                "success": True,
                "file": Path(pcb_path).name,
                "artifact_id": board.id,
                "version": board.version,
                "layers": len(gir.board.layers),
                "statistics": stats,
                "analysis": analysis,
                "message": f"PCB loaded: {Path(pcb_path).name}"
            }
            
            # Add design rules info if extracted
            if design_rules:
                result["design_rules"] = design_rules
                result["message"] += " (with design rules!)"
            
            return result
        except Exception as e:
            import traceback
            return {"error": f"{str(e)}\n{traceback.format_exc()}"}
    
    def load_from_altium_export(self, pcb_info_path: str = None, drc_report_path: str = None) -> dict:
        """
        Load from Altium-exported JSON files.
        
        This uses REAL data exported by running scripts inside Altium Designer:
        - pcb_info.json: From exportPCBInfo.pas
        - verification_report.json: From runDRC.pas
        
        Args:
            pcb_info_path: Path to pcb_info.json (default: project folder)
            drc_report_path: Path to verification_report.json (optional)
            
        Returns:
            dict with loaded data and analysis
        """
        try:
            base_path = Path(__file__).parent
            
            # Default paths - check for Altium export first
            if pcb_info_path is None:
                # Try altium_pcb_info.json first (from command server export)
                altium_export = base_path / "altium_pcb_info.json"
                if altium_export.exists():
                    pcb_info_path = altium_export
                else:
                    # Also check for timestamped export files (altium_export_*.json)
                    export_files = sorted(base_path.glob("altium_export_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if export_files:
                        pcb_info_path = export_files[0]  # Use most recent export file
                    else:
                        pcb_info_path = base_path / "pcb_info.json"
            else:
                pcb_info_path = Path(pcb_info_path)
            
            if drc_report_path is None:
                drc_report_path = base_path / "verification_report.json"
            else:
                drc_report_path = Path(drc_report_path)
            
            # Load PCB info
            if not pcb_info_path.exists():
                return {
                    "error": f"PCB info file not found: {pcb_info_path}",
                    "hint": "Run exportPCBInfo.pas in Altium Designer first"
                }
            
            with open(pcb_info_path, 'r', encoding='utf-8') as f:
                pcb_data = json.load(f)
            
            # Check if it's from Altium (has export_source)
            source = pcb_data.get('export_source', 'python_file_reader')
            
            # Import to G-IR
            gir = self.importer.import_pcb_info(str(pcb_info_path))
            
            if not gir:
                return {"error": "Failed to create G-IR from Altium export"}
            
            # Create artifact
            board = self.importer.create_pcb_board_artifact(gir, str(pcb_info_path))
            board = self.store.create(board)
            
            # Store current state
            self.current_pcb_path = str(pcb_info_path)
            self.current_artifact_id = board.id
            self.current_gir = gir
            
            # Get statistics
            stats = pcb_data.get('statistics', {})
            
            # Extract and store design rules from export
            rules = pcb_data.get('rules', [])
            if rules:
                self.current_design_rules = rules
            
            # Auto-analyze
            analysis = self._auto_analyze_pcb(gir, stats)
            
            # Load DRC violations if available
            drc_violations = []
            if drc_report_path.exists():
                try:
                    with open(drc_report_path, 'r', encoding='utf-8') as f:
                        drc_data = json.load(f)
                    drc_violations = drc_data.get('violations', [])
                    
                    # Add Altium DRC violations to analysis
                    for viol in drc_violations:
                        analysis['issues'].append({
                            "severity": viol.get('severity', 'error'),
                            "type": "altium_drc",
                            "message": viol.get('description', viol.get('rule', 'DRC Violation')),
                            "rule": viol.get('rule', 'Unknown'),
                            "location": viol.get('location', {})
                        })
                except Exception as e:
                    print(f"Warning: Could not load DRC report: {e}")
            
            return {
                "success": True,
                "source": "altium_designer" if source == "altium_designer" else "python_file_reader",
                "file": pcb_data.get('file_name', 'Unknown'),
                "artifact_id": board.id,
                "version": board.version,
                "statistics": stats,
                "analysis": analysis,
                "drc_violations": len(drc_violations),
                "message": f"Loaded from Altium export: {pcb_data.get('file_name', 'Unknown')}"
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def _auto_analyze_pcb(self, gir, stats: dict) -> dict:
        """
        Analyze PCB and provide board statistics.
        
        NOTE: We provide statistics only, not DRC violations.
        The Python file reader cannot accurately detect:
        - Unrouted nets (tracks are in binary format without net info)
        - Polygon pour connectivity (ground/power planes)
        - True design rule violations
        
        For DRC, users should run Altium Designer's built-in DRC.
        """
        issues = []
        recommendations = []
        
        # Categorize nets for informational purposes
        power_nets = []
        signal_nets = []
        ground_nets = []
        
        for net in gir.nets:
            net_name = net.name.upper()
            if any(p in net_name for p in ['GND', 'GROUND', 'VSS', 'AGND', 'DGND']):
                ground_nets.append(net)
            elif any(p in net_name for p in ['VCC', 'VDD', '+', 'PWR', 'POWER', 'VIN']):
                power_nets.append(net)
            else:
                signal_nets.append(net)
        
        # Provide informational summary (not DRC)
        component_count = len(gir.footprints)
        if component_count > 100:
            recommendations.append({
                "priority": "info",
                "action": "review_placement",
                "description": f"Complex board with {component_count} components"
            })
        
        # Always recommend running Altium DRC
        recommendations.append({
            "priority": "info",
            "action": "run_altium_drc",
            "description": "Run Design Rule Check in Altium Designer for accurate violation detection"
        })
        
        # Return board statistics (not DRC violations)
        return {
            "summary": {
                "total_issues": 0,  # We don't report false DRC violations
                "errors": 0,
                "warnings": 0,
                "power_nets": len(power_nets),
                "ground_nets": len(ground_nets),
                "signal_nets": len(signal_nets),
                "components": component_count,
                "tracks": len(gir.tracks),
                "vias": len(gir.vias)
            },
            "issues": [],  # Empty - use Altium DRC for real violations
            "recommendations": recommendations,
            "note": "For DRC violations, use Altium Designer: Tools → Design Rule Check"
        }
    
    def get_current_artifact(self) -> dict:
        """Get current artifact info"""
        if not self.current_artifact_id:
            return {"error": "No PCB loaded"}
        
        return {
            "artifact_id": self.current_artifact_id,
            "file": Path(self.current_pcb_path).name if self.current_pcb_path else None,
            "folder": f"artifacts/{self.current_artifact_id}/",
            "files": [
                f"artifacts/{self.current_artifact_id}/index.json",
                f"artifacts/{self.current_artifact_id}/v1.json",
                f"artifacts/{self.current_artifact_id}/current.json"
            ]
        }
    
    def get_pcb_info(self) -> dict:
        """Get current PCB info with full details for AI agent"""
        if not self.current_pcb_path:
            return {"error": "No PCB loaded. Use /load endpoint first."}
        
        try:
            raw_data = self.reader.read_pcb(self.current_pcb_path)
            
            # Build comprehensive response for AI agent
            return {
                "file_name": Path(self.current_pcb_path).name,
                "file": Path(self.current_pcb_path).name,
                "artifact_id": self.current_artifact_id,
                
                # Board size
                "board_size": raw_data.get('board_size', {}),
                
                # Layer info
                "layers": raw_data.get('layers', []),
                "layer_count": raw_data.get('layer_count', 0),
                
                # Statistics
                "statistics": raw_data.get('statistics', {}),
                
                # Components with details
                "components": raw_data.get('components', []),
                
                # Nets with details
                "nets": raw_data.get('nets', []),
                
                # Design rules (use stored rules or extract from data)
                "rules": self.current_design_rules if self.current_design_rules else self._extract_design_rules(raw_data),
                
                # Sample tracks/vias for context
                "tracks": raw_data.get('tracks', [])[:10],
                "vias": raw_data.get('vias', [])[:10],
                "pads": raw_data.get('pads', [])[:10],
                
                # Metadata
                "metadata": raw_data.get('metadata', {})
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _extract_design_rules(self, raw_data: dict) -> list:
        """Extract design rules from raw PCB data"""
        rules = []
        
        # Get rules from export
        exported_rules = raw_data.get('rules', [])
        if exported_rules:
            return exported_rules
        
        # If no rules in export, try to get from Altium export file
        try:
            altium_export = Path("altium_pcb_info.json")
            if altium_export.exists():
                with open(altium_export, 'r', encoding='utf-8') as f:
                    export_data = json.load(f)
                    rules = export_data.get('rules', [])
                    if rules:
                        return rules
        except:
            pass
        
        # Default rules if none found
        return [
            {
                "name": "Default Clearance",
                "type": "clearance",
                "clearance_mm": 0.2,
                "enabled": True
            },
            {
                "name": "Default Width",
                "type": "width",
                "min_width_mm": 0.15,
                "preferred_width_mm": 0.25,
                "enabled": True
            },
            {
                "name": "Default Via",
                "type": "via",
                "min_hole_mm": 0.2,
                "enabled": True
            }
        ]
    
    def generate_routing_suggestions(self, filter_type: str = None) -> dict:
        """
        Generate intelligent routing suggestions based on actual PCB analysis.
        
        Args:
            filter_type: Optional filter - "power", "unrouted", "signal", etc.
        """
        if not self.current_artifact_id or not self.current_gir:
            return {"error": "No PCB loaded"}
        
        try:
            suggestions = []
            
            # Analyze which nets are actually routed (have tracks)
            routed_net_ids = {track.net_id for track in self.current_gir.tracks}
            
            # Get components connected to each net
            net_to_components = {}
            for footprint in self.current_gir.footprints:
                for pad in footprint.pads:
                    if pad.net_id:
                        if pad.net_id not in net_to_components:
                            net_to_components[pad.net_id] = []
                        net_to_components[pad.net_id].append(footprint.ref)
            
            # Analyze each net
            for net in self.current_gir.nets:
                net_name = net.name.upper()
                net_id = net.id
                
                # Check if net is routed
                is_routed = net_id in routed_net_ids
                connected_components = net_to_components.get(net_id, [])
                component_count = len(connected_components)
                
                # Skip routed nets unless specifically asking for all
                if is_routed and filter_type != "all":
                    continue
                
                # Determine net type and priority
                is_power = any(p in net_name for p in ['VCC', 'VDD', 'VSS', 'GND', 'GROUND', '+', '-', 'POWER', 'PWR', 'VIN', 'VOUT'])
                is_clock = 'CLK' in net_name or 'CLOCK' in net_name
                is_signal = any(p in net_name for p in ['DATA', 'SDA', 'SCL', 'TX', 'RX', 'MOSI', 'MISO', 'SCK', 'CS'])
                
                # Apply filter if specified
                if filter_type:
                    if filter_type == "power" and not is_power:
                        continue
                    elif filter_type == "unrouted" and is_routed:
                        continue
                    elif filter_type == "signal" and not is_signal:
                        continue
                
                # Determine priority
                if is_power:
                    priority = "HIGH"
                    if not is_routed:
                        recommendation = f"🔴 URGENT: Power net '{net.name}' is UNROUTED! Route with wide traces (0.5-1.0mm) for power integrity."
                    else:
                        recommendation = f"✅ Power net '{net.name}' is routed. Consider widening traces if current width < 0.5mm."
                    width_suggestion = "0.5-1.0mm"
                    layer_suggestion = "Top layer or dedicated power plane"
                elif is_clock:
                    priority = "HIGH"
                    if not is_routed:
                        recommendation = f"🔴 URGENT: Clock net '{net.name}' is UNROUTED! Route as short as possible with matched lengths."
                    else:
                        recommendation = f"✅ Clock net '{net.name}' is routed. Verify length matching if differential pair."
                    width_suggestion = "0.2-0.3mm (controlled impedance)"
                    layer_suggestion = "Top layer, avoid vias"
                elif is_signal:
                    priority = "MEDIUM"
                    if not is_routed:
                        recommendation = f"⚠️ Signal net '{net.name}' needs routing. Route with controlled impedance, avoid vias when possible."
                    else:
                        recommendation = f"✅ Signal net '{net.name}' is routed. Check for crosstalk with adjacent traces."
                    width_suggestion = "0.15-0.25mm"
                    layer_suggestion = "Top or bottom layer"
                else:
                    priority = "NORMAL"
                    if not is_routed:
                        recommendation = f"📋 Net '{net.name}' needs routing. Standard routing with minimum clearance."
                    else:
                        recommendation = f"✅ Net '{net.name}' is routed."
                    width_suggestion = "0.15-0.2mm (default)"
                    layer_suggestion = "Any available layer"
                
                # Build suggestion
                suggestion = {
                    "net": net.name,
                    "net_id": net_id,
                    "priority": priority,
                    "status": "routed" if is_routed else "unrouted",
                    "recommendation": recommendation,
                    "width_suggestion": width_suggestion,
                    "layer_suggestion": layer_suggestion,
                    "connected_components": component_count,
                    "component_list": connected_components[:5]  # First 5 components
                }
                
                suggestions.append(suggestion)
            
            # Sort by priority and routed status (unrouted first)
            priority_order = {"HIGH": 0, "MEDIUM": 1, "NORMAL": 2}
            suggestions.sort(key=lambda x: (
                priority_order.get(x["priority"], 3),
                0 if x["status"] == "unrouted" else 1,  # Unrouted first
                -x.get("connected_components", 0)  # More connections = higher priority
            ))
            
            # Generate summary
            total_nets = len(self.current_gir.nets)
            routed_count = len(routed_net_ids)
            unrouted_count = total_nets - routed_count
            power_nets = [s for s in suggestions if s["priority"] == "HIGH" and any(p in s["net"].upper() for p in ['VCC', 'VDD', 'GND', '+', '-', 'POWER'])]
            
            summary = f"Found {len(suggestions)} net(s) needing attention. {unrouted_count} unrouted, {routed_count} routed."
            if power_nets:
                unrouted_power = [s for s in power_nets if s["status"] == "unrouted"]
                if unrouted_power:
                    summary += f" ⚠️ {len(unrouted_power)} power net(s) UNROUTED - route immediately!"
            
            return {
                "success": True,
                "suggestions": suggestions[:20],  # Limit to top 20
                "count": len(suggestions),
                "total_nets": total_nets,
                "routed_nets": routed_count,
                "unrouted_nets": unrouted_count,
                "summary": summary
            }
        except Exception as e:
            import traceback
            return {"error": f"{str(e)}\n{traceback.format_exc()}"}
    
    def route_net(self, net_id: str, start: list, end: list, layer: str = "L1", width: float = 0.25) -> dict:
        """Route a net"""
        if not self.current_artifact_id:
            return {"error": "No PCB loaded"}
        
        try:
            patch = self.routing.route_net(
                artifact_id=self.current_artifact_id,
                net_id=net_id,
                start_pos=start,
                end_pos=end,
                layer_id=layer,
                width_mm=width
            )
            
            if patch:
                return {
                    "success": True,
                    "message": f"Route created for {net_id}",
                    "operation": patch.ops[0].op if patch.ops else None,
                    "version": f"{patch.from_version} -> {patch.to_version}"
                }
            else:
                return {"error": "Failed to create route"}
        except Exception as e:
            return {"error": str(e)}
    
    def place_via(self, net_id: str, position: list, layers: list = None, drill: float = 0.3) -> dict:
        """Place a via"""
        if not self.current_artifact_id:
            return {"error": "No PCB loaded"}
        
        layers = layers or ["L1", "L4"]
        
        try:
            patch = self.routing.place_via(
                artifact_id=self.current_artifact_id,
                net_id=net_id,
                position=position,
                layers=layers,
                drill_mm=drill
            )
            
            if patch:
                return {
                    "success": True,
                    "message": f"Via placed for {net_id}",
                    "position": position,
                    "layers": layers
                }
            else:
                return {"error": "Failed to place via"}
        except Exception as e:
            return {"error": str(e)}
    
    def run_drc(self) -> dict:
        """
        Run DRC check.
        
        NOTE: Python file reader cannot detect all connectivity (e.g., polygon pours,
        power planes). For accurate DRC, use Altium Designer's built-in DRC.
        
        This provides basic analysis only - not a replacement for Altium DRC.
        """
        if not self.current_artifact_id or not self.current_gir:
            return {"error": "No PCB loaded"}
        
        try:
            # Board statistics
            stats = {
                "components": len(self.current_gir.footprints),
                "nets": len(self.current_gir.nets),
                "tracks": len(self.current_gir.tracks),
                "vias": len(self.current_gir.vias)
            }
            
            # We cannot accurately detect unrouted nets because:
            # 1. Track binary data doesn't include net associations reliably
            # 2. Polygon pours (copper planes) provide connectivity we can't see
            # 3. Power/ground planes connect nets without individual tracks
            
            # Return honest result - recommend using Altium DRC
            return {
                "success": True,
                "violations": [],
                "summary": {
                    "total": 0,
                    "errors": 0,
                    "warnings": 0
                },
                "message": "Board analysis complete. For accurate DRC, run Design Rule Check in Altium Designer (Tools → Design Rule Check).",
                "stats": stats,
                "note": "Python file reader provides board statistics. Altium Designer DRC provides accurate violation detection."
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def _old_run_drc(self) -> dict:
        """Original DRC using DRC module (kept for reference)"""
        try:
            violations_artifact = self.drc.run_drc(
                self.current_artifact_id,
                self.constraint_artifact_id
            )
            
            if violations_artifact:
                violations = self.drc.get_violations(violations_artifact.id)
                return {
                    "success": True,
                    "violations_artifact_id": violations_artifact.id,
                    "violation_count": len(violations),
                    "violations": violations
                }
            else:
                return {"error": "DRC failed"}
        except Exception as e:
            return {"error": str(e)}
    
    # ==================== ALTIUM SCRIPT CLIENT ====================
    # For applying changes to Altium via command_server.pas
    # Small commands (~100 bytes) - no memory issues
    
    def apply_to_altium(self, action: str, **kwargs) -> dict:
        """Apply a change to Altium via script server"""
        if not SCRIPT_CLIENT_AVAILABLE or not self.script_client:
            return {"error": "Script client not available"}
        
        try:
            if action == "add_track":
                return self.script_client.add_track(
                    kwargs.get("net", ""),
                    kwargs.get("x1", 0), kwargs.get("y1", 0),
                    kwargs.get("x2", 10), kwargs.get("y2", 10),
                    kwargs.get("width", 0.25)
                )
            elif action == "add_via":
                return self.script_client.add_via(
                    kwargs.get("x", 0), kwargs.get("y", 0),
                    kwargs.get("net", ""),
                    kwargs.get("hole", 0.3), kwargs.get("diameter", 0.6)
                )
            elif action == "move_component":
                return self.script_client.move_component(
                    kwargs.get("designator", "U1"),
                    kwargs.get("x", 0), kwargs.get("y", 0),
                    kwargs.get("rotation", 0)
                )
            elif action == "ping":
                if self.script_client.ping():
                    return {"success": True, "message": "Script server is running"}
                else:
                    return {"error": "Script server not responding"}
            else:
                return {"error": f"Unknown action: {action}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_altium_status(self) -> dict:
        """Get Altium script client status"""
        connected = False
        if SCRIPT_CLIENT_AVAILABLE and self.script_client:
            try:
                connected = self.script_client.ping()
            except:
                pass
        
        return {
            "script_client_available": SCRIPT_CLIENT_AVAILABLE,
            "script_server_running": connected,
            "how_to_start": "Run command_server.pas in Altium: DXP → Run Script → StartServer",
            "features": [
                "add_track - Add track to PCB",
                "add_via - Add via to PCB",
                "move_component - Move component"
            ] if SCRIPT_CLIENT_AVAILABLE else []
        }


# Global server instance
mcp_server = AltiumMCPServer()


class MCPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for MCP Server"""
    
    def _send_json(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self._send_json({}, 200)
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        if path == "/health":
            self._send_json({
                "status": "healthy",
                "method": "python_file_reader",
                "pcb_loaded": mcp_server.current_pcb_path is not None,
                "current_file": Path(mcp_server.current_pcb_path).name if mcp_server.current_pcb_path else None
            })
        
        elif path == "/status" or path == "/altium/status":
            self._send_json({
                "connected": True,
                "method": "python_file_reader",
                "message": "MCP Server ready. Use Python file reader - NO Altium scripts needed!",
                "pcb_loaded": mcp_server.current_pcb_path is not None,
                "current_file": Path(mcp_server.current_pcb_path).name if mcp_server.current_pcb_path else None,
                "artifact_id": mcp_server.current_artifact_id
            })
        
        elif path == "/pcb/info" or path == "/altium/pcb/info":
            self._send_json(mcp_server.get_pcb_info())
        
        elif path == "/pcb/artifact" or path == "/artifact":
            self._send_json(mcp_server.get_current_artifact())
        
        elif path.startswith("/routing/suggestions"):
            # Parse query parameters
            filter_type = None
            if "?" in path:
                query_string = path.split("?")[1]
                params = parse_qs(query_string)
                filter_type = params.get("filter", [None])[0]
            self._send_json(mcp_server.generate_routing_suggestions(filter_type=filter_type))
        
        elif path == "/drc/run":
            self._send_json(mcp_server.run_drc())
        
        elif path == "/altium/status":
            self._send_json(mcp_server.get_altium_status())
        
        elif path == "/altium/ping":
            self._send_json(mcp_server.apply_to_altium("ping"))
        
        else:
            self._send_json({"error": "Not found", "endpoints": [
                "/health",
                "/status",
                "/pcb/info - Get loaded PCB information",
                "/routing/suggestions - Get routing suggestions",
                "/drc/run - Run DRC check",
                "POST /pcb/load - Load .PcbDoc file",
                "POST /routing/route - Create route",
                "POST /routing/via - Place via",
                "--- OPTIONAL: Apply to Altium ---",
                "/altium/status - Check script server status",
                "/altium/ping - Test script server connection",
                "POST /altium/apply - Apply action to Altium"
            ]}, 404)
    
    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        try:
            data = json.loads(body.decode()) if body else {}
        except:
            data = {}
        
        if path == "/pcb/load" or path == "/altium/pcb/load":
            pcb_path = data.get("path")
            if not pcb_path:
                self._send_json({"error": "Missing 'path' parameter"}, 400)
                return
            
            result = mcp_server.load_pcb(pcb_path)
            self._send_json(result)
        
        elif path == "/pcb/load-altium-export":
            # Load from Altium-exported JSON files
            pcb_info_path = data.get("pcb_info_path")  # Optional, defaults to pcb_info.json
            drc_report_path = data.get("drc_report_path")  # Optional
            
            result = mcp_server.load_from_altium_export(pcb_info_path, drc_report_path)
            self._send_json(result)
        
        elif path == "/routing/route":
            net_id = data.get("net_id", "net-1")
            start = data.get("start", [0, 0])
            end = data.get("end", [10, 10])
            layer = data.get("layer", "L1")
            width = data.get("width", 0.25)
            
            result = mcp_server.route_net(net_id, start, end, layer, width)
            self._send_json(result)
        
        elif path == "/routing/via":
            net_id = data.get("net_id", "net-1")
            position = data.get("position", [5, 5])
            layers = data.get("layers", ["L1", "L4"])
            drill = data.get("drill", 0.3)
            
            result = mcp_server.place_via(net_id, position, layers, drill)
            self._send_json(result)
        
        # Altium script server endpoints (optional - for applying changes)
        elif path == "/altium/apply":
            action = data.get("action", "ping")
            result = mcp_server.apply_to_altium(action, **data)
            self._send_json(result)
        
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def log_message(self, format, *args):
        """Custom logging"""
        print(f"[MCP] {format % args}")


def run_server(port=8765):
    """Run the MCP server"""
    server = HTTPServer(("", port), MCPRequestHandler)
    
    print("=" * 60)
    print("EagilinsED MCP Server")
    print("=" * 60)
    print(f"Server: http://localhost:{port}")
    print()
    print("Endpoints:")
    print("  GET  /health              - Server health check")
    print("  GET  /status              - Connection status")
    print("  GET  /pcb/info            - Get PCB info")
    print("  GET  /routing/suggestions - Get routing suggestions")
    print("  GET  /drc/run             - Run DRC check")
    print()
    print("  POST /pcb/load            - Load PCB file")
    print("       {\"path\": \"path/to/file.PcbDoc\"}")
    print()
    print("  POST /routing/route       - Route a net")
    print("       {\"net_id\": \"net-1\", \"start\": [0,0], \"end\": [10,10]}")
    print()
    print("  POST /routing/via         - Place a via")
    print("       {\"net_id\": \"net-1\", \"position\": [5,5]}")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='EagilinsED MCP Server')
    parser.add_argument('--port', type=int, default=8765, help='Server port (default: 8765)')
    args = parser.parse_args()
    
    run_server(args.port)
