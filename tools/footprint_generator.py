"""
LLM-Powered Footprint Generator

Uses LLM to analyze component designators, values, and specifications
to generate appropriate PCB footprint specifications.
"""
import json
import re
from typing import Dict, Any, List, Optional
from llm_client import LLMClient
import logging

logger = logging.getLogger(__name__)


class FootprintGenerator:
    """Generates PCB footprint specifications using LLM analysis"""
    
    # Standard component designator prefixes
    COMPONENT_PREFIXES = {
        'C': 'capacitor',
        'R': 'resistor',
        'L': 'inductor',
        'D': 'diode',
        'Q': 'transistor',
        'U': 'integrated_circuit',
        'IC': 'integrated_circuit',
        'J': 'connector',
        'P': 'connector',
        'T': 'transformer',
        'X': 'crystal',
        'Y': 'crystal',
        'SW': 'switch',
        'S': 'switch',
        'K': 'relay',
        'F': 'fuse',
        'VR': 'variable_resistor',
        'RV': 'variable_resistor',
        'LED': 'led',
        'LS': 'speaker',
        'B': 'battery',
    }
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
    
    def get_component_type_from_designator(self, designator: str) -> str:
        """Extract component type from designator prefix"""
        designator_upper = designator.upper()
        
        # Check multi-character prefixes first (e.g., "LED", "SW")
        for prefix, comp_type in sorted(self.COMPONENT_PREFIXES.items(), key=lambda x: -len(x[0])):
            if designator_upper.startswith(prefix):
                return comp_type
        
        return 'unknown'
    
    def analyze_component_with_llm(self, component: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Use LLM to analyze component and generate footprint specification
        
        Args:
            component: Component dict with designator, value, footprint, pin_count, etc.
        
        Returns:
            Footprint specification dict with pad layout, dimensions, etc.
        """
        designator = component.get('designator', '')
        value = component.get('value', '')
        footprint = component.get('footprint', '')
        pin_count = component.get('pin_count', 0)
        lib_reference = component.get('lib_reference', '')
        
        comp_type = self.get_component_type_from_designator(designator)
        
        system_prompt = """You are an expert PCB footprint engineer specializing in IPC-7351 standard footprints. Your job is to research and generate accurate PCB footprint specifications based on industry standards.

CRITICAL: You MUST use EXACT IPC-7351 standard dimensions. These are industry standards - use your knowledge to look up the correct values.

IPC-7351 STANDARD FOOTPRINT DIMENSIONS (EXACT VALUES - Use these precisely):

PASSIVE SMD COMPONENTS (Capacitors/Resistors) - IPC-7351 NOMINAL DIMENSIONS:

**0603 Package (R0603, C0603, L0603):**
- Body size: 1.6mm (length) × 0.8mm (width)
- Pad width (A/B): 0.95mm (EXACT - NOT 0.8mm, NOT 1.0mm)
- Pad height (D): 1.0mm (EXACT)
- Inner pad spacing (C1/C2): 0.8mm (distance from pad edge to center)
- Pad center-to-center spacing: 1.75mm (calculated as: 0.8 + 0.95/2 + 0.95/2 = 1.75mm)
- Pad 1 position: x = -0.875mm, y = 0mm
- Pad 2 position: x = +0.875mm, y = 0mm
- Silkscreen outline: 3.1mm × 1.5mm
- Courtyard outline: 3.5mm × 1.8mm

**0805 Package:**
- Body size: 2.0mm × 1.25mm
- Pad width: 1.2mm
- Pad height: 1.4mm
- Pad center spacing: 2.0mm (Pad 1 at x=-1.0mm, Pad 2 at x=+1.0mm)
- Silkscreen: 3.8mm × 2.0mm

**2512 Package (C2512):**
- Body size: 6.3mm × 3.2mm
- Pad width: 1.8mm
- Pad height: 3.4mm
- Pad center spacing: 5.5mm (Pad 1 at x=-2.75mm, Pad 2 at x=+2.75mm)
- Silkscreen: 8.0mm × 4.5mm

**2220 Package (C2220):**
- Body size: 5.6mm × 5.0mm
- Pad width: 2.2mm
- Pad height: 5.5mm
- Pad center spacing: 5.0mm (Pad 1 at x=-2.5mm, Pad 2 at x=+2.5mm)
- Silkscreen: 7.5mm × 6.5mm

**2010 Package (R2010):**
- Body size: 5.0mm × 2.5mm
- Pad width: 1.8mm
- Pad height: 2.8mm
- Pad center spacing: 4.5mm (Pad 1 at x=-2.25mm, Pad 2 at x=+2.25mm)
- Silkscreen: 7.0mm × 3.5mm

**0402 Package:**
- Body size: 1.0mm × 0.5mm
- Pad width: 0.5mm
- Pad height: 0.6mm
- Pad center spacing: 0.8mm (Pad 1 at x=-0.4mm, Pad 2 at x=+0.4mm)
- Silkscreen: 2.4mm × 1.2mm

DIODE PACKAGES:
- SOD-123: Body 3.7×1.6mm, Pad spacing 2.8mm (±1.4mm), Pad size 1.0×1.8mm
- SOD-123FL: Body 3.7×1.6mm, Pad spacing 2.8mm (±1.4mm), Pad size 1.0×1.8mm
- SOD-323: Body 1.7×1.25mm, Pad spacing 1.3mm (±0.65mm), Pad size 0.6×1.4mm
- SOD-523: Body 1.3×0.9mm, Pad spacing 1.0mm (±0.5mm), Pad size 0.5×0.9mm
- SMB: Body 5.4×3.6mm, Pad spacing 4.4mm (±2.2mm), Pad size 2.2×4.0mm
- SMC: Body 7.1×5.2mm, Pad spacing 6.0mm (±3.0mm), Pad size 2.5×5.4mm

TRANSISTOR PACKAGES:
- SOT-23: 3 pins, Pad 1 at (-0.95, -1.0), Pad 2 at (0.95, -1.0), Pad 3 at (0.0, 1.0), Pad size 0.6×0.7mm
- SOT-23-5: 5 pins, Pad size 0.6×0.7mm, Pitch 0.95mm
- SOT-89: 3 pins + tab, Pad size 0.7×1.2mm
- SOT-223: 4 pins + tab, Pad size 1.0×1.5mm

POWER PACKAGES:
- TO-252: 3 pins + tab, Pad 1 at (-2.28, -3.4), Pad 3 at (2.28, -3.4), Tab at (0, 1.5) size 6.0×5.6mm
- TO-263-2: 3 pins + tab, Pad 1 at (-2.54, -4.5), Pad 3 at (2.54, -4.5), Tab at (0, 2.0) size 10.0×7.5mm
- TO-263-7: 7 pins + tab, Pin pitch 1.27mm, Tab size 10.0×7.5mm

IC PACKAGES:
- SOIC-8: Body 5.0×4.0mm, Pad size 0.6×1.5mm, Pin pitch 1.27mm, Dual row
- ESOP8L: Similar to SOIC-8 with thermal pad

KEY PRINCIPLES:
1. Pad center spacing = Body length - (pad extension on each side)
   Example: 2512 body is 6.3mm long. With 0.4mm pad extension each side:
   Pad spacing = 6.3 - 0.4 - 0.4 = 5.5mm (±2.75mm)
   
2. Pad size should be: Width = body width + 0.2-0.4mm, Height = appropriate for solder fillet
   
3. Silkscreen: Slightly larger than body (typically +0.3-0.5mm each side)
   
4. Courtyard: Body + clearance (typically +0.5-1.0mm each side)

OUTPUT FORMAT (JSON):
{
    "footprint_name": "standard footprint name (e.g., '0805', 'SOT-23', 'SOIC-8')",
    "component_type": "capacitor|resistor|diode|transistor|ic|connector|etc",
    "package_type": "smd|through_hole|mixed",
    "pads": [
        {
            "name": "1",
            "x": -2.75,
            "y": 0.0,
            "width": 1.8,
            "height": 3.2,
            "shape": "rectangular",
            "layer": "top",
            "hole_size": 0.0
        }
    ],
    "silkscreen": {
        "width": 6.9,
        "height": 3.4
    },
    "courtyard": {
        "width": 7.3,
        "height": 3.8
    },
    "notes": "IPC-7351 standard footprint"
}

CRITICAL REQUIREMENTS:
- All dimensions in millimeters
- For SMD: layer="top", hole_size=0
- For through-hole: layer="multilayer", hole_size > 0
- Pad positions (x, y) are relative to component center (0,0)
- Pad spacing must be calculated correctly based on body size and IPC standards
- Pad size must match IPC-7351 recommendations for the package
- If footprint name is provided (e.g., "C2512", "R0603", "SOT-23", "TO-252", etc.), you MUST look up the correct IPC-7351 dimensions for that specific package
- For packages NOT listed in the reference examples above, use your knowledge of IPC-7351 standards to determine correct dimensions
- Extract package size from value string if present (e.g., "0603-0.1uF" -> 0603 package)
- DO NOT guess or approximate - use your knowledge of IPC-7351 standards to provide accurate dimensions
- If you're unsure about a package, look it up using your knowledge of industry standards (IPC-7351, JEDEC, etc.)
"""
        
        user_message = f"""Analyze this component and generate a complete footprint specification with CORRECT IPC-7351 standard dimensions:

Designator: {designator}
Value: {value}
Existing Footprint Name: {footprint}
Library Reference: {lib_reference}
Pin Count: {pin_count}
Detected Component Type: {comp_type}

CRITICAL: You MUST use the EXACT dimensions from the IPC-7351 standards above.

For 0603 package (R0603, C0603, L0603) - USE THESE EXACT VALUES:
{{
  "pads": [
    {{"name": "1", "x": -0.875, "y": 0.0, "width": 0.95, "height": 1.0, "shape": "rectangular", "layer": "top", "hole_size": 0.0}},
    {{"name": "2", "x": 0.875, "y": 0.0, "width": 0.95, "height": 1.0, "shape": "rectangular", "layer": "top", "hole_size": 0.0}}
  ],
  "silkscreen": {{"width": 3.1, "height": 1.5}},
  "courtyard": {{"width": 3.5, "height": 1.8}}
}}

For 0805 package:
{{
  "pads": [
    {{"name": "1", "x": -1.0, "y": 0.0, "width": 1.2, "height": 1.4, "shape": "rectangular", "layer": "top", "hole_size": 0.0}},
    {{"name": "2", "x": 1.0, "y": 0.0, "width": 1.2, "height": 1.4, "shape": "rectangular", "layer": "top", "hole_size": 0.0}}
  ],
  "silkscreen": {{"width": 3.8, "height": 2.0}}
}}

For 2512 package (C2512):
{{
  "pads": [
    {{"name": "1", "x": -2.75, "y": 0.0, "width": 1.8, "height": 3.4, "shape": "rectangular", "layer": "top", "hole_size": 0.0}},
    {{"name": "2", "x": 2.75, "y": 0.0, "width": 1.8, "height": 3.4, "shape": "rectangular", "layer": "top", "hole_size": 0.0}}
  ],
  "silkscreen": {{"width": 8.0, "height": 4.5}}
}}

For 2220 package (C2220):
{{
  "pads": [
    {{"name": "1", "x": -2.5, "y": 0.0, "width": 2.2, "height": 5.5, "shape": "rectangular", "layer": "top", "hole_size": 0.0}},
    {{"name": "2", "x": 2.5, "y": 0.0, "width": 2.2, "height": 5.5, "shape": "rectangular", "layer": "top", "hole_size": 0.0}}
  ],
  "silkscreen": {{"width": 7.5, "height": 6.5}}
}}

For 2010 package (R2010):
{{
  "pads": [
    {{"name": "1", "x": -2.25, "y": 0.0, "width": 1.8, "height": 2.8, "shape": "rectangular", "layer": "top", "hole_size": 0.0}},
    {{"name": "2", "x": 2.25, "y": 0.0, "width": 1.8, "height": 2.8, "shape": "rectangular", "layer": "top", "hole_size": 0.0}}
  ],
  "silkscreen": {{"width": 7.0, "height": 3.5}}
}}

IMPORTANT RULES:
1. If the footprint name matches one of the packages above (e.g., "R0603", "0603", "C0603"), use the EXACT dimensions from that package
2. Pad positions (x, y) are relative to component center (0, 0)
3. All dimensions must be in millimeters
4. For 2-pin SMD: Pad 1 at (-spacing/2, 0), Pad 2 at (+spacing/2, 0)
5. Pad width and height must match the EXACT values - do NOT round or approximate
6. For packages NOT listed above, use your knowledge of IPC-7351 standards to look up the correct dimensions

Generate a complete footprint specification in JSON format. If the footprint name matches a package above, use those EXACT dimensions. Do NOT use approximate values."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        try:
            # Use very low temperature for precise, deterministic results
            response = self.llm_client.chat(messages, temperature=0.0)
            
            if response:
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    footprint_spec = json.loads(json_match.group())
                    
                    # Basic validation only - check for obvious errors, but trust LLM for dimensions
                    footprint_spec = self._validate_footprint_spec_basic(footprint_spec, footprint, pin_count)
                    
                    logger.info(f"Generated footprint for {designator}: {footprint_spec.get('footprint_name')}")
                    return footprint_spec
                else:
                    logger.warning(f"No JSON found in LLM response for {designator}")
        except Exception as e:
            logger.error(f"Error generating footprint for {designator}: {e}")
        
        return None
    
    def _validate_footprint_spec_basic(self, spec: Dict[str, Any], footprint_name: str, pin_count: int) -> Dict[str, Any]:
        """
        Basic validation only - check for obvious structural errors (missing pads, invalid values)
        Do NOT correct dimensions - trust the LLM to provide correct IPC-7351 dimensions from its knowledge
        """
        pads = spec.get('pads', [])
        
        # Only validate structure, not dimensions
        if not pads:
            logger.warning(f"No pads found in footprint spec for {footprint_name}, using fallback")
            return None
        
        # Check for obviously invalid values (negative sizes, zero spacing, etc.)
        for pad in pads:
            if pad.get('width', 0) <= 0 or pad.get('height', 0) <= 0:
                logger.warning(f"Invalid pad dimensions in {footprint_name}, using fallback")
                return None
        
        # For 2-pin footprints, ensure pads are on opposite sides
        if len(pads) == 2 and pin_count == 2:
            pad1_x = pads[0].get('x', 0)
            pad2_x = pads[1].get('x', 0)
            spacing = abs(pad2_x - pad1_x)
            
            # Only flag if spacing is unreasonably small (<0.1mm) or large (>50mm)
            if spacing < 0.1:
                logger.warning(f"Pad spacing too small ({spacing:.2f}mm) for {footprint_name}, using fallback")
                return None
            if spacing > 50:
                logger.warning(f"Pad spacing too large ({spacing:.2f}mm) for {footprint_name}, using fallback")
                return None
        
        # All basic checks passed - trust LLM dimensions
        return spec
    
    def generate_footprints_batch(self, components: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Generate footprints for multiple components - OPTIMIZED: Groups by unique footprint
        Uses LLM to generate one spec per unique footprint (reduces API calls significantly)
        
        Args:
            components: List of component dicts
        
        Returns:
            Dict mapping designator -> footprint specification
        """
        # Step 1: Group components by footprint name
        footprint_groups = {}
        for component in components:
            designator = component.get('designator', '')
            if not designator:
                continue
            
            footprint_name = component.get('footprint', '').strip()
            if not footprint_name:
                # Try to infer from value (e.g., "0603-0.1uF" -> "0603")
                value = component.get('value', '')
                footprint_name = self._extract_package_from_value(value)
            
            if not footprint_name:
                footprint_name = f"UNKNOWN_{component.get('pin_count', 2)}PIN"
            
            # Normalize footprint name (uppercase, remove spaces)
            footprint_key = footprint_name.upper().strip()
            
            if footprint_key not in footprint_groups:
                footprint_groups[footprint_key] = {
                    'footprint_name': footprint_name,
                    'components': [],
                    'representative': component  # Use first component as representative
                }
            
            footprint_groups[footprint_key]['components'].append(component)
        
        logger.info(f"Grouped {len(components)} components into {len(footprint_groups)} unique footprints")
        
        # Step 2: Generate one footprint spec per unique footprint using LLM
        footprint_specs = {}
        for footprint_key, group_data in footprint_groups.items():
            footprint_name = group_data['footprint_name']
            representative = group_data['representative']
            component_count = len(group_data['components'])
            
            logger.info(f"Generating footprint '{footprint_name}' for {component_count} components using LLM")
            
            # Generate footprint spec using LLM (one call per unique footprint)
            footprint_spec = self.analyze_component_with_llm(representative)
            
            if not footprint_spec:
                # Fallback: generate basic footprint
                logger.warning(f"LLM generation failed for {footprint_name}, using fallback")
                footprint_spec = self._generate_fallback_footprint(representative)
            
            # Store the footprint spec
            footprint_specs[footprint_key] = footprint_spec
            
            # Add metadata about which components use this footprint
            footprint_spec['component_designators'] = [
                comp.get('designator') for comp in group_data['components']
            ]
            footprint_spec['component_count'] = component_count
        
        # Step 3: Map all components to their footprint specs
        results = {}
        for component in components:
            designator = component.get('designator', '')
            if not designator:
                continue
            
            footprint_name = component.get('footprint', '').strip()
            if not footprint_name:
                value = component.get('value', '')
                footprint_name = self._extract_package_from_value(value)
            
            if not footprint_name:
                footprint_name = f"UNKNOWN_{component.get('pin_count', 2)}PIN"
            
            footprint_key = footprint_name.upper().strip()
            
            if footprint_key in footprint_specs:
                results[designator] = footprint_specs[footprint_key].copy()
                # Remove component list from individual results (keep only in footprint_specs)
                if 'component_designators' in results[designator]:
                    del results[designator]['component_designators']
            else:
                # Fallback
                results[designator] = self._generate_fallback_footprint(component)
        
        # Also return footprint_specs for library generation
        results['_footprint_libraries'] = footprint_specs
        
        logger.info(f"Generated {len(footprint_specs)} unique footprints for {len(components)} components")
        
        return results
    
    def _extract_package_from_value(self, value: str) -> str:
        """Extract package size from component value string"""
        if not value:
            return ''
        
        # Common package patterns: 0402, 0603, 0805, 1206, 1210, etc.
        import re
        patterns = [
            r'(\d{4})',  # 4-digit packages: 0402, 0603, 0805, 1206, 1210, 1812, 2010, 2220, 2512
            r'(\d{3})',  # 3-digit packages: 0201, 0302
            r'(SOT-\d+)',  # SOT packages: SOT-23, SOT-89, SOT-223
            r'(SOIC-\d+)',  # SOIC packages: SOIC-8, SOIC-14, SOIC-16
            r'(TSSOP-\d+)',  # TSSOP packages
            r'(QFP-\d+)',  # QFP packages
            r'(TO-\d+)',  # TO packages: TO-92, TO-220, TO-252
            r'(SOD-\d+)',  # SOD packages: SOD-123, SOD-323
        ]
        
        for pattern in patterns:
            match = re.search(pattern, value, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return ''
    
    def _generate_fallback_footprint(self, component: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a basic footprint when LLM fails"""
        designator = component.get('designator', '')
        pin_count = component.get('pin_count', 2)
        comp_type = self.get_component_type_from_designator(designator)
        
        # Basic 2-pin SMD footprint
        if pin_count == 2:
            return {
                "footprint_name": "SMD_2PIN",
                "component_type": comp_type,
                "package_type": "smd",
                "pads": [
                    {
                        "name": "1",
                        "x": -1.0,
                        "y": 0.0,
                        "width": 1.2,
                        "height": 1.2,
                        "shape": "rectangular",
                        "layer": "top",
                        "hole_size": 0.0
                    },
                    {
                        "name": "2",
                        "x": 1.0,
                        "y": 0.0,
                        "width": 1.2,
                        "height": 1.2,
                        "shape": "rectangular",
                        "layer": "top",
                        "hole_size": 0.0
                    }
                ],
                "silkscreen": {"width": 2.5, "height": 1.0},
                "courtyard": {"width": 3.0, "height": 1.5},
                "notes": "Fallback footprint"
            }
        
        # Multi-pin IC footprint (dual-row)
        pads_per_side = (pin_count + 1) // 2
        pads = []
        pitch = 1.27  # Standard 50 mil pitch
        
        for i in range(pads_per_side):
            # Left side
            pads.append({
                "name": str(i + 1),
                "x": -2.5,
                "y": (i - pads_per_side/2 + 0.5) * pitch,
                "width": 0.6,
                "height": 1.5,
                "shape": "rectangular",
                "layer": "top",
                "hole_size": 0.0
            })
            
            # Right side
            if (i + pads_per_side + 1) <= pin_count:
                pads.append({
                    "name": str(pin_count - i),
                    "x": 2.5,
                    "y": (i - pads_per_side/2 + 0.5) * pitch,
                    "width": 0.6,
                    "height": 1.5,
                    "shape": "rectangular",
                    "layer": "top",
                    "hole_size": 0.0
                })
        
        return {
            "footprint_name": f"SMD_{pin_count}PIN",
            "component_type": comp_type,
            "package_type": "smd",
            "pads": pads,
            "silkscreen": {"width": 3.0, "height": pads_per_side * pitch + 1.0},
            "courtyard": {"width": 3.5, "height": pads_per_side * pitch + 1.5},
            "notes": "Fallback multi-pin footprint"
        }
    
    def organize_footprints_by_category(self, footprint_specs: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Organize footprints by component category for library creation
        
        Args:
            footprint_specs: Dict of footprint_key -> footprint_spec (from _footprint_libraries)
        
        Returns:
            Dict mapping category -> list of footprint specs
        """
        categories = {
            'resistors': [],
            'capacitors': [],
            'diodes': [],
            'transistors': [],
            'ics': [],
            'connectors': [],
            'inductors': [],
            'transformers': [],
            'switches': [],
            'crystals': [],
            'other': []
        }
        
        for footprint_key, spec in footprint_specs.items():
            if footprint_key == '_footprint_libraries':
                continue
            
            comp_type = spec.get('component_type', 'unknown').lower()
            
            # Map component types to categories
            if comp_type in ['resistor', 'variable_resistor']:
                categories['resistors'].append(spec)
            elif comp_type == 'capacitor':
                categories['capacitors'].append(spec)
            elif comp_type == 'diode' or comp_type == 'led':
                categories['diodes'].append(spec)
            elif comp_type == 'transistor':
                categories['transistors'].append(spec)
            elif comp_type in ['integrated_circuit', 'ic']:
                categories['ics'].append(spec)
            elif comp_type in ['connector']:
                categories['connectors'].append(spec)
            elif comp_type == 'inductor':
                categories['inductors'].append(spec)
            elif comp_type == 'transformer':
                categories['transformers'].append(spec)
            elif comp_type in ['switch', 'relay']:
                categories['switches'].append(spec)
            elif comp_type in ['crystal', 'oscillator']:
                categories['crystals'].append(spec)
            else:
                categories['other'].append(spec)
        
        # Remove empty categories
        return {k: v for k, v in categories.items() if v}
    
    def prepare_library_structure(self, footprint_specs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Prepare footprint data structure for Altium PCB library creation
        
        Args:
            footprint_specs: Dict of footprint_key -> footprint_spec (from _footprint_libraries)
        
        Returns:
            Organized structure ready for library file generation
        """
        # Organize by category
        categorized = self.organize_footprints_by_category(footprint_specs)
        
        # Count statistics
        total_footprints = sum(len(specs) for specs in categorized.values())
        total_components = sum(
            spec.get('component_count', 0) 
            for specs in categorized.values() 
            for spec in specs
        )
        
        return {
            'categories': categorized,
            'statistics': {
                'total_footprints': total_footprints,
                'total_components': total_components,
                'category_counts': {k: len(v) for k, v in categorized.items()}
            },
            'footprints': footprint_specs
        }