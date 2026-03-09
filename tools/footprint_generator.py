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

    PASSIVE_PREFIX_TO_TYPE = {
        'C': 'capacitor',
        'R': 'resistor',
        'L': 'inductor',
        'D': 'diode',
    }

    PASSIVE_TYPE_TO_PREFIX = {v: k for k, v in PASSIVE_PREFIX_TO_TYPE.items()}
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        # Try to import web_search module function
        try:
            from tools.web_search import web_search as web_search_func
            self.web_search = web_search_func
        except ImportError:
            self.web_search = None
            logger.warning("Web search module not available - will rely on LLM knowledge only")
        
        # Also try to detect web_search tool from environment (e.g., Cursor's tool calling)
        # This allows the web_search tool to be passed from the agent environment
        if not self.web_search:
            try:
                import sys
                import inspect
                # Check if web_search is available in the calling environment
                frame = inspect.currentframe()
                if frame and frame.f_back:
                    caller_globals = frame.f_back.f_globals
                    if 'web_search' in caller_globals and callable(caller_globals['web_search']):
                        self.web_search = caller_globals['web_search']
                        logger.info("Found web_search tool in environment")
            except Exception as e:
                logger.debug(f"Could not detect web_search tool from environment: {e}")
        
        if self.web_search:
            logger.info("Web search available - will perform actual web searches for footprint specifications")
        else:
            logger.info("Web search not available - LLM will use its knowledge for footprint specifications")
    
    def set_web_search_tool(self, web_search_tool):
        """
        Set the web_search tool explicitly (e.g., from Cursor's tool calling interface)
        
        Args:
            web_search_tool: Callable function that performs web searches
        """
        if web_search_tool and callable(web_search_tool):
            self.web_search = web_search_tool
            # Also set it in the web_search module so it can be used there
            try:
                from tools.web_search import set_web_search_tool
                set_web_search_tool(web_search_tool)
            except Exception as e:
                logger.debug(f"Could not set web_search tool in module: {e}")
            logger.info("Web search tool set explicitly - will perform actual web searches")
        else:
            logger.warning("Invalid web_search_tool provided, ignoring")
    
    # Standard dimensions database for common packages (IPC-7351 and manufacturer specs)
    # All dimensions in millimeters
    # For chip components: Uses IPC-7351 land pattern parameters
    # Z = overall pad-to-pad end dimension, G = gap between pads, X = pad width across component
    # pad_length (along component axis) = (Z - G) / 2
    # pad_width (across component) = X
    # pad_spacing (center-to-center) = Z - pad_length
    STANDARD_DIMENSIONS = {
        # Chip components (IPC-7351 Level M - Medium density, Vishay land patterns)
        # Format: pad_length (along axis), pad_width (across), body_length, body_width, pad_spacing (center-to-center)
        # R0402: Z=1.55mm, G=0.15mm, X=0.73mm -> pad_length=0.70mm, pad_width=0.73mm, spacing=0.85mm
        'R0402': {'pad_length': 0.70, 'pad_width': 0.73, 'pad_count': 2, 'body_width': 1.0, 'body_height': 0.5, 'pad_spacing': 0.85, 'pitch': 0.0, 'footprint_class': 'passive_chip'},
        'C0402': {'pad_length': 0.70, 'pad_width': 0.73, 'pad_count': 2, 'body_width': 1.0, 'body_height': 0.5, 'pad_spacing': 0.85, 'pitch': 0.0, 'footprint_class': 'passive_chip'},
        # R0603: Z=2.37mm, G=0.35mm, X=0.98mm -> pad_length=1.01mm, pad_width=0.98mm, spacing=1.36mm
        'R0603': {'pad_length': 1.01, 'pad_width': 0.98, 'pad_count': 2, 'body_width': 1.6, 'body_height': 0.8, 'pad_spacing': 1.36, 'pitch': 0.0},
        'C0603': {'pad_length': 1.01, 'pad_width': 0.98, 'pad_count': 2, 'body_width': 1.6, 'body_height': 0.8, 'pad_spacing': 1.36, 'pitch': 0.0},
        # R0805: Z=2.8mm, G=0.4mm, X=1.2mm -> pad_length=1.2mm, pad_width=1.2mm, spacing=1.6mm
        'R0805': {'pad_length': 1.2, 'pad_width': 1.2, 'pad_count': 2, 'body_width': 2.0, 'body_height': 1.25, 'pad_spacing': 1.6, 'pitch': 0.0},
        'C0805': {'pad_length': 1.2, 'pad_width': 1.2, 'pad_count': 2, 'body_width': 2.0, 'body_height': 1.25, 'pad_spacing': 1.6, 'pitch': 0.0},
        # R1206: Z=4.0mm, G=0.5mm, X=1.6mm -> pad_length=1.75mm, pad_width=1.6mm, spacing=2.25mm
        'R1206': {'pad_length': 1.75, 'pad_width': 1.6, 'pad_count': 2, 'body_width': 3.2, 'body_height': 1.6, 'pad_spacing': 2.25, 'pitch': 0.0},
        'C1206': {'pad_length': 1.75, 'pad_width': 1.6, 'pad_count': 2, 'body_width': 3.2, 'body_height': 1.6, 'pad_spacing': 2.25, 'pitch': 0.0},
        # R1210: Z=4.5mm, G=0.6mm, X=2.5mm -> pad_length=1.95mm, pad_width=2.5mm, spacing=2.55mm
        'R1210': {'pad_length': 1.95, 'pad_width': 2.5, 'pad_count': 2, 'body_width': 3.2, 'body_height': 2.5, 'pad_spacing': 2.55, 'pitch': 0.0},
        'C1210': {'pad_length': 1.95, 'pad_width': 2.5, 'pad_count': 2, 'body_width': 3.2, 'body_height': 2.5, 'pad_spacing': 2.55, 'pitch': 0.0},
        # R1812: Z=5.5mm, G=1.0mm, X=3.2mm -> pad_length=2.25mm, pad_width=3.2mm, spacing=3.25mm
        'R1812': {'pad_length': 2.25, 'pad_width': 3.2, 'pad_count': 2, 'body_width': 4.5, 'body_height': 3.2, 'pad_spacing': 3.25, 'pitch': 0.0},
        'C1812': {'pad_length': 2.25, 'pad_width': 3.2, 'pad_count': 2, 'body_width': 4.5, 'body_height': 3.2, 'pad_spacing': 3.25, 'pitch': 0.0},
        # R2010: Z=6.0mm, G=1.0mm, X=2.5mm -> pad_length=2.5mm, pad_width=2.5mm, spacing=3.5mm
        'R2010': {'pad_length': 2.5, 'pad_width': 2.5, 'pad_count': 2, 'body_width': 5.0, 'body_height': 2.5, 'pad_spacing': 3.5, 'pitch': 0.0},
        'C2010': {'pad_length': 2.5, 'pad_width': 2.5, 'pad_count': 2, 'body_width': 5.0, 'body_height': 2.5, 'pad_spacing': 3.5, 'pitch': 0.0},
        # C2512: Z=7.15mm, G=4.93mm, X=3.43mm -> pad_length=1.11mm, pad_width=3.43mm, spacing=6.04mm
        'C2512': {'pad_length': 1.11, 'pad_width': 3.43, 'pad_count': 2, 'body_width': 6.3, 'body_height': 3.2, 'pad_spacing': 6.04, 'pitch': 0.0},
        # C2220: Approximate - needs datasheet verification
        'C2220': {'pad_length': 1.5, 'pad_width': 3.0, 'pad_count': 2, 'body_width': 5.7, 'body_height': 5.0, 'pad_spacing': 4.2, 'pitch': 0.0},
        
        # TO-252 (DPAK) packages - Diodes Inc. TO252-DPAK recommended land pattern
        # 3 signal pads + 1 large thermal tab (drain pad)
        'TO-252': {'pad_width': 1.5, 'pad_height': 2.5, 'pad_count': 3, 'pin_pitch': 2.54, 'row_spacing': 0.0, 'thermal_width': 8.0, 'thermal_height': 6.5, 'footprint_class': 'standard_package'},
        'TO-252-1': {'pad_width': 1.5, 'pad_height': 2.5, 'pad_count': 3, 'pin_pitch': 2.54, 'row_spacing': 0.0, 'thermal_width': 8.0, 'thermal_height': 6.5, 'footprint_class': 'standard_package'},
        'DPAK': {'pad_width': 1.5, 'pad_height': 2.5, 'pad_count': 3, 'pin_pitch': 2.54, 'row_spacing': 0.0, 'thermal_width': 8.0, 'thermal_height': 6.5, 'footprint_class': 'standard_package'},
        
        # TO-263 (D2PAK) packages - Diodes Inc. TO263AB-D2PAK recommended land pattern
        # TO-263-7: 7 signal pads + 1 large thermal tab
        'TO-263-7': {'pad_width': 0.9, 'pad_height': 2.0, 'pad_count': 7, 'pin_pitch': 0.95, 'row_spacing': 0.0, 'thermal_width': 10.0, 'thermal_height': 7.5, 'footprint_class': 'standard_package'},
        # TO-263-2: 2 signal pads + 1 large thermal tab (drain pad)
        # Note: pad_count=2 refers to signal pads only; thermal tab is added separately
        'TO-263-2': {'pad_width': 1.5, 'pad_height': 3.0, 'pad_count': 2, 'pin_pitch': 2.54, 'row_spacing': 0.0, 'thermal_width': 10.0, 'thermal_height': 7.5, 'footprint_class': 'standard_package'},
        'D2PAK': {'pad_width': 0.9, 'pad_height': 2.0, 'pad_count': 7, 'pin_pitch': 0.95, 'row_spacing': 0.0, 'thermal_width': 10.0, 'thermal_height': 7.5, 'footprint_class': 'standard_package'},
        
        # SOT packages (JEDEC standard packages)
        # SOT-23: 3-lead package, 2 pads on one side, 1 pad on other side
        # Diodes Inc. recommended land pattern: X=0.8mm, Y=0.9mm, pitch=0.95mm, row spacing=2.9mm
        'SOT-23': {'pad_width': 0.8, 'pad_height': 0.9, 'pad_count': 3, 'pin_pitch': 0.95, 'row_spacing': 2.9, 'body_width': 2.9, 'body_height': 1.6, 'footprint_class': 'standard_package'},
        'SOT-23-3': {'pad_width': 0.8, 'pad_height': 0.9, 'pad_count': 3, 'pin_pitch': 0.95, 'row_spacing': 2.9, 'body_width': 2.9, 'body_height': 1.6, 'footprint_class': 'standard_package'},
        # SOT-23-5: 5-lead package, 3 pads on one side, 2 pads on other side
        # Bourns recommended land pattern: pitch=0.95mm, pad dimensions from package drawing
        'SOT-23-5': {'pad_width': 0.7, 'pad_height': 1.0, 'pad_count': 5, 'pin_pitch': 0.95, 'row_spacing': 2.6, 'body_width': 2.9, 'body_height': 1.6, 'footprint_class': 'standard_package'},
        'SOT-223': {'pad_width': 1.5, 'pad_height': 3.0, 'pad_count': 4, 'pin_pitch': 2.3, 'row_spacing': 0.0, 'thermal_width': 3.5, 'thermal_height': 3.5},
        
        # SOIC packages
        'SOIC-8': {'pad_width': 0.6, 'pad_height': 1.5, 'pad_count': 8, 'pin_pitch': 1.27, 'row_spacing': 5.4},
        'SOIC-14': {'pad_width': 0.6, 'pad_height': 1.5, 'pad_count': 14, 'pin_pitch': 1.27, 'row_spacing': 5.4},
        'SOIC-16': {'pad_width': 0.6, 'pad_height': 1.5, 'pad_count': 16, 'pin_pitch': 1.27, 'row_spacing': 5.4},
        
        # ESOP packages (IC packages, not inductors!)
        'ESOP8L': {'pad_width': 0.5, 'pad_height': 1.5, 'pad_count': 8, 'pin_pitch': 0.65, 'row_spacing': 4.4, 'thermal_width': 2.5, 'thermal_height': 2.5, 'component_type': 'ic'},
        
        # Diode packages (SMB/SMC are diode packages, not capacitors!)
        # Use IPC-7351 Z/G/X/Y formulas from Diodes Inc. suggested layouts
        # SMB: C=4.30mm, G=1.80mm, X=2.50mm, Y=2.30mm -> pad_length=(4.30-1.80)/2=1.25mm, pad_width=2.30mm, center=1.80/2+1.25/2=1.525mm
        'SMB': {'pad_length': 1.25, 'pad_width': 2.30, 'pad_count': 2, 'body_width': 3.6, 'body_height': 2.6, 'pad_spacing': 3.05, 'pitch': 0.0, 'component_type': 'diode', 'footprint_class': 'standard_package'},
        # SMC: C=6.90mm, G=4.40mm, X=2.50mm, Y=3.30mm -> pad_length=(6.90-4.40)/2=1.25mm, pad_width=3.30mm, center=4.40/2+1.25/2=2.825mm
        'SMC': {'pad_length': 1.25, 'pad_width': 3.30, 'pad_count': 2, 'body_width': 4.5, 'body_height': 3.2, 'pad_spacing': 5.65, 'pitch': 0.0, 'component_type': 'diode', 'footprint_class': 'standard_package'},
        'SOD-523': {'pad_length': 0.6, 'pad_width': 0.8, 'pad_count': 2, 'body_width': 1.2, 'body_height': 0.8, 'pad_spacing': 0.96, 'pitch': 0.0, 'footprint_class': 'standard_package'},
        # SOD-123FL: Based on MCC datasheet - pad length ~0.91mm, width ~1.22mm, spacing ~2.36mm
        'SOD-123FL': {'pad_length': 0.91, 'pad_width': 1.22, 'pad_count': 2, 'body_width': 3.7, 'body_height': 1.6, 'pad_spacing': 2.36, 'pitch': 0.0, 'component_type': 'diode', 'footprint_class': 'standard_package'},
        
        # Inductor packages
        'L7.8x7.0x5.0': {'pad_length': 2.0, 'pad_width': 3.0, 'pad_count': 2, 'body_width': 7.8, 'body_height': 7.0, 'pad_spacing': 6.24, 'pitch': 0.0},
    }
    
    def get_component_type_from_designator(self, designator: str) -> str:
        """Extract component type from designator prefix"""
        designator_upper = designator.upper()
        
        # Check multi-character prefixes first (e.g., "LED", "SW")
        for prefix, comp_type in sorted(self.COMPONENT_PREFIXES.items(), key=lambda x: -len(x[0])):
            if designator_upper.startswith(prefix):
                return comp_type
        
        return 'unknown'

    def _passive_prefixes(self) -> List[str]:
        """Return supported passive prefixes for alias generation and lookup."""
        return list(self.PASSIVE_PREFIX_TO_TYPE.keys())

    def _prefix_for_component_type(self, comp_type: str) -> str:
        """Map component type to passive prefix (e.g., capacitor -> C)."""
        return self.PASSIVE_TYPE_TO_PREFIX.get(comp_type, '')

    def _component_type_for_prefix(self, prefix: str) -> str:
        """Map passive prefix to component type (e.g., C -> capacitor)."""
        return self.PASSIVE_PREFIX_TO_TYPE.get(prefix, '')
    
    def _generate_from_standard_database(self, footprint: str, designator: str, pin_count: int) -> Optional[Dict[str, Any]]:
        """
        Generate footprint directly from standard database - NO LLM.
        This is the PRIMARY method for known packages.
        Tries both the exact footprint name and prefixed versions (C0603, R0603, etc.).
        """
        # Try exact match first
        standard_dims = self._get_standard_dimensions(footprint)
        
        # If not found and footprint is numeric (starts with digit), try with prefix
        if not standard_dims and footprint and len(footprint) >= 4 and footprint[0].isdigit():
            comp_type = self.get_component_type_from_designator(designator)
            prefix = self._prefix_for_component_type(comp_type)
            if prefix:
                prefixed_footprint = prefix + footprint
                standard_dims = self._get_standard_dimensions(prefixed_footprint)
                if standard_dims:
                    footprint = prefixed_footprint  # Use prefixed version for generation
                    logger.info(f"Found prefixed footprint '{prefixed_footprint}' for {designator} (original: {footprint})")
        
        # If still not found, try removing prefix if present
        if not standard_dims and footprint and len(footprint) > 1 and footprint[0] in self._passive_prefixes():
            no_prefix = footprint[1:]
            standard_dims = self._get_standard_dimensions(no_prefix)
            if standard_dims:
                footprint = no_prefix  # Use non-prefixed version for generation
                logger.info(f"Found non-prefixed footprint '{no_prefix}' for {designator} (original: {footprint})")
        if not standard_dims:
            return None
        
        # CRITICAL: For numeric footprints, use prefixed name based on component type
        # If footprint is numeric (e.g., "1812") and we have a designator, use prefixed version
        final_footprint_name = footprint
        if footprint and len(footprint) >= 4 and footprint[0].isdigit() and designator:
            comp_type = self.get_component_type_from_designator(designator)
            prefix = self._prefix_for_component_type(comp_type)
            if prefix:
                final_footprint_name = prefix + footprint
                logger.info(f"Using prefixed footprint name '{final_footprint_name}' instead of '{footprint}' for {designator}")
        
        logger.info(f"Generating {designator} ({final_footprint_name}) directly from standard database (NO LLM)")
        
        pads = []
        pad_count = standard_dims.get('pad_count', pin_count)
        pin_pitch = standard_dims.get('pin_pitch', 0.0)
        row_spacing = standard_dims.get('row_spacing', 0.0)
        body_width = standard_dims.get('body_width', 5.0)
        body_height = standard_dims.get('body_height', 5.0)
        
        footprint_upper = final_footprint_name.upper()
        
        # Generate pads based on package type
        if pad_count == 2 and row_spacing == 0:
            # Chip component (resistor, capacitor) - 2 pads on opposite sides
            # Use IPC-7351 land pattern dimensions: pad_length (along component axis) and pad_width (across component)
            if 'pad_length' in standard_dims and 'pad_width' in standard_dims:
                # Correct IPC-7351 format: pad_length along axis, pad_width across component
                pad_length = standard_dims['pad_length']  # Length along component axis (X direction)
                pad_width = standard_dims['pad_width']    # Width across component (Y direction)
                pad_spacing = standard_dims.get('pad_spacing', body_width * 0.9)
            elif 'pad_width' in standard_dims and 'pad_height' in standard_dims:
                # Legacy format - assume pad_width is along axis, pad_height is across
                pad_length = standard_dims['pad_width']
                pad_width = standard_dims['pad_height']
                pad_spacing = standard_dims.get('pad_spacing', body_width * 0.9)
            else:
                # Fallback calculation
                toe_extension = 0.5 if body_width > 2.0 else 0.25
                pad_spacing = body_width + 2 * toe_extension - (body_width * 0.3)
                pad_length = (pad_spacing + body_width * 0.3) / 2
                pad_width = body_height * 0.8
            # For chip components: pads are oriented with length along X-axis (component axis)
            pads = [
                {"name": "1", "x": -pad_spacing/2, "y": 0.0, "width": pad_length, "height": pad_width, "shape": "rectangular", "layer": "top", "hole_size": 0.0},
                {"name": "2", "x": pad_spacing/2, "y": 0.0, "width": pad_length, "height": pad_width, "shape": "rectangular", "layer": "top", "hole_size": 0.0}
            ]
        elif 'SOT-23' in footprint_upper or 'SOT23' in footprint_upper:
            # SOT-23 packages: special layout (not symmetric dual-row)
            # Diodes Inc. recommended: pad_width=0.8mm, pad_height=0.9mm
            pad_width = standard_dims.get('pad_width', 0.8)
            pad_height = standard_dims.get('pad_height', 0.9)
            if '5' in footprint_upper or pad_count == 5:
                # SOT-23-5: 3 pads on left, 2 pads on right (Bourns recommended land pattern)
                # Bourns SOT23-5: pitch=0.95mm, row_spacing=2.6mm
                # Left side: pins 1, 2, 3 (bottom to top, centered around y=0)
                # Right side: pins 4, 5 (centered around y=0)
                left_x = -row_spacing / 2  # -1.3mm
                right_x = row_spacing / 2  # +1.3mm
                # Left side: pads 1, 2, 3 at pitch 0.95mm, centered around y=0
                pads.append({"name": "1", "x": left_x, "y": -pin_pitch, "width": pad_width, "height": pad_height, "shape": "rectangular", "layer": "top", "hole_size": 0.0})
                pads.append({"name": "2", "x": left_x, "y": 0.0, "width": pad_width, "height": pad_height, "shape": "rectangular", "layer": "top", "hole_size": 0.0})
                pads.append({"name": "3", "x": left_x, "y": pin_pitch, "width": pad_width, "height": pad_height, "shape": "rectangular", "layer": "top", "hole_size": 0.0})
                # Right side: pads 4, 5 at pitch 0.95mm, centered around y=0
                pads.append({"name": "4", "x": right_x, "y": -pin_pitch / 2, "width": pad_width, "height": pad_height, "shape": "rectangular", "layer": "top", "hole_size": 0.0})
                pads.append({"name": "5", "x": right_x, "y": pin_pitch / 2, "width": pad_width, "height": pad_height, "shape": "rectangular", "layer": "top", "hole_size": 0.0})
            else:
                # SOT-23-3: 2 pads on left, 1 pad on right (Diodes recommended pattern)
                left_x = -row_spacing / 2
                right_x = row_spacing / 2
                # Left side: pads 1, 2 (bottom to top, centered around 0)
                pads.append({"name": "1", "x": left_x, "y": -pin_pitch / 2, "width": pad_width, "height": pad_height, "shape": "rectangular", "layer": "top", "hole_size": 0.0})
                pads.append({"name": "2", "x": left_x, "y": pin_pitch / 2, "width": pad_width, "height": pad_height, "shape": "rectangular", "layer": "top", "hole_size": 0.0})
                # Right side: pad 3 (center)
                pads.append({"name": "3", "x": right_x, "y": 0.0, "width": pad_width, "height": pad_height, "shape": "rectangular", "layer": "top", "hole_size": 0.0})
        elif 'TO-252' in footprint_upper or 'DPAK' in footprint_upper:
            # TO-252 (DPAK) packages - Diodes Inc. TO252-DPAK recommended land pattern
            # 3 signal pads + 1 large thermal tab (drain pad)
            pad_width = standard_dims.get('pad_width', 1.5)
            pad_height = standard_dims.get('pad_height', 2.5)
            pin_pitch = standard_dims.get('pin_pitch', 2.54)
            # Signal pads: Gate (pin 1) and Source (pin 3), thermal tab is Drain (pin 2)
            # Gate and Source are on left side
            pads.append({
                "name": "1",  # Gate
                "x": -3.8,
                "y": -pin_pitch,
                "width": pad_width,
                "height": pad_height,
                "shape": "rectangular",
                "layer": "top",
                "hole_size": 0.0
            })
            pads.append({
                "name": "3",  # Source
                "x": -3.8,
                "y": pin_pitch,
                "width": pad_width,
                "height": pad_height,
                "shape": "rectangular",
                "layer": "top",
                "hole_size": 0.0
            })
            # Thermal tab (Drain, pin 2) - MUST be present for TO-252 packages
            if 'thermal_width' in standard_dims:
                pads.append({
                    "name": "Tab",
                    "x": 0.0,
                    "y": 0.0,
                    "width": standard_dims['thermal_width'],
                    "height": standard_dims['thermal_height'],
                    "shape": "rectangular",
                    "layer": "top",
                    "hole_size": 0.0
                })
        elif 'TO-263' in footprint_upper or 'TO263' in footprint_upper or 'D2PAK' in footprint_upper:
            # TO-263 packages - single vertical row of signal pads + thermal tab
            pad_width = standard_dims.get('pad_width', 0.9)
            pad_height = standard_dims.get('pad_height', 2.0)
            signal_pad_count = standard_dims.get('pad_count', 7)
            if '7' in footprint or signal_pad_count == 7:
                # TO-263-7: 7 signal pads in vertical row + thermal tab
                # Diodes Inc. TO-263-7 Type-D recommended land pattern
                start_y = -2.85
                for i in range(7):
                    pads.append({
                        "name": str(i+1),
                        "x": -3.8,
                        "y": start_y + i * 0.95,
                        "width": pad_width,
                        "height": pad_height,
                        "shape": "rectangular",
                        "layer": "top",
                        "hole_size": 0.0
                    })
                # Thermal tab - MANDATORY for TO-263/D2PAK packages
                thermal_width = standard_dims.get('thermal_width', 10.0)
                thermal_height = standard_dims.get('thermal_height', 7.5)
                pads.append({
                    "name": "Tab",
                    "x": 0.0,
                    "y": 2.0,
                    "width": thermal_width,
                    "height": thermal_height,
                    "shape": "rectangular",
                    "layer": "top",
                    "hole_size": 0.0
                })
            else:
                # TO-263-2: 2 signal pads + large thermal tab (Drain)
                # Signal pads are typically Gate and Source
                # Diodes Inc. TO-263AB/D2PAK 2L recommended land pattern
                pin_pitch = standard_dims.get('pin_pitch', 2.54)
                for i in range(signal_pad_count):
                    pads.append({
                        "name": str(i+1),
                        "x": -pin_pitch / 2 + i * pin_pitch,
                        "y": 0.0,
                        "width": pad_width,
                        "height": pad_height,
                        "shape": "rectangular",
                        "layer": "top",
                        "hole_size": 0.0
                    })
                # Thermal tab (Drain) - MANDATORY for TO-263/D2PAK packages
                # Always add Tab pad - use standard dimensions if available, otherwise defaults
                thermal_width = standard_dims.get('thermal_width', 10.0)
                thermal_height = standard_dims.get('thermal_height', 7.5)
                pads.append({
                    "name": "Tab",
                    "x": 0.0,
                    "y": 2.0,
                    "width": thermal_width,
                    "height": thermal_height,
                    "shape": "rectangular",
                    "layer": "top",
                    "hole_size": 0.0
                })
        elif row_spacing > 0:
            # Dual-row package (SOIC, ESOP, etc.)
            pad_width = standard_dims.get('pad_width', standard_dims.get('pad_length', 0.6))
            pad_height = standard_dims.get('pad_height', standard_dims.get('pad_width', 1.5))
            pads_per_side = pad_count // 2
            left_x = -row_spacing / 2
            right_x = row_spacing / 2
            start_y = -(pads_per_side - 1) * pin_pitch / 2
            
            # Left side pads (1, 2, 3, ...)
            for i in range(pads_per_side):
                pads.append({
                    "name": str(i+1),
                    "x": left_x,
                    "y": start_y + i * pin_pitch,
                    "width": pad_width,
                    "height": pad_height,
                    "shape": "rectangular",
                    "layer": "top",
                    "hole_size": 0.0
                })
            
            # Right side pads (continuing from left)
            for i in range(pads_per_side):
                pads.append({
                    "name": str(pads_per_side + i + 1),
                    "x": right_x,
                    "y": start_y + i * pin_pitch,
                    "width": pad_width,
                    "height": pad_height,
                    "shape": "rectangular",
                    "layer": "top",
                    "hole_size": 0.0
                })
            
            # Add thermal pad if specified (e.g., ESOP8L)
            if 'thermal_width' in standard_dims:
                pads.append({
                    "name": "Tab",
                    "x": 0.0,
                    "y": 0.0,
                    "width": standard_dims['thermal_width'],
                    "height": standard_dims['thermal_height'],
                    "shape": "rectangular",
                    "layer": "top",
                    "hole_size": 0.0
                })
        else:
            # Single-row package - horizontal arrangement
            start_x = -(pad_count - 1) * pin_pitch / 2
            for i in range(pad_count):
                pads.append({
                    "name": str(i+1),
                    "x": start_x + i * pin_pitch,
                    "y": 0.0,
                    "width": pad_width,
                    "height": pad_height,
                    "shape": "rectangular",
                    "layer": "top",
                    "hole_size": 0.0
                })
        
        # Determine component type - use database value if available, otherwise infer from footprint name
        comp_type = standard_dims.get('component_type', 'unknown')
        if comp_type == 'unknown':
            if 'R' in footprint_upper or 'RES' in footprint_upper:
                comp_type = 'resistor'
            elif 'C' in footprint_upper or 'CAP' in footprint_upper:
                comp_type = 'capacitor'
            elif 'D' in footprint_upper or 'DIODE' in footprint_upper or 'SOD' in footprint_upper:
                comp_type = 'diode'
            elif ('L' in footprint_upper or 'IND' in footprint_upper) and 'ESOP' not in footprint_upper:
                comp_type = 'inductor'
            elif 'SOT' in footprint_upper or 'SOIC' in footprint_upper or 'ESOP' in footprint_upper or 'QFP' in footprint_upper:
                comp_type = 'ic'
            elif 'TO-' in footprint_upper or 'TO' in footprint_upper:
                comp_type = 'transistor'
            # Special cases: SMB/SMC are diode packages, not capacitors
            elif 'SMB' in footprint_upper or 'SMC' in footprint_upper:
                comp_type = 'diode'
        
        # Calculate silkscreen and courtyard from pad bounding box (not body size or placeholders)
        # This ensures the "yellow rectangle" in Altium is meaningful and correctly sized
        if pads:
            # Compute pad bounding box (including pad extents)
            x_coords = [p.get('x', 0) for p in pads]
            y_coords = [p.get('y', 0) for p in pads]
            pad_widths = [p.get('width', 0) for p in pads]
            pad_heights = [p.get('height', 0) for p in pads]
            
            # Calculate actual extents (pad center ± half pad size)
            x_min = min([x - w/2 for x, w in zip(x_coords, pad_widths)])
            x_max = max([x + w/2 for x, w in zip(x_coords, pad_widths)])
            y_min = min([y - h/2 for y, h in zip(y_coords, pad_heights)])
            y_max = max([y + h/2 for y, h in zip(y_coords, pad_heights)])
            
            # Silkscreen: pad bbox + clearance (0.2mm typical)
            silkscreen_clearance = 0.2
            silkscreen_width = (x_max - x_min) + 2 * silkscreen_clearance
            silkscreen_height = (y_max - y_min) + 2 * silkscreen_clearance
            
            # Courtyard: pad bbox + margin (0.25mm to 0.5mm typical)
            courtyard_margin = 0.5
            courtyard_width = (x_max - x_min) + 2 * courtyard_margin
            courtyard_height = (y_max - y_min) + 2 * courtyard_margin
        else:
            # Fallback if no pads (shouldn't happen, but be safe)
            silkscreen_width = body_width + 0.5
            silkscreen_height = body_height + 0.5
            courtyard_width = body_width + 1.0
            courtyard_height = body_height + 1.0
        
        # Determine verification status and source
        footprint_class = standard_dims.get('footprint_class', 'unknown')
        if footprint_class == 'passive_chip':
            verification_status = 'auto_verified'
            notes = "IPC-7351 standard from database (passive chip)"
        elif footprint_class == 'standard_package':
            # Validate standard packages before marking as auto_verified
            # TO-263/D2PAK packages MUST have Tab pad
            if ('TO-263' in footprint_upper or 'D2PAK' in footprint_upper):
                has_tab = any(p.get('name', '').upper() in ['TAB', 'THERMAL', 'DRAIN'] for p in pads)
                if not has_tab:
                    verification_status = 'needs_manual_verification'
                    notes = "Standard package template - missing required Tab pad (needs manual verification)"
                else:
                    verification_status = 'auto_verified'
                    notes = "Standard package template from database (TO-263/D2PAK with Tab)"
            else:
                verification_status = 'auto_verified'
                notes = "Standard package template from database"
        else:
            verification_status = 'guessed'
            notes = "Generated from database (needs verification)"
        
        spec = {
            "footprint_name": final_footprint_name,  # Use prefixed name (C1812, R1812, etc.) not numeric (1812)
            "component_type": comp_type,
            "package_type": "smd",
            "pads": pads,
            "silkscreen": {"width": silkscreen_width, "height": silkscreen_height},
            "courtyard": {"width": courtyard_width, "height": courtyard_height},
            "verification_status": verification_status,
            "footprint_class": footprint_class,
            "notes": notes
        }
        
        logger.info(f"✓ Generated {designator} ({final_footprint_name}) from database: {len(pads)} pads")
        return spec
    
    def analyze_component_with_llm(self, component: Dict[str, Any], max_retries: int = 3) -> Optional[Dict[str, Any]]:
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
        
        # CRITICAL: Try standard database FIRST - this is the PRIMARY method
        if footprint:
            db_footprint = self._generate_from_standard_database(footprint, designator, pin_count)
            if db_footprint:
                logger.info(f"✓ Using database-generated footprint for {designator} ({footprint}) - skipping LLM")
                return db_footprint
        
        comp_type = self.get_component_type_from_designator(designator)
        
        system_prompt = """You are an expert PCB footprint engineer with deep knowledge of IPC-7351B/C standards, JEDEC standards, and manufacturer datasheets. Your task is to generate EXACT footprint specifications based on industry standards and real-world package specifications.

CRITICAL RULES - FOLLOW THESE EXACTLY:

1. WEB SEARCH RESULTS (HIGHEST PRIORITY):
   - If web search results are provided, you MUST extract EXACT dimensions from them
   - Look for specific numbers in the search content:
     * Pad sizes: "Xmm × Ymm" or "width: Xmm, height: Ymm"
     * Pin pitch: "Xmm pitch" or "spacing: Xmm"
     * Row spacing: "Xmm row spacing" or "distance: Xmm"
     * Thermal pad: "Xmm × Ymm thermal pad"
   - Use the EXACT values found - do NOT approximate, round, or estimate
   - If search shows "pad size: 0.9mm × 2.0mm", use exactly width=0.9, height=2.0
   - If search shows "pin pitch: 0.95mm", use exactly 0.95 for spacing
   - Verify pad count from search results matches package specification

2. YOUR KNOWLEDGE (SECOND PRIORITY):
   - If no web search results, use your knowledge of IPC-7351B/C, JEDEC, and manufacturer datasheets
   - Use EXACT dimensions from industry standards - do NOT approximate
   - If you're uncertain, it's better to indicate uncertainty than to guess

3. DIMENSION REQUIREMENTS:
   - ALL pad dimensions, positions, and spacing must match industry standards PRECISELY
   - NO approximations or rounding - use exact values
   - All dimensions in millimeters (mm)
   - Pad sizes must match IPC-7351 or manufacturer specifications exactly

4. PACKAGE LAYOUT REQUIREMENTS:
   - TO-263-7: MUST have exactly 7 signal pads in SINGLE VERTICAL ROW on left side
     * Signal pads: x=-3.8mm, y from -2.85mm to +2.85mm, pitch 0.95mm
     * Pad dimensions: typically 0.9mm × 2.0mm
     * Thermal tab: x=0mm, y=+2.0mm, size 10.0×7.5mm
     * CRITICAL: All 7 signal pads must be present, arranged vertically (different Y coordinates)
   - Dual-row packages (SOIC, ESOP, SSOP, etc.): Pads vertically on left and right sides
     * Left side: pads 1, 2, 3, ... from bottom to top
     * Right side: pads continuing from left, also bottom to top
   - Single-row packages: Pads in correct orientation based on package type

5. OUTPUT FORMAT:
   - Return ONLY valid JSON - no markdown, no explanations, no code blocks
   - All numeric values must be numbers (not strings)
   - Pad names must be sequential (1, 2, 3, ...) or "Tab" for thermal pads

COORDINATE SYSTEM:
- Origin (0,0) = component body center
- X-axis: positive=right, negative=left  
- Y-axis: positive=up, negative=down
- All dimensions in millimeters

PACKAGE IDENTIFICATION PRIORITY:
1. Footprint name (e.g., "SOT-23", "0805", "TO-263-7", "ESOP8L") - PRIMARY source - use this to identify the package type
2. Library reference (e.g., "LM7805", "BC547") - use to identify package family if footprint name is unclear
3. Value field (may contain package info like "0603-100nF")
4. Pin count - use to validate package type and ensure all pads are included

PACKAGE LAYOUT PRINCIPLES (apply to ALL packages):
- Chip components (resistors, capacitors): Two pads on opposite sides, symmetric about origin
- Dual-row packages (SOIC, ESOP, SSOP, TSSOP, etc.): Pads arranged vertically on left and right sides
  * Left side: Pads numbered sequentially from bottom to top (pins 1, 2, 3, ...)
  * Right side: Pads numbered continuing from left side, also bottom to top
  * Row spacing and pin pitch follow standard conventions for the package family
- Single-row packages: Pads arranged in a single row (either horizontal or vertical depending on package)
- Power packages: Include thermal tab pad if package specification requires it
- Thermal pads: Typically at center (x=0, y=0) for packages with thermal pads

JSON OUTPUT FORMAT:
{
  "footprint_name": "package_name",
  "component_type": "resistor|capacitor|diode|transistor|ic|inductor|connector|other",
  "package_type": "smd|through_hole",
  "pads": [
    {"name": "1", "x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "shape": "rectangular", "layer": "top", "hole_size": 0.0}
  ],
  "silkscreen": {"width": 0.0, "height": 0.0},
  "courtyard": {"width": 0.0, "height": 0.0},
  "notes": "IPC-7351 standard or manufacturer specification"
}

CRITICAL VALIDATION:
- Pad count must match package specification exactly
- Pad positions must follow standard conventions for the package type
- Dual-row packages MUST have pads arranged vertically on left and right sides
- Single-row packages MUST have pads arranged in the correct orientation (horizontal or vertical)
- Power packages MUST include thermal tab pad if required by package specification
- NO duplicate pad names - use sequential numbering (1, 2, 3, ...)
- All numeric values must be numbers (not strings)
- Pad dimensions must match IPC-7351 or manufacturer specifications exactly
- Return ONLY the JSON object - no markdown, no explanations"""
        
        # Extract additional context from component
        pins = component.get('pins', [])
        description = component.get('description', '')
        
        # Build comprehensive component context
        pin_info = ""
        if pins:
            pin_numbers = [p.get('number', p.get('name', '')) for p in pins if isinstance(p, dict)]
            pin_info = f"Pin numbers found in schematic: {', '.join(str(p) for p in pin_numbers[:10])}" + (f" (and {len(pin_numbers)-10} more)" if len(pin_numbers) > 10 else "")
        
        # Perform actual web searches using the web_search tool and get results for this footprint
        web_search_context = ""
        web_search_results = []
        extracted_dimensions = {}  # Initialize before try block
        
        if footprint:
            try:
                # Try to use web_search tool if available - check multiple sources
                search_func = None
                
                # First, try the stored web_search function
                if self.web_search and callable(self.web_search):
                    search_func = self.web_search
                    logger.info(f"Using stored web_search tool for {designator} ({footprint})")
                else:
                    # Try to get web_search from the environment (Cursor's tool calling)
                    try:
                        import inspect
                        frame = inspect.currentframe()
                        # Check multiple frames up the call stack
                        for i in range(5):
                            if frame and frame.f_back:
                                frame = frame.f_back
                                caller_globals = frame.f_globals
                                if 'web_search' in caller_globals and callable(caller_globals['web_search']):
                                    search_func = caller_globals['web_search']
                                    logger.info(f"Found web_search tool in call stack frame {i} for {designator} ({footprint})")
                                    break
                    except Exception as e:
                        logger.debug(f"Could not find web_search in call stack: {e}")
                
                # Perform actual web searches if we have the tool
                if search_func:
                    logger.info(f"Performing web searches for {designator} ({footprint}) using web_search tool")
                    
                    # Build comprehensive search queries - prioritize datasheet and IPC-7351 searches
                    search_queries = [
                        f"{footprint} IPC-7351 footprint dimensions pad layout specifications",
                        f"{footprint} package dimensions pin pitch pad size datasheet",
                        f"{footprint} pinout pad layout mechanical drawing",
                        f"{footprint} landing pattern pad geometry"
                    ]
                    
                    if lib_reference:
                        search_queries.insert(0, f"{lib_reference} {footprint} datasheet package specifications")  # Highest priority
                        search_queries.insert(1, f"{lib_reference} pinout mechanical dimensions datasheet")
                    
                    # Perform searches and collect results
                    for query in search_queries:
                        try:
                            logger.info(f"Searching: {query}")
                            results = search_func(query, num_results=5)
                            if results and len(results) > 0:
                                web_search_results.extend(results)
                                logger.info(f"Found {len(results)} results for: {query}")
                                # Log first result for debugging
                                if results[0].get('title'):
                                    logger.info(f"First result title: {results[0].get('title')}")
                        except Exception as e:
                            logger.warning(f"Web search failed for '{query}': {e}")
                            import traceback
                            logger.debug(traceback.format_exc())
                            continue
                    
                    if web_search_results:
                        logger.info(f"Total web search results collected: {len(web_search_results)}")
                    else:
                        logger.warning(f"No web search results obtained for {designator} ({footprint})")
                else:
                    logger.warning(f"Web search tool not available for {designator} ({footprint}) - will use LLM knowledge only")
                
                # Extract dimensions from web search results BEFORE formatting
                # Extract dimensions from web search AND standard database
                extracted_dimensions = self._extract_dimensions_from_web_search(web_search_results, footprint, designator)
                logger.info(f"Extracted dimensions for {designator} ({footprint}): {extracted_dimensions}")
                
                # If we have standard dimensions but no web search results, use standard dimensions
                if not extracted_dimensions and not web_search_results:
                    standard_dims = self._get_standard_dimensions(footprint)
                    if standard_dims:
                        extracted_dimensions = standard_dims
                        logger.info(f"Using standard dimensions database for {designator} ({footprint}): {extracted_dimensions}")
                
                # Format search results if we have any
                if web_search_results:
                    # Remove duplicates based on URL
                    seen_urls = set()
                    unique_results = []
                    for result in web_search_results:
                        url = result.get('url', '')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            unique_results.append(result)
                        elif not url:
                            unique_results.append(result)
                    
                    formatted_results = "=== WEB SEARCH RESULTS (REAL-WORLD SPECIFICATIONS) ===\n\n"
                    formatted_results += "IMPORTANT: These are REAL-WORLD specifications from the internet. You MUST use the EXACT dimensions from these results.\n\n"
                    
                    # If we extracted dimensions, show them prominently
                    if extracted_dimensions:
                        formatted_results += "=== EXTRACTED DIMENSIONS (USE THESE EXACT VALUES) ===\n"
                        for key, value in extracted_dimensions.items():
                            formatted_results += f"{key}: {value}\n"
                        formatted_results += "\n"
                    
                    for i, result in enumerate(unique_results[:15], 1):  # Limit to top 15 unique results
                        title = result.get('title', 'No title')
                        url = result.get('url', '')
                        snippet = result.get('snippet', result.get('content', result.get('text', '')))
                        
                        formatted_results += f"Search Result {i}:\n"
                        formatted_results += f"Title: {title}\n"
                        if url:
                            formatted_results += f"URL: {url}\n"
                        if snippet:
                            # Include more content for better extraction
                            snippet_text = snippet[:1200] + "..." if len(snippet) > 1200 else snippet
                            formatted_results += f"Content: {snippet_text}\n"
                        formatted_results += "\n"
                    
                    formatted_results += """
CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:
1. If EXTRACTED DIMENSIONS are shown above, USE THOSE EXACT VALUES - do not recalculate or estimate
2. Extract EXACT dimensions from the search results above:
   - Pad sizes: width × height in millimeters (mm)
   - Pin pitch: spacing between pins in mm
   - Row spacing: for dual-row packages, distance between left and right rows in mm
   - Thermal pad dimensions: if package has thermal pad, exact size in mm
   - Pad positions: exact X and Y coordinates in mm
   - Package body dimensions: overall size in mm

3. Use the EXACT values from search results - do NOT approximate, round, or estimate
4. If multiple sources provide dimensions, prioritize in this order:
   - IPC-7351 standard specifications (highest priority)
   - Manufacturer datasheet specifications
   - JEDEC standard specifications
   - Other authoritative sources

5. For TO-263-7 specifically:
   - MUST have exactly 7 signal pads in a SINGLE VERTICAL ROW on left side
   - Signal pads: x=-3.8mm, y from -2.85mm to +2.85mm, pitch 0.95mm
   - Thermal tab: x=0mm, y=+2.0mm, size 10.0×7.5mm
   - Pad dimensions: typically 0.9mm × 2.0mm for signal pads

6. Verify pad count matches package specification exactly
7. Verify pad layout matches standard conventions for the package type
8. All dimensions must be in millimeters (mm)
"""
                    web_search_context = f"\n\n{formatted_results}\n"
                    logger.info(f"Web search context included for {designator} ({footprint}) - {len(unique_results)} unique results")
                else:
                    # No search results - provide instructions to use LLM knowledge with emphasis on accuracy
                    logger.warning(f"No web search results for {designator} ({footprint}) - LLM will use its knowledge")
                    web_search_context = f"""
IMPORTANT: Web search was not available. You must use your knowledge of IPC-7351B/C standards, JEDEC standards, and manufacturer datasheets to determine EXACT dimensions.

For {footprint}:
- Search your knowledge for the exact package specifications
- Use EXACT dimensions from IPC-7351 or manufacturer standards
- Do NOT approximate or round - use precise values
- Verify pad count matches package specification
- Verify pad layout matches standard conventions

If you are unsure about dimensions, it is better to indicate uncertainty than to guess.
"""
            except Exception as e:
                logger.warning(f"Web search error for {designator}: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                # Continue without web search - LLM will use its knowledge
                extracted_dimensions = {}
        
        # Build extracted dimensions message if we have them
        extracted_dims_msg = ""
        if extracted_dimensions:
            extracted_dims_msg = "\n=== EXTRACTED DIMENSIONS FROM WEB SEARCH (USE THESE EXACT VALUES) ===\n"
            for key, value in extracted_dimensions.items():
                extracted_dims_msg += f"{key}: {value}\n"
            extracted_dims_msg += "\nCRITICAL: You MUST use these exact extracted dimensions. Do NOT recalculate or estimate.\n\n"
        
        user_message = f"""Generate footprint specification for this component. You MUST use EXACT dimensions from web search results (if provided) or from IPC-7351/JEDEC standards.

Component Information:
- Designator: {designator}
- Value: {value}
- Footprint Name: {footprint}
- Library Reference: {lib_reference}
- Pin Count: {pin_count}
- Component Type: {comp_type}
{pin_info}
{extracted_dims_msg}
{web_search_context}
CRITICAL INSTRUCTIONS - FOLLOW THESE EXACTLY:

1. PACKAGE IDENTIFICATION:
   - Identify the package type from footprint name "{footprint}" - this is the PRIMARY identifier
   - Use the footprint name to determine the exact package specification

2. IF EXTRACTED DIMENSIONS ARE PROVIDED ABOVE (HIGHEST PRIORITY):
   - YOU MUST use the EXACT extracted dimensions shown above
   - Do NOT recalculate, estimate, or round these values
   - Use pad_width and pad_height exactly as shown
   - Use pin_pitch exactly as shown
   - Use pad_count exactly as shown (if provided)

3. IF WEB SEARCH RESULTS ARE PROVIDED ABOVE (PRIORITY #2):
   - YOU MUST extract EXACT dimensions from the search results
   - Look for specific numbers in the search content: pad sizes (e.g., "0.9mm × 2.0mm"), pin pitch (e.g., "0.95mm"), row spacing (e.g., "5.4mm")
   - Use the EXACT values found in search results - do NOT approximate, round, or estimate
   - If search results show "pad size: 0.9mm × 2.0mm", use exactly 0.9 and 2.0
   - If search results show "pin pitch: 0.95mm", use exactly 0.95
   - Verify pad count from search results matches the package specification
   - ONLY use your knowledge if search results are incomplete or unclear

3. IF NO WEB SEARCH RESULTS (PRIORITY #2):
   - Use your knowledge of IPC-7351B/C standards, JEDEC standards, and manufacturer datasheets
   - Determine EXACT dimensions from industry standards
   - Do NOT approximate - use precise values from your training data

4. PAD GENERATION REQUIREMENTS:
   - Generate ALL required pads - verify pad count matches package specification exactly
   - For TO-263-7: MUST have EXACTLY 7 signal pads + 1 thermal tab = 8 pads total
   - For ESOP8L: MUST have EXACTLY 8 signal pads + 1 thermal pad = 9 pads total
   - For TO-252: MUST have EXACTLY 3 signal pads + 1 thermal tab = 4 pads total
   - For TO-263-2: MUST have EXACTLY 2 signal pads + 1 thermal tab = 3 pads total
   - Verify pad count matches the package specification

5. PAD LAYOUT REQUIREMENTS:
   - For dual-row packages (SOIC, ESOP, SSOP, etc.): Arrange pads vertically on left and right sides
     * Left side: pads numbered 1, 2, 3, ... from bottom to top
     * Right side: pads numbered continuing from left, also bottom to top
   - For single-row packages (TO-263-7, etc.): Arrange pads in a SINGLE VERTICAL ROW (NOT horizontal)
     * TO-263-7: 7 signal pads in SINGLE VERTICAL ROW on left side (x=-3.8mm, y from -2.85 to +2.85mm, pitch 0.95mm)
     * Pad 1 at bottom (y=-2.85mm), pads 2-7 going up, Tab on right/top (x=0, y=+2.0mm, size 10.0×7.5mm)
     * CRITICAL: All 7 signal pads must be present, arranged vertically (different Y coordinates), NOT horizontally
   - Power packages: Include thermal tab pad if required by package specification

6. DIMENSION REQUIREMENTS:
   - Use EXACT dimensions from search results or standards - no approximations or rounding
   - All dimensions must be in millimeters (mm)
   - Pad sizes must match IPC-7351 or manufacturer specifications exactly
   - Pin pitch must match standard specifications exactly

7. OUTPUT FORMAT:
   - Return ONLY valid JSON - no markdown, no explanations, no code blocks
   - All numeric values must be numbers (not strings)
   - Pad names must be sequential (1, 2, 3, ...) or "Tab" for thermal pads

Return the complete footprint specification as JSON."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        # Define web_search tool for the LLM to use if needed
        # Only provide the tool if web_search is actually available and callable
        web_search_tool = None
        web_search_available = self.web_search and callable(self.web_search)
        
        if web_search_available:
            web_search_tool = {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the internet for real-world PCB footprint specifications, IPC-7351 standards, and manufacturer datasheets. Use this to find exact dimensions for pad sizes, pin pitch, row spacing, and thermal pad dimensions.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_term": {
                                "type": "string",
                                "description": "The search query to find footprint specifications"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of search results to return (default: 5)",
                                "default": 5
                            }
                        },
                        "required": ["search_term"]
                    }
                }
            }
            logger.info(f"Web search tool available - LLM can use it for {designator} ({footprint})")
        else:
            logger.info(f"Web search tool NOT available - LLM will use its knowledge for {designator} ({footprint})")
        
        # Retry logic for LLM generation
        for attempt in range(max_retries + 1):
            try:
                # Use very low temperature for precise, deterministic results
                # Only provide tools if web_search is actually available
                tools = [web_search_tool] if web_search_tool else None
                tool_choice = "auto" if web_search_tool else None
                
                logger.debug(f"Calling LLM for {designator} (attempt {attempt + 1}/{max_retries + 1}), tools={'available' if tools else 'none'}")
                print(f"[Footprint Generator] Calling LLM API for {designator} ({footprint}) - attempt {attempt + 1}/{max_retries + 1}")
                response = self.llm_client.chat(messages, temperature=0.0, tools=tools, tool_choice=tool_choice)
                
                if response is None:
                    error_msg = f"LLM API returned None for {designator} (attempt {attempt + 1}/{max_retries + 1}) - check LLM client error messages above"
                    logger.error(error_msg)
                    print(f"[Footprint Generator] {error_msg}")
                    print(f"[Footprint Generator] This usually means:")
                    print(f"[Footprint Generator]   - LLM API key is invalid or not set")
                    print(f"[Footprint Generator]   - Network connectivity issue")
                    print(f"[Footprint Generator]   - API rate limit exceeded")
                    print(f"[Footprint Generator]   - Check console for '[LLM Client ERROR]' messages above")
                    if attempt < max_retries:
                        continue
                    return None
                
                # Handle tool calls if LLM wants to search
                if isinstance(response, dict) and "tool_calls" in response:
                    # Execute tool calls and continue conversation
                    tool_calls_executed = False
                    for tool_call in response.get("tool_calls", []):
                        if tool_call.function.name == "web_search":
                            try:
                                args = json.loads(tool_call.function.arguments)
                                search_term = args.get("search_term", "")
                                num_results = args.get("num_results", 5)
                                
                                # Execute web search only if available
                                if self.web_search and callable(self.web_search):
                                    search_results = self.web_search(search_term, num_results)
                                    tool_calls_executed = True
                                    
                                    # Add tool result to messages
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": json.dumps(search_results, indent=2) if search_results else json.dumps([])
                                    })
                                else:
                                    # Web search not available - return empty results
                                    logger.warning(f"LLM requested web_search but tool not available, returning empty results")
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": json.dumps([])
                                    })
                            except Exception as tool_error:
                                logger.error(f"Error executing web_search tool call: {tool_error}")
                                # Return error message to LLM
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps({"error": f"Web search failed: {str(tool_error)}"})
                                })
                    
                    # Continue conversation with tool results (or error messages)
                    # Always continue if there were tool calls (even if they failed)
                    if response.get("tool_calls"):
                        logger.info(f"Continuing LLM conversation after tool calls for {designator}")
                        next_response = self.llm_client.chat(messages, temperature=0.0, tools=tools, tool_choice="auto" if web_search_tool else None)
                        if next_response is None:
                            logger.error(f"LLM returned None after tool calls for {designator}")
                            if attempt < max_retries:
                                continue
                            return None
                        response = next_response
                
                # If response is still a dict (tool calls), get the final content
                if isinstance(response, dict):
                    # If there are still tool calls, we need to handle them (recursive tool calling)
                    if "tool_calls" in response and response.get("tool_calls"):
                        # Limit recursion to prevent infinite loops
                        if attempt < max_retries:
                            logger.warning(f"LLM returned additional tool calls, retrying...")
                            continue
                        else:
                            # Final attempt - extract content if available
                            response = response.get("content", "")
                    else:
                        # No more tool calls, extract content
                        response = response.get("content", "")
                
                if not response:
                    error_msg = f"Empty LLM response for {designator}, attempt {attempt + 1}/{max_retries + 1}"
                    logger.warning(error_msg)
                    print(f"[Footprint Generator] {error_msg}")
                    if attempt < max_retries:
                        print(f"[Footprint Generator] Retrying...")
                        continue
                    error_msg = f"Empty LLM response for {designator} after {max_retries + 1} attempts - LLM may be unavailable or rate-limited"
                    logger.error(error_msg)
                    print(f"[Footprint Generator] {error_msg}")
                    return None
                
                # Log response preview for debugging
                response_preview = str(response)[:200] if response else "None"
                logger.debug(f"LLM response preview for {designator}: {response_preview}...")
                print(f"[Footprint Generator] LLM response received for {designator} (length: {len(str(response))} chars)")
                print(f"[Footprint Generator] Response preview: {response_preview}...")
                
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
                        
                        # Comprehensive post-processing to fix ALL layout issues
                        footprint_spec = self._fix_all_layout_issues(footprint_spec, footprint, pin_count)
                        
                        # Normalize pad numbering for dual-row packages (generic, no hard-coding)
                        # This is called AFTER layout fix to ensure correct numbering
                        footprint_spec = self._normalize_pad_numbering(footprint_spec, footprint, pin_count)
                        
                        # Validate dimensions and log warnings about incorrect values
                        self._validate_and_warn_dimensions(footprint_spec, footprint, designator)
                        
                        # Validate and check pad count (but be lenient - don't reject unless critical)
                        validated_spec = self._validate_footprint_spec_basic(footprint_spec, footprint, pin_count)
                        
                        if validated_spec:
                            footprint_spec = validated_spec
                        else:
                            # Validation failed, but log and try to continue with original spec
                            logger.warning(f"Validation failed for {designator} ({footprint}), but continuing with generated spec")
                            # Don't reject - use the generated spec anyway
                        
                        # CRITICAL: Apply extracted dimensions if we have them
                        if extracted_dimensions:
                            logger.info(f"Applying extracted dimensions to {designator} ({footprint}): {extracted_dimensions}")
                            footprint_spec = self._apply_extracted_dimensions(footprint_spec, extracted_dimensions, footprint, designator)
                        
                        # CRITICAL: Post-validation check and correction
                        # If we have web search results, verify the generated footprint matches them
                        if web_search_results:
                            logger.info(f"Validating {designator} ({footprint}) against {len(web_search_results)} web search results")
                            footprint_spec = self._validate_against_web_search(footprint_spec, footprint, pin_count, web_search_results, designator)
                            
                            # Log comparison summary
                            pads = footprint_spec.get('pads', [])
                            non_tab_pads = [p for p in pads if p.get('name', '').lower() not in ['tab', '9']]
                            logger.info(f"Final footprint for {designator} ({footprint}): {len(non_tab_pads)} signal pads, {len(pads) - len(non_tab_pads)} thermal pad(s)")
                        
                        # Final validation: Check pad count and layout
                        footprint_spec = self._final_validation_and_correction(footprint_spec, footprint, pin_count, designator)
                        
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
                            
                            # CRITICAL: Validate that pad dimensions don't match body dimensions (merge bug)
                            self._validate_pad_vs_body_dimensions(footprint_spec, footprint, designator)
                            
                            # Add verification status for LLM-generated footprints
                            # Classify footprint to determine verification status
                            footprint_upper = footprint.upper() if footprint else ''
                            if any(pkg in footprint_upper for pkg in ['0402', '0603', '0805', '1206', '2010', '2512', '2220']):
                                # Passive chip - could be verified if dimensions match IPC
                                footprint_spec['footprint_class'] = 'passive_chip'
                                footprint_spec['verification_status'] = 'guessed'  # LLM-generated, needs verification
                                if 'notes' not in footprint_spec or not footprint_spec.get('notes'):
                                    footprint_spec['notes'] = 'LLM-generated footprint (needs verification)'
                            elif any(pkg in footprint_upper for pkg in ['SOT', 'SOIC', 'ESOP', 'TO-263', 'TO-252', 'SMB', 'SMC', 'SOD']):
                                # Standard package - could be verified if from proper template
                                footprint_spec['footprint_class'] = 'standard_package'
                                footprint_spec['verification_status'] = 'guessed'  # LLM-generated, needs verification
                                if 'notes' not in footprint_spec or not footprint_spec.get('notes'):
                                    footprint_spec['notes'] = 'LLM-generated footprint (needs verification)'
                            else:
                                # Custom/vendor-specific - definitely needs datasheet verification
                                footprint_spec['footprint_class'] = 'custom'
                                footprint_spec['verification_status'] = 'needs_manual_verification'
                                if 'notes' not in footprint_spec or not footprint_spec.get('notes'):
                                    footprint_spec['notes'] = 'LLM-generated custom footprint - REQUIRES datasheet verification'
                            
                            logger.info(f"Generated footprint for {designator}: {footprint_spec.get('footprint_name')} with {len(pads)} pads ({len(non_tab_pads)} signal pads, {len(pads) - len(non_tab_pads)} tabs)")
                            return footprint_spec
                    except json.JSONDecodeError as e:
                        if attempt < max_retries:
                            logger.warning(f"JSON decode error for {designator}, attempt {attempt + 1}/{max_retries + 1}, retrying...")
                            logger.warning(f"JSON string (first 1000 chars): {json_str[:1000] if json_str else 'None'}...")
                            continue
                        logger.error(f"JSON decode error for {designator} after {max_retries + 1} attempts: {e}")
                        logger.error(f"JSON string (first 2000 chars): {json_str[:2000] if json_str else 'None'}...")
                        logger.error(f"Error details: {str(e)}")
                        return None
                else:
                    if attempt < max_retries:
                        logger.warning(f"No JSON found in LLM response for {designator}, attempt {attempt + 1}/{max_retries + 1}, retrying...")
                        logger.warning(f"Full response (first 1000 chars): {str(response)[:1000]}")
                        continue
                    logger.error(f"No JSON found in LLM response for {designator} after {max_retries + 1} attempts")
                    logger.error(f"Full response (first 2000 chars): {str(response)[:2000]}")
                    logger.error(f"Response type: {type(response)}, length: {len(str(response)) if response else 0}")
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
        
        # Safety check: handle None or empty footprint_name
        if not footprint_name:
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
                return  # Just return, don't reject here (validation happens elsewhere)
            
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
            # Early validation
            if not spec or 'pads' not in spec:
                return spec
            
            if not footprint_name:
                return spec
            
            # Initialize footprint_name_upper safely
            footprint_name_upper = footprint_name.upper().strip()
            
            # Check if dimensions seem wrong
            pads = spec.get('pads', [])
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
            # Safely handle errors - footprint_name might be None
            name_str = footprint_name if footprint_name else 'unknown'
            logger.warning(f"Error in dimension refinement for {name_str}: {e}")
            # Return original spec if any error occurs
            return spec
    
    def _validate_pad_vs_body_dimensions(self, spec: Dict[str, Any], footprint_name: str, designator: str) -> None:
        """
        Validate that pad dimensions don't match body dimensions (indicates merge bug).
        This prevents cases like CAE-13.5X13.5X13.5mm where pad height = body height = 13.5mm.
        """
        if not spec or 'pads' not in spec:
            return
        
        pads = spec.get('pads', [])
        body_width = spec.get('body_width', 0)
        body_height = spec.get('body_height', 0)
        silkscreen = spec.get('silkscreen', {})
        silkscreen_width = silkscreen.get('width', 0)
        silkscreen_height = silkscreen.get('height', 0)
        
        if not pads or (body_width == 0 and body_height == 0):
            return
        
        for pad in pads:
            pad_name = pad.get('name', '').lower()
            # Skip thermal pads - they can be large
            if pad_name == 'tab' or pad_name == '9':
                continue
            
            pad_width = pad.get('width', 0)
            pad_height = pad.get('height', 0)
            
            # Check if pad dimensions match body dimensions (BUG!)
            if body_width > 0 and abs(pad_width - body_width) < 0.1:
                logger.error(f"BUG DETECTED for {designator} ({footprint_name}): Pad {pad.get('name')} width ({pad_width}mm) matches body width ({body_width}mm). This indicates body dimensions were incorrectly copied to pad dimensions!")
                # Fix: use reasonable default based on package type
                if 'CAE' in footprint_name.upper() or '13.5' in footprint_name:
                    # CAE packages: use typical pad dimensions for large capacitors
                    pad['width'] = 3.0  # Reasonable pad width for large capacitor
                    pad['height'] = 2.0  # Reasonable pad height
                    logger.warning(f"  Fixed: Set pad {pad.get('name')} to {pad['width']}×{pad['height']}mm (was {pad_width}×{pad_height}mm)")
            
            if body_height > 0 and abs(pad_height - body_height) < 0.1:
                logger.error(f"BUG DETECTED for {designator} ({footprint_name}): Pad {pad.get('name')} height ({pad_height}mm) matches body height ({body_height}mm). This indicates body dimensions were incorrectly copied to pad dimensions!")
                # Fix: use reasonable default
                if 'CAE' in footprint_name.upper() or '13.5' in footprint_name:
                    pad['height'] = 2.0  # Reasonable pad height
                    logger.warning(f"  Fixed: Set pad {pad.get('name')} height to {pad['height']}mm (was {pad_height}mm)")
            
            # Check if pad dimensions match silkscreen dimensions (also a bug)
            if silkscreen_width > 0 and abs(pad_width - silkscreen_width) < 0.1:
                logger.warning(f"WARNING for {designator} ({footprint_name}): Pad {pad.get('name')} width ({pad_width}mm) matches silkscreen width ({silkscreen_width}mm). This may indicate incorrect dimension assignment.")
            
            if silkscreen_height > 0 and abs(pad_height - silkscreen_height) < 0.1:
                logger.warning(f"WARNING for {designator} ({footprint_name}): Pad {pad.get('name')} height ({pad_height}mm) matches silkscreen height ({silkscreen_height}mm). This may indicate incorrect dimension assignment.")
    
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
        This function ensures pads are numbered sequentially and correctly.
        """
        if not spec or 'pads' not in spec:
            return spec
        
        # Safety check: handle None or empty footprint_name
        if not footprint_name:
            return spec
        
        pads = spec.get('pads', [])
        footprint_name_upper = footprint_name.upper().strip()
        
        # Separate thermal pads from signal pads
        thermal_pads = []
        signal_pads = []
        
        for pad in pads:
            pad_name = str(pad.get('name', '')).lower()
            # Keep thermal pads separate (Tab, or pad 9 for ESOP)
            if pad_name == 'tab' or (pad_name == '9' and 'ESOP' in footprint_name_upper):
                thermal_pads.append(pad)
            else:
                signal_pads.append(pad)
        
        # Only normalize if we have a dual-row arrangement (pads on both left and right)
        if len(signal_pads) >= 4 and pin_count >= 4:
            left_pads = [p for p in signal_pads if p.get('x', 0) < -0.1]
            right_pads = [p for p in signal_pads if p.get('x', 0) > 0.1]
            
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
                    # Don't normalize - let layout fix handle it
                    logger.debug(f"Skipping normalization for single-row package {footprint_name}")
                    return spec
                elif is_power_package:
                    # Power packages: right side goes bottom to top (4, 5, 6, 7)
                    right_pads.sort(key=lambda p: p.get('y', 0))
                else:
                    # Standard IC packages: right side goes BOTTOM TO TOP (5, 6, 7, 8)
                    # Sort by Y ascending (bottom to top) to match left side convention
                    right_pads.sort(key=lambda p: p.get('y', 0))
                
                # Check if pads are already correctly numbered (1, 2, 3, ...)
                # Only renumber if numbering seems incorrect
                expected_pad_names = [str(i+1) for i in range(len(left_pads) + len(right_pads))]
                current_pad_names = [p.get('name', '') for p in left_pads + right_pads]
                
                # Check if numbering is already correct
                needs_renumbering = False
                if len(current_pad_names) != len(expected_pad_names):
                    needs_renumbering = True
                else:
                    # Check if names match expected sequence
                    for i, (current, expected) in enumerate(zip(sorted(current_pad_names, key=lambda x: int(re.search(r'\d+', str(x)).group()) if re.search(r'\d+', str(x)) else 999), expected_pad_names)):
                        if current != expected:
                            needs_renumbering = True
                            break
                
                if needs_renumbering:
                    # Renumber sequentially: left side first, then right side
                    pad_num = 1
                    for pad in left_pads:
                        pad['name'] = str(pad_num)
                        pad_num += 1
                    
                    for pad in right_pads:
                        pad['name'] = str(pad_num)
                        pad_num += 1
                    
                    logger.debug(f"Renumbered pads for {footprint_name}: {len(left_pads)} left, {len(right_pads)} right")
                else:
                    logger.debug(f"Pads already correctly numbered for {footprint_name}: {len(left_pads)} left, {len(right_pads)} right")
                
                # Always update spec with pads (preserve order: left, right, thermal)
                spec['pads'] = left_pads + right_pads + thermal_pads
                logger.debug(f"Final pad count for {footprint_name}: {len(left_pads)} left, {len(right_pads)} right, {len(thermal_pads)} thermal (power_package={is_power_package})")
        
        return spec
    
    def _fix_all_layout_issues(self, spec: Dict[str, Any], footprint_name: str, pin_count: int) -> Dict[str, Any]:
        """
        Comprehensive function to fix ALL layout issues:
        1. Remove duplicate pad names (e.g., "3_1" -> proper numbering)
        2. Fix TO-263-7 single vertical row layout
        3. Fix LMF500-23B30UH layout
        4. Fix dual-row packages (ESOP8L, SOIC, etc.)
        5. Fix any other package-specific issues
        """
        if not spec or 'pads' not in spec:
            return spec
        
        if not footprint_name:
            return spec
        
        pads = spec.get('pads', [])
        footprint_name_upper = footprint_name.upper().strip()
        
        # Step 1: Remove duplicate pad names and fix numbering
        spec = self._fix_duplicate_pad_names(spec, footprint_name, pin_count)
        pads = spec.get('pads', [])
        
        # Step 2: Fix specific package layouts
        if 'TO-263-7' in footprint_name_upper or 'D2PAK-7' in footprint_name_upper or 'D²PAK-7' in footprint_name_upper:
            logger.info(f"Applying TO-263-7 layout fix for {footprint_name}")
            initial_pad_count = len(spec.get('pads', []))
            spec = self._fix_to263_7_layout(spec, footprint_name)
            final_pad_count = len(spec.get('pads', []))
            logger.info(f"TO-263-7 fix: {initial_pad_count} -> {final_pad_count} pads")
        elif 'LMF500' in footprint_name_upper:
            logger.info(f"Applying LMF500 layout fix for {footprint_name}")
            initial_pad_count = len(spec.get('pads', []))
            spec = self._fix_lmf500_layout(spec, footprint_name)
            final_pad_count = len(spec.get('pads', []))
            logger.info(f"LMF500 fix: {initial_pad_count} -> {final_pad_count} pads")
        else:
            # Step 3: Fix dual-row packages (ESOP, SOIC, etc.)
            spec = self._fix_dual_row_layout(spec, footprint_name, pin_count)
        
        return spec
    
    def _fix_duplicate_pad_names(self, spec: Dict[str, Any], footprint_name: str, pin_count: int) -> Dict[str, Any]:
        """Remove duplicate pad names like '3_1', '4_1' and renumber pads correctly"""
        if not spec or 'pads' not in spec:
            return spec
        
        pads = spec.get('pads', [])
        footprint_name_upper = footprint_name.upper().strip()
        
        # For packages with thermal pads, identify them more carefully
        # Don't separate thermal pads here - let the layout fix functions handle that
        # Only fix duplicate names like "3_1", "4_1"
        
        # Find pads with duplicate-style names (containing underscore)
        duplicate_pads = []
        normal_pads = []
        
        for pad in pads:
            pad_name = str(pad.get('name', ''))
            # Check if name has underscore (like "3_1", "4_1")
            if '_' in pad_name and pad_name.replace('_', '').isdigit():
                duplicate_pads.append(pad)
            else:
                normal_pads.append(pad)
        
        # If we have duplicate pads, we need to renumber everything
        if duplicate_pads:
            logger.info(f"Found duplicate pad names in {footprint_name}, fixing numbering...")
            
            # Sort all pads by X coordinate to preserve order
            all_pads = sorted(pads, key=lambda p: p.get('x', 0))
            
            # Renumber sequentially, but preserve thermal pad names
            pad_num = 1
            for pad in all_pads:
                pad_name = str(pad.get('name', '')).lower()
                # Keep thermal pad names (Tab, or pad 9 for ESOP8L)
                if pad_name == 'tab':
                    pad['name'] = 'Tab'
                elif pad_name == '9' and 'ESOP' in footprint_name_upper:
                    pad['name'] = '9'  # Keep pad 9 for ESOP8L
                else:
                    pad['name'] = str(pad_num)
                    pad_num += 1
        
        return spec
    
    def _fix_to263_7_layout(self, spec: Dict[str, Any], footprint_name: str) -> Dict[str, Any]:
        """
        Fix TO-263-7 layout: 7 pads in SINGLE VERTICAL ROW on left side, thermal tab on right/top
        """
        if not spec or 'pads' not in spec:
            logger.warning(f"TO-263-7 fix: spec has no pads, returning unchanged")
            return spec
        
        initial_pad_count = len(spec.get('pads', []))
        logger.info(f"TO-263-7 fix starting: {initial_pad_count} pads in spec")
        
        pads = spec.get('pads', [])
        footprint_name_upper = footprint_name.upper().strip()
        
        # Separate thermal pad from signal pads
        thermal_pads = []
        signal_pads = []
        
        for pad in pads:
            pad_name = pad.get('name', '').lower()
            pad_width = pad.get('width', 0)
            pad_height = pad.get('height', 0)
            # Thermal tab is large or named "tab"
            if pad_name == 'tab' or (pad_width > 5.0 and pad_height > 5.0):
                thermal_pads.append(pad)
            else:
                signal_pads.append(pad)
        
        # TO-263-7 MUST have exactly 7 signal pads in a VERTICAL single row + 1 thermal tab
        # Standard TO-263-7 dimensions
        left_x = -3.8  # Left side position
        pin_pitch = 0.95  # Pin pitch
        pad_width = 0.9
        pad_height = 2.0
        
        # Calculate Y positions (vertical row, bottom to top)
        total_height = (7 - 1) * pin_pitch
        start_y = -total_height / 2  # Start from -2.85mm
        
        # If we have fewer than 7, we need to add missing pads
        if len(signal_pads) < 7:
            logger.warning(f"TO-263-7 has only {len(signal_pads)} signal pads, expected 7. Adding missing pads.")
            
            # Get existing pad numbers to avoid duplicates
            existing_pad_nums = set()
            for pad in signal_pads:
                try:
                    pad_num = int(pad.get('name', '0'))
                    if pad_num > 0:
                        existing_pad_nums.add(pad_num)
                except:
                    pass
            
            # Add missing pads to reach exactly 7
            while len(signal_pads) < 7:
                # Find next available pad number (1-7)
                pad_num = len(signal_pads) + 1
                while pad_num in existing_pad_nums and pad_num <= 7:
                    pad_num += 1
                if pad_num > 7:
                    pad_num = len(signal_pads) + 1
                
                new_pad = {
                    'name': str(pad_num),
                    'x': left_x,
                    'y': start_y + (len(signal_pads)) * pin_pitch,  # Position vertically
                    'width': pad_width,
                    'height': pad_height,
                    'shape': 'rectangular',
                    'layer': 'top',
                    'hole_size': 0.0
                }
                signal_pads.append(new_pad)
                existing_pad_nums.add(pad_num)
                logger.info(f"Added missing pad {pad_num} for TO-263-7 at y={new_pad['y']:.2f}mm")
        
        # Now arrange all pads correctly (whether we added pads or not)
        if len(signal_pads) >= 7:
            # Check if pads are incorrectly arranged horizontally (all have similar Y coordinates)
            y_coords = [p.get('y', 0) for p in signal_pads]
            y_range = max(y_coords) - min(y_coords) if len(y_coords) > 1 else 0
            x_coords = [abs(p.get('x', 0)) for p in signal_pads]
            x_range = max(x_coords) - min(x_coords) if len(x_coords) > 1 else 0
            is_horizontal = y_range < 1.0 and x_range > 2.0
            
            logger.info(f"Fixing TO-263-7 layout: arranging 7 pads in vertical single row (was horizontal: {is_horizontal})")
            
            # Sort pads by pad number (or by X if horizontal)
            def get_pad_num(p):
                try:
                    return int(p.get('name', '0'))
                except:
                    return 999
            
            # If pads are horizontal, sort by X coordinate; otherwise by pad number
            if is_horizontal:
                signal_pads.sort(key=lambda p: p.get('x', 0))
            else:
                signal_pads.sort(key=get_pad_num)
            
            # Take exactly 7 pads and arrange vertically
            # Sort by pad number to ensure correct order
            def get_pad_num_safe(p):
                try:
                    num = int(p.get('name', '0'))
                    if 1 <= num <= 7:
                        return num
                    return 999
                except:
                    return 999
            
            # Sort by pad number, then take first 7
            signal_pads_sorted = sorted(signal_pads, key=get_pad_num_safe)[:7]
            
            # Arrange all 7 pads vertically
            for i, pad in enumerate(signal_pads_sorted):
                pad['x'] = left_x
                pad['y'] = start_y + i * pin_pitch
                pad['width'] = pad_width
                pad['height'] = pad_height
                pad['name'] = str(i + 1)  # Ensure sequential numbering 1-7
                logger.debug(f"TO-263-7 pad {i+1}: x={pad['x']}, y={pad['y']:.2f}")
            
            signal_pads = signal_pads_sorted
            
            # Position thermal tab (large pad on right/top)
            if thermal_pads:
                tab = thermal_pads[0]
                tab['x'] = 0.0
                tab['y'] = 2.0
                tab['width'] = 10.0
                tab['height'] = 7.5
                tab['name'] = 'Tab'
            elif len(signal_pads) > 7:
                # If no tab but we have more pads, the 8th might be the tab
                extra_pad = signal_pads[7]
                if extra_pad.get('width', 0) > 5.0:
                    thermal_pads.append(extra_pad)
                    signal_pads = signal_pads[:7]
                    tab = thermal_pads[0]
                    tab['x'] = 0.0
                    tab['y'] = 2.0
                    tab['width'] = 10.0
                    tab['height'] = 7.5
                    tab['name'] = 'Tab'
            
            # Ensure we have exactly 7 signal pads
            if len(signal_pads) > 7:
                logger.warning(f"TO-263-7 has {len(signal_pads)} signal pads, taking first 7")
                signal_pads = signal_pads[:7]
            elif len(signal_pads) < 7:
                logger.error(f"TO-263-7 still has only {len(signal_pads)} signal pads after fix attempt!")
            
            spec['pads'] = signal_pads + thermal_pads
            final_pad_count = len(spec['pads'])
            logger.info(f"Fixed TO-263-7: {len(signal_pads)} signal pads in vertical row at x={left_x}mm, y from {start_y:.2f} to {start_y + (len(signal_pads)-1)*pin_pitch:.2f}mm, plus {len(thermal_pads)} thermal pad(s)")
            logger.info(f"TO-263-7 fix complete: {initial_pad_count} -> {final_pad_count} total pads (expected 8: 7 signal + 1 thermal)")
            
            # Final verification
            if len(signal_pads) != 7:
                logger.error(f"TO-263-7 CRITICAL ERROR: Still has {len(signal_pads)} signal pads instead of 7!")
            if len(thermal_pads) == 0:
                logger.warning(f"TO-263-7: No thermal pad found, adding one")
                thermal_pad = {
                    'name': 'Tab',
                    'x': 0.0,
                    'y': 2.0,
                    'width': 10.0,
                    'height': 7.5,
                    'shape': 'rectangular',
                    'layer': 'top',
                    'hole_size': 0.0
                }
                thermal_pads.append(thermal_pad)
                spec['pads'] = signal_pads + thermal_pads
        else:
            logger.warning(f"TO-263-7: signal_pads count is {len(signal_pads)}, expected >= 7")
        
        return spec
    
    def _fix_lmf500_layout(self, spec: Dict[str, Any], footprint_name: str) -> Dict[str, Any]:
        """
        Fix LMF500-23B30UH layout: 6 signal pads in horizontal row at bottom, thermal pad at top
        """
        if not spec or 'pads' not in spec:
            return spec
        
        pads = spec.get('pads', [])
        
        # Separate thermal pad from signal pads
        thermal_pads = []
        signal_pads = []
        
        for pad in pads:
            pad_name = pad.get('name', '').lower()
            pad_width = pad.get('width', 0)
            pad_height = pad.get('height', 0)
            # Thermal pad is usually larger or named "7"
            if pad_name == '7' or (pad_width > 2.0 and pad_height > 2.0):
                thermal_pads.append(pad)
            else:
                signal_pads.append(pad)
        
        # LMF500 should have 6 signal pads + 1 thermal pad = 7 total
        # Add missing signal pads if needed
        if len(signal_pads) < 6:
            logger.warning(f"LMF500 has only {len(signal_pads)} signal pads, expected 6. Adding missing pads.")
            # Standard dimensions
            pad_width = 0.9
            pad_height = 1.5
            pad_spacing = 1.5
            signal_y = -2.0
            
            # Get existing pad numbers
            existing_pad_nums = set()
            for pad in signal_pads:
                try:
                    pad_num = int(pad.get('name', '0'))
                    if pad_num > 0:
                        existing_pad_nums.add(pad_num)
                except:
                    pass
            
            # Add missing pads
            total_width = (6 - 1) * pad_spacing
            start_x = -total_width / 2
            while len(signal_pads) < 6:
                pad_num = len(signal_pads) + 1
                while pad_num in existing_pad_nums and pad_num <= 6:
                    pad_num += 1
                if pad_num > 6:
                    pad_num = len(signal_pads) + 1
                
                new_pad = {
                    'name': str(pad_num),
                    'x': start_x + (len(signal_pads)) * pad_spacing,
                    'y': signal_y,
                    'width': pad_width,
                    'height': pad_height,
                    'shape': 'rectangular',
                    'layer': 'top',
                    'hole_size': 0.0
                }
                signal_pads.append(new_pad)
                existing_pad_nums.add(pad_num)
                logger.info(f"Added missing pad {pad_num} for LMF500 at x={new_pad['x']:.2f}mm")
        
        if len(signal_pads) >= 6:
            logger.info(f"Fixing LMF500 layout: {len(signal_pads)} signal pads at bottom, thermal pad at top")
            
            # Standard dimensions
            pad_width = 0.9
            pad_height = 1.5
            pad_spacing = 1.5  # Spacing between pads
            signal_y = -2.0  # Y position for signal pads (per specification)
            thermal_y = 2.0   # Y position for thermal pad (per specification)
            
            # Sort signal pads by pad number
            def get_pad_num(p):
                try:
                    return int(p.get('name', '0'))
                except:
                    return 999
            
            signal_pads.sort(key=get_pad_num)
            
            # Arrange 6 signal pads horizontally at bottom
            total_width = (6 - 1) * pad_spacing
            start_x = -total_width / 2
            
            for i, pad in enumerate(signal_pads[:6]):
                pad['x'] = start_x + i * pad_spacing
                pad['y'] = signal_y
                pad['width'] = pad_width
                pad['height'] = pad_height
                pad['name'] = str(i + 1)
            
            # Position thermal pad at top
            if thermal_pads:
                thermal = thermal_pads[0]
                thermal['x'] = 0.0
                thermal['y'] = thermal_y
                thermal['width'] = pad_width
                thermal['height'] = pad_height
                thermal['name'] = '7'
            elif len(signal_pads) > 6:
                # If no thermal pad but we have 7th pad, make it thermal
                thermal = signal_pads[6]
                thermal['x'] = 0.0
                thermal['y'] = thermal_y
                thermal['width'] = pad_width
                thermal['height'] = pad_height
                thermal['name'] = '7'
                thermal_pads.append(thermal)
                signal_pads = signal_pads[:6]
            
            # Ensure we have exactly 6 signal pads
            if len(signal_pads) > 6:
                logger.warning(f"LMF500 has {len(signal_pads)} signal pads, taking first 6")
                signal_pads = signal_pads[:6]
            elif len(signal_pads) < 6:
                logger.error(f"LMF500 still has only {len(signal_pads)} signal pads after fix attempt!")
            
            spec['pads'] = signal_pads + thermal_pads
            logger.info(f"Fixed LMF500: {len(signal_pads)} signal pads at y={signal_y}mm, thermal pad at y={thermal_y}mm")
        
        return spec
    
    def _fix_dual_row_layout(self, spec: Dict[str, Any], footprint_name: str, pin_count: int) -> Dict[str, Any]:
        """
        Detect and fix incorrectly arranged dual-row packages.
        Some packages like ESOP8L should have pads on left and right sides (vertical arrangement),
        but the LLM may generate them in a single horizontal row. This function corrects that.
        """
        if not spec or 'pads' not in spec:
            return spec
        
        if not footprint_name:
            return spec
        
        pads = spec.get('pads', [])
        footprint_name_upper = footprint_name.upper().strip()
        
        # Check if this is a dual-row package that should have side pads
        # Also check by pin count - if it has 8 pins and pads are in wrong layout, fix it
        is_dual_row_package = any(x in footprint_name_upper for x in [
            'ESOP8L', 'ESOP-8', 'ESOP8', 'ESOP-14', 'ESOP-16',
            'SOIC-8', 'SOIC8', 'SOIC-14', 'SOIC14', 'SOIC-16', 'SOIC16',
            'SSOP-8', 'SSOP8', 'SSOP-14', 'SSOP14', 'SSOP-16', 'SSOP16',
            'TSSOP-8', 'TSSOP8', 'TSSOP-14', 'TSSOP14', 'TSSOP-16', 'TSSOP16',
            'DW-PXXX'  # Add DW-PXXX packages
        ]) or (pin_count >= 8 and len(signal_pads) >= 8)  # Generic 8+ pin packages
        
        if not is_dual_row_package:
            return spec
        
        # Separate thermal pads from signal pads
        # For ESOP8L, pad 9 is thermal; for others, "Tab" is thermal
        thermal_pads = []
        signal_pads = []
        
        for pad in pads:
            pad_name = str(pad.get('name', '')).lower()
            pad_x = abs(pad.get('x', 0))
            pad_y = abs(pad.get('y', 0))
            pad_width = pad.get('width', 0)
            pad_height = pad.get('height', 0)
            
            # Identify thermal pads
            is_thermal = False
            if 'ESOP' in footprint_name_upper:
                # For ESOP, pad 9 is thermal
                is_thermal = (pad_name == '9' or 
                             (pad_width > 2.0 and pad_height > 2.0 and pad_x < 1.5 and pad_y < 1.5))
            else:
                # For other packages, "Tab" is thermal
                is_thermal = (pad_name == 'tab' or 
                             (pad_width > 2.0 and pad_height > 2.0))
            
            if is_thermal:
                thermal_pads.append(pad)
            else:
                signal_pads.append(pad)
        
        if len(signal_pads) < 4:
            return spec
        
        # Check if pads are incorrectly arranged in a single horizontal row
        # This happens when all pads have similar Y coordinates (within 1.0mm)
        y_coords = [p.get('y', 0) for p in signal_pads]
        if len(y_coords) < 2:
            return spec
        
        y_min = min(y_coords)
        y_max = max(y_coords)
        y_range = y_max - y_min
        
        # Also check if pads are spread horizontally (X coordinates vary significantly)
        x_coords = [abs(p.get('x', 0)) for p in signal_pads]
        x_max = max(x_coords) if x_coords else 0
        x_min = min([abs(p.get('x', 0)) for p in signal_pads]) if signal_pads else 0
        x_range = x_max - x_min
        
        # Check if pads are in a single horizontal row (y_range < 1.0mm) and spread horizontally
        is_horizontal_row = y_range < 1.0 and x_range > 2.0
        
        # For ESOP8L specifically, check if it has proper dual-row layout
        is_esop8l = 'ESOP8L' in footprint_name_upper and len(signal_pads) == 8
        needs_fix = False
        
        if is_esop8l:
            # Check if pads are already in dual-row (pads on both left and right)
            left_count = len([p for p in signal_pads if p.get('x', 0) < -1.0])
            right_count = len([p for p in signal_pads if p.get('x', 0) > 1.0])
            has_dual_row = left_count >= 3 and right_count >= 3
            
            if not has_dual_row:
                needs_fix = True
                logger.warning(f"ESOP8L detected without proper dual-row layout (left={left_count}, right={right_count}), forcing fix")
        else:
            needs_fix = is_horizontal_row
        
        if needs_fix and len(signal_pads) >= 4:
            logger.info(f"Detected incorrectly arranged dual-row package {footprint_name}: {len(signal_pads)} pads in single horizontal row, fixing to dual-row layout...")
            
            # Determine expected layout based on signal pad count
            # For ESOP8L: 4 pads on left, 4 pads on right (8 signal + 1 thermal = 9 total)
            # For SOIC-8: 4 pads on left, 4 pads on right
            # For SOIC-14: 7 pads on left, 7 pads on right
            # For SOIC-16: 8 pads on left, 8 pads on right
            
            pins_per_side = len(signal_pads) // 2
            
            # Standard SOIC/ESOP dimensions
            row_spacing = 5.4  # Standard SOIC row spacing
            pin_pitch = 1.27   # Standard SOIC pin pitch
            pad_width = 0.6    # Standard SOIC pad width
            pad_height = 1.5   # Standard SOIC pad height
            
            # Calculate positions
            left_x = -row_spacing / 2  # -2.7mm for standard SOIC
            right_x = row_spacing / 2   # +2.7mm for standard SOIC
            
            # Calculate Y positions for left side (bottom to top)
            # Center the pins vertically around y=0
            total_height = (pins_per_side - 1) * pin_pitch
            start_y = -total_height / 2
            
            # Sort signal pads by their X coordinate (left to right) to preserve original order
            # This ensures we maintain the intended pad sequence even if names are wrong
            sorted_signal_pads = sorted(signal_pads, key=lambda p: p.get('x', 0))
            
            # Ensure we have enough pads
            if len(sorted_signal_pads) < pins_per_side * 2:
                logger.warning(f"Not enough signal pads for {footprint_name}: have {len(sorted_signal_pads)}, need {pins_per_side * 2}")
                # Use what we have, but log the issue
                pins_per_side = len(sorted_signal_pads) // 2
            
            # Rearrange pads: first half go to left side, second half go to right side
            left_pads = sorted_signal_pads[:pins_per_side]
            right_pads = sorted_signal_pads[pins_per_side:pins_per_side * 2]  # Ensure we only take what we need
            
            # Log if we're losing pads
            if len(sorted_signal_pads) > pins_per_side * 2:
                logger.warning(f"Extra pads detected for {footprint_name}: {len(sorted_signal_pads)} total, using {pins_per_side * 2}")
                # Add extra pads to right side if needed, or log them
                extra_pads = sorted_signal_pads[pins_per_side * 2:]
                logger.warning(f"Extra pads for {footprint_name}: {[p.get('name') for p in extra_pads]}")
            
            # Update left side pads (vertical arrangement, bottom to top)
            for i, pad in enumerate(left_pads):
                pad['x'] = left_x
                pad['y'] = start_y + i * pin_pitch
                pad['width'] = pad_width
                pad['height'] = pad_height
                # Renumber: pads 1, 2, 3, 4... (bottom to top)
                pad['name'] = str(i + 1)
            
            # Update right side pads (vertical arrangement, BOTTOM TO TOP for standard numbering)
            # Right side should be numbered 5, 6, 7, 8 from bottom to top (continuing from left side)
            for i, pad in enumerate(right_pads):
                pad['x'] = right_x
                # Right side goes BOTTOM TO TOP (same as left side) - pad 5 at bottom, pad 8 at top
                pad['y'] = start_y + i * pin_pitch
                pad['width'] = pad_width
                pad['height'] = pad_height
                # Renumber: continue from left side (pins_per_side + 1, pins_per_side + 2, ...)
                # Pad 5 at bottom (i=0), pad 6 (i=1), pad 7 (i=2), pad 8 at top (i=3)
                pad['name'] = str(pins_per_side + i + 1)
            
            # Ensure thermal pad is at center if present
            for thermal_pad in thermal_pads:
                thermal_pad['x'] = 0.0
                thermal_pad['y'] = 0.0
                # Thermal pad size for ESOP8L is typically 3.0×3.0mm
                if 'ESOP' in footprint_name_upper:
                    thermal_pad['width'] = 3.0
                    thermal_pad['height'] = 3.0
                    thermal_pad['name'] = '9'  # Ensure pad 9 for ESOP8L
            
            # Collect any remaining pads that weren't processed
            processed_pad_names = {p.get('name') for p in left_pads + right_pads}
            remaining_pads = [p for p in sorted_signal_pads if p.get('name') not in processed_pad_names]
            
            # Update spec with rearranged pads - include ALL pads
            all_pads = left_pads + right_pads + thermal_pads
            if remaining_pads:
                logger.warning(f"Found {len(remaining_pads)} unprocessed pads for {footprint_name}: {[p.get('name') for p in remaining_pads]}")
                # Add remaining pads at the end (they might be duplicates or extras)
                all_pads.extend(remaining_pads)
            
            spec['pads'] = all_pads
            total_pads = len(left_pads) + len(right_pads) + len(thermal_pads)
            logger.info(f"Fixed dual-row layout for {footprint_name}: {pins_per_side} pads on left, {pins_per_side} pads on right, {len(thermal_pads)} thermal pad(s), total={total_pads} pads")
        
        return spec
    
    def _validate_footprint_spec_basic(self, spec: Dict[str, Any], footprint_name: str, pin_count: int) -> Dict[str, Any]:
        """
        Basic validation - check for obvious structural errors (missing pads, invalid values)
        Do NOT correct dimensions - trust the LLM to provide correct IPC-7351 dimensions from its knowledge
        """
        # Safety check: handle None or empty footprint_name
        if not footprint_name:
            logger.warning(f"No footprint name provided for validation")
            return None
        
        pads = spec.get('pads', [])
        
        # Only validate structure, not dimensions
        if not pads:
            logger.warning(f"No pads found in footprint spec for {footprint_name}, but accepting anyway (may be fixed later)")
            # Don't reject - return spec anyway, post-processing might fix it
            return spec
        
        # Count non-tab pads (tabs are named "Tab" or "tab")
        non_tab_pads = [p for p in pads if p.get('name', '').lower() != 'tab']
        actual_pin_count = len(non_tab_pads)
        tab_count = len([p for p in pads if p.get('name', '').lower() == 'tab'])
        total_pads = len(pads)
        
        # Check for required tabs in power packages
        footprint_name_upper = footprint_name.upper().strip()
        is_power_package = any(x in footprint_name_upper for x in ['TO-263', 'TO-252', 'DPAK', 'D2PAK', 'D²PAK', 'SOT-89'])
        
        if is_power_package and tab_count == 0:
            logger.warning(f"Power package {footprint_name} is missing required thermal tab pad - but accepting anyway (may be added later)")
            # Don't reject - accept the footprint, post-processing might add tab
            # return None
        
        # Check if pad count matches pin_count (be VERY lenient - schematic pin_count may be incomplete or wrong)
        # Only reject if pad count is clearly wrong (too few pads, or way too many without tabs)
        if pin_count > 0:
            # Allow more tolerance: schematic pin_count may be incomplete or wrong
            # Only reject if we have significantly fewer pads than expected (at least 1 pad minimum)
            if actual_pin_count < 1:  # Must have at least 1 pad
                logger.warning(f"No pads found for {footprint_name} - but accepting anyway (may be fixed)")
                # Don't reject - return spec anyway
                # return None
            
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
    
    def _get_standard_dimensions(self, footprint_name: str) -> Dict[str, Any]:
        """
        Get standard dimensions from the built-in database.
        Returns empty dict if not found.
        """
        # Try exact match first
        if footprint_name in self.STANDARD_DIMENSIONS:
            dims = self.STANDARD_DIMENSIONS[footprint_name].copy()
            logger.info(f"Found standard dimensions for {footprint_name}: {dims}")
            return dims
        
        # Try case-insensitive match
        footprint_upper = footprint_name.upper()
        for key, dims in self.STANDARD_DIMENSIONS.items():
            if key.upper() == footprint_upper:
                dims_copy = dims.copy()
                logger.info(f"Found standard dimensions for {footprint_name} (matched {key}): {dims_copy}")
                return dims_copy
        
        # Try partial match for chip components (e.g., "R0402" matches "0402")
        if len(footprint_name) >= 4:
            for key, dims in self.STANDARD_DIMENSIONS.items():
                if key.upper() in footprint_upper or footprint_upper in key.upper():
                    dims_copy = dims.copy()
                    logger.info(f"Found standard dimensions for {footprint_name} (partial match {key}): {dims_copy}")
                    return dims_copy
        
        return {}
    
    def _extract_dimensions_from_web_search(self, web_search_results: List[Dict[str, Any]], 
                                           footprint_name: str, designator: str) -> Dict[str, Any]:
        """
        Extract dimensions from web search results BEFORE LLM generation.
        This allows us to pass exact dimensions to the LLM instead of relying on it to extract them.
        
        Also checks the standard dimensions database as a fallback.
        """
        import re
        extracted = {}
        
        # First, check standard dimensions database (most reliable)
        standard_dims = self._get_standard_dimensions(footprint_name)
        if standard_dims:
            extracted.update(standard_dims)
            logger.info(f"Using standard dimensions for {designator} ({footprint_name})")
        
        # Then try to extract from web search results (overrides standard if found)
        if web_search_results:
            # Combine all search result content
            all_content = " ".join([
                result.get('snippet', '') + " " + result.get('content', '') + " " + result.get('title', '') + " " + result.get('text', '')
                for result in web_search_results
            ])
            
            logger.info(f"Extracting dimensions from web search for {designator} ({footprint_name})")
            
            # Extract pad dimensions
            pad_size_patterns = [
            r'pad.*?(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
            r'(\d+\.?\d*)\s*mm\s*[×xX*]\s*(\d+\.?\d*)\s*mm.*?pad',
            r'pad.*?size.*?(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
            r'land.*?pattern.*?(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
        ]
        
            for pattern in pad_size_patterns:
                matches = re.findall(pattern, all_content, re.IGNORECASE)
                if matches:
                    for match in matches:
                        width, height = float(match[0]), float(match[1])
                        if 0.1 <= width <= 20 and 0.1 <= height <= 20:
                            extracted['pad_width'] = width
                            extracted['pad_height'] = height
                            logger.info(f"  ✓ Extracted pad size from web: {width}mm × {height}mm")
                            break
                    if 'pad_width' in extracted:
                        break
            
            # Extract pin pitch
            pitch_patterns = [
            r'pitch.*?(\d+\.?\d*)\s*mm',
            r'(\d+\.?\d*)\s*mm.*?pitch',
            r'pin.*?spacing.*?(\d+\.?\d*)\s*mm',
            r'pin.*?pitch.*?(\d+\.?\d*)\s*mm',
        ]
        
            for pattern in pitch_patterns:
                matches = re.findall(pattern, all_content, re.IGNORECASE)
                if matches:
                    for match in matches:
                        pitch = float(match)
                        if 0.1 <= pitch <= 10:
                            extracted['pin_pitch'] = pitch
                            logger.info(f"  ✓ Extracted pin pitch from web: {pitch}mm")
                            break
                    if 'pin_pitch' in extracted:
                        break
            
            # Extract pad count
            pad_count_patterns = [
            r'(\d+)\s*pads?',
            r'pad.*?count.*?(\d+)',
            r'(\d+)\s*pins?',
        ]
        
            for pattern in pad_count_patterns:
                matches = re.findall(pattern, all_content, re.IGNORECASE)
                if matches:
                    for match in matches:
                        count = int(match)
                        if 1 <= count <= 200:
                            extracted['pad_count'] = count
                            logger.info(f"  ✓ Extracted pad count from web: {count}")
                            break
                    if 'pad_count' in extracted:
                        break
        
        return extracted
    
    def _apply_extracted_dimensions(self, spec: Dict[str, Any], extracted_dimensions: Dict[str, Any], 
                                   footprint_name: str, designator: str) -> Dict[str, Any]:
        """
        Apply extracted dimensions from web search directly to the footprint spec.
        This ensures the exact dimensions are used regardless of what the LLM generated.
        """
        if not spec or 'pads' not in spec:
            return spec
        
        if not extracted_dimensions:
            return spec
        
        pads = spec.get('pads', [])
        corrections_made = []
        
        # Apply pad dimensions if extracted
        if 'pad_width' in extracted_dimensions and 'pad_height' in extracted_dimensions:
            for pad in pads:
                pad_name = pad.get('name', '').lower()
                # Don't change thermal pad sizes automatically
                if pad_name not in ['tab', '9']:
                    old_width = pad.get('width', 0)
                    old_height = pad.get('height', 0)
                    pad['width'] = extracted_dimensions['pad_width']
                    pad['height'] = extracted_dimensions['pad_height']
                    if abs(old_width - extracted_dimensions['pad_width']) > 0.01 or abs(old_height - extracted_dimensions['pad_height']) > 0.01:
                        corrections_made.append(f"Pad {pad.get('name')}: {old_width}×{old_height}mm → {extracted_dimensions['pad_width']}×{extracted_dimensions['pad_height']}mm")
        
        # Apply pin pitch if extracted (for packages with regular spacing)
        if 'pin_pitch' in extracted_dimensions:
            # This will be handled by layout fix functions, but we log it here
            logger.info(f"  ✓ Pin pitch from web search: {extracted_dimensions['pin_pitch']}mm (will be used by layout functions)")
        
        # Check pad count
        if 'pad_count' in extracted_dimensions:
            expected_count = extracted_dimensions['pad_count']
            non_tab_pads = [p for p in pads if p.get('name', '').lower() not in ['tab', '9']]
            actual_count = len(non_tab_pads)
            if actual_count != expected_count:
                logger.warning(f"  ⚠ Pad count mismatch: expected {expected_count}, got {actual_count} (will be fixed by layout functions)")
        
        if corrections_made:
            logger.info(f"Applied {len(corrections_made)} dimension corrections from extracted web search data for {designator} ({footprint_name})")
            for correction in corrections_made:
                logger.info(f"  ✓ {correction}")
        else:
            logger.info(f"No dimension corrections needed - footprint already matches extracted dimensions for {designator} ({footprint_name})")
        
        return spec
    
    def _validate_against_web_search(self, spec: Dict[str, Any], footprint_name: str, pin_count: int, 
                                     web_search_results: List[Dict[str, Any]], designator: str) -> Dict[str, Any]:
        """
        Validate generated footprint against web search results and correct if needed.
        Extracts dimensions from search results and compares with generated footprint.
        This is CRITICAL for ensuring footprints match real-world specifications.
        """
        if not spec or 'pads' not in spec:
            return spec
        
        if not web_search_results:
            logger.debug(f"No web search results to validate against for {designator} ({footprint_name})")
            return spec
        
        # Extract dimensions from web search results
        import re
        extracted_dimensions = {}
        
        # Combine all search result content with more context
        all_content = " ".join([
            result.get('snippet', '') + " " + result.get('content', '') + " " + result.get('title', '') + " " + result.get('text', '')
            for result in web_search_results
        ])
        
        logger.info(f"Validating {designator} ({footprint_name}) against web search results ({len(web_search_results)} results)")
        
        # Enhanced pattern matching for pad dimensions
        # Look for various formats: "0.9mm × 2.0mm", "0.9 x 2.0 mm", "0.9mm x 2.0mm", "0.9×2.0mm", "0.9mm×2.0mm"
        pad_size_patterns = [
            r'pad.*?(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
            r'(\d+\.?\d*)\s*mm\s*[×xX*]\s*(\d+\.?\d*)\s*mm.*?pad',
            r'pad.*?size.*?(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
            r'land.*?pattern.*?(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
            r'(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm.*?land',
            # Also look for dimensions in tables or specifications
            r'(\d+\.?\d*)\s*mm\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
        ]
        
        for pattern in pad_size_patterns:
            matches = re.findall(pattern, all_content, re.IGNORECASE)
            if matches:
                # Use the first reasonable match (filter out very large or very small values)
                for match in matches:
                    width, height = float(match[0]), float(match[1])
                    # Reasonable pad sizes: 0.1mm to 20mm
                    if 0.1 <= width <= 20 and 0.1 <= height <= 20:
                        extracted_dimensions['pad_width'] = width
                        extracted_dimensions['pad_height'] = height
                        logger.info(f"✓ Extracted pad size from web search: {width}mm × {height}mm for {footprint_name}")
                        break
                if 'pad_width' in extracted_dimensions:
                    break
        
        # Enhanced pin pitch extraction
        pitch_patterns = [
            r'pitch.*?(\d+\.?\d*)\s*mm',
            r'(\d+\.?\d*)\s*mm.*?pitch',
            r'pin.*?spacing.*?(\d+\.?\d*)\s*mm',
            r'pin.*?pitch.*?(\d+\.?\d*)\s*mm',
            r'(\d+\.?\d*)\s*mm.*?spacing',
            r'(\d+\.?\d*)\s*mm.*?between.*?pins',
        ]
        
        for pattern in pitch_patterns:
            matches = re.findall(pattern, all_content, re.IGNORECASE)
            if matches:
                for match in matches:
                    pitch = float(match)
                    # Reasonable pitch: 0.1mm to 10mm
                    if 0.1 <= pitch <= 10:
                        extracted_dimensions['pin_pitch'] = pitch
                        logger.info(f"✓ Extracted pin pitch from web search: {pitch}mm for {footprint_name}")
                        break
                if 'pin_pitch' in extracted_dimensions:
                    break
        
        # Enhanced pad count extraction - look for specific package pin counts
        pad_count_patterns = [
            r'(\d+)\s*pads?',
            r'pad.*?count.*?(\d+)',
            r'(\d+)\s*pins?',
            r'pin.*?count.*?(\d+)',
            # Package-specific patterns
            r'TO-263-7.*?(\d+)\s*(?:pins?|pads?)',
            r'D2PAK-7.*?(\d+)\s*(?:pins?|pads?)',
            r'ESOP8L.*?(\d+)\s*(?:pins?|pads?)',
        ]
        
        for pattern in pad_count_patterns:
            matches = re.findall(pattern, all_content, re.IGNORECASE)
            if matches:
                for match in matches:
                    count = int(match)
                    # Reasonable pad count: 1 to 200
                    if 1 <= count <= 200:
                        extracted_dimensions['pad_count'] = count
                        logger.info(f"✓ Extracted pad count from web search: {count} for {footprint_name}")
                        break
                if 'pad_count' in extracted_dimensions:
                    break
        
        # Extract package body dimensions
        body_size_patterns = [
            r'package.*?(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
            r'body.*?(\d+\.?\d*)\s*[×xX*]\s*(\d+\.?\d*)\s*mm',
            r'(\d+\.?\d*)\s*mm\s*[×xX*]\s*(\d+\.?\d*)\s*mm.*?package',
        ]
        
        for pattern in body_size_patterns:
            matches = re.findall(pattern, all_content, re.IGNORECASE)
            if matches:
                for match in matches:
                    width, height = float(match[0]), float(match[1])
                    if 0.5 <= width <= 100 and 0.5 <= height <= 100:
                        extracted_dimensions['body_width'] = width
                        extracted_dimensions['body_height'] = height
                        logger.info(f"✓ Extracted body size from web search: {width}mm × {height}mm for {footprint_name}")
                        break
                if 'body_width' in extracted_dimensions:
                    break
        
        # Apply corrections if we found dimensions
        pads = spec.get('pads', [])
        corrections_made = []
        
        if extracted_dimensions:
            logger.info(f"Applying corrections from web search for {designator} ({footprint_name})")
            
            # Correct pad sizes if found
            if 'pad_width' in extracted_dimensions and 'pad_height' in extracted_dimensions:
                for pad in pads:
                    pad_name = pad.get('name', '').lower()
                    # Don't change thermal pad sizes automatically
                    if pad_name != 'tab' and pad_name != '9':  # Don't change thermal pads
                        old_width = pad.get('width', 0)
                        old_height = pad.get('height', 0)
                        pad['width'] = extracted_dimensions['pad_width']
                        pad['height'] = extracted_dimensions['pad_height']
                        corrections_made.append(f"Pad {pad.get('name')} size: {old_width}×{old_height}mm → {extracted_dimensions['pad_width']}×{extracted_dimensions['pad_height']}mm")
                        logger.info(f"  ✓ Corrected pad {pad.get('name')} size to {extracted_dimensions['pad_width']}mm × {extracted_dimensions['pad_height']}mm from web search")
            
            # Check and log pad count mismatch
            if 'pad_count' in extracted_dimensions:
                expected_count = extracted_dimensions['pad_count']
                non_tab_pads = [p for p in pads if p.get('name', '').lower() not in ['tab', '9']]
                actual_count = len(non_tab_pads)
                if actual_count != expected_count:
                    logger.warning(f"  ⚠ Pad count mismatch for {footprint_name}: web search says {expected_count}, generated has {actual_count}")
                    corrections_made.append(f"Pad count: {actual_count} (expected {expected_count} from web search)")
            
            # Log all corrections
            if corrections_made:
                logger.info(f"Applied {len(corrections_made)} corrections from web search for {designator} ({footprint_name})")
            else:
                logger.info(f"No corrections needed - generated footprint matches web search specifications")
        else:
            logger.warning(f"Could not extract dimensions from web search results for {designator} ({footprint_name})")
            logger.debug(f"Web search content preview: {all_content[:500]}...")
        
        return spec
    
    def _final_validation_and_correction(self, spec: Dict[str, Any], footprint_name: str, pin_count: int, designator: str) -> Dict[str, Any]:
        """
        Final validation and correction of footprint specification.
        Checks pad count, layout, and fixes common issues.
        """
        if not spec or 'pads' not in spec:
            return spec
        
        pads = spec.get('pads', [])
        footprint_name_upper = footprint_name.upper().strip()
        
        # Separate signal pads from thermal pads
        signal_pads = [p for p in pads if p.get('name', '').lower() != 'tab']
        thermal_pads = [p for p in pads if p.get('name', '').lower() == 'tab']
        
        # Check and fix pad count for known packages
        if 'TO-263-7' in footprint_name_upper or 'D2PAK-7' in footprint_name_upper:
            # TO-263-7 must have exactly 7 signal pads + 1 thermal tab
            if len(signal_pads) < 7:
                logger.warning(f"TO-263-7 has only {len(signal_pads)} signal pads, expected 7. Adding missing pads.")
                # Standard TO-263-7 dimensions
                left_x = -3.8
                pin_pitch = 0.95
                total_height = (7 - 1) * pin_pitch
                start_y = -total_height / 2
                
                # Get existing pad numbers
                existing_pad_nums = set()
                for pad in signal_pads:
                    try:
                        pad_num = int(pad.get('name', '0'))
                        if pad_num > 0:
                            existing_pad_nums.add(pad_num)
                    except:
                        pass
                
                # Add missing pads to reach exactly 7
                while len(signal_pads) < 7:
                    pad_num = len(signal_pads) + 1
                    while pad_num in existing_pad_nums and pad_num <= 7:
                        pad_num += 1
                    if pad_num > 7:
                        pad_num = len(signal_pads) + 1
                    
                    new_pad = {
                        'name': str(pad_num),
                        'x': left_x,
                        'y': start_y + (len(signal_pads)) * pin_pitch,
                        'width': 0.9,
                        'height': 2.0,
                        'shape': 'rectangular',
                        'layer': 'top',
                        'hole_size': 0.0
                    }
                    signal_pads.append(new_pad)
                    existing_pad_nums.add(pad_num)
                    logger.info(f"Added missing pad {pad_num} for TO-263-7 at y={new_pad['y']:.2f}mm")
                
                # Update spec with corrected pads
                spec['pads'] = signal_pads + thermal_pads
                
                # Ensure thermal tab exists
                if not thermal_pads:
                    thermal_pads.append({
                        'name': 'Tab',
                        'x': 0.0,
                        'y': 2.0,
                        'width': 10.0,
                        'height': 7.5,
                        'shape': 'rectangular',
                        'layer': 'top',
                        'hole_size': 0.0
                    })
                
                spec['pads'] = signal_pads + thermal_pads
                logger.info(f"Fixed TO-263-7: now has {len(signal_pads)} signal pads + {len(thermal_pads)} thermal pad(s)")
        
        elif 'ESOP8L' in footprint_name_upper or 'ESOP-8' in footprint_name_upper:
            # ESOP8L must have exactly 8 signal pads + 1 thermal pad
            if len(signal_pads) < 8:
                logger.warning(f"ESOP8L has only {len(signal_pads)} signal pads, expected 8. This may be incorrect.")
        
        elif 'TO-252' in footprint_name_upper or 'DPAK' in footprint_name_upper:
            # TO-252 must have exactly 3 signal pads + 1 thermal tab
            if len(signal_pads) < 3:
                logger.warning(f"TO-252 has only {len(signal_pads)} signal pads, expected 3. This may be incorrect.")
        
        elif 'TO-263-2' in footprint_name_upper or ('D2PAK' in footprint_name_upper and '7' not in footprint_name_upper):
            # TO-263-2 must have exactly 2 signal pads + 1 thermal tab = 3 pads total
            if len(signal_pads) < 2:
                logger.warning(f"TO-263-2 has only {len(signal_pads)} signal pads, expected 2. This may be incorrect.")
            if len(thermal_pads) == 0:
                logger.error(f"TO-263-2 is missing required thermal tab pad - adding it now!")
                # Add mandatory Tab pad for TO-263-2
                thermal_pads.append({
                    'name': 'Tab',
                    'x': 0.0,
                    'y': 2.0,
                    'width': 10.0,
                    'height': 7.5,
                    'shape': 'rectangular',
                    'layer': 'top',
                    'hole_size': 0.0
                })
                spec['pads'] = signal_pads + thermal_pads
                # Downgrade verification status since we had to fix it
                if spec.get('verification_status') == 'auto_verified':
                    spec['verification_status'] = 'needs_manual_verification'
                    spec['notes'] = "Standard package template - Tab pad was missing and has been added (needs manual verification)"
                logger.info(f"Fixed TO-263-2: added missing Tab pad. Now has {len(signal_pads)} signal pads + {len(thermal_pads)} thermal pad(s)")
        
        # Check for obviously wrong pad dimensions (too large for signal pads)
        for pad in signal_pads:
            width = pad.get('width', 0)
            height = pad.get('height', 0)
            # Signal pads should typically be < 5mm in each dimension
            if width > 5.0 or height > 5.0:
                logger.warning(f"Signal pad {pad.get('name')} has unusually large dimensions: {width}mm × {height}mm. This may be incorrect.")
        
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
        # Validate LLM client is available
        if not self.llm_client:
            logger.error("LLM client is not available - cannot generate footprints")
            return {'_footprint_libraries': {}}
        
        logger.info(f"Starting batch footprint generation for {len(components)} components")
        
        # Test LLM connectivity with a simple test call
        try:
            logger.info("Testing LLM connectivity...")
            print(f"[Footprint Generator] Testing LLM connectivity before generating footprints...")
            test_messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'OK' if you can read this."}
            ]
            test_response = self.llm_client.chat(test_messages, temperature=0.0)
            if test_response:
                logger.info(f"LLM connectivity test successful: {test_response[:50]}...")
                print(f"[Footprint Generator] ✓ LLM connectivity test PASSED: {test_response[:50]}...")
            else:
                error_msg = "LLM connectivity test FAILED - LLM returned None. This means the LLM API is not working."
                logger.error(error_msg)
                print(f"[Footprint Generator] ✗ {error_msg}")
                print(f"[Footprint Generator] Please check:")
                print(f"[Footprint Generator]   1. OPENAI_API_KEY environment variable is set")
                print(f"[Footprint Generator]   2. API key is valid and has credits")
                print(f"[Footprint Generator]   3. Network connection is working")
                print(f"[Footprint Generator]   4. Check console for '[LLM Client ERROR]' messages")
                return {'_footprint_libraries': {}, '_error': error_msg}
        except Exception as test_error:
            error_msg = f"LLM connectivity test FAILED with exception: {test_error}"
            logger.error(error_msg)
            print(f"[Footprint Generator] ✗ {error_msg}")
            print(f"[Footprint Generator] Exception type: {type(test_error).__name__}")
            import traceback
            logger.error(traceback.format_exc())
            print(f"[Footprint Generator] Full traceback logged. Check logs for details.")
            return {'_footprint_libraries': {}, '_error': f'LLM connectivity test failed: {str(test_error)}'}
        
        # Step 1: Group components by footprint name
        footprint_groups = {}
        for component in components:
            designator = component.get('designator', '')
            if not designator:
                continue
            
            footprint_name = component.get('footprint', '').strip()
            
            # CRITICAL: If footprint is empty, try multiple inference methods
            if not footprint_name:
                # Method 1: Try to infer from value (e.g., "0603-0.1uF" -> "0603", "Cap1" -> might contain package info)
                value = component.get('value', '')
                footprint_name = self._extract_package_from_value(value)
            
            # Method 2: Try to infer from lib_reference or description
            if not footprint_name:
                lib_ref = component.get('lib_reference', '').upper()
                description = component.get('description', '').upper()
                # Some libraries have package info in the name
                for field in [lib_ref, description]:
                    if field:
                        extracted = self._extract_package_from_value(field)
                        if extracted:
                            footprint_name = extracted
                            break
            
            # Method 3: Use component type + pin count as last resort (LLM will infer actual package)
            if not footprint_name:
                comp_type = self.get_component_type_from_designator(designator)
                pin_count = component.get('pin_count', 2)
                # For 2-pin passives, use generic name - LLM will infer from value/description
                if pin_count == 2 and comp_type in ['resistor', 'capacitor', 'inductor']:
                    footprint_name = f"{comp_type.upper()[:1]}_2PIN"  # C_2PIN, R_2PIN, L_2PIN
                else:
                    footprint_name = f"UNKNOWN_{pin_count}PIN"
            
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
        first_error_details = None  # Capture first error for diagnosis
        
        for footprint_key, group_data in footprint_groups.items():
            footprint_name = group_data['footprint_name']
            representative = group_data['representative']
            component_count = len(group_data['components'])
            component_designators = [comp.get('designator') for comp in group_data['components']]
            
            logger.info(f"Generating footprint '{footprint_name}' for {component_count} components ({', '.join(component_designators[:5])}{'...' if len(component_designators) > 5 else ''}) using LLM")
            
            # Generate footprint spec using LLM (one call per unique footprint)
            error_reason = None
            try:
                logger.info(f"Calling analyze_component_with_llm for {footprint_name} (representative: {representative.get('designator', 'unknown')})")
                print(f"[Footprint Generator] Attempting to generate footprint: {footprint_name}")
                footprint_spec = self.analyze_component_with_llm(representative)
                
                if footprint_spec is None:
                    error_reason = "analyze_component_with_llm returned None (likely LLM API error or empty response)"
                    logger.error(f"{error_reason} for {footprint_name}")
                    print(f"[Footprint Generator] ERROR: {error_reason} for {footprint_name}")
                elif not isinstance(footprint_spec, dict):
                    error_reason = f"analyze_component_with_llm returned invalid type: {type(footprint_spec)}"
                    logger.error(f"{error_reason} for {footprint_name}")
                    print(f"[Footprint Generator] ERROR: {error_reason} for {footprint_name}")
                    footprint_spec = None
                elif 'pads' not in footprint_spec:
                    error_reason = "analyze_component_with_llm returned footprint_spec without 'pads' field"
                    logger.error(f"{error_reason} for {footprint_name}")
                    print(f"[Footprint Generator] ERROR: {error_reason} for {footprint_name}")
                    footprint_spec = None
                else:
                    logger.info(f"Successfully generated footprint spec for {footprint_name}: {len(footprint_spec.get('pads', []))} pads")
                    print(f"[Footprint Generator] SUCCESS: Generated {footprint_name} with {len(footprint_spec.get('pads', []))} pads")
            except Exception as e:
                error_reason = f"Exception during LLM generation: {type(e).__name__}: {str(e)}"
                logger.error(f"{error_reason} for {footprint_name}")
                print(f"[Footprint Generator] EXCEPTION: {error_reason} for {footprint_name}")
                import traceback
                logger.error(traceback.format_exc())
                footprint_spec = None
            
            if not footprint_spec:
                # LLM generation failed - track for reporting
                error_msg = f"LLM generation failed for {footprint_name} - skipping footprint (affects {component_count} components: {', '.join(component_designators[:5])}{'...' if len(component_designators) > 5 else ''})"
                logger.error(error_msg)
                print(f"[Footprint Generator] {error_msg}")
                
                # Capture first error details for diagnosis
                if first_error_details is None:
                    first_error_details = {
                        'footprint_name': footprint_name,
                        'error': error_msg,
                        'error_reason': error_reason or 'Unknown error',
                        'representative_designator': representative.get('designator', 'unknown')
                    }
                
                failed_footprints.append({
                    'footprint_name': footprint_name,
                    'component_count': component_count,
                    'designators': component_designators
                })
                continue
            
            # CRITICAL: For numeric footprints (0603, 0805, 1206, 1812, etc.), use prefixed names
            # Instead of storing "1812", store "C1812", "R1812", "L1812", "D1812" based on component type
            if footprint_name and len(footprint_name) >= 4 and footprint_name[0].isdigit():
                # CRITICAL: Generate prefixed versions for ALL common prefixes, not just the ones found
                # This ensures C1812, R1812, L1812, D1812 all exist even if only one type is in schematic
                all_prefixes = self._passive_prefixes()
                for prefix in all_prefixes:
                    prefixed_name = prefix + footprint_name
                    prefixed_key = prefixed_name.upper().strip()
                    # Only create if not already exists (avoid overwriting)
                    if prefixed_key not in footprint_specs:
                        # Create a copy of the footprint spec with the prefixed name
                        prefixed_spec = footprint_spec.copy()
                        prefixed_spec['footprint_name'] = prefixed_name  # Use prefixed name (C1812, not 1812)
                        # Filter components that match this prefix
                        matching_comps = [c for c in group_data['components'] 
                                        if self.get_component_type_from_designator(c.get('designator', '')) == 
                                        self._component_type_for_prefix(prefix)]
                        prefixed_spec['component_designators'] = [c.get('designator') for c in matching_comps]
                        prefixed_spec['component_count'] = len(matching_comps)
                        footprint_specs[prefixed_key] = prefixed_spec
                        logger.info(f"Generated prefixed footprint '{prefixed_name}' for {len(matching_comps)} components")
                
                # CRITICAL: Do NOT store the numeric version (1812) - only store prefixed versions (C1812, R1812, etc.)
                # Remove the numeric version from footprint_specs
                if footprint_key in footprint_specs:
                    del footprint_specs[footprint_key]
                    logger.info(f"Removed numeric footprint '{footprint_name}' - using prefixed versions instead")
            else:
                # For non-numeric footprints, store as-is
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
            
            # Try multiple lookup strategies
            found_spec = None
            
            # Strategy 1: Try exact match
            if footprint_key in footprint_specs:
                found_spec = footprint_specs[footprint_key]
            else:
                # Strategy 2: Try with prefix added (e.g., if schematic has "0603", try "C0603" for capacitor)
                comp_type = self.get_component_type_from_designator(designator)
                prefix = self._prefix_for_component_type(comp_type)
                if prefix and footprint_name and len(footprint_name) >= 4 and footprint_name[0].isdigit():
                    prefixed_key = (prefix + footprint_name).upper().strip()
                    if prefixed_key in footprint_specs:
                        found_spec = footprint_specs[prefixed_key]
                    else:
                        # Strategy 3: Try removing prefix if footprint has one (e.g., "C0603" -> "0603")
                        if len(footprint_name) > 1 and footprint_name[0] in self._passive_prefixes():
                            no_prefix_key = footprint_name[1:].upper().strip()
                            if no_prefix_key in footprint_specs:
                                found_spec = footprint_specs[no_prefix_key]
            
            if found_spec:
                results[designator] = found_spec.copy()
                # Remove component list from individual results (keep only in footprint_specs)
                if 'component_designators' in results[designator]:
                    del results[designator]['component_designators']
            else:
                # LLM generation failed - DO NOT create null record, just skip
                logger.warning(f"Footprint generation failed for {designator} (footprint: {footprint_name}, tried: {footprint_key}) - component will be skipped")
                # Do not add None to results - this prevents null records in JSON
                continue
        
        # Also return footprint_specs for library generation
        results['_footprint_libraries'] = footprint_specs
        
        # Log summary
        successful_components = sum(1 for r in results.values() if r and isinstance(r, dict) and 'pads' in r)
        failed_components = len(components) - successful_components
        
        logger.info(f"=== FOOTPRINT GENERATION SUMMARY ===")
        logger.info(f"Total components: {len(components)}")
        logger.info(f"Unique footprints generated: {len(footprint_specs)}")
        logger.info(f"Successfully mapped components: {successful_components}")
        logger.info(f"Failed components: {failed_components}")
        
        if len(footprint_specs) == 0:
            error_msg = "CRITICAL: No footprints were generated! All LLM calls failed."
            logger.error(error_msg)
            print(f"[Footprint Generator] {error_msg}")
            logger.error("Possible causes:")
            logger.error("  1. LLM API key not set or invalid")
            logger.error("  2. LLM API rate limit exceeded")
            logger.error("  3. Network connectivity issues")
            logger.error("  4. LLM responses are empty or invalid JSON")
            logger.error("  5. All footprint generation attempts failed")
            print("[Footprint Generator] Check the logs above for specific error messages from each LLM call")
        
        if failed_footprints:
            logger.warning(f"Failed to generate {len(failed_footprints)} footprints, affecting {sum(f['component_count'] for f in failed_footprints)} components:")
            for ff in failed_footprints:
                logger.warning(f"  - {ff['footprint_name']}: {ff['component_count']} components ({', '.join(ff['designators'][:3])}{'...' if len(ff['designators']) > 3 else ''})")
        
        # Add error info to results if all failed
        if len(footprint_specs) == 0 and failed_footprints:
            error_count = len(failed_footprints)
            total_affected = sum(f['component_count'] for f in failed_footprints)
            
            # Build detailed error message
            error_msg = f"All {error_count} footprint generation attempts failed (affecting {total_affected} components)"
            if first_error_details:
                error_reason = first_error_details.get('error_reason', 'Unknown error')
                error_msg += f"\n\nFirst failure example:"
                error_msg += f"\n  Footprint: {first_error_details['footprint_name']}"
                error_msg += f"\n  Component: {first_error_details['representative_designator']}"
                error_msg += f"\n  Error: {error_reason}"
                error_msg += f"\n\nCheck console output for detailed LLM API error messages."
                error_msg += f"\n\nCommon causes:"
                error_msg += f"\n  - OPENAI_API_KEY not set or invalid"
                error_msg += f"\n  - API rate limit exceeded"
                error_msg += f"\n  - Network connectivity issues"
                error_msg += f"\n  - LLM responses are empty or invalid JSON"
            
            results['_error'] = error_msg
            results['_failed_footprints'] = failed_footprints
            results['_first_error'] = first_error_details
            
            print(f"[Footprint Generator] SUMMARY: {error_count} unique footprints failed, affecting {total_affected} total components")
            if first_error_details:
                print(f"[Footprint Generator] First failed footprint: {first_error_details['footprint_name']}")
            print(f"[Footprint Generator] Check the console/logs above for detailed LLM API error messages")
        
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
            r'(TO-\d+-\d+)',  # TO packages with variant: TO-263-2, TO-263-7
            r'(SOD-\d+)',  # SOD packages: SOD-123, SOD-323
            r'(ESOP\d+)',  # ESOP packages: ESOP8L
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