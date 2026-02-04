"""
Patch Operations
Per Architecture Spec §6.2

MVP Patch Types:
- MoveComponent
- MoveTrackSegment
- AddTrackSegment
- DeleteTrackSegment
- AddVia
- DeleteVia
- RegionReroute
- UpdateNetclassWidth
- UpdateClearanceParam
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class MoveComponentOp(BaseModel):
    """
    MoveComponent patch operation
    Moves a component to a new position and/or rotation
    """
    op: str = Field(default="MoveComponent", description="Operation type")
    component_ref: str = Field(..., description="Component reference designator (e.g., 'U1', 'R1')")
    new_position_mm: List[float] = Field(..., description="New position [x, y] in mm")
    new_rotation_deg: Optional[float] = Field(None, description="New rotation in degrees (optional)")
    layer: Optional[str] = Field(None, description="New layer (optional)")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        return {
            "op": self.op,
            "path": f"/footprints/{self._find_footprint_index()}",
            "payload": {
                "component_ref": self.component_ref,
                "new_position_mm": self.new_position_mm,
                "new_rotation_deg": self.new_rotation_deg,
                "layer": self.layer
            }
        }
    
    def _find_footprint_index(self) -> str:
        """Find footprint index (simplified - would need artifact context)"""
        # In real implementation, would search artifact for component
        return "0"  # Placeholder


class MoveTrackSegmentOp(BaseModel):
    """
    MoveTrackSegment patch operation
    Moves a track segment endpoint
    """
    op: str = Field(default="MoveTrackSegment", description="Operation type")
    track_id: str = Field(..., description="Track ID")
    segment_index: int = Field(..., description="Segment index within track")
    new_to_pos: Optional[List[float]] = Field(None, description="New 'to' position [x, y] in mm")
    new_from_pos: Optional[List[float]] = Field(None, description="New 'from' position [x, y] in mm")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        return {
            "op": self.op,
            "path": f"/tracks/{self._find_track_index()}/segments/{self.segment_index}",
            "payload": {
                "track_id": self.track_id,
                "segment_index": self.segment_index,
                "new_to_pos": self.new_to_pos,
                "new_from_pos": self.new_from_pos
            }
        }
    
    def _find_track_index(self) -> str:
        """Find track index (simplified)"""
        return "0"  # Placeholder


class AddTrackSegmentOp(BaseModel):
    """
    AddTrackSegment patch operation
    Adds a new track segment
    """
    op: str = Field(default="AddTrackSegment", description="Operation type")
    track_id: Optional[str] = Field(None, description="Existing track ID (if adding to existing track)")
    net_id: str = Field(..., description="Net ID this track belongs to")
    layer_id: str = Field(..., description="Layer ID")
    from_pos: List[float] = Field(..., description="Start position [x, y] in mm")
    to_pos: List[float] = Field(..., description="End position [x, y] in mm")
    width_mm: float = Field(..., description="Track width in mm")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        if self.track_id:
            # Add segment to existing track
            return {
                "op": self.op,
                "path": f"/tracks/{self._find_track_index()}/segments",
                "value": {
                    "from_pos": self.from_pos,
                    "to_pos": self.to_pos,
                    "width_mm": self.width_mm
                },
                "payload": {
                    "track_id": self.track_id,
                    "net_id": self.net_id,
                    "layer_id": self.layer_id
                }
            }
        else:
            # Create new track
            return {
                "op": self.op,
                "path": "/tracks",
                "value": {
                    "id": f"trk-new-{hash(str(self.from_pos))}",
                    "net_id": self.net_id,
                    "layer_id": self.layer_id,
                    "segments": [{
                        "from_pos": self.from_pos,
                        "to_pos": self.to_pos,
                        "width_mm": self.width_mm
                    }]
                },
                "payload": {
                    "net_id": self.net_id,
                    "layer_id": self.layer_id
                }
            }
    
    def _find_track_index(self) -> str:
        """Find track index (simplified)"""
        return "0"  # Placeholder


class DeleteTrackSegmentOp(BaseModel):
    """
    DeleteTrackSegment patch operation
    Removes a track segment (or entire track if last segment)
    """
    op: str = Field(default="DeleteTrackSegment", description="Operation type")
    track_id: str = Field(..., description="Track ID")
    segment_index: Optional[int] = Field(None, description="Segment index (None = delete entire track)")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        if self.segment_index is not None:
            return {
                "op": self.op,
                "path": f"/tracks/{self._find_track_index()}/segments/{self.segment_index}",
                "payload": {
                    "track_id": self.track_id,
                    "segment_index": self.segment_index
                }
            }
        else:
            return {
                "op": self.op,
                "path": f"/tracks/{self._find_track_index()}",
                "payload": {
                    "track_id": self.track_id
                }
            }
    
    def _find_track_index(self) -> str:
        """Find track index (simplified)"""
        return "0"  # Placeholder


class AddViaOp(BaseModel):
    """
    AddVia patch operation
    Adds a via at a position
    """
    op: str = Field(default="AddVia", description="Operation type")
    net_id: str = Field(..., description="Net ID")
    position: List[float] = Field(..., description="Via position [x, y] in mm")
    drill_mm: float = Field(..., description="Drill diameter in mm")
    layers: List[str] = Field(..., description="Layer IDs this via connects")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        return {
            "op": self.op,
            "path": "/vias",
            "value": {
                "id": f"via-new-{hash(str(self.position))}",
                "net_id": self.net_id,
                "position": self.position,
                "drill_mm": self.drill_mm,
                "layers": self.layers
            },
            "payload": {
                "net_id": self.net_id,
                "position": self.position
            }
        }


class DeleteViaOp(BaseModel):
    """
    DeleteVia patch operation
    Removes a via
    """
    op: str = Field(default="DeleteVia", description="Operation type")
    via_id: str = Field(..., description="Via ID")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        return {
            "op": self.op,
            "path": f"/vias/{self._find_via_index()}",
            "payload": {
                "via_id": self.via_id
            }
        }
    
    def _find_via_index(self) -> str:
        """Find via index (simplified)"""
        return "0"  # Placeholder


class RegionRerouteOp(BaseModel):
    """
    RegionReroute patch operation
    Reroutes a region (simplified: list of track changes)
    """
    op: str = Field(default="RegionReroute", description="Operation type")
    region_bbox: List[float] = Field(..., description="Region bounding box [x1, y1, x2, y2]")
    track_changes: List[Dict[str, Any]] = Field(..., description="List of track modifications")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        return {
            "op": self.op,
            "path": "/tracks",
            "payload": {
                "region_bbox": self.region_bbox,
                "track_changes": self.track_changes
            }
        }


class UpdateNetclassWidthOp(BaseModel):
    """
    UpdateNetclassWidth patch operation
    Updates trace width for a net class
    """
    op: str = Field(default="UpdateNetclassWidth", description="Operation type")
    netclass_id: str = Field(..., description="Net class ID")
    new_width_mm: float = Field(..., description="New trace width in mm")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        return {
            "op": self.op,
            "path": f"/netclasses/{self._find_netclass_index()}/defaults/trace_width_mm",
            "value": self.new_width_mm,
            "payload": {
                "netclass_id": self.netclass_id,
                "new_width_mm": self.new_width_mm
            }
        }
    
    def _find_netclass_index(self) -> str:
        """Find netclass index (simplified)"""
        return "0"  # Placeholder


class UpdateClearanceParamOp(BaseModel):
    """
    UpdateClearanceParam patch operation
    Updates clearance parameter for a rule
    """
    op: str = Field(default="UpdateClearanceParam", description="Operation type")
    rule_id: str = Field(..., description="Rule ID")
    new_clearance_mm: float = Field(..., description="New clearance in mm")

    def to_patch_op(self) -> Dict[str, Any]:
        """Convert to PatchOp format"""
        return {
            "op": self.op,
            "path": f"/rules/{self._find_rule_index()}/params/min_clearance_mm",
            "value": self.new_clearance_mm,
            "payload": {
                "rule_id": self.rule_id,
                "new_clearance_mm": self.new_clearance_mm
            }
        }
    
    def _find_rule_index(self) -> str:
        """Find rule index (simplified)"""
        return "0"  # Placeholder
