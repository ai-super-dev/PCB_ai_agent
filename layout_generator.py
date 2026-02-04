"""
Layout Generator - Autonomous PCB Layout Generation

This module generates actual PCB layouts from schematic data:
- Converts functional blocks to board zones
- Calculates component coordinates
- Generates placement commands
- Creates design constraints

This is the core intelligence that enables autonomous layout generation.
"""
import json
import math
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class BoardZone(Enum):
    """Board placement zones"""
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    CENTER_LEFT = "center_left"
    CENTER = "center"
    CENTER_RIGHT = "center_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"
    LEFT_EDGE = "left_edge"
    RIGHT_EDGE = "right_edge"
    TOP_EDGE = "top_edge"
    BOTTOM_EDGE = "bottom_edge"


class BlockType(Enum):
    """Functional block types"""
    POWER_SUPPLY = "power"
    MCU = "mcu"
    FPGA = "fpga"
    MEMORY = "memory"
    INTERFACE = "interface"
    ANALOG = "analog"
    PROTECTION = "protection"
    TIMING = "timing"
    CONNECTOR = "connector"
    LED_DISPLAY = "display"
    SENSOR = "sensor"
    PASSIVE = "passive"
    OTHER = "other"


@dataclass
class ComponentPlacement:
    """Represents a component placement"""
    designator: str
    x: float  # mm
    y: float  # mm
    rotation: float  # degrees
    layer: str  # "Top" or "Bottom"
    block_name: str
    priority: int


@dataclass
class DesignConstraint:
    """Represents a design constraint/rule"""
    name: str
    rule_type: str  # clearance, width, via, etc.
    value: float
    unit: str
    scope: str  # net class, component, global
    description: str


class LayoutGenerator:
    """
    Generates PCB layouts from schematic analysis.
    
    Flow:
    1. Analyze schematic → Identify functional blocks
    2. Define board zones → Assign blocks to zones
    3. Calculate positions → Generate X,Y for each component
    4. Generate constraints → Create design rules
    5. Output commands → Ready for Altium execution
    """
    
    def __init__(self, board_width: float = 100.0, board_height: float = 80.0):
        """
        Initialize layout generator.
        
        Args:
            board_width: Board width in mm
            board_height: Board height in mm
        """
        self.board_width = board_width
        self.board_height = board_height
        self.margin = 5.0  # Edge margin in mm
        self.component_spacing = 2.0  # Min spacing between components
        self.placements: List[ComponentPlacement] = []
        self.constraints: List[DesignConstraint] = []
        self.functional_blocks: Dict[str, List[str]] = {}
        
        # Zone priorities for different block types
        self.zone_assignments = {
            BlockType.POWER_SUPPLY: BoardZone.BOTTOM_LEFT,
            BlockType.MCU: BoardZone.CENTER,
            BlockType.FPGA: BoardZone.CENTER,
            BlockType.MEMORY: BoardZone.CENTER_RIGHT,
            BlockType.INTERFACE: BoardZone.RIGHT_EDGE,
            BlockType.ANALOG: BoardZone.TOP_LEFT,
            BlockType.PROTECTION: BoardZone.LEFT_EDGE,
            BlockType.TIMING: BoardZone.CENTER,  # Near MCU
            BlockType.CONNECTOR: BoardZone.BOTTOM_EDGE,
            BlockType.LED_DISPLAY: BoardZone.TOP_EDGE,
            BlockType.SENSOR: BoardZone.TOP_RIGHT,
            BlockType.PASSIVE: BoardZone.CENTER,  # Distributed
            BlockType.OTHER: BoardZone.CENTER,
        }
    
    def set_board_size(self, width: float, height: float):
        """Set board dimensions"""
        self.board_width = width
        self.board_height = height
    
    def get_zone_bounds(self, zone: BoardZone) -> Tuple[float, float, float, float]:
        """
        Get the bounding box for a board zone.
        Returns (x_min, y_min, x_max, y_max) in mm.
        """
        w = self.board_width
        h = self.board_height
        m = self.margin
        
        # Divide board into 3x3 grid + edges
        third_w = (w - 2 * m) / 3
        third_h = (h - 2 * m) / 3
        
        zone_bounds = {
            BoardZone.TOP_LEFT: (m, h - m - third_h, m + third_w, h - m),
            BoardZone.TOP_CENTER: (m + third_w, h - m - third_h, m + 2*third_w, h - m),
            BoardZone.TOP_RIGHT: (m + 2*third_w, h - m - third_h, w - m, h - m),
            BoardZone.CENTER_LEFT: (m, m + third_h, m + third_w, h - m - third_h),
            BoardZone.CENTER: (m + third_w, m + third_h, m + 2*third_w, h - m - third_h),
            BoardZone.CENTER_RIGHT: (m + 2*third_w, m + third_h, w - m, h - m - third_h),
            BoardZone.BOTTOM_LEFT: (m, m, m + third_w, m + third_h),
            BoardZone.BOTTOM_CENTER: (m + third_w, m, m + 2*third_w, m + third_h),
            BoardZone.BOTTOM_RIGHT: (m + 2*third_w, m, w - m, m + third_h),
            BoardZone.LEFT_EDGE: (m, m, m + 10, h - m),
            BoardZone.RIGHT_EDGE: (w - m - 10, m, w - m, h - m),
            BoardZone.TOP_EDGE: (m, h - m - 10, w - m, h - m),
            BoardZone.BOTTOM_EDGE: (m, m, w - m, m + 10),
        }
        
        return zone_bounds.get(zone, (m, m, w - m, h - m))
    
    def classify_component(self, designator: str, value: str = "", 
                          description: str = "", footprint: str = "") -> BlockType:
        """
        Classify a component into a functional block type.
        """
        designator_upper = designator.upper()
        value_upper = value.upper()
        desc_upper = description.upper()
        
        # Check designator prefix
        if designator_upper.startswith("U"):
            # IC - need to determine type
            if any(x in desc_upper for x in ["STM32", "ATMEGA", "PIC", "ESP", "NRF", "MSP"]):
                return BlockType.MCU
            elif any(x in desc_upper for x in ["FPGA", "CPLD", "SPARTAN", "CYCLONE"]):
                return BlockType.FPGA
            elif any(x in desc_upper for x in ["FLASH", "EEPROM", "SRAM", "SDRAM"]):
                return BlockType.MEMORY
            elif any(x in desc_upper for x in ["LDO", "REGULATOR", "BUCK", "BOOST", "DC-DC"]):
                return BlockType.POWER_SUPPLY
            elif any(x in desc_upper for x in ["USB", "UART", "RS485", "CAN", "ETH"]):
                return BlockType.INTERFACE
            elif any(x in desc_upper for x in ["OPAMP", "ADC", "DAC", "COMPARATOR"]):
                return BlockType.ANALOG
            elif any(x in desc_upper for x in ["ESD", "TVS", "PROTECTION"]):
                return BlockType.PROTECTION
            else:
                return BlockType.OTHER
        
        elif designator_upper.startswith("J") or designator_upper.startswith("P"):
            return BlockType.CONNECTOR
        
        elif designator_upper.startswith("Y") or designator_upper.startswith("X"):
            return BlockType.TIMING
        
        elif designator_upper.startswith("D"):
            if "LED" in desc_upper:
                return BlockType.LED_DISPLAY
            else:
                return BlockType.PROTECTION
        
        elif designator_upper.startswith("L"):
            # Inductors - often power or analog
            if any(x in value_upper for x in ["UH", "MH"]):
                return BlockType.POWER_SUPPLY
            return BlockType.ANALOG
        
        elif designator_upper.startswith(("R", "C")):
            return BlockType.PASSIVE
        
        elif designator_upper.startswith("Q"):
            return BlockType.ANALOG
        
        elif designator_upper.startswith("F"):
            return BlockType.PROTECTION
        
        else:
            return BlockType.OTHER
    
    def estimate_component_size(self, designator: str, footprint: str = "") -> Tuple[float, float]:
        """
        Estimate component size (width, height) in mm based on footprint.
        Returns conservative estimates for placement.
        """
        footprint_upper = footprint.upper()
        designator_upper = designator.upper()
        
        # Common footprint sizes
        if "0402" in footprint_upper:
            return (1.0, 0.5)
        elif "0603" in footprint_upper:
            return (1.6, 0.8)
        elif "0805" in footprint_upper:
            return (2.0, 1.25)
        elif "1206" in footprint_upper:
            return (3.2, 1.6)
        elif "SOT23" in footprint_upper or "SOT-23" in footprint_upper:
            return (3.0, 1.5)
        elif "SOIC" in footprint_upper or "SOP" in footprint_upper:
            return (5.0, 4.0)
        elif "QFP" in footprint_upper or "TQFP" in footprint_upper:
            return (12.0, 12.0)
        elif "QFN" in footprint_upper:
            return (5.0, 5.0)
        elif "BGA" in footprint_upper:
            return (15.0, 15.0)
        elif "DIP" in footprint_upper:
            return (20.0, 8.0)
        
        # Estimate by designator type
        if designator_upper.startswith("U"):
            return (8.0, 8.0)  # Default IC size
        elif designator_upper.startswith("J"):
            return (15.0, 5.0)  # Connector
        elif designator_upper.startswith("Y"):
            return (5.0, 2.0)  # Crystal
        elif designator_upper.startswith(("R", "C")):
            return (2.0, 1.0)  # Default passive
        elif designator_upper.startswith("L"):
            return (4.0, 4.0)  # Inductor
        else:
            return (3.0, 3.0)  # Default
    
    def generate_layout(self, components: List[Dict], 
                       functional_blocks: List[Dict] = None) -> List[ComponentPlacement]:
        """
        Generate component placements from schematic data.
        
        Args:
            components: List of component dicts with designator, value, footprint, etc.
            functional_blocks: Optional pre-analyzed functional blocks
            
        Returns:
            List of ComponentPlacement objects with X,Y coordinates
        """
        self.placements = []
        
        # Group components by functional block type
        component_groups: Dict[BlockType, List[Dict]] = {bt: [] for bt in BlockType}
        
        for comp in components:
            designator = comp.get("designator", "")
            value = comp.get("value", "")
            description = comp.get("description", "")
            footprint = comp.get("footprint", "")
            
            block_type = self.classify_component(designator, value, description, footprint)
            component_groups[block_type].append(comp)
        
        # Place components by zone
        placement_priority = 0
        
        for block_type, comps in component_groups.items():
            if not comps:
                continue
            
            zone = self.zone_assignments.get(block_type, BoardZone.CENTER)
            x_min, y_min, x_max, y_max = self.get_zone_bounds(zone)
            
            # Calculate grid for this zone
            zone_width = x_max - x_min
            zone_height = y_max - y_min
            
            # Place components in a grid within the zone
            current_x = x_min + self.component_spacing
            current_y = y_max - self.component_spacing
            max_row_height = 0
            
            for comp in comps:
                designator = comp.get("designator", "")
                footprint = comp.get("footprint", "")
                comp_w, comp_h = self.estimate_component_size(designator, footprint)
                
                # Check if we need to move to next row
                if current_x + comp_w > x_max - self.component_spacing:
                    current_x = x_min + self.component_spacing
                    current_y -= max_row_height + self.component_spacing
                    max_row_height = 0
                
                # Check if we're out of zone (overflow to next available space)
                if current_y - comp_h < y_min:
                    current_y = y_max - self.component_spacing
                    # Could expand to adjacent zone, for now just continue
                
                placement = ComponentPlacement(
                    designator=designator,
                    x=round(current_x + comp_w / 2, 2),  # Center point
                    y=round(current_y - comp_h / 2, 2),
                    rotation=0,
                    layer="Top",
                    block_name=block_type.value,
                    priority=placement_priority
                )
                self.placements.append(placement)
                
                current_x += comp_w + self.component_spacing
                max_row_height = max(max_row_height, comp_h)
                placement_priority += 1
        
        return self.placements
    
    def generate_placement_commands(self) -> List[Dict[str, Any]]:
        """
        Convert placements to Altium command format.
        Returns list of commands ready for execution.
        """
        commands = []
        
        for placement in self.placements:
            commands.append({
                "command": "move_component",
                "parameters": {
                    "designator": placement.designator,
                    "x": placement.x,
                    "y": placement.y,
                    "rotation": placement.rotation,
                    "layer": placement.layer
                },
                "priority": placement.priority,
                "block": placement.block_name
            })
        
        return commands
    
    def generate_constraints(self, signal_analysis: Dict = None) -> List[DesignConstraint]:
        """
        Generate design constraints based on component types and signals.
        """
        self.constraints = []
        
        # Default constraints
        self.constraints.append(DesignConstraint(
            name="Default_Clearance",
            rule_type="clearance",
            value=0.2,
            unit="mm",
            scope="global",
            description="Minimum clearance between conductors"
        ))
        
        self.constraints.append(DesignConstraint(
            name="Default_Track_Width",
            rule_type="width",
            value=0.25,
            unit="mm",
            scope="global",
            description="Default track width"
        ))
        
        self.constraints.append(DesignConstraint(
            name="Power_Track_Width",
            rule_type="width",
            value=0.5,
            unit="mm",
            scope="net_class:Power",
            description="Power track width"
        ))
        
        self.constraints.append(DesignConstraint(
            name="Ground_Track_Width",
            rule_type="width",
            value=0.5,
            unit="mm",
            scope="net_class:Ground",
            description="Ground track width"
        ))
        
        # High-speed constraints if detected
        if signal_analysis and signal_analysis.get("high_speed_nets"):
            self.constraints.append(DesignConstraint(
                name="HighSpeed_Clearance",
                rule_type="clearance",
                value=0.3,
                unit="mm",
                scope="net_class:HighSpeed",
                description="High-speed signal clearance"
            ))
            
            self.constraints.append(DesignConstraint(
                name="HighSpeed_Track_Width",
                rule_type="width",
                value=0.2,
                unit="mm",
                scope="net_class:HighSpeed",
                description="High-speed controlled impedance width"
            ))
        
        # Differential pair constraints
        if signal_analysis and signal_analysis.get("differential_pairs"):
            self.constraints.append(DesignConstraint(
                name="DiffPair_Gap",
                rule_type="differential_gap",
                value=0.15,
                unit="mm",
                scope="net_class:DiffPair",
                description="Differential pair gap"
            ))
        
        return self.constraints
    
    def get_placement_summary(self) -> Dict[str, Any]:
        """Get summary of generated placements"""
        summary = {
            "total_components": len(self.placements),
            "by_block": {},
            "board_size": {
                "width_mm": self.board_width,
                "height_mm": self.board_height
            },
            "constraints_count": len(self.constraints)
        }
        
        for placement in self.placements:
            block = placement.block_name
            summary["by_block"][block] = summary["by_block"].get(block, 0) + 1
        
        return summary
    
    def export_to_json(self) -> str:
        """Export placements and constraints to JSON"""
        data = {
            "board": {
                "width_mm": self.board_width,
                "height_mm": self.board_height
            },
            "placements": [
                {
                    "designator": p.designator,
                    "x": p.x,
                    "y": p.y,
                    "rotation": p.rotation,
                    "layer": p.layer,
                    "block": p.block_name
                }
                for p in self.placements
            ],
            "constraints": [
                {
                    "name": c.name,
                    "type": c.rule_type,
                    "value": c.value,
                    "unit": c.unit,
                    "scope": c.scope,
                    "description": c.description
                }
                for c in self.constraints
            ]
        }
        return json.dumps(data, indent=2)


# Convenience function
def generate_layout_from_schematic(schematic_data: Dict, 
                                   board_width: float = 100.0,
                                   board_height: float = 80.0) -> Dict[str, Any]:
    """
    Generate a complete layout from schematic data.
    
    Args:
        schematic_data: Schematic data with components, nets, etc.
        board_width: Board width in mm
        board_height: Board height in mm
        
    Returns:
        Dict with placements, commands, and constraints
    """
    generator = LayoutGenerator(board_width, board_height)
    
    components = schematic_data.get("components", [])
    generator.generate_layout(components)
    generator.generate_constraints(schematic_data.get("signal_analysis"))
    
    return {
        "placements": generator.placements,
        "commands": generator.generate_placement_commands(),
        "constraints": generator.constraints,
        "summary": generator.get_placement_summary(),
        "json": generator.export_to_json()
    }

