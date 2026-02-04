"""
Artifact models
Per Architecture Spec §3.2

Artifacts are versioned objects stored in the canonical artifact graph.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
import uuid
from datetime import datetime


class ArtifactType(str, Enum):
    """Artifact types per Spec §3.1"""
    PCB_BOARD = "pcb.board"
    PCB_SCHEMATIC = "pcb.schematic"
    PCB_FOOTPRINT = "pcb.footprint"
    CONSTRAINT_RULESET = "constraint.ruleSet"
    CONSTRAINT_HS_RULES = "constraint.hsRules"
    CONSTRAINT_VIOLATIONS = "constraint.violations"
    AI_SUGGESTION_PATCH = "ai.suggestion.patch"
    AI_INTENT = "ai.intent"
    ECO_CHANGESET = "eco.changeSet"
    LIBRARY_PART = "library.part"
    UI_VIEWSTATE = "ui.viewState"
    EXECUTION_RUN = "execution.run"
    EXECUTION_RESULT = "execution.result"
    USER_OVERRIDE = "user.override"


class SourceEngine(str, Enum):
    """Source engine types"""
    ALTIUM = "altium"
    CADENCE = "cadence"
    KICAD = "kicad"
    INTERNAL = "internal"


class CreatedBy(str, Enum):
    """Who created the artifact"""
    USER = "user"
    AGENT = "agent"
    ENGINE = "engine"


class ArtifactRelation(BaseModel):
    """Relation between artifacts"""
    role: str = Field(..., description="Relation role (e.g., 'uses', 'contains')")
    target_id: str = Field(..., description="Target artifact ID")


class ArtifactMeta(BaseModel):
    """Artifact metadata"""
    source_engine: Optional[SourceEngine] = Field(None, description="Source engine")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Creation timestamp (ISO8601)")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="Update timestamp (ISO8601)")
    created_by: CreatedBy = Field(default=CreatedBy.USER, description="Who created this artifact")
    tags: List[str] = Field(default_factory=list, description="Optional tags")


class Artifact(BaseModel):
    """
    Artifact structure
    Per Architecture Spec §3.2
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique artifact identifier (UUID)")
    type: ArtifactType = Field(..., description="Artifact type")
    version: int = Field(default=1, description="Artifact version (monotonic increment)")
    relations: List[ArtifactRelation] = Field(default_factory=list, description="Relations to other artifacts")
    data: Dict[str, Any] = Field(default_factory=dict, description="Artifact data (G-IR, C-IR, etc.)")
    meta: ArtifactMeta = Field(default_factory=ArtifactMeta, description="Artifact metadata")

    def increment_version(self) -> 'Artifact':
        """Create a new version of this artifact"""
        new_artifact = self.model_copy(deep=True)
        new_artifact.version += 1
        new_artifact.meta.updated_at = datetime.utcnow().isoformat()
        return new_artifact

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "type": "pcb.board",
                "version": 1,
                "relations": [
                    {"role": "uses", "target_id": "constraint-ruleset-id"}
                ],
                "data": {
                    "board": {
                        "outline": {"polygon": [[0, 0], [100, 0], [100, 80], [0, 80]]},
                        "layers": [
                            {"id": "L1", "name": "Top", "kind": "signal", "index": 1}
                        ],
                        "stackup": {
                            "layers": ["L1"],
                            "thickness_mm": 1.6,
                            "dielectrics": []
                        }
                    },
                    "nets": [],
                    "tracks": [],
                    "vias": [],
                    "footprints": []
                },
                "meta": {
                    "source_engine": "altium",
                    "created_at": "2025-12-21T10:00:00Z",
                    "updated_at": "2025-12-21T10:00:00Z",
                    "created_by": "user",
                    "tags": []
                }
            }
        }
