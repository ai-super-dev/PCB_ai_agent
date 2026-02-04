"""
Design Analyzer - Intelligent Schematic/PCB Analysis Engine

This module provides intelligent analysis of schematic and PCB data:
- Functional block detection
- Component classification
- Signal analysis
- Design intent inference
"""
import json
from typing import Dict, List, Any, Optional
from llm_client import LLMClient


class DesignAnalyzer:
    """
    Intelligent design analysis engine that uses LLM to understand
    schematic topology and generate design insights.
    """
    
    def __init__(self, llm_client: LLMClient = None):
        self.llm_client = llm_client or LLMClient()
        self.schematic_data = None
        self.pcb_data = None
        self.analysis_cache = {}
    
    def load_schematic_data(self, data: Dict[str, Any]):
        """Load schematic data for analysis"""
        self.schematic_data = data
        self.analysis_cache = {}  # Clear cache on new data
    
    def load_pcb_data(self, data: Dict[str, Any]):
        """Load PCB data for analysis"""
        self.pcb_data = data
    
    def analyze_schematic(self) -> Dict[str, Any]:
        """
        Perform comprehensive schematic analysis.
        Returns functional blocks, signal paths, and design insights.
        """
        if not self.schematic_data:
            return {"error": "No schematic data loaded"}
        
        # Build analysis context
        components = self.schematic_data.get("components", [])
        nets = self.schematic_data.get("nets", []) or self.schematic_data.get("wires", [])
        
        analysis = {
            "component_summary": self._summarize_components(components),
            "functional_blocks": self._detect_functional_blocks(components, nets),
            "signal_analysis": self._analyze_signals(nets),
            "design_type": self._infer_design_type(components),
            "critical_components": self._identify_critical_components(components),
            "recommendations": []
        }
        
        return analysis
    
    def _summarize_components(self, components: List[Dict]) -> Dict[str, Any]:
        """Summarize component types and counts"""
        summary = {
            "total": len(components),
            "by_type": {},
            "by_prefix": {}
        }
        
        for comp in components:
            designator = comp.get("designator", "")
            # Extract prefix (R, C, U, etc.)
            prefix = ''.join(c for c in designator if c.isalpha())
            
            summary["by_prefix"][prefix] = summary["by_prefix"].get(prefix, 0) + 1
        
        # Map prefixes to component types
        type_mapping = {
            "R": "Resistors",
            "C": "Capacitors",
            "L": "Inductors",
            "U": "ICs",
            "Q": "Transistors",
            "D": "Diodes",
            "J": "Connectors",
            "Y": "Crystals",
            "F": "Fuses",
            "FB": "Ferrite Beads"
        }
        
        for prefix, count in summary["by_prefix"].items():
            type_name = type_mapping.get(prefix, f"Other ({prefix})")
            summary["by_type"][type_name] = summary["by_type"].get(type_name, 0) + count
        
        return summary
    
    def _detect_functional_blocks(self, components: List[Dict], nets: List[Dict]) -> List[Dict]:
        """
        Use LLM to detect functional blocks in the schematic.
        Groups components by function (power, MCU, interfaces, etc.)
        """
        if not components:
            return []
        
        # Prepare component list for LLM
        comp_list = []
        for comp in components[:50]:  # Limit for token efficiency
            comp_list.append({
                "designator": comp.get("designator", ""),
                "value": comp.get("value", ""),
                "footprint": comp.get("footprint", ""),
                "description": comp.get("description", "")
            })
        
        prompt = f"""Analyze these electronic components and identify functional blocks.

Components:
{json.dumps(comp_list, indent=2)}

Identify and group components into functional blocks such as:
- Power Supply (regulators, inductors, bulk capacitors)
- MCU/Processor Section (microcontroller + support components)
- Communication Interfaces (USB, UART, SPI, I2C, Ethernet)
- Analog Section (op-amps, ADCs, filters)
- Protection Circuits (ESD, fuses, TVS)
- Clock/Timing (crystals, oscillators)
- Memory (Flash, EEPROM, RAM)
- Sensors
- LED/Display

Return JSON format:
{{
    "blocks": [
        {{
            "name": "Block Name",
            "type": "power|mcu|interface|analog|protection|timing|memory|sensor|display|other",
            "components": ["U1", "C1", "C2"],
            "description": "Brief description of function",
            "critical_constraints": ["constraint1", "constraint2"]
        }}
    ]
}}"""

        messages = [
            {"role": "system", "content": "You are an expert PCB design engineer. Analyze component lists and identify functional blocks."},
            {"role": "user", "content": prompt}
        ]
        
        response = self.llm_client.chat(messages, temperature=0.3)
        
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                return result.get("blocks", [])
        except:
            pass
        
        return []
    
    def _analyze_signals(self, nets: List[Dict]) -> Dict[str, Any]:
        """Analyze signal types and characteristics"""
        signal_analysis = {
            "power_nets": [],
            "ground_nets": [],
            "high_speed_nets": [],
            "analog_nets": [],
            "digital_nets": [],
            "differential_pairs": []
        }
        
        for net in nets:
            net_name = net.get("name", "") or net.get("net_name", "")
            net_name_upper = net_name.upper()
            
            # Classify by name patterns
            if any(p in net_name_upper for p in ["VCC", "VDD", "3V3", "5V", "12V", "VBAT", "+V"]):
                signal_analysis["power_nets"].append(net_name)
            elif any(p in net_name_upper for p in ["GND", "VSS", "GROUND", "AGND", "DGND"]):
                signal_analysis["ground_nets"].append(net_name)
            elif any(p in net_name_upper for p in ["CLK", "CLOCK", "USB", "ETH", "HDMI", "PCIE"]):
                signal_analysis["high_speed_nets"].append(net_name)
            elif any(p in net_name_upper for p in ["AIN", "AOUT", "VREF", "SENSE"]):
                signal_analysis["analog_nets"].append(net_name)
            
            # Detect differential pairs
            if net_name.endswith("_P") or net_name.endswith("+"):
                pair_name = net_name[:-2] if net_name.endswith("_P") else net_name[:-1]
                signal_analysis["differential_pairs"].append(pair_name)
        
        return signal_analysis
    
    def _infer_design_type(self, components: List[Dict]) -> str:
        """Infer the overall design type from components"""
        component_names = " ".join([
            f"{c.get('designator', '')} {c.get('value', '')} {c.get('description', '')}"
            for c in components
        ]).upper()
        
        # Check for design type indicators
        if any(x in component_names for x in ["STM32", "ATMEGA", "PIC", "ESP32", "NRF"]):
            return "Microcontroller Board"
        elif any(x in component_names for x in ["FPGA", "CPLD", "SPARTAN", "CYCLONE"]):
            return "FPGA Board"
        elif any(x in component_names for x in ["LM2596", "LM7805", "MP1584", "TPS5430"]):
            return "Power Supply"
        elif any(x in component_names for x in ["RF", "ANTENNA", "BALUN", "LNA"]):
            return "RF/Wireless Module"
        elif any(x in component_names for x in ["OPAMP", "OPA", "LM358", "TL072"]):
            return "Analog Circuit"
        else:
            return "Mixed Signal Board"
    
    def _identify_critical_components(self, components: List[Dict]) -> List[Dict]:
        """Identify components that need special attention in layout"""
        critical = []
        
        for comp in components:
            designator = comp.get("designator", "")
            value = comp.get("value", "").upper()
            desc = comp.get("description", "").upper()
            
            criticality = None
            reason = None
            
            # ICs are generally critical
            if designator.startswith("U"):
                criticality = "high"
                reason = "Main IC - requires proper decoupling and routing"
            
            # Crystals need careful placement
            elif designator.startswith("Y"):
                criticality = "high"
                reason = "Crystal - place close to IC, short traces, ground plane"
            
            # High-value inductors (switching)
            elif designator.startswith("L") and any(x in value for x in ["UH", "MH"]):
                criticality = "medium"
                reason = "Inductor - consider EMI, keep sensitive circuits away"
            
            # Connectors
            elif designator.startswith("J"):
                criticality = "medium"
                reason = "Connector - must be on board edge, consider mechanical"
            
            if criticality:
                critical.append({
                    "designator": designator,
                    "criticality": criticality,
                    "reason": reason
                })
        
        return critical
    
    def generate_placement_strategy(self) -> Dict[str, Any]:
        """
        Generate a placement strategy based on schematic analysis.
        Returns recommended placement zones and component positions.
        """
        if not self.schematic_data:
            return {"error": "No schematic data loaded"}
        
        # First analyze the schematic
        analysis = self.analyze_schematic()
        blocks = analysis.get("functional_blocks", [])
        
        prompt = f"""Based on this PCB design analysis, generate a placement strategy.

Design Type: {analysis.get('design_type', 'Unknown')}

Functional Blocks:
{json.dumps(blocks, indent=2)}

Critical Components:
{json.dumps(analysis.get('critical_components', []), indent=2)}

Signal Analysis:
{json.dumps(analysis.get('signal_analysis', {}), indent=2)}

Generate a placement strategy with:
1. Block placement zones (which area of PCB for each block)
2. Component placement priorities (what to place first)
3. Critical spacing requirements
4. Recommended board zones (power, digital, analog separation)

Return JSON format:
{{
    "board_zones": [
        {{"zone": "zone_name", "location": "top-left|top-right|bottom-left|bottom-right|center|edge", "blocks": ["block1"], "reason": "why"}}
    ],
    "placement_order": [
        {{"step": 1, "action": "Place X", "components": ["U1"], "constraints": ["near Y", "away from Z"]}}
    ],
    "critical_spacing": [
        {{"component": "C1", "near": "U1", "max_distance_mm": 3, "reason": "decoupling"}}
    ],
    "routing_priorities": [
        {{"net_type": "power|ground|high_speed", "priority": 1, "guidelines": ["guideline1"]}}
    ]
}}"""

        messages = [
            {"role": "system", "content": "You are an expert PCB layout engineer. Generate optimal placement strategies."},
            {"role": "user", "content": prompt}
        ]
        
        response = self.llm_client.chat(messages, temperature=0.3)
        
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        
        return {"error": "Failed to generate placement strategy"}
    
    def review_design(self) -> Dict[str, Any]:
        """
        Review the current design for potential issues.
        Returns warnings, errors, and suggestions.
        """
        issues = []
        suggestions = []
        
        if self.schematic_data:
            components = self.schematic_data.get("components", [])
            
            # Check for missing decoupling
            ics = [c for c in components if c.get("designator", "").startswith("U")]
            caps = [c for c in components if c.get("designator", "").startswith("C")]
            
            if len(ics) > 0 and len(caps) < len(ics) * 2:
                issues.append({
                    "type": "warning",
                    "category": "decoupling",
                    "message": f"Potential missing decoupling capacitors. Found {len(ics)} ICs but only {len(caps)} capacitors.",
                    "recommendation": "Add 100nF decoupling capacitor near each IC power pin"
                })
            
            # Check for ESD protection on interfaces
            connectors = [c for c in components if c.get("designator", "").startswith("J")]
            if connectors and not any("ESD" in str(c.get("description", "")).upper() for c in components):
                issues.append({
                    "type": "suggestion",
                    "category": "protection",
                    "message": "No ESD protection components detected",
                    "recommendation": "Consider adding TVS diodes on external interfaces"
                })
        
        return {
            "issues": issues,
            "suggestions": suggestions,
            "score": max(0, 100 - len(issues) * 10)
        }


# Convenience function for quick analysis
def analyze_design(schematic_data: Dict, pcb_data: Dict = None) -> Dict[str, Any]:
    """Quick function to analyze a design"""
    analyzer = DesignAnalyzer()
    analyzer.load_schematic_data(schematic_data)
    if pcb_data:
        analyzer.load_pcb_data(pcb_data)
    
    return {
        "analysis": analyzer.analyze_schematic(),
        "placement_strategy": analyzer.generate_placement_strategy(),
        "design_review": analyzer.review_design()
    }

