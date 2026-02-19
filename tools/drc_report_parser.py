"""
DRC Report Parser
Parses Altium Designer HTML DRC reports and extracts detailed violations
"""
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from html.parser import HTMLParser
from html import unescape


class AltiumDRCReportParser:
    """Parse Altium Designer DRC HTML reports"""
    
    def __init__(self):
        self.violations = []
        self.warnings = []
        self.current_section = None
        self.in_violation_table = False
        self.current_row = {}
        self.current_cell = ""
        self.cell_index = 0
    
    def parse_report(self, report_path: str) -> Dict[str, Any]:
        """
        Parse Altium DRC HTML report
        
        Args:
            report_path: Path to HTML report file
            
        Returns:
            Dict with violations, warnings, and summary
        """
        if not Path(report_path).exists():
            return {
                "error": f"Report file not found: {report_path}",
                "violations": [],
                "warnings": [],
                "summary": {}
            }
        
        try:
            with open(report_path, 'r', encoding='utf-8', errors='ignore') as f:
                html = f.read()
            
            return self._parse_html(html)
            
        except Exception as e:
            return {
                "error": f"Error parsing report: {str(e)}",
                "violations": [],
                "warnings": [],
                "summary": {}
            }
    
    def _parse_html(self, html: str) -> Dict[str, Any]:
        """Parse HTML content"""
        # Extract summary statistics
        summary = self._extract_summary(html)
        
        # Extract violations by type
        violations_by_type = self._extract_violations_by_type(html)
        
        # Extract detailed violations
        detailed_violations = self._extract_detailed_violations(html)
        
        return {
            "summary": summary,
            "violations_by_type": violations_by_type,
            "detailed_violations": detailed_violations,
            "total_violations": summary.get("violations", 0),
            "total_warnings": summary.get("warnings", 0)
        }
    
    def _extract_summary(self, html: str) -> Dict[str, Any]:
        """Extract summary statistics from HTML"""
        summary = {
            "violations": 0,
            "warnings": 0,
            "passed": True
        }
        
        # Extract violations count
        violations_match = re.search(
            r'Rule\s+Violations:</td>.*?<td[^>]*>(\d+)</td>',
            html,
            re.IGNORECASE | re.DOTALL
        )
        if violations_match:
            summary["violations"] = int(violations_match.group(1))
        
        # Extract warnings count
        warnings_match = re.search(
            r'Warnings:</td>.*?<td[^>]*>(\d+)</td>',
            html,
            re.IGNORECASE | re.DOTALL
        )
        if warnings_match:
            summary["warnings"] = int(warnings_match.group(1))
        
        summary["passed"] = (summary["violations"] == 0 and summary["warnings"] == 0)
        
        return summary
    
    def _extract_violations_by_type(self, html: str) -> Dict[str, int]:
        """Extract violations grouped by rule type"""
        violations_by_type = {}
        
        # Pattern for violation type table rows
        # <a href="#...">Rule Name (Constraint)</a></td><td>count</td>
        pattern = r'<a\s+href="#[^"]*">([^<]+(?:Constraint|Rule)[^<]*)</a></td>\s*<td[^>]*>(\d+)</td>'
        matches = re.findall(pattern, html, re.IGNORECASE)
        
        for rule_name, count in matches:
            count_int = int(count)
            if count_int > 0:
                # Clean rule name
                rule_clean = rule_name.split('(')[0].strip()
                violations_by_type[rule_clean] = violations_by_type.get(rule_clean, 0) + count_int
        
        return violations_by_type
    
    def _extract_detailed_violations(self, html: str) -> List[Dict[str, Any]]:
        """Extract detailed violation information"""
        violations = []
        
        # Pattern 1: Extract from violation tables
        # Look for table rows with violation details
        # Format: <tr>...<td>Component/Net</td><td>Rule</td><td>Message</td>...</tr>
        
        # Pattern for violation entries in tables
        violation_pattern = r'<tr[^>]*>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>([^<]+)</td>.*?</tr>'
        
        # More specific pattern for Altium DRC report format
        # Look for <acronym> tags which contain violation messages
        acronym_pattern = r'<acronym\s+title="([^"]*)">(.*?)</acronym>'
        acronym_matches = re.findall(acronym_pattern, html, re.IGNORECASE)
        
        for title, text in acronym_matches:
            text_clean = unescape(re.sub(r'<[^>]+>', '', text)).strip()
            if self._is_detailed_violation_line(text_clean):
                violation = self._parse_violation_message(title, text_clean)
                if violation:
                    violations.append(violation)
        
        # Also try to extract from table cells
        # Pattern: <td>Component</td><td>Net</td><td>Rule</td><td>Message</td>
        table_row_pattern = r'<tr[^>]*>(.*?)</tr>'
        rows = re.findall(table_row_pattern, html, re.DOTALL | re.IGNORECASE)
        
        for row in rows:
            # Extract all <td> cells
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cells) >= 3:
                # Try to identify violation rows
                cell_text = ' '.join([re.sub(r'<[^>]+>', '', cell).strip() for cell in cells])
                if self._is_detailed_violation_line(unescape(cell_text)):
                    violation = {
                        "component": cells[0].strip() if len(cells) > 0 else "",
                        "net": cells[1].strip() if len(cells) > 1 else "",
                        "rule": cells[2].strip() if len(cells) > 2 else "",
                        "message": cell_text[:200],  # First 200 chars
                        "type": self._classify_violation_type(cell_text)
                    }
                    violations.append(violation)
        
        # Remove duplicates
        seen = set()
        unique_violations = []
        for v in violations:
            key = (v.get("message", ""), v.get("rule", ""))
            if key not in seen:
                seen.add(key)
                unique_violations.append(v)
        
        return unique_violations[:20]  # Limit to first 20

    def _is_detailed_violation_line(self, text: str) -> bool:
        """Return True only for real per-violation detail lines, not summary/header rows."""
        if not text:
            return False

        t = text.strip()
        t_lower = t.lower()

        # Must contain the detailed violation marker (e.g. "Short-Circuit Constraint: ...")
        if "constraint:" not in t_lower:
            return False

        # Exclude report summary/table labels that are not actual violation instances
        if any(bad in t_lower for bad in ("rule violations:", "total violations:", "warnings:")):
            return False

        return True
    
    def _parse_violation_message(self, title: str, text: str) -> Optional[Dict[str, Any]]:
        """Parse a violation message into structured data"""
        # Clean the message
        message = unescape(text).strip()
        title_clean = unescape(title).strip()
        
        # Extract component/net/rule from message
        component = ""
        net = ""
        rule = ""
        
        # Try to extract component (e.g., "U1", "C135")
        comp_match = re.search(r'\b([A-Z]\d+)\b', message)
        if comp_match:
            component = comp_match.group(1)
        
        # Try to extract net name
        net_match = re.search(r'Net[:\s]+([A-Za-z0-9_+-]+)', message, re.IGNORECASE)
        if net_match:
            net = net_match.group(1)
        
        # Extract rule type
        rule_type = self._classify_violation_type(message)
        
        # Extract location if available
        location = {}
        # Prefer explicit Altium location marker if present:
        # "Location : [X = 144.336mm][Y = 25.609mm]"
        loc_match = re.search(r'\[X\s*=\s*([0-9.]+)mm\]\[Y\s*=\s*([0-9.]+)mm\]', message, re.IGNORECASE)
        if loc_match:
            location = {
                "x_mm": float(loc_match.group(1)),
                "y_mm": float(loc_match.group(2))
            }
        else:
            # Fallback to first coordinate tuple in text
            pair_match = re.search(r'\(([0-9.]+),\s*([0-9.]+)\)', message)
            if pair_match:
                location = {
                    "x_mm": float(pair_match.group(1)),
                    "y_mm": float(pair_match.group(2))
                }
        
        return {
            "message": message,
            "title": title_clean,
            "component": component,
            "net": net,
            "rule": rule_type,
            "type": rule_type,
            "location": location,
            "severity": "error" if "violation" in message.lower() else "warning"
        }
    
    def _classify_violation_type(self, text: str) -> str:
        """Classify violation type from message text"""
        text_lower = text.lower()
        
        if "clearance" in text_lower:
            return "clearance"
        elif "width" in text_lower or "trace" in text_lower:
            return "trace_width"
        elif "via" in text_lower:
            return "via"
        elif "unrouted" in text_lower or "un-routed" in text_lower or "not routed" in text_lower:
            return "unrouted_net"
        elif "short" in text_lower:
            return "short_circuit"
        elif "silk" in text_lower or "overlay" in text_lower:
            return "silkscreen"
        else:
            return "other"
    
    def find_latest_report(self, project_path: str = "PCB_Project") -> Optional[str]:
        """
        Find the latest DRC report in Project Outputs folder
        
        Args:
            project_path: Path to PCB project folder
            
        Returns:
            Path to latest report or None
        """
        # Try multiple possible locations (order matters - check most likely first)
        possible_dirs = []
        
        # First, check project directory for any "Output" folder
        project_dir = Path(project_path)
        if project_dir.exists():
            for item in project_dir.iterdir():
                if item.is_dir() and "Output" in item.name:
                    possible_dirs.append(item)
        
        # Then check standard locations
        possible_dirs.extend([
            Path(project_path) / "Project Outputs for PCB_Project",
            Path(project_path) / "Project Outputs",
            Path("PCB_Project/Project Outputs for PCB_Project"),  # Exact path from user
            Path("Project Outputs for PCB_Project"),
            Path("Project Outputs"),
        ])
        
        all_reports = []
        
        # Search all possible directories
        for outputs_dir in possible_dirs:
            if outputs_dir.exists():
                # Find all DRC HTML reports (case-insensitive pattern)
                html_files = list(outputs_dir.glob("Design Rule Check*.html"))
                html_files.extend(outputs_dir.glob("design rule check*.html"))  # Case variations
                all_reports.extend(html_files)
        
        if not all_reports:
            return None
        
        # Return the most recent one
        return str(max(all_reports, key=lambda p: p.stat().st_mtime))


def parse_drc_report(report_path: str = None) -> Dict[str, Any]:
    """
    Convenience function to parse DRC report
    
    Args:
        report_path: Path to report (auto-finds latest if None)
        
    Returns:
        Parsed report data
    """
    parser = AltiumDRCReportParser()
    
    if report_path is None:
        report_path = parser.find_latest_report()
        if not report_path:
            return {
                "error": "No DRC report found. Run DRC in Altium Designer first.",
                "violations": [],
                "warnings": [],
                "summary": {}
            }
    
    return parser.parse_report(report_path)
