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
                # Check PCB_Project folder first, then root
                altium_export = base_path / "PCB_Project" / "altium_pcb_info.json"
                if not altium_export.exists():
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
                
                # Full tracks/vias/pads data for DRC
                "tracks": raw_data.get('tracks', []),
                "vias": raw_data.get('vias', []),
                "pads": raw_data.get('pads', []),
                
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
            # Check PCB_Project folder first, then root
            altium_export = Path("PCB_Project") / "altium_pcb_info.json"
            if not altium_export.exists():
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
    
    def _format_rule_name_for_display(self, rule: Dict[str, Any]) -> str:
        """Format rule name with parameters in Altium style"""
        rule_name = rule.get('name', 'Unnamed Rule')
        rule_type = rule.get('type') or rule.get('kind', 'other')
        
        # Build parameter string
        params = []
        
        if rule_type == 'clearance':
            clearance = rule.get('clearance_mm', 0)
            if clearance > 0:
                params.append(f"Gap={clearance}mm")
            scope1 = rule.get('scope1', 'All')
            scope2 = rule.get('scope2', 'All')
            if scope1 != 'All' or scope2 != 'All':
                if rule.get('scope1_polygon'):
                    params.append(f"InNamedPolygon('{rule['scope1_polygon']}')")
                params.append(f"({scope1}),({scope2})")
            else:
                params.append("(All),(All)")
        
        elif rule_type == 'width':
            min_w = rule.get('min_width_mm', 0)
            max_w = rule.get('max_width_mm', 0)
            pref_w = rule.get('preferred_width_mm', 0)
            if min_w > 0 or max_w > 0 or pref_w > 0:
                width_str = f"Min={min_w}mm"
                if max_w > 0:
                    width_str += f" Max={max_w}mm"
                if pref_w > 0:
                    width_str += f" Preferred={pref_w}mm"
                params.append(width_str)
            params.append("(All)")
        
        elif rule_type in ['via', 'hole_size']:
            min_h = rule.get('min_hole_mm', 0)
            max_h = rule.get('max_hole_mm', 0)
            if min_h > 0 or max_h > 0:
                hole_str = f"Min={min_h}mm"
                if max_h > 0:
                    hole_str += f" Max={max_h}mm"
                params.append(hole_str)
            params.append("(All)")
        
        elif rule_type == 'short_circuit':
            allowed = rule.get('allowed', False)
            params.append(f"Allowed={'Yes' if allowed else 'No'}")
            params.append("(All),(All)")
        
        elif rule_type == 'unrouted_net':
            params.append("((All))")
        
        elif rule_type == 'modified_polygon':
            allow_mod = rule.get('allow_modified', False)
            allow_shelved = rule.get('allow_shelved', False)
            params.append(f"Allow modified: {'Yes' if allow_mod else 'No'}")
            params.append(f"Allow shelved: {'Yes' if allow_shelved else 'No'}")
        
        elif rule_type == 'plane_connect':
            expansion = rule.get('expansion_mm', 0)
            cond_width = rule.get('conductor_width_mm', 0)
            air_gap = rule.get('air_gap_mm', 0)
            entries = rule.get('conductor_count', 0)
            if expansion > 0:
                params.append(f"Expansion={expansion}mm")
            if cond_width > 0:
                params.append(f"Conductor Width={cond_width}mm")
            if air_gap > 0:
                params.append(f"Air Gap={air_gap}mm")
            if entries > 0:
                params.append(f"Entries={entries}")
            params.append("(All)")
        
        elif rule_type == 'hole_to_hole_clearance':
            gap = rule.get('gap_mm', 0)
            if gap > 0:
                params.append(f"Gap={gap}mm")
            params.append("(All).(All)")
        
        elif rule_type == 'solder_mask_sliver':
            gap = rule.get('gap_mm', 0)
            if gap > 0:
                params.append(f"Gap={gap}mm")
            params.append("(All),(All)")
        
        elif rule_type == 'silk_to_solder_mask':
            clearance = rule.get('clearance_mm', 0)
            params.append(f"Clearance={clearance}mm")
            params.append("(IsPad). (All)")
        
        elif rule_type == 'silk_to_silk':
            clearance = rule.get('clearance_mm', 0)
            params.append(f"Clearance={clearance}mm")
            params.append("(All),(All).")
        
        elif rule_type == 'height':
            min_h = rule.get('min_height_mm', 0)
            max_h = rule.get('max_height_mm', 0)
            pref_h = rule.get('preferred_height_mm', 0)
            if min_h > 0 or max_h > 0 or pref_h > 0:
                height_str = f"Min={min_h}mm"
                if max_h > 0:
                    height_str += f" Max={max_h}mm"
                if pref_h > 0:
                    height_str += f" Preferred={pref_h}mm"
                params.append(height_str)
            params.append("(All).")
        
        elif rule_type == 'net_antennae':
            tolerance = rule.get('tolerance_mm', 0)
            params.append(f"Tolerance={tolerance}mm")
            params.append("(All)")
        
        # Build final formatted name
        if params:
            return f"{rule_name} ({', '.join(params)})"
        else:
            return rule_name
    
    def get_design_rules(self) -> dict:
        """
        Get all design rules from the current PCB or from Altium export file
        
        Returns:
            Dictionary with rules information
        """
        try:
            # PRIORITY 1: Get rules from Altium export file (most complete)
            # This has ALL rules exported directly from Altium
            rules = []
            
            # Check for Altium export file (most recent)
            base_path = Path(".")
            altium_export_files = []
            
            # Collect ALL possible export files from all locations
            # PRIORITY: Check PCB_Project folder first (where files are now stored)
            project_path = Path("PCB_Project")
            if project_path.exists():
                if (project_path / "altium_pcb_info.json").exists():
                    altium_export_files.append(project_path / "altium_pcb_info.json")
                altium_export_files.extend(project_path.glob("altium_export_*.json"))
            
            # Also check root directory (for backward compatibility)
            if (base_path / "altium_pcb_info.json").exists():
                altium_export_files.append(base_path / "altium_pcb_info.json")
            
            # Check for timestamped export files in root (altium_export_*.json)
            altium_export_files.extend(base_path.glob("altium_export_*.json"))
            
            # CRITICAL: Sort ALL files by modification time (most recent first)
            # This ensures we always use the newest file, regardless of location
            altium_export_files = sorted(
                altium_export_files,
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True
            )
            
            # Try to read from most recent export file
            export_file_used = None
            for export_file in altium_export_files:
                try:
                    # Try reading with UTF-8 first, fallback to latin-1 if needed
                    try:
                        with open(export_file, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                    except:
                        with open(export_file, 'r', encoding='latin-1', errors='replace') as f:
                            content = f.read()
                    
                    # Try to parse JSON, with better error handling
                    try:
                        export_data = json.loads(content)
                    except json.JSONDecodeError as je:
                        # Try to fix common JSON issues
                        # Fix invalid escape sequences
                        import re
                        # Replace invalid backslashes (but keep valid ones)
                        fixed_content = re.sub(r'\\(?![\\"/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', content)
                        try:
                            export_data = json.loads(fixed_content)
                        except:
                            print(f"JSON decode error in {export_file.name} at line {je.lineno}: {je.msg}")
                            raise
                    
                    exported_rules = export_data.get('rules', [])
                    if exported_rules and len(exported_rules) > 0:
                        rules = exported_rules
                        export_file_used = export_file
                        print(f"Loaded {len(rules)} rules from {export_file.name}")
                        
                        # CRITICAL: If rules have 0.0 values, try to get actual values from PCB file
                        # The DelphiScript API can't read rule values, but Python file reader can!
                        pcb_file_path = export_data.get('file_name', '')
                        if pcb_file_path:
                            # Fix path separators for cross-platform compatibility
                            pcb_file_path = pcb_file_path.replace('\\', os.sep).replace('/', os.sep)
                            
                            # Check if we need to merge values (if any clearance rule has 0.0)
                            needs_merge = any(
                                r.get('clearance_mm', 0) == 0.0 or 
                                r.get('min_width_mm', 0) == 0.0 or
                                r.get('min_hole_mm', 0) == 0.0
                                for r in rules
                            )
                            
                            if needs_merge and os.path.exists(pcb_file_path):
                                try:
                                    # Read actual rule values from PCB file using Python file reader
                                    pcb_data = self.reader.read_pcb(pcb_file_path)
                                    if pcb_data and 'rules' in pcb_data:
                                        file_reader_rules = pcb_data['rules']
                                        # Create a lookup by rule name (case-insensitive)
                                        file_reader_lookup = {r.get('name', '').upper(): r for r in file_reader_rules}
                                        
                                        # Merge values from file reader into exported rules
                                        merged_count = 0
                                        for rule in rules:
                                            rule_name = rule.get('name', '').upper()
                                            if rule_name in file_reader_lookup:
                                                file_rule = file_reader_lookup[rule_name]
                                                
                                                # CRITICAL: Update rule type from file reader (handles custom-named rules)
                                                # This ensures LBBZHUANYONG, KZBZHUANYONG etc. are correctly typed
                                                file_rule_type = file_rule.get('type', '')
                                                if file_rule_type and file_rule_type != 'other':
                                                    rule['type'] = file_rule_type
                                                    # Also update category based on type
                                                    if file_rule_type == 'clearance':
                                                        rule['category'] = 'Electrical'
                                                    elif file_rule_type in ['width', 'via', 'routing_corners', 'routing_topology', 'routing_priority', 'routing_layers']:
                                                        rule['category'] = 'Routing'
                                                    elif file_rule_type == 'short_circuit' or file_rule_type == 'unrouted_net':
                                                        rule['category'] = 'Electrical'
                                                    elif 'mask' in file_rule_type:
                                                        rule['category'] = 'Mask'
                                                    elif file_rule_type == 'plane':
                                                        rule['category'] = 'Plane'
                                                    elif file_rule_type == 'testpoint':
                                                        rule['category'] = 'Testpoint'
                                                    elif file_rule_type == 'smt':
                                                        rule['category'] = 'SMT'
                                                
                                                # Update clearance value if it's 0.0
                                                if rule.get('type') == 'clearance':
                                                    if rule.get('clearance_mm', 0) == 0.0:
                                                        new_value = file_rule.get('clearance_mm', 0.0)
                                                        if new_value > 0:
                                                            rule['clearance_mm'] = new_value
                                                            merged_count += 1
                                                
                                                # Update width values if they're 0.0
                                                elif rule.get('type') == 'width':
                                                    if rule.get('min_width_mm', 0) == 0.0:
                                                        new_val = file_rule.get('min_width_mm', 0.0)
                                                        if new_val > 0:
                                                            rule['min_width_mm'] = new_val
                                                            merged_count += 1
                                                    if rule.get('preferred_width_mm', 0) == 0.0:
                                                        new_val = file_rule.get('preferred_width_mm', 0.0)
                                                        if new_val > 0:
                                                            rule['preferred_width_mm'] = new_val
                                                    if rule.get('max_width_mm', 0) == 0.0:
                                                        new_val = file_rule.get('max_width_mm', 0.0)
                                                        if new_val > 0:
                                                            rule['max_width_mm'] = new_val
                                                
                                                # Update via values
                                                elif rule.get('type') == 'via':
                                                    if rule.get('min_hole_mm', 0) == 0.0:
                                                        new_val = file_rule.get('min_hole_mm', 0.0)
                                                        if new_val > 0:
                                                            rule['min_hole_mm'] = new_val
                                                            merged_count += 1
                                                    if rule.get('max_hole_mm', 0) == 0.0:
                                                        new_val = file_rule.get('max_hole_mm', 0.0)
                                                        if new_val > 0:
                                                            rule['max_hole_mm'] = new_val
                                                    if rule.get('min_diameter_mm', 0) == 0.0:
                                                        new_val = file_rule.get('min_diameter_mm', 0.0)
                                                        if new_val > 0:
                                                            rule['min_diameter_mm'] = new_val
                                                    if rule.get('max_diameter_mm', 0) == 0.0:
                                                        new_val = file_rule.get('max_diameter_mm', 0.0)
                                                        if new_val > 0:
                                                            rule['max_diameter_mm'] = new_val
                                                    # Merge preferred values
                                                    if 'preferred_hole_mm' in file_rule:
                                                        rule['preferred_hole_mm'] = file_rule['preferred_hole_mm']
                                                    if 'preferred_diameter_mm' in file_rule:
                                                        rule['preferred_diameter_mm'] = file_rule['preferred_diameter_mm']
                                                    if 'via_style' in file_rule:
                                                        rule['via_style'] = file_rule['via_style']
                                                
                                                # Update routing corners
                                                elif rule.get('type') == 'routing_corners':
                                                    # Merge all routing corner parameters
                                                    for key in ['corner_style', 'setback_mm', 'setback_to_mm']:
                                                        if key in file_rule:
                                                            rule[key] = file_rule[key]
                                                            merged_count += 1
                                                
                                                # Update routing topology
                                                elif rule.get('type') == 'routing_topology':
                                                    if 'topology' in file_rule:
                                                        rule['topology'] = file_rule['topology']
                                                        merged_count += 1
                                                
                                                # Update routing priority
                                                elif rule.get('type') == 'routing_priority':
                                                    if 'priority_value' in file_rule:
                                                        rule['priority_value'] = file_rule['priority_value']
                                                        merged_count += 1
                                                
                                                # Update short circuit allowed status
                                                elif rule.get('type') == 'short_circuit':
                                                    if 'allowed' not in rule or rule.get('allowed') is None:
                                                        rule['allowed'] = file_rule.get('allowed', False)
                                                        merged_count += 1
                                                
                                                # Update mask expansion
                                                elif rule.get('type') == 'paste_mask':
                                                    # Merge all paste mask parameters
                                                    for key in ['expansion_mm', 'expansion_bottom_mm', 'tented_top', 'tented_bottom', 
                                                               'use_paste_smd', 'use_top_paste_th', 'use_bottom_paste_th', 'measurement_method']:
                                                        if key in file_rule:
                                                            rule[key] = file_rule[key]
                                                            merged_count += 1
                                                elif rule.get('type') == 'solder_mask':
                                                    # Merge all solder mask parameters
                                                    for key in ['expansion_mm', 'expansion_bottom_mm', 'tented_top', 'tented_bottom']:
                                                        if key in file_rule:
                                                            rule[key] = file_rule[key]
                                                            merged_count += 1
                                                # Update diff pairs routing
                                                elif rule.get('type') == 'diff_pairs_routing' or (rule.get('name', '').upper() == 'DIFFPAIRSROUTING'):
                                                    # Merge all diff pairs parameters
                                                    for key in ['min_width_mm', 'max_width_mm', 'preferred_width_mm', 
                                                               'min_gap_mm', 'max_gap_mm', 'preferred_gap_mm', 'max_uncoupled_length_mm']:
                                                        if key in file_rule:
                                                            rule[key] = file_rule[key]
                                                            merged_count += 1
                                                    rule['type'] = 'diff_pairs_routing'  # Ensure correct type
                                                    rule['category'] = 'Routing'  # Ensure correct category
                                                
                                                # Update plane clearance
                                                elif rule.get('type') == 'plane_clearance' or (rule.get('name', '').upper() == 'PLANECLEARANCE'):
                                                    # Always merge plane clearance (even if exported value is 0.0)
                                                    new_value = file_rule.get('clearance_mm', 0.0)
                                                    if new_value > 0:
                                                        rule['clearance_mm'] = new_value
                                                        rule['type'] = 'plane_clearance'  # Ensure correct type
                                                        rule['category'] = 'Plane'  # Ensure correct category
                                                        merged_count += 1
                                                
                                                # Update plane connect
                                                elif rule.get('type') == 'plane_connect' or (rule.get('name', '').upper() == 'PLANECONNECT'):
                                                    # Merge all plane connect parameters
                                                    for key in ['connect_style', 'expansion_mm', 'air_gap_mm', 'conductor_width_mm', 'conductor_count']:
                                                        if key in file_rule:
                                                            rule[key] = file_rule[key]
                                                            merged_count += 1
                                                    rule['type'] = 'plane_connect'  # Ensure correct type
                                                    rule['category'] = 'Plane'  # Ensure correct category
                                                
                                                # Update component clearance
                                                elif rule.get('type') == 'component_clearance':
                                                    if rule.get('clearance_mm', 0) == 0.0:
                                                        new_value = file_rule.get('clearance_mm', 0.0)
                                                        if new_value > 0:
                                                            rule['clearance_mm'] = new_value
                                                            merged_count += 1
                                                
                                                # CRITICAL: Merge ALL other fields from file reader that are missing or 0
                                                # This ensures we get all parameters (corner_style, topology, via_style, preferred values, etc.)
                                                excluded_keys = {'name', 'kind', 'enabled', 'priority', 'scope', 'type'}
                                                for key, value in file_rule.items():
                                                    if key not in excluded_keys:
                                                        # If the rule doesn't have this key, or it's 0/empty, use file reader value
                                                        if key not in rule:
                                                            rule[key] = value
                                                            if not (isinstance(value, (int, float)) and value == 0):
                                                                merged_count += 1
                                                        elif isinstance(rule.get(key), (int, float)) and rule.get(key) == 0:
                                                            if isinstance(value, (int, float)) and value != 0:
                                                                rule[key] = value
                                                                merged_count += 1
                                                        elif not rule.get(key) and value:
                                                            rule[key] = value
                                                            merged_count += 1
                                        
                                        if merged_count > 0:
                                            print(f"Merged {merged_count} rule values from PCB file reader")
                                        else:
                                            print(f"Warning: Found {len(file_reader_rules)} rules in PCB file but could not merge values (names may not match)")
                                except Exception as e:
                                    print(f"Could not merge rule values from PCB file: {e}")
                                    # Continue with exported rules even if merge fails
                        
                        break
                except Exception as e:
                    print(f"Error reading {export_file}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # If we found rules from export, use them (don't fall back to constraint artifact)
            # The constraint artifact only has auto-generated rules, not the real Altium rules
            if rules:
                # Rules found from Altium export - use them!
                print(f"Using {len(rules)} rules from Altium export file")
            elif altium_export_files:
                # Export file exists but has no rules - might be empty or corrupted
                return {
                    "success": False,
                    "error": "Export file found but contains no rules",
                    "message": f"Found export file but it has no rules. Please re-export from Altium:\n1. In Altium Designer, run command_server.pas\n2. Execute 'ExportPCBInfo' procedure\n3. Make sure PCB has rules defined (Design → Rules)",
                    "rules": [],
                    "rules_by_category": {},
                    "statistics": {"total": 0, "enabled": 0, "by_category": {}, "by_type": {}}
                }
            else:
                # No export file found - user needs to export from Altium
                return {
                    "success": False,
                    "error": "No Altium export file found",
                    "message": "Please export PCB info from Altium Designer first:\n1. In Altium Designer: File → Run Script → command_server.pas\n2. Execute: 'ExportPCBInfo' procedure\n3. This creates altium_pcb_info.json with ALL rules from your PCB",
                    "rules": [],
                    "rules_by_category": {},
                    "statistics": {"total": 0, "enabled": 0, "by_category": {}, "by_type": {}}
                }
            
            # PRIORITY 2: Only use constraint artifact if NO export file exists at all
            # (This should rarely happen - export file should always exist if user exported)
            if not rules and self.constraint_artifact_id:
                try:
                    cir = self.drc.get_cir_from_artifact(self.constraint_artifact_id)
                    if cir:
                        # Convert C-IR rules to display format
                        for rule in cir.rules:
                            rule_dict = {
                                "name": rule.id,
                                "type": rule.type.value,
                                "enabled": rule.enabled,
                                "priority": rule.priority
                            }
                            
                            # Add type-specific parameters
                            if rule.type == RuleType.CLEARANCE:
                                rule_dict["clearance_mm"] = rule.params.min_clearance_mm
                                rule_dict["category"] = "Electrical"
                            elif rule.type == RuleType.TRACE_WIDTH:
                                rule_dict["min_width_mm"] = rule.params.min_width_mm
                                rule_dict["preferred_width_mm"] = rule.params.preferred_width_mm
                                rule_dict["max_width_mm"] = rule.params.max_width_mm
                                rule_dict["category"] = "Routing"
                            elif rule.type == RuleType.VIA:
                                rule_dict["min_hole_mm"] = rule.params.min_drill_mm
                                rule_dict["max_hole_mm"] = rule.params.max_drill_mm
                                rule_dict["category"] = "Routing"
                            
                            # Add scope information
                            if rule.scope.netclass:
                                rule_dict["scope_first"] = f"InNetClass('{rule.scope.netclass}')"
                            elif rule.scope.nets:
                                rule_dict["scope_first"] = f"InNet({', '.join(rule.scope.nets)})"
                            else:
                                rule_dict["scope_first"] = "All"
                            
                            rules.append(rule_dict)
                except Exception as e:
                    print(f"Error reading from constraint artifact: {e}")
            
            # If no rules found at all, return helpful error
            if not rules:
                return {
                    "success": False,
                    "error": "No rules found",
                    "message": "No design rules found. Please export from Altium:\n1. In Altium: File → Run Script → command_server.pas\n2. Execute: ExportPCBInfo\n3. This exports ALL rules to altium_pcb_info.json",
                    "rules": [],
                    "rules_by_category": {},
                    "statistics": {"total": 0, "enabled": 0, "by_category": {}, "by_type": {}}
                }
            
            # Group rules by category
            rules_by_category = {}
            for rule in rules:
                category = rule.get('category', 'Other')
                if category not in rules_by_category:
                    rules_by_category[category] = []
                rules_by_category[category].append(rule)
            
            # Count rules by type
            rule_stats = {
                "total": len(rules),
                "enabled": len([r for r in rules if r.get('enabled', True)]),
                "by_category": {cat: len(rules) for cat, rules in rules_by_category.items()},
                "by_type": {}
            }
            
            for rule in rules:
                rule_type = rule.get('type', 'other')
                rule_stats["by_type"][rule_type] = rule_stats["by_type"].get(rule_type, 0) + 1
            
            return {
                "success": True,
                "rules": rules,
                "rules_by_category": rules_by_category,
                "statistics": rule_stats
            }
        except Exception as e:
            return {"error": str(e)}
    
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
        Run comprehensive Python DRC check.
        
        This performs real DRC validation using Python - no Altium required!
        Checks all standard design rules: clearance, width, via, short-circuit, etc.
        """
        if not self.current_pcb_path:
            return {"error": "No PCB loaded. Use /pcb/load endpoint first."}
        
        try:
            # Get full PCB data
            raw_data = self.reader.read_pcb(self.current_pcb_path)
            
            if 'error' in raw_data:
                return {"error": raw_data['error']}
            
            # Get design rules
            rules = self.current_design_rules if self.current_design_rules else self._extract_design_rules(raw_data)
            
            # Ensure rules is a list (not tuple or other type)
            if not isinstance(rules, list):
                if isinstance(rules, tuple):
                    rules = list(rules)
                else:
                    rules = []
            
            # If no rules found, use comprehensive defaults (matching common Altium rules)
            if not rules:
                rules = [
                    {
                        "name": "Clearance Constraint",
                        "type": "clearance",
                        "clearance_mm": 0.2,
                        "scope1": "All",
                        "scope2": "All",
                        "enabled": True
                    },
                    {
                        "name": "Width Constraint",
                        "type": "width",
                        "min_width_mm": 0.254,
                        "max_width_mm": 15.0,
                        "preferred_width_mm": 0.838,
                        "enabled": True
                    },
                    {
                        "name": "Short-Circuit Constraint",
                        "type": "short_circuit",
                        "allowed": False,
                        "enabled": True
                    },
                    {
                        "name": "Un-Routed Net Constraint",
                        "type": "unrouted_net",
                        "enabled": True
                    },
                    {
                        "name": "Hole Size Constraint",
                        "type": "hole_size",
                        "min_hole_mm": 0.025,
                        "max_hole_mm": 5.0,
                        "enabled": True
                    },
                    {
                        "name": "Hole To Hole Clearance",
                        "type": "hole_to_hole_clearance",
                        "gap_mm": 0.254,
                        "enabled": True
                    },
                    {
                        "name": "Minimum Solder Mask Sliver",
                        "type": "solder_mask_sliver",
                        "gap_mm": 0.06,
                        "enabled": True
                    },
                    {
                        "name": "Silk To Solder Mask",
                        "type": "silk_to_solder_mask",
                        "clearance_mm": 0.0,
                        "enabled": True
                    },
                    {
                        "name": "Silk to Silk",
                        "type": "silk_to_silk",
                        "clearance_mm": 0.0,
                        "enabled": True
                    },
                    {
                        "name": "Height Constraint",
                        "type": "height",
                        "min_height_mm": 0.0,
                        "max_height_mm": 25.4,
                        "preferred_height_mm": 12.7,
                        "enabled": True
                    }
                ]
            
                # Prepare PCB data for DRC engine (need full data, not samples)
                pcb_data = {
                    "tracks": raw_data.get('tracks', []),
                    "vias": raw_data.get('vias', []),
                    "pads": raw_data.get('pads', []),
                    "nets": raw_data.get('nets', []),
                    "components": raw_data.get('components', []),
                    "polygons": raw_data.get('polygons', [])  # Now includes polygon/pour data
                }
            
            # Run Python DRC engine
            from runtime.drc.python_drc_engine import PythonDRCEngine
            
            drc_engine = PythonDRCEngine()
            try:
                drc_result = drc_engine.run_drc(pcb_data, rules)
            except Exception as e:
                import traceback
                traceback.print_exc()
                return {"error": f"DRC engine error: {str(e)}"}
            
            # Format result similar to Altium DRC report
            summary = drc_result.get("summary", {})
            violations_by_type = drc_result.get("violations_by_type", {})
            violations = drc_result.get("violations", [])
            warnings = drc_result.get("warnings", [])
            
            # Build violations by rule name (matching Altium format)
            violations_by_rule = {}
            for v in violations + warnings:
                # Handle case where v might be a tuple or other type
                if not isinstance(v, dict):
                    continue
                rule_name = v.get("rule_name", "Unknown Rule")
                violations_by_rule[rule_name] = violations_by_rule.get(rule_name, 0) + 1
            
            # Build complete rules list with counts (including rules with 0 violations)
            # Format rule names similar to Altium (with parameters)
            all_rules_checked = []
            
            # Track which rule types are actually checked by Python DRC engine
            python_drc_checked_types = {
                'clearance', 'width', 'via', 'hole_size', 'short_circuit', 
                'unrouted_net', 'hole_to_hole_clearance', 'solder_mask_sliver',
                'silk_to_solder_mask', 'silk_to_silk', 'height', 'modified_polygon',
                'net_antennae'
            }
            
            # Process all rules from PCB
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                rule_name = rule.get('name', 'Unnamed Rule')
                rule_type = rule.get('type') or rule.get('kind', 'other')
                
                # Normalize rule type
                rule_type_lower = str(rule_type).lower()
                if 'clearance' in rule_type_lower:
                    normalized_type = 'clearance'
                elif 'width' in rule_type_lower and 'via' not in rule_type_lower:
                    normalized_type = 'width'
                elif 'via' in rule_type_lower or 'hole' in rule_type_lower:
                    normalized_type = 'via' if 'via' in rule_type_lower else 'hole_size'
                elif 'short' in rule_type_lower:
                    normalized_type = 'short_circuit'
                elif 'unrouted' in rule_type_lower:
                    normalized_type = 'unrouted_net'
                elif 'solder' in rule_type_lower and 'mask' in rule_type_lower:
                    normalized_type = 'solder_mask_sliver'
                elif 'silk' in rule_type_lower:
                    if 'solder' in rule_type_lower or 'mask' in rule_type_lower:
                        normalized_type = 'silk_to_solder_mask'
                    else:
                        normalized_type = 'silk_to_silk'
                elif 'height' in rule_type_lower:
                    normalized_type = 'height'
                elif 'polygon' in rule_type_lower:
                    normalized_type = 'modified_polygon'
                elif 'antenna' in rule_type_lower:
                    normalized_type = 'net_antennae'
                elif 'hole' in rule_type_lower and 'clearance' in rule_type_lower:
                    normalized_type = 'hole_to_hole_clearance'
                else:
                    normalized_type = rule_type_lower
                
                # Format rule name with parameters (Altium style)
                formatted_name = self._format_rule_name_for_display(rule)
                
                # Get violation count for this rule
                count = violations_by_rule.get(rule_name, 0)
                
                # Check if this rule type is checked by Python DRC
                is_checked_by_python = normalized_type in python_drc_checked_types
                
                all_rules_checked.append({
                    "rule_name": rule_name,
                    "formatted_name": formatted_name,
                    "rule_type": normalized_type,
                    "count": count,
                    "enabled": rule.get('enabled', True),
                    "checked_by_python": is_checked_by_python
                })
            
            # Add any rules that have violations but weren't in the rules list
            for rule_name, count in violations_by_rule.items():
                if not any(r.get("rule_name") == rule_name for r in all_rules_checked):
                    all_rules_checked.append({
                        "rule_name": rule_name,
                        "formatted_name": rule_name,
                        "rule_type": "unknown",
                        "count": count,
                        "enabled": True,
                        "checked_by_python": True  # If it has violations, it was checked
                    })
            
            # Sort by count (violations first) then by name
            all_rules_checked.sort(key=lambda x: (-x["count"], x["formatted_name"]))
            
            # Count rules checked by Python DRC
            python_checked_rules = [r for r in all_rules_checked if r.get("checked_by_python", False)]
            
            return {
                "success": True,
                "summary": {
                    "warnings": summary.get("warnings", 0),
                    "rule_violations": summary.get("rule_violations", 0),
                    "total": summary.get("total", 0),
                    "passed": summary.get("passed", False)
                },
                "violations_by_type": violations_by_type,
                "violations_by_rule": violations_by_rule,
                "all_rules_checked": all_rules_checked,  # New: all rules with counts
                "violations": violations,
                "warnings": warnings,
                "detailed_violations": violations,
                "total_violations": summary.get("rule_violations", 0),
                "total_warnings": summary.get("warnings", 0),
                "message": "DRC check completed using Python validation engine",
                "filename": Path(self.current_pcb_path).name if self.current_pcb_path else "Unknown",
                "python_checked_rules": python_checked_rules,
                "total_rules": len(all_rules_checked),
                "rules_checked_count": len(python_checked_rules)
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"DRC check failed: {str(e)}"}
    
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
    
    def auto_generate_drc_rules(self, update_existing: bool = True) -> dict:
        """
        Automatically generate DRC rules from current PCB design
        
        Args:
            update_existing: If True, merge with existing rules; if False, replace
            
        Returns:
            Dictionary with generated rules information
        """
        if not self.current_artifact_id:
            return {"error": "No PCB loaded"}
        
        try:
            constraint_artifact = self.drc.auto_generate_rules(
                self.current_artifact_id,
                constraint_artifact_id=self.constraint_artifact_id if update_existing else None,
                update_existing=update_existing
            )
            
            if constraint_artifact:
                # Update current constraint artifact ID
                self.constraint_artifact_id = constraint_artifact.id
                
                # Get rule count
                cir = self.drc.get_cir_from_artifact(constraint_artifact.id)
                rule_count = len(cir.rules) if cir else 0
                
                return {
                    "success": True,
                    "constraint_artifact_id": constraint_artifact.id,
                    "rule_count": rule_count,
                    "message": f"Generated {rule_count} DRC rules automatically"
                }
            else:
                return {"error": "Failed to generate rules"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_drc_suggestions(self, violations_artifact_id: Optional[str] = None) -> dict:
        """
        Get automatic suggestions based on DRC violations
        
        Args:
            violations_artifact_id: Optional violations artifact ID
            
        Returns:
            Dictionary with suggestions
        """
        if not self.current_artifact_id:
            return {"error": "No PCB loaded"}
        
        try:
            suggestions = self.drc.get_suggestions(
                violations_artifact_id=violations_artifact_id,
                board_artifact_id=self.current_artifact_id,
                constraint_artifact_id=self.constraint_artifact_id
            )
            
            summary = self.drc.suggestion_updater.get_suggestion_summary(suggestions)
            
            return {
                "success": True,
                "suggestions": suggestions,
                "summary": summary,
                "count": len(suggestions)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def update_drc_suggestions(self) -> dict:
        """
        Check for updates to DRC suggestions
        
        Returns:
            Dictionary with update information
        """
        try:
            update_info = self.drc.update_suggestions()
            return update_info
        except Exception as e:
            return {"error": str(e)}
    
    def learn_from_drc_violations(self, violations_artifact_id: str) -> dict:
        """
        Learn from DRC violations and automatically update rules
        
        Args:
            violations_artifact_id: Violations artifact ID
            
        Returns:
            Dictionary with updated rules information
        """
        if not self.constraint_artifact_id:
            return {"error": "No constraint rules loaded"}
        
        try:
            updated_constraint = self.drc.learn_from_violations(
                violations_artifact_id,
                self.constraint_artifact_id
            )
            
            if updated_constraint:
                # Update current constraint artifact ID
                self.constraint_artifact_id = updated_constraint.id
                
                return {
                    "success": True,
                    "constraint_artifact_id": updated_constraint.id,
                    "message": "Rules updated based on violations"
                }
            else:
                return {"error": "Failed to update rules"}
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
        
        elif path == "/drc/auto-generate-rules":
            # Parse query parameters
            update_existing = True
            if "?" in path:
                query_string = path.split("?")[1]
                params = parse_qs(query_string)
                update_existing = params.get("update_existing", ["true"])[0].lower() == "true"
            self._send_json(mcp_server.auto_generate_drc_rules(update_existing=update_existing))
        
        elif path.startswith("/drc/suggestions"):
            # Parse query parameters
            violations_artifact_id = None
            if "?" in path:
                query_string = path.split("?")[1]
                params = parse_qs(query_string)
                violations_artifact_id = params.get("violations_artifact_id", [None])[0]
            self._send_json(mcp_server.get_drc_suggestions(violations_artifact_id=violations_artifact_id))
        
        elif path == "/drc/update-suggestions":
            self._send_json(mcp_server.update_drc_suggestions())
        
        elif path == "/drc/rules" or path == "/design-rules":
            self._send_json(mcp_server.get_design_rules())
        
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
                "/drc/auto-generate-rules - Automatically generate DRC rules",
                "/drc/suggestions - Get DRC violation suggestions",
                "/drc/update-suggestions - Check for suggestion updates",
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
        
        elif path == "/drc/learn":
            violations_artifact_id = data.get("violations_artifact_id")
            if not violations_artifact_id:
                self._send_json({"error": "Missing 'violations_artifact_id' parameter"}, 400)
                return
            result = mcp_server.learn_from_drc_violations(violations_artifact_id)
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
