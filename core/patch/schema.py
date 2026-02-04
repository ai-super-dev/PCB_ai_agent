"""
Patch Schema
Per Architecture Spec §6.1

Patches are append-only diffs describing artifact transformation.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class PatchMeta(BaseModel):
    """Patch metadata"""
    author: str = Field(..., description="User or agent ID that created the patch")
    source: str = Field(..., description="Source: 'canvas', 'agent', 'engineSync', 'user'")
    explain: Optional[str] = Field(None, description="Explanation of the patch (for AI patches)")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Creation timestamp")


class PatchOp(BaseModel):
    """
    Patch operation
    
    Operations can be:
    - "replace": Replace value at path
    - "add": Add new element
    - "remove": Remove element
    - Specific op types: "MoveComponent", "AddTrackSegment", etc.
    """
    op: str = Field(..., description="Operation type")
    path: Optional[str] = Field(None, description="JSON pointer path (e.g., '/tracks/0/segments/0/to')")
    value: Optional[Any] = Field(None, description="New value (for replace operations)")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Operation-specific payload")


class Patch(BaseModel):
    """
    Patch structure
    Per Architecture Spec §6.1
    
    Patches transform artifacts from one version to another.
    """
    artifact_id: str = Field(..., description="Target artifact ID")
    from_version: int = Field(..., description="Source version (must match artifact current version)")
    to_version: int = Field(..., description="Target version (must be from_version + 1)")
    ops: List[PatchOp] = Field(default_factory=list, description="List of patch operations")
    meta: PatchMeta = Field(..., description="Patch metadata")

    def validate_version_consistency(self):
        """Validate that to_version = from_version + 1"""
        if self.to_version != self.from_version + 1:
            raise ValueError(
                f"Version inconsistency: to_version ({self.to_version}) must be from_version + 1 ({self.from_version + 1})"
            )

    class Config:
        json_schema_extra = {
            "example": {
                "artifact_id": "550e8400-e29b-41d4-a716-446655440000",
                "from_version": 3,
                "to_version": 4,
                "ops": [
                    {
                        "op": "replace",
                        "path": "/tracks/0/segments/0/to",
                        "value": [32.0, 10.0]
                    }
                ],
                "meta": {
                    "author": "user-123",
                    "source": "agent",
                    "explain": "AI: improved clearance and reduced skew",
                    "created_at": "2025-12-21T10:00:00Z"
                }
            }
        }
