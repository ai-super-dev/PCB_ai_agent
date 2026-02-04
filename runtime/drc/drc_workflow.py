"""
DRC Workflow
Per Week 1 Task 11: Implement DRC Workflow

Workflow: Board → DRC → Violations
"""
from typing import List, Optional, Dict, Any
from .drc_module import DRCModule
from core.artifacts.store import ArtifactStore
from core.artifacts.models import Artifact, ArtifactType


class DRCWorkflow:
    """
    DRC workflow manager
    
    Handles complete DRC workflow: Board → DRC → Violations
    """
    
    def __init__(self, artifact_store: Optional[ArtifactStore] = None):
        """
        Initialize DRC workflow
        
        Args:
            artifact_store: Artifact store instance
        """
        self.drc_module = DRCModule(artifact_store)
        self.store = artifact_store or ArtifactStore()
    
    def run_drc_workflow(self, board_artifact_id: str, 
                        constraint_artifact_id: Optional[str] = None) -> Optional[Artifact]:
        """
        Run complete DRC workflow
        
        Args:
            board_artifact_id: Board artifact ID
            constraint_artifact_id: Constraint artifact ID (auto-find if None)
            
        Returns:
            Violations artifact or None if workflow fails
        """
        # Step 1: Get constraint artifact if not provided
        if constraint_artifact_id is None:
            constraint_artifact_id = self._find_constraint_artifact(board_artifact_id)
            if not constraint_artifact_id:
                print("Warning: No constraint artifact found, using default rules")
                return None
        
        # Step 2: Run DRC
        violations_artifact = self.drc_module.run_drc(
            board_artifact_id=board_artifact_id,
            constraint_artifact_id=constraint_artifact_id
        )
        
        if not violations_artifact:
            print("Error: DRC failed to produce violations")
            return None
        
        # Step 3: Return violations artifact
        return violations_artifact
    
    def _find_constraint_artifact(self, board_artifact_id: str) -> Optional[str]:
        """
        Find constraint artifact related to board artifact
        
        Args:
            board_artifact_id: Board artifact ID
            
        Returns:
            Constraint artifact ID or None
        """
        # Get board artifact to check relations
        board_artifact = self.store.read(board_artifact_id)
        if not board_artifact:
            return None
        
        # Check relations
        for relation in board_artifact.relations:
            if relation.get("role") == "uses":
                target_id = relation.get("target_id")
                target_artifact = self.store.read(target_id)
                if target_artifact and target_artifact.type == ArtifactType.CONSTRAINT_RULESET:
                    return target_id
        
        # If no relation found, search for any constraint artifact
        constraint_artifacts = self.store.list_artifacts(ArtifactType.CONSTRAINT_RULESET)
        if constraint_artifacts:
            return constraint_artifacts[0].id
        
        return None
    
    def get_violations_summary(self, violations_artifact_id: str) -> Dict[str, Any]:
        """
        Get summary of violations
        
        Args:
            violations_artifact_id: Violations artifact ID
            
        Returns:
            Summary dict with violation counts, types, etc.
        """
        violations = self.drc_module.get_violations(violations_artifact_id)
        
        summary = {
            "total_violations": len(violations),
            "by_type": {},
            "by_severity": {},
            "violations": violations
        }
        
        for viol in violations:
            viol_type = viol.get("type", "unknown")
            severity = viol.get("severity", "error")
            
            summary["by_type"][viol_type] = summary["by_type"].get(viol_type, 0) + 1
            summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1
        
        return summary
    
    def display_violations(self, violations_artifact_id: str) -> None:
        """
        Display violations to user (console output for MVP)
        
        Args:
            violations_artifact_id: Violations artifact ID
        """
        summary = self.get_violations_summary(violations_artifact_id)
        
        print("=" * 60)
        print("DRC Violations Report")
        print("=" * 60)
        print(f"Total Violations: {summary['total_violations']}")
        print()
        print("By Type:")
        for viol_type, count in summary["by_type"].items():
            print(f"  {viol_type}: {count}")
        print()
        print("By Severity:")
        for severity, count in summary["by_severity"].items():
            print(f"  {severity}: {count}")
        print()
        print("Violations:")
        for i, viol in enumerate(summary["violations"][:10], 1):  # Show first 10
            print(f"  {i}. {viol.get('type', 'unknown')} - {viol.get('message', '')}")
            loc = viol.get("location", {})
            print(f"     Location: ({loc.get('x_mm', 0):.2f}, {loc.get('y_mm', 0):.2f}) on {loc.get('layer', 'unknown')}")
        
        if summary["total_violations"] > 10:
            print(f"  ... and {summary['total_violations'] - 10} more violations")
        print("=" * 60)
