"""
Artifact Store
File-based artifact storage with versioning
Per Architecture Spec §3.3

For MVP: Simple file-based storage (one JSON file per artifact)
Future: Can migrate to PostgreSQL or other database
"""
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from .models import Artifact, ArtifactType


class ArtifactStore:
    """
    File-based artifact store
    
    Storage structure:
    artifacts/
      {artifact_id}/
        v1.json
        v2.json
        ...
        current.json  # Latest version
        index.json    # Metadata
    """
    
    def __init__(self, base_path: str = "artifacts"):
        """
        Initialize artifact store
        
        Args:
            base_path: Base directory for artifact storage
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def _get_artifact_dir(self, artifact_id: str) -> Path:
        """Get directory for a specific artifact"""
        return self.base_path / artifact_id
    
    def _get_version_file(self, artifact_id: str, version: int) -> Path:
        """Get file path for a specific version"""
        artifact_dir = self._get_artifact_dir(artifact_id)
        return artifact_dir / f"v{version}.json"
    
    def _get_current_file(self, artifact_id: str) -> Path:
        """Get file path for current version"""
        artifact_dir = self._get_artifact_dir(artifact_id)
        return artifact_dir / "current.json"
    
    def _get_index_file(self, artifact_id: str) -> Path:
        """Get index file path"""
        artifact_dir = self._get_artifact_dir(artifact_id)
        return artifact_dir / "index.json"
    
    def create(self, artifact: Artifact) -> Artifact:
        """
        Create a new artifact
        
        Args:
            artifact: Artifact to create
            
        Returns:
            Created artifact (with generated ID if not provided)
        """
        artifact_dir = self._get_artifact_dir(artifact.id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        # Save version 1
        version_file = self._get_version_file(artifact.id, 1)
        with open(version_file, 'w', encoding='utf-8') as f:
            json.dump(artifact.model_dump(), f, indent=2, default=str)
        
        # Save as current
        current_file = self._get_current_file(artifact.id)
        with open(current_file, 'w', encoding='utf-8') as f:
            json.dump(artifact.model_dump(), f, indent=2, default=str)
        
        # Save index
        self._save_index(artifact)
        
        return artifact
    
    def read(self, artifact_id: str, version: Optional[int] = None) -> Optional[Artifact]:
        """
        Read an artifact
        
        Args:
            artifact_id: Artifact ID
            version: Specific version to read (None = latest)
            
        Returns:
            Artifact or None if not found
        """
        if version is None:
            # Read current version
            current_file = self._get_current_file(artifact_id)
            if not current_file.exists():
                return None
            with open(current_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            # Read specific version
            version_file = self._get_version_file(artifact_id, version)
            if not version_file.exists():
                return None
            with open(version_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        return Artifact(**data)
    
    def update(self, artifact: Artifact) -> Artifact:
        """
        Update an artifact (creates new version)
        
        Args:
            artifact: Updated artifact (must have incremented version)
            
        Returns:
            Updated artifact
        """
        # Verify version increment
        existing = self.read(artifact.id)
        if existing and artifact.version <= existing.version:
            raise ValueError(f"Version must be incremented. Current: {existing.version}, New: {artifact.version}")
        
        artifact_dir = self._get_artifact_dir(artifact.id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        # Save new version
        version_file = self._get_version_file(artifact.id, artifact.version)
        with open(version_file, 'w', encoding='utf-8') as f:
            json.dump(artifact.model_dump(), f, indent=2, default=str)
        
        # Update current
        current_file = self._get_current_file(artifact.id)
        with open(current_file, 'w', encoding='utf-8') as f:
            json.dump(artifact.model_dump(), f, indent=2, default=str)
        
        # Update index
        self._save_index(artifact)
        
        return artifact
    
    def delete(self, artifact_id: str) -> bool:
        """
        Delete an artifact (and all versions)
        
        Args:
            artifact_id: Artifact ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        artifact_dir = self._get_artifact_dir(artifact_id)
        if not artifact_dir.exists():
            return False
        
        import shutil
        shutil.rmtree(artifact_dir)
        return True
    
    def list_artifacts(self, artifact_type: Optional[ArtifactType] = None) -> List[Artifact]:
        """
        List all artifacts (or filter by type)
        
        Args:
            artifact_type: Optional filter by type
            
        Returns:
            List of artifacts (current versions only)
        """
        artifacts = []
        
        if not self.base_path.exists():
            return artifacts
        
        for artifact_dir in self.base_path.iterdir():
            if not artifact_dir.is_dir():
                continue
            
            artifact_id = artifact_dir.name
            current_file = self._get_current_file(artifact_id)
            
            if not current_file.exists():
                continue
            
            try:
                artifact = self.read(artifact_id)
                if artifact:
                    if artifact_type is None or artifact.type == artifact_type:
                        artifacts.append(artifact)
            except Exception:
                # Skip corrupted artifacts
                continue
        
        return artifacts
    
    def get_version_history(self, artifact_id: str) -> List[int]:
        """
        Get list of available versions for an artifact
        
        Args:
            artifact_id: Artifact ID
            
        Returns:
            List of version numbers
        """
        artifact_dir = self._get_artifact_dir(artifact_id)
        if not artifact_dir.exists():
            return []
        
        versions = []
        for file in artifact_dir.glob("v*.json"):
            try:
                version = int(file.stem[1:])  # Remove 'v' prefix
                versions.append(version)
            except ValueError:
                continue
        
        return sorted(versions)
    
    def _save_index(self, artifact: Artifact):
        """Save artifact index (metadata)"""
        index_file = self._get_index_file(artifact.id)
        index_data = {
            "id": artifact.id,
            "type": artifact.type.value,
            "version": artifact.version,
            "created_at": artifact.meta.created_at,
            "updated_at": artifact.meta.updated_at,
            "created_by": artifact.meta.created_by.value,
            "source_engine": artifact.meta.source_engine.value if artifact.meta.source_engine else None
        }
        
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, indent=2)
