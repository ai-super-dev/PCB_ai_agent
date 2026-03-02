"""
LLM-Powered Footprint Generator

Uses LLM to analyze component designators, values, and specifications
to generate appropriate PCB footprint specifications.
"""
import json
import re
import logging
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
        # Try to import web_search if available
        try:
            from tools.web_search import web_search
            self.web_search = web_search
        except ImportError:
            self.web_search = None
            logger.warning("Web search not available - will rely on LLM knowledge only")
    
    def get_component_type_from_designator(self, designator: str) -> str:
        """Extract component type from designator prefix"""
        designator_upper = designator.upper()
        
        # Check multi-character prefixes first (e.g., "LED", "SW")
        for prefix, comp_type in sorted(self.COMPONENT_PREFIXES.items(), key=lambda x: -len(x[0])):
            if designator_upper.startswith(prefix):
                return comp_type
        
        return 'unknown'
    
    def analyze_component_with_llm(self, component: Dict[str, Any], max_retries: int = 2) -> Optional[Dict[str, Any]]:
        """
        Use LLM to analyze component and generate footprint specification
        
        Args:
            component: Component dict with designator, value, footprint, pin_count, etc.
            max_retries: Maximum number of retry attempts if generation fails (default: 2)
        
        Returns:
            Footprint specification dict with pad layout, dimensions, etc.
        """
        designator = component.get('designator', '')
        value = component.get('value', '')
        footprint = component.get('footprint', '')
        pin_count = component.get('pin_count', 0)
        lib_reference = component.get('lib_reference', '')
        
        comp_type = self.get_component_type_from_designator(designator)
        
        system_prompt = """You are an expert PCB footprint engineer specializing in IPC-7351 standard footprints and manufacturer datasheets. Your job is to research and generate accurate PCB footprint specifications.

CRITICAL: You MUST use your knowledge to look up EXACT IPC-7351 standard dimensions and manufacturer datasheet specifications. 
- Do NOT guess or approximate - use your training data knowledge of industry standards
- Do NOT use rounded or approximate values - use EXACT dimensions from IPC-7351 standards
- Pad sizes, spacing, and positions must be PRECISE - match industry standards exactly
- For common packages (0603, 0805, SOIC, SOT, TO-263, etc.), you have exact IPC-7351 dimensions in your training data - use them precisely

COORDINATE SYSTEM:
- All pad positions (x, y) are relative to component CENTER at (0, 0)
- X-axis: positive = right, negative = left
- Y-axis: positive = up, negative = down
- Component center is the geometric center of the component body

YOUR TASK:
1. Identify the package type from the component information provided
2. Use your knowledge of IPC-7351 standards to look up the EXACT dimensions - do not approximate
3. For power packages (TO-263, TO-252, etc.), use manufacturer datasheet specifications with EXACT values
4. For standard packages (0603, 0805, SOIC, SOT, etc.), use IPC-7351 nominal dimensions with EXACT values
5. Ensure pad sizes, positions, and spacing match industry standards EXACTLY - use precise values, not rounded approximations
6. For packages with thermal tabs, ensure the tab pad is large enough for heat dissipation (typically 6-10mm × 5-8mm)
7. Understand package mechanical structure:
   - Single-row packages (TO-263-7): All pins on one side only
   - Dual-row packages (SOIC, etc.): Pins on both sides
   - Power packages: May have large thermal tabs

DIMENSION ACCURACY REQUIREMENTS:
- Pad width and height must be EXACT IPC-7351 values (e.g., 0.95mm not 1.0mm, 1.5mm not 1.6mm)
- Pad spacing must be EXACT (e.g., 1.75mm not 1.8mm, 2.7mm not 2.5mm)
- Pad positions must be PRECISE (e.g., -2.7mm not -2.5mm, -4.5mm not -4.0mm)
- Do NOT round dimensions - use the exact values from IPC-7351 standards
- For power packages, use exact datasheet dimensions (e.g., TO-263-2 signal pads: 0.9mm × 2.0mm, Tab: 10.0mm × 7.5mm)

IMPORTANT PACKAGE CHARACTERISTICS:

- Passive SMD components (0603, 0805, 1206, etc.): Two pads, typically on opposite sides
- Diode packages (SOD-123, SOD-323, etc.): Two pads, typically on opposite sides
- Transistor packages (SOT-23, SOT-89, etc.): 3-5 pins, may have thermal tabs
- Power packages (TO-252, TO-263, etc.): Signal pins + large thermal tab pad
  - TO-263-7 (D²PAK-7): SINGLE-ROW package - all 7 pins on ONE SIDE ONLY, plus thermal tab
  - TO-263-2 (D²PAK): 3 pins + thermal tab
- IC packages (SOIC, TSSOP, etc.): Dual-row packages with pins on both sides
- Generic multi-pin: May be single-row or dual-row depending on package

KEY PRINCIPLES:
1. Use IPC-7351 standards for pad dimensions and spacing
2. Pad size = body width + appropriate extension for solder fillet
3. Pad spacing = calculated from body length and pad extension
4. Silkscreen: Slightly larger than body (typically +0.3-0.5mm each side)
5. Courtyard: Body + clearance (typically +0.5-1.0mm each side)
6. For dual-row packages: Pin 1 at left bottom, counter-clockwise numbering
7. For single-row packages: All pins on one side, sequential numbering
8. For power packages with tabs: Large thermal pad for heat dissipation

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
- Pad numbering must follow standard conventions (pin 1 marked, counter-clockwise for dual-row)
- For dual-row packages, ensure correct pin numbering sequence
- If footprint name is provided (e.g., "C2512", "R0603", "SOT-23", "TO-252", "SOIC-8", etc.), you MUST look up the correct IPC-7351 dimensions for that specific package
- For packages NOT listed in the reference examples above, use your knowledge of IPC-7351 standards to determine correct dimensions
- Extract package size from value string if present (e.g., "0603-0.1uF" -> 0603 package)
- DO NOT guess or approximate - use your knowledge of IPC-7351 standards to provide accurate dimensions
- If you're unsure about a package, look it up using your knowledge of industry standards (IPC-7351, JEDEC, etc.)
"""
        
        # Extract additional context from component
        pins = component.get('pins', [])
        description = component.get('description', '')
        
        # Build comprehensive component context
        pin_info = ""
        if pins:
            pin_numbers = [p.get('number', p.get('name', '')) for p in pins if isinstance(p, dict)]
            pin_info = f"Pin numbers found in schematic: {', '.join(str(p) for p in pin_numbers[:10])}" + (f" (and {len(pin_numbers)-10} more)" if len(pin_numbers) > 10 else "")
        
        user_message = f"""Analyze this component and generate a complete footprint specification with CORRECT IPC-7351 standard dimensions:

COMPONENT INFORMATION:
- Designator: {designator}
- Value: {value}
- Existing Footprint Name: {footprint}
- Library Reference: {lib_reference}
- Pin Count (from schematic): {pin_count}
- Detected Component Type: {comp_type}
- Description: {description}
- {pin_info}

CRITICAL PACKAGE IDENTIFICATION:
1. The "Existing Footprint Name" is the PRIMARY source for package identification
2. Match the footprint name to IPC-7351 standards (e.g., "TO-263-7" = TO-263-7 package, "SOT-23-5" = SOT-23-5 package)
3. If footprint name contains package info (e.g., "C2512" = 2512 package, "R0603" = 0603 package), use that
4. The pin_count from schematic may be INCOMPLETE - use the footprint name to determine the correct pin count
5. For power packages (TO-252, TO-263, etc.), you MUST include the thermal tab pad:
   - TO-263-2 (D²PAK): 3 signal pins (at bottom, negative y) + 1 large thermal tab (at top, positive y) = 4 pads total
   - TO-252 (DPAK): 3 signal pins (at bottom, negative y) + 1 large thermal tab (at top, positive y) = 4 pads total
   - TO-263-7 (D²PAK-7): 7 signal pins (all on left side, single-row) + 1 large thermal tab = 8 pads total
6. Power package layouts: Signal pins are typically at the bottom (negative y), thermal tab is at the top (positive y)

CRITICAL: You MUST use your knowledge to look up EXACT IPC-7351 standard dimensions and manufacturer datasheet specifications for the package type identified.

SEARCH FOR EXACT DIMENSIONS:
- Use your training data knowledge of IPC-7351 standards to find EXACT dimensions
- For common packages (0603, 0805, SOIC, SOT, TO-263, etc.), you have precise IPC-7351 values in your knowledge
- For power packages, use manufacturer datasheet specifications with EXACT values
- DO NOT approximate or round - use the precise values from standards
- If you're unsure, search your knowledge base for the exact package dimensions

INSTRUCTIONS:
1. Identify the package type from the footprint name, value, or library reference
2. Search your knowledge for EXACT IPC-7351 standard dimensions for this package
3. For power packages, search for manufacturer datasheet specifications with EXACT values
4. Generate ALL pads required for the package (don't omit any)
5. Ensure pad sizes, positions, and spacing match industry standards EXACTLY (not approximations)
6. For packages with thermal tabs, include the tab pad with correct size and position from datasheet
7. Understand package structure (single-row vs dual-row):
   - TO-263-7 (D²PAK-7): SINGLE-ROW - all 7 pins on ONE SIDE ONLY (left side, negative x), plus thermal tab (center, positive y)
   - TO-263-2 (D²PAK): 3 signal pins at bottom (negative y, typically y=-4.5mm), plus large thermal tab at top (positive y, typically y=+2.0mm)
   - TO-252 (DPAK): 3 signal pins at bottom (negative y, typically y=-3.4mm), plus large thermal tab at top (positive y, typically y=+1.5mm)
   - SOIC packages: DUAL-ROW - pins on both sides
   - SOT-23-5: DUAL-ROW - 3 pins left, 2 pins right
   - SOT-89: 3 signal pins at bottom (small pads ~0.6-0.8mm × 1.0-1.5mm) + 1 thermal tab at top (large pad ~1.5-2.0mm × 2.5-3.0mm) = 4 pads total
     CRITICAL: SOT-89 MUST have a thermal tab pad - it's a power package!
     Signal pins: typically 0.6mm × 1.0mm, positioned at y=-1.5mm, x=-1.5mm, 0mm, +1.5mm
     Thermal tab: typically 1.5mm × 2.5mm, positioned at y=+1.0mm, x=0mm

CRITICAL FOR POWER PACKAGES:
- Signal pins MUST be at the bottom (negative y coordinate)
- Thermal tab MUST be at the top (positive y coordinate) 
- Thermal tab MUST be much larger than signal pins (typically 6-10mm × 5-8mm)
- DO NOT place all pads at y=0.0 - power packages have vertical layout!

OUTPUT FORMAT:
{{
  "footprint_name": "package_name",
  "component_type": "resistor|capacitor|diode|transistor|ic|etc",
  "package_type": "smd|through_hole|mixed",
  "pads": [
    {{"name": "1", "x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "shape": "rectangular", "layer": "top", "hole_size": 0.0}}
  ],
  "silkscreen": {{"width": 0.0, "height": 0.0}},
  "courtyard": {{"width": 0.0, "height": 0.0}},
  "notes": "IPC-7351 standard footprint"
}}

IMPORTANT RULES:
1. PACKAGE IDENTIFICATION: Use the footprint name, library reference, or value field to identify the package type
2. PIN COUNT: The schematic pin_count may be incomplete - use the footprint name to determine the correct pin count
3. PAD POSITIONS: All pad positions (x, y) are relative to component center (0, 0) in millimeters - use EXACT values
4. PAD SIZES: Look up EXACT IPC-7351 dimensions for the package type - each package has specific pad dimensions
   CRITICAL: Use PRECISE values from IPC-7351 standards, not rounded approximations
   - For 0603: Pad width should be ~0.95mm (NOT 1.0mm), height ~1.0mm, spacing ~1.75mm
   - For 0805: Pad width should be ~1.2mm (NOT 1.0mm), height ~1.4mm, spacing ~2.0mm
   - For SOIC-8: Pad width 0.6mm, height 1.5mm, row spacing 5.4mm, pin pitch 1.27mm (EXACT)
   - For SOT-23: Pad width 0.6mm, height 0.7mm (NOT 0.6mm × 1.5mm)
   - For SOT-89: Signal pads 0.6mm × 1.0mm (NOT 1.5mm × 2.5mm), Thermal tab 1.5mm × 2.5mm at top
     CRITICAL: SOT-89 has 4 pads total: 3 small signal pads (at y=-1.5mm) + 1 large thermal tab (at y=+1.0mm)
   - For TO-263-2: Signal pads 0.9mm × 2.0mm, Tab 10.0mm × 7.5mm (EXACT datasheet values)
   - For TO-252: Signal pads 0.9mm × 1.5mm, Tab 6.0mm × 5.6mm (EXACT datasheet values)
5. PAD SPACING: Calculate EXACT spacing from body dimensions - do not approximate
   - Spacing = Body length - (pad extension on each side)
   - Use precise calculations, not rounded values
6. PACKAGE STRUCTURE: Understand if the package is single-row or dual-row
   - TO-263-7 (D²PAK-7): SINGLE-ROW - all 7 pins on ONE SIDE ONLY, plus thermal tab
   - SOIC packages: DUAL-ROW - pins on both sides
7. GENERATE ALL PADS: Do not omit any pads - generate the complete footprint
8. THERMAL TABS: For power packages, include the thermal tab pad with EXACT size from datasheet
9. SILKSCREEN & COURTYARD: Always include silkscreen and courtyard dimensions

CRITICAL JSON FORMAT REQUIREMENTS:
1. Return ONLY valid JSON - no markdown, no code blocks, no explanations
2. Each pad object must have ALL fields: "name", "x", "y", "width", "height", "shape", "layer", "hole_size"
3. All numeric values must be numbers (not strings)
4. Use your knowledge of IPC-7351 standards to provide accurate dimensions
5. For power packages, use manufacturer datasheet specifications when available

EXAMPLE - SOT-89 (4 pads: 3 signal + 1 thermal tab):
{{
  "footprint_name": "SOT-89",
  "component_type": "transistor",
  "package_type": "smd",
  "pads": [
    {{"name": "1", "x": -1.5, "y": -1.5, "width": 0.6, "height": 1.0, "shape": "rectangular", "layer": "top", "hole_size": 0.0}},
    {{"name": "2", "x": 0.0, "y": -1.5, "width": 0.6, "height": 1.0, "shape": "rectangular", "layer": "top", "hole_size": 0.0}},
    {{"name": "3", "x": 1.5, "y": -1.5, "width": 0.6, "height": 1.0, "shape": "rectangular", "layer": "top", "hole_size": 0.0}},
    {{"name": "Tab", "x": 0.0, "y": 1.0, "width": 1.5, "height": 2.5, "shape": "rectangular", "layer": "top", "hole_size": 0.0}}
  ],
  "silkscreen": {{"width": 4.5, "height": 4.0}},
  "courtyard": {{"width": 5.0, "height": 4.5}},
  "notes": "IPC-7351 standard footprint"
}}

Return ONLY the JSON object, nothing else."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Retry logic for LLM generation
        for attempt in range(max_retries + 1):
            try:
                # Use very low temperature for precise, deterministic results
                response = self.llm_client.chat(messages, temperature=0.0)
                
                if not response:
                    if attempt < max_retries:
                        logger.warning(f"Empty LLM response for {designator}, attempt {attempt + 1}/{max_retries + 1}, retrying...")
                        continue
                    logger.error(f"Empty LLM response for {designator} after {max_retries + 1} attempts")
                    return None
                
                # Improved JSON extraction - find the largest valid JSON object
                # Try to find JSON starting with { and ending with matching }
                json_str = None
                
                # Method 1: Try to find JSON block between ```json and ``` or just ```
                code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
                if code_block_match:
                    json_str = code_block_match.group(1)
                else:
                    # Method 2: Find JSON object by matching braces
                    brace_count = 0
                    start_idx = -1
                    for i, char in enumerate(response):
                        if char == '{':
                            if brace_count == 0:
                                start_idx = i
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0 and start_idx >= 0:
                                json_str = response[start_idx:i+1]
                                break
                
                # Method 3: Fallback to simple regex
                if not json_str:
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                
                if json_str:
                    try:
                        footprint_spec = json.loads(json_str)
                        
                        # Normalize pad numbering for dual-row packages (generic, no hard-coding)
                        footprint_spec = self._normalize_pad_numbering(footprint_spec, footprint, pin_count)
                        
                        # Validate dimensions and log warnings about incorrect values
                        self._validate_and_warn_dimensions(footprint_spec, footprint, designator)
                        
                        # Validate and check pad count
                        footprint_spec = self._validate_footprint_spec_basic(footprint_spec, footprint, pin_count)
                        
                        if footprint_spec:
                            # Try to refine dimensions if they seem incorrect (second LLM call for accuracy)
                            try:
                                footprint_spec = self._refine_dimensions_with_llm(footprint_spec, component, footprint)
                            except Exception as refine_error:
                                logger.warning(f"Dimension refinement failed for {designator} ({footprint}): {refine_error}")
                                # Continue with original spec if refinement fails
                                pass
                            # Double-check pad count matches
                            pads = footprint_spec.get('pads', [])
                            non_tab_pads = [p for p in pads if p.get('name', '').lower() != 'tab']
                            
                            if pin_count > 0 and len(non_tab_pads) != pin_count:
                                logger.warning(f"Pad count mismatch after validation for {designator}: expected {pin_count} pins, got {len(non_tab_pads)} pads. Response may be truncated.")
                                # Log the actual pads we got
                                pad_names = [p.get('name', '') for p in pads]
                                logger.warning(f"Pads received: {pad_names}")
                                
                                # Try to detect if pads are missing from a sequence
                                pad_numbers = []
                                for p in non_tab_pads:
                                    try:
                                        pad_num = int(p.get('name', '0'))
                                        pad_numbers.append(pad_num)
                                    except ValueError:
                                        pass
                                
                                if pad_numbers:
                                    pad_numbers.sort()
                                    expected_numbers = list(range(1, pin_count + 1))
                                    missing = [n for n in expected_numbers if n not in pad_numbers]
                                    if missing:
                                        logger.warning(f"Missing pad numbers: {missing}. This suggests the LLM response was truncated.")
                            
                            # Validate pad dimensions and log warnings
                            self._validate_pad_dimensions(footprint_spec, footprint, designator)
                            
                            logger.info(f"Generated footprint for {designator}: {footprint_spec.get('footprint_name')} with {len(pads)} pads ({len(non_tab_pads)} signal pads, {len(pads) - len(non_tab_pads)} tabs)")
                            return footprint_spec
                    except json.JSONDecodeError as e:
                        if attempt < max_retries:
                            logger.warning(f"JSON decode error for {designator}, attempt {attempt + 1}/{max_retries + 1}, retrying...")
                            logger.debug(f"JSON string: {json_str[:500]}...")
                            continue
                        logger.error(f"JSON decode error for {designator} after {max_retries + 1} attempts: {e}")
                        logger.debug(f"JSON string: {json_str[:500]}...")
                        return None
                else:
                    if attempt < max_retries:
                        logger.warning(f"No JSON found in LLM response for {designator}, attempt {attempt + 1}/{max_retries + 1}, retrying...")
                        logger.debug(f"Response preview: {response[:500]}...")
                        continue
                    logger.warning(f"No JSON found in LLM response for {designator} after {max_retries + 1} attempts")
                    logger.debug(f"Response preview: {response[:500]}...")
                    return None
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Error generating footprint for {designator}, attempt {attempt + 1}/{max_retries + 1}, retrying: {e}")
                    continue
                logger.error(f"Error generating footprint for {designator} after {max_retries + 1} attempts: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                return None
        
        return None
    
    def _validate_and_warn_dimensions(self, spec: Dict[str, Any], footprint_name: str, designator: str) -> None:
        """
        Validate pad dimensions and log warnings if they seem incorrect.
        This is for debugging - does NOT correct dimensions (no hard-coding).
        Checks for common issues like wrong pad sizes, incorrect spacing, etc.
        """
        if not spec or 'pads' not in spec:
            return
        
        pads = spec.get('pads', [])
        footprint_name_upper = footprint_name.upper().strip()
        
        # Check for obviously wrong dimensions for common packages
        if '0603' in footprint_name_upper:
            for pad in pads:
                width = pad.get('width', 0)
                height = pad.get('height', 0)
                # 0603 should have pads around 0.95mm × 1.0mm
                if width > 1.2 or width < 0.7 or height > 1.3 or height < 0.8:
                    logger.warning(f"{designator} ({footprint_name}): Pad {pad.get('name')} size {width}×{height}mm seems wrong for 0603 (expected ~0.95×1.0mm)")
        
        if '0805' in footprint_name_upper:
            for pad in pads:
                width = pad.get('width', 0)
                height = pad.get('height', 0)
                # 0805 should have pads around 1.2mm × 1.4mm
                if width > 1.5 or width < 0.9 or height > 1.7 or height < 1.1:
                    logger.warning(f"{designator} ({footprint_name}): Pad {pad.get('name')} size {width}×{height}mm seems wrong for 0805 (expected ~1.2×1.4mm)")
        
        if 'SOT-23' in footprint_name_upper and 'SOT-23-5' not in footprint_name_upper:
            for pad in pads:
                pad_name = pad.get('name', '').lower()
                if pad_name != 'tab':
                    width = pad.get('width', 0)
                    height = pad.get('height', 0)
                    # SOT-23 should have pads around 0.6mm × 0.7mm
                    if abs(width - 0.6) > 0.1 or abs(height - 0.7) > 0.1:
                        logger.warning(f"{designator} ({footprint_name}): Pad {pad.get('name')} size {width}×{height}mm seems wrong for SOT-23 (expected 0.6×0.7mm)")
        
        if 'SOT-89' in footprint_name_upper:
            # SOT-89 must have 4 pads: 3 signal pads + 1 thermal tab
            non_tab_pads = [p for p in pads if p.get('name', '').lower() != 'tab']
            tab_pads = [p for p in pads if p.get('name', '').lower() == 'tab']
            
            if len(tab_pads) == 0:
                logger.warning(f"{designator} ({footprint_name}): SOT-89 is missing required thermal tab pad - REJECTING")
                return None  # Reject SOT-89 without tab
            
            if len(non_tab_pads) != 3:
                logger.warning(f"{designator} ({footprint_name}): SOT-89 should have 3 signal pads, got {len(non_tab_pads)}")
            
            # Check signal pad sizes (should be small, ~0.6mm × 1.0mm)
            for pad in non_tab_pads:
                width = pad.get('width', 0)
                height = pad.get('height', 0)
                # Signal pads should be small
                if width > 1.0 or height > 1.5:
                    logger.warning(f"{designator} ({footprint_name}): Signal pad {pad.get('name')} size {width}×{height}mm seems wrong for SOT-89 (expected ~0.6×1.0mm for signal pads)")
            
            # Check thermal tab size (should be large, ~1.5mm × 2.5mm)
            if len(tab_pads) > 0:
                tab = tab_pads[0]
                tab_width = tab.get('width', 0)
                tab_height = tab.get('height', 0)
                if tab_width < 1.0 or tab_height < 2.0:
                    logger.warning(f"{designator} ({footprint_name}): Thermal tab size {tab_width}×{tab_height}mm seems too small for SOT-89 (expected ~1.5×2.5mm)")
        
        # Check pad spacing for 2-pin packages
        non_tab_pads = [p for p in pads if p.get('name', '').lower() != 'tab']
        if len(non_tab_pads) == 2:
            pad1_x = non_tab_pads[0].get('x', 0)
            pad2_x = non_tab_pads[1].get('x', 0)
            spacing = abs(pad2_x - pad1_x)
            
            if '0603' in footprint_name_upper:
                # 0603 spacing should be around 1.75mm
                if abs(spacing - 1.75) > 0.2:
                    logger.warning(f"{designator} ({footprint_name}): Pad spacing {spacing:.2f}mm seems wrong for 0603 (expected ~1.75mm)")
            
            if '0805' in footprint_name_upper:
                # 0805 spacing should be around 2.0mm
                if abs(spacing - 2.0) > 0.2:
                    logger.warning(f"{designator} ({footprint_name}): Pad spacing {spacing:.2f}mm seems wrong for 0805 (expected ~2.0mm)")
    
    def _refine_dimensions_with_llm(self, spec: Dict[str, Any], component: Dict[str, Any], footprint_name: str) -> Dict[str, Any]:
        """
        Use LLM to refine dimensions if they seem incorrect.
        This is a second pass to improve accuracy without hard-coding.
        """
        try:
            if not spec or 'pads' not in spec:
                return spec
            
            if not footprint_name:
                return spec
            
            # Check if dimensions seem wrong
            pads = spec.get('pads', [])
            footprint_name_upper = footprint_name.upper().strip()
            needs_refinement = False
            
            # Check for common issues that suggest wrong dimensions
            if '0603' in footprint_name_upper and len(pads) == 2:
                for pad in pads:
                    width = pad.get('width', 0)
                    height = pad.get('height', 0)
                    if width > 1.2 or width < 0.7 or height > 1.3 or height < 0.8:
                        needs_refinement = True
                        break
            
            if '0805' in footprint_name_upper and len(pads) == 2:
                for pad in pads:
                    width = pad.get('width', 0)
                    height = pad.get('height', 0)
                    if width > 1.5 or width < 0.9 or height > 1.7 or height < 1.1:
                        needs_refinement = True
                        break
            
            # If dimensions seem wrong, ask LLM to correct them
            if needs_refinement:
                logger.info(f"Dimensions seem incorrect for {footprint_name}, asking LLM to refine...")
                refinement_prompt = f"""The following footprint specification has incorrect dimensions. Please correct them to match EXACT IPC-7351 standards.

