"""
Patch module
Per Architecture Spec §6

Patches are versioned diffs that transform artifact state.
"""
from .schema import Patch, PatchOp, PatchMeta
from .operations import (
    MoveComponentOp, MoveTrackSegmentOp, AddTrackSegmentOp, DeleteTrackSegmentOp,
    AddViaOp, DeleteViaOp, RegionRerouteOp, UpdateNetclassWidthOp, UpdateClearanceParamOp
)

__all__ = [
    'Patch', 'PatchOp', 'PatchMeta',
    'MoveComponentOp', 'MoveTrackSegmentOp', 'AddTrackSegmentOp', 'DeleteTrackSegmentOp',
    'AddViaOp', 'DeleteViaOp', 'RegionRerouteOp', 'UpdateNetclassWidthOp', 'UpdateClearanceParamOp'
]
