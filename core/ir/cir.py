"""
Constraint Internal Representation (C-IR)
Per Architecture Spec §4.2

Models rules, constraints, and design intent.
"""
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum


class RuleType(str, Enum):
    """Design rule types"""
    CLEARANCE = "clearance"
    TRACE_WIDTH = "traceWidth"
    VIA = "via"
    DIFFERENTIAL_PAIR = "differentialPair"
    LENGTH_BUDGET = "lengthBudget"
    RETURN_PATH = "returnPath"
    CROSSTALK = "crosstalk"


class RuleScope(BaseModel):
    """Rule scope definition"""
    nets: Optional[List[str]] = Field(None, description="List of net IDs this rule applies to")
    netclass: Optional[str] = Field(None, description="Net class name this rule applies to")
    components: Optional[List[str]] = Field(None, description="List of component refs this rule applies to")
    layers: Optional[List[str]] = Field(None, description="List of layer IDs this rule applies to")


class RuleParams(BaseModel):
    """Rule parameters (varies by rule type)"""
    # Clearance rule
    min_clearance_mm: Optional[float] = Field(None, description="Minimum clearance in mm")
    
    # Trace width rule
    min_width_mm: Optional[float] = Field(None, description="Minimum trace width in mm")
    preferred_width_mm: Optional[float] = Field(None, description="Preferred trace width in mm")
    max_width_mm: Optional[float] = Field(None, description="Maximum trace width in mm")
    
    # Via rule
    min_drill_mm: Optional[float] = Field(None, description="Minimum via drill diameter in mm")
    max_drill_mm: Optional[float] = Field(None, description="Maximum via drill diameter in mm")
    
    # Differential pair
    pair_gap_mm: Optional[float] = Field(None, description="Differential pair gap in mm")
    max_skew_ps: Optional[float] = Field(None, description="Maximum skew in picoseconds")
    
    # Length budget
    target_length_mm: Optional[float] = Field(None, description="Target length in mm")
    max_delta_mm: Optional[float] = Field(None, description="Maximum length delta in mm")
    
    # Return path
    forbid_split_plane_crossing: Optional[bool] = Field(None, description="Forbid crossing plane splits")
    min_plane_continuity_mm: Optional[float] = Field(None, description="Minimum plane continuity in mm")
    
    # Crosstalk
    min_spacing_mm: Optional[float] = Field(None, description="Minimum spacing to avoid crosstalk in mm")
    max_coupling_coeff: Optional[float] = Field(None, description="Maximum coupling coefficient")
    
    # Engine-specific extensions
    extensions: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Engine-specific parameters")


class Rule(BaseModel):
    """
    Design rule definition
    Per Architecture Spec §4.2.1
    """
    id: str = Field(..., description="Unique rule identifier")
    type: RuleType = Field(..., description="Rule type")
    scope: RuleScope = Field(..., description="Rule scope (which nets/components/layers)")
    params: RuleParams = Field(..., description="Rule parameters")
    enabled: bool = Field(default=True, description="Whether this rule is enabled")
    priority: int = Field(default=0, description="Rule priority (higher = more important)")


class NetclassDefaults(BaseModel):
    """Default values for a net class"""
    trace_width_mm: Optional[float] = Field(None, description="Default trace width in mm")
    clearance_mm: Optional[float] = Field(None, description="Default clearance in mm")
    via_size_mm: Optional[float] = Field(None, description="Default via size in mm")


class Netclass(BaseModel):
    """
    Net class definition
    Per Architecture Spec §4.2.1
    """
    id: str = Field(..., description="Unique net class identifier")
    name: str = Field(..., description="Net class name (e.g., 'Power', 'HighSpeed')")
    nets: List[str] = Field(default_factory=list, description="List of net IDs in this class")
    defaults: NetclassDefaults = Field(default_factory=NetclassDefaults, description="Default values for this net class")


class ConstraintIR(BaseModel):
    """
    Complete Constraint Internal Representation
    Per Architecture Spec §4.2
    """
    rules: List[Rule] = Field(default_factory=list, description="List of design rules")
    netclasses: List[Netclass] = Field(default_factory=list, description="List of net classes")

    class Config:
        json_schema_extra = {
            "example": {
                "rules": [
                    {
                        "id": "rule-clearance-1",
                        "type": "clearance",
                        "scope": {"nets": ["net-gnd", "net-vcc"]},
                        "params": {"min_clearance_mm": 0.15},
                        "enabled": True,
                        "priority": 0
                    },
                    {
                        "id": "rule-width-1",
                        "type": "traceWidth",
                        "scope": {"netclass": "power"},
                        "params": {
                            "min_width_mm": 0.25,
                            "preferred_width_mm": 0.3
                        },
                        "enabled": True,
                        "priority": 0
                    }
                ],
                "netclasses": [
                    {
                        "id": "nc-power",
                        "name": "Power",
                        "nets": ["net-vcc"],
                        "defaults": {
                            "trace_width_mm": 0.3,
                            "clearance_mm": 0.2
                        }
                    }
                ]
            }
        }