Footprint Name: {footprint_name}
Current Specification:
{json.dumps(spec, indent=2)}

CRITICAL: You must provide EXACT IPC-7351 dimensions, not approximations. Use precise values from IPC-7351 standards.

Return ONLY the corrected JSON object with exact dimensions, nothing else."""
                
                try:
                    refinement_response = self.llm_client.chat([
                        {"role": "system", "content": "You are an expert PCB engineer. Correct footprint dimensions to match EXACT IPC-7351 standards. Return only valid JSON."},
                        {"role": "user", "content": refinement_prompt}
                    ], temperature=0.0)
                    
                    if refinement_response:
                        # Extract JSON from refinement response
                        json_match = re.search(r'\{.*\}', refinement_response, re.DOTALL)
                        if json_match:
                            refined_spec = json.loads(json_match.group(0))
                            logger.info(f"Refined dimensions for {footprint_name}")
                            return refined_spec
                except Exception as e:
                    logger.debug(f"Dimension refinement failed for {footprint_name}: {e}")
            
            return spec
        
        except Exception as e:
            logger.warning(f"Error in dimension refinement for {footprint_name if footprint_name else 'unknown'}: {e}")
            # Return original spec if any error occurs
            return spec
    
    def _validate_pad_dimensions(self, spec: Dict[str, Any], footprint_name: str, designator: str) -> None:
        """
        Validate pad dimensions and log warnings if they seem incorrect.
        This is for debugging - does NOT correct dimensions (no hard-coding).
        """
        if not spec or 'pads' not in spec:
            return
        
        pads = spec.get('pads', [])
        footprint_name_upper = footprint_name.upper().strip()
        
        # Check for common issues
        all_same_size = True
        if len(pads) > 1:
            first_pad = pads[0]
            first_width = first_pad.get('width', 0)
            first_height = first_pad.get('height', 0)
            
            for pad in pads[1:]:
                pad_name = pad.get('name', '').lower()
                # Skip tab pads - they should be different
                if pad_name == 'tab':
                    continue
                
                pad_width = pad.get('width', 0)
                pad_height = pad.get('height', 0)
                
                if abs(pad_width - first_width) > 0.01 or abs(pad_height - first_height) > 0.01:
                    all_same_size = False
                    break
            
            # Warn if all pads have the same size (might indicate wrong dimensions)
            if all_same_size and len(pads) > 2:
                logger.warning(f"{designator} ({footprint_name}): All pads have same size {first_width}×{first_height}mm - verify this is correct for package type")
        
        # Check for specific package type issues (log only, don't correct)
        if 'SOT-23-5' in footprint_name_upper:
            for pad in pads:
                pad_name = pad.get('name', '').lower()
                if pad_name != 'tab':
                    width = pad.get('width', 0)
                    height = pad.get('height', 0)
                    if abs(width - 0.6) > 0.01 or abs(height - 0.7) > 0.01:
                        logger.warning(f"{designator} ({footprint_name}): Pad {pad.get('name')} size is {width}×{height}mm, expected 0.6×0.7mm for SOT-23-5")
        
        # Log pad dimensions for debugging
        if logger.isEnabledFor(logging.DEBUG):
            for pad in pads:
                logger.debug(f"{designator} pad {pad.get('name')}: {pad.get('width')}×{pad.get('height')}mm at ({pad.get('x')}, {pad.get('y')})")
    
    def _normalize_pad_numbering(self, spec: Dict[str, Any], footprint_name: str, pin_count: int) -> Dict[str, Any]:
        """
        Generic normalization of pad numbering for dual-row packages.
        Does NOT hard-code specific package types - works generically for any dual-row package.
        """
        if not spec or 'pads' not in spec:
            return spec
        
        pads = spec.get('pads', [])
        non_tab_pads = [p for p in pads if p.get('name', '').lower() != 'tab']
        
        # Only normalize if we have a dual-row arrangement (pads on both left and right)
        if len(non_tab_pads) >= 4 and pin_count >= 4:
            left_pads = [p for p in non_tab_pads if p.get('x', 0) < -0.1]
            right_pads = [p for p in non_tab_pads if p.get('x', 0) > 0.1]
            
            # Only proceed if we have pads on both sides (dual-row)
            if len(left_pads) > 0 and len(right_pads) > 0:
                # Sort left pads by y (bottom to top) - pins 1, 2, 3...
                left_pads.sort(key=lambda p: p.get('y', 0))
                
                # For right side: Standard convention is counter-clockwise
                # This means: after left side (bottom to top), continue at right top, then down
                # So right side should be sorted top to bottom (negative y first)
                # Check if this is a power package (TO-263, TO-252) - these have different conventions
                # NOTE: TO-263-7 is SINGLE-ROW and will be handled separately below
                is_power_package = any(x in footprint_name_upper for x in ['TO-263', 'TO-252', 'DPAK', 'D2PAK'])
                
                # Check if this is TO-263-7 or similar single-row power package
                is_single_row_power = 'TO-263-7' in footprint_name_upper or 'D2PAK-7' in footprint_name_upper
                
                if is_single_row_power:
                    # TO-263-7 is SINGLE-ROW - all pins on one side, no right side!
                    # Don't normalize - let LLM handle it correctly
                    logger.debug(f"Skipping normalization for single-row package {footprint_name}")
                    return spec
                elif is_power_package:
                    # Power packages: right side goes bottom to top (4, 5, 6, 7)
                    right_pads.sort(key=lambda p: p.get('y', 0))
                else:
                    # Standard IC packages: right side goes top to bottom (counter-clockwise)
                    right_pads.sort(key=lambda p: -p.get('y', 0))
                
                # Renumber sequentially: left side first, then right side
                pad_num = 1
                for pad in left_pads:
                    pad['name'] = str(pad_num)
                    pad_num += 1
                
                for pad in right_pads:
                    pad['name'] = str(pad_num)
                    pad_num += 1
                
                logger.debug(f"Normalized pad numbering for {footprint_name}: {len(left_pads)} left, {len(right_pads)} right (power_package={is_power_package})")
        
        return spec
    
    def _validate_footprint_spec_basic(self, spec: Dict[str, Any], footprint_name: str, pin_count: int) -> Dict[str, Any]:
        """
        Basic validation - check for obvious structural errors (missing pads, invalid values)
        Do NOT correct dimensions - trust the LLM to provide correct IPC-7351 dimensions from its knowledge
        """
        pads = spec.get('pads', [])
        
        # Only validate structure, not dimensions
        if not pads:
            logger.warning(f"No pads found in footprint spec for {footprint_name}, using fallback")
            return None
        
        # Count non-tab pads (tabs are named "Tab" or "tab")
        non_tab_pads = [p for p in pads if p.get('name', '').lower() != 'tab']
        actual_pin_count = len(non_tab_pads)
        tab_count = len([p for p in pads if p.get('name', '').lower() == 'tab'])
        total_pads = len(pads)
        
        # Check for required tabs in power packages
        footprint_name_upper = footprint_name.upper().strip()
        is_power_package = any(x in footprint_name_upper for x in ['TO-263', 'TO-252', 'DPAK', 'D2PAK', 'D²PAK', 'SOT-89'])
        
        if is_power_package and tab_count == 0:
            logger.warning(f"Power package {footprint_name} is missing required thermal tab pad - REJECTING (must have tab)")
            # Reject power packages without tabs - they're unusable
            return None
        
        # Check if pad count matches pin_count (be VERY lenient - schematic pin_count may be incomplete or wrong)
        # Only reject if pad count is clearly wrong (too few pads, or way too many without tabs)
        if pin_count > 0:
            # Allow more tolerance: schematic pin_count may be incomplete or wrong
            # Only reject if we have significantly fewer pads than expected (at least 1 pad minimum)
            if actual_pin_count < 1:  # Must have at least 1 pad
                logger.warning(f"No pads found for {footprint_name} - rejecting")
                return None
            
            # Don't reject based on pin_count mismatch - accept what LLM generated
            # The LLM may know better than the schematic pin_count
            if actual_pin_count < max(1, int(pin_count * 0.2)):  # At least 20% of expected pins, or at least 1 pad
                logger.warning(f"Pad count seems low for {footprint_name}: expected {pin_count} pins, got {actual_pin_count} pads - but accepting anyway")
                # Don't reject - accept the footprint
            
            # If we have way more pads than pins without tabs, might be an issue (but allow 3x for packages with many pins)
            if total_pads > pin_count * 3.0 and tab_count == 0:
                logger.warning(f"Pad count seems high for {footprint_name}: expected {pin_count} pins, got {total_pads} pads (no tabs) - but accepting anyway")
                # Don't reject - accept the footprint
        
        # Check for obviously invalid values (negative sizes, zero spacing, etc.)
        for pad in pads:
            if pad.get('width', 0) <= 0 or pad.get('height', 0) <= 0:
                logger.warning(f"Invalid pad dimensions in {footprint_name} pad {pad.get('name', 'unknown')}: width={pad.get('width')}, height={pad.get('height')} - but accepting anyway")
                # Don't reject - try to fix by setting minimum size
                if pad.get('width', 0) <= 0:
                    pad['width'] = 0.5  # Default minimum
                if pad.get('height', 0) <= 0:
                    pad['height'] = 0.5  # Default minimum
        
        # For 2-pin footprints, ensure pads are on opposite sides (but be VERY lenient)
        if len(non_tab_pads) == 2:
            pad1_x = non_tab_pads[0].get('x', 0)
            pad2_x = non_tab_pads[1].get('x', 0)
            spacing = abs(pad2_x - pad1_x)
            
            # Only flag if spacing is unreasonably small (<0.01mm) or very large (>200mm)
            if spacing < 0.01:  # Very small spacing - might be an error
                logger.warning(f"Pad spacing very small ({spacing:.2f}mm) for {footprint_name} - but accepting anyway")
                # Don't reject - accept the footprint
            if spacing > 200:  # Very large spacing - might be an error
                logger.warning(f"Pad spacing very large ({spacing:.2f}mm) for {footprint_name} - but accepting anyway")
                # Don't reject - accept the footprint
        
        # Check for duplicate pad names (except tabs) - fix by renaming duplicates
        pad_names = [p.get('name', '') for p in non_tab_pads]
        if len(pad_names) != len(set(pad_names)):
            logger.warning(f"Duplicate pad names found in {footprint_name} - fixing by renaming")
            # Fix duplicates by renaming
            seen = set()
            for pad in non_tab_pads:
                pad_name = pad.get('name', '').lower()
                original_name = pad.get('name', '')
                if pad_name in seen:
                    # Rename duplicate
                    pad_num = 1
                    while f"{pad_name}_{pad_num}" in seen:
                        pad_num += 1
                    pad['name'] = f"{original_name}_{pad_num}"
                    seen.add(f"{pad_name}_{pad_num}")
                else:
                    seen.add(pad_name)
        
        # Ensure silkscreen and courtyard are present
        if 'silkscreen' not in spec or not spec.get('silkscreen'):
            logger.warning(f"Missing silkscreen in {footprint_name}, adding default")
            # Add default silkscreen based on pad extents
            if pads:
                x_coords = [p.get('x', 0) for p in pads]
                y_coords = [p.get('y', 0) for p in pads]
                max_width = max([abs(x) + p.get('width', 0)/2 for x, p in zip(x_coords, pads)])
                max_height = max([abs(y) + p.get('height', 0)/2 for y, p in zip(y_coords, pads)])
                spec['silkscreen'] = {
                    'width': max_width * 2 + 1.0,
                    'height': max_height * 2 + 1.0
                }
        
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
        failed_footprints = []
        for footprint_key, group_data in footprint_groups.items():
            footprint_name = group_data['footprint_name']
            representative = group_data['representative']
            component_count = len(group_data['components'])
            component_designators = [comp.get('designator') for comp in group_data['components']]
            
            logger.info(f"Generating footprint '{footprint_name}' for {component_count} components ({', '.join(component_designators[:5])}{'...' if len(component_designators) > 5 else ''}) using LLM")
            
            # Generate footprint spec using LLM (one call per unique footprint)
            footprint_spec = self.analyze_component_with_llm(representative)
            
            if not footprint_spec:
                # LLM generation failed - track for reporting
                logger.error(f"LLM generation failed for {footprint_name} - skipping footprint (affects {component_count} components: {', '.join(component_designators[:5])}{'...' if len(component_designators) > 5 else ''})")
                failed_footprints.append({
                    'footprint_name': footprint_name,
                    'component_count': component_count,
                    'designators': component_designators
                })
                continue
            
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
                # LLM generation failed - skip this component
                logger.error(f"LLM generation failed for {designator} - skipping component")
                results[designator] = None
        
        # Also return footprint_specs for library generation
        results['_footprint_libraries'] = footprint_specs
        
        # Log summary
        successful_components = sum(1 for r in results.values() if r and isinstance(r, dict) and 'pads' in r)
        failed_components = len(components) - successful_components
        
        logger.info(f"Generated {len(footprint_specs)} unique footprints for {len(components)} components")
        logger.info(f"Successfully mapped {successful_components} components, {failed_components} components failed")
        
        if failed_footprints:
            logger.warning(f"Failed to generate {len(failed_footprints)} footprints, affecting {sum(f['component_count'] for f in failed_footprints)} components:")
            for ff in failed_footprints:
                logger.warning(f"  - {ff['footprint_name']}: {ff['component_count']} components ({', '.join(ff['designators'][:3])}{'...' if len(ff['designators']) > 3 else ''})")
        
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
    
    # REMOVED: _generate_fallback_footprint - no hard-coded fallbacks
    # The LLM should always generate footprints using its knowledge of IPC-7351 standards
    
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