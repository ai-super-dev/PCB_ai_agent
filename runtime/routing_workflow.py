"""
Complete Routing & DRC Workflow
Per Week 1 Task 14: End-to-End Workflow

Workflow: Import → Route → DRC → Export → Execute
"""
from typing import Optional, Dict, Any, List
from core.artifacts.store import ArtifactStore
from core.artifacts.models import Artifact, ArtifactType
from runtime.routing.routing_module import RoutingModule
from runtime.routing.routing_export import RoutingExporter
from runtime.drc.drc_workflow import DRCWorkflow
from adapters.altium.importer import AltiumImporter


class RoutingDRCWorkflow:
    """
    Complete routing and DRC workflow
    
    Handles: Import → Route → DRC → Export
    """
    
    def __init__(self, artifact_store: Optional[ArtifactStore] = None):
        """
        Initialize workflow
        
        Args:
            artifact_store: Artifact store instance
        """
        self.store = artifact_store or ArtifactStore()
        self.routing_module = RoutingModule(self.store, enable_drc_validation=True)
        self.drc_workflow = DRCWorkflow(self.store)
        self.exporter = RoutingExporter(self.store)
        self.importer = AltiumImporter()
    
    def run_complete_workflow(self, pcb_info_path: str, design_rules_path: str,
                             output_path: str = "pcb_commands.json") -> Dict[str, Any]:
        """
        Run complete workflow: Import → Route → DRC → Export
        
        Args:
            pcb_info_path: Path to Altium pcb_info.json
            design_rules_path: Path to Altium design_rules.json
            output_path: Output path for routing commands
            
        Returns:
            Workflow result dict
        """
        result = {
            "success": False,
            "board_artifact_id": None,
            "constraint_artifact_id": None,
            "routing_suggestions": [],
            "violations_artifact_id": None,
            "export_path": None,
            "errors": []
        }
        
        try:
            # Step 1: Import from Altium
            print("Step 1: Importing from Altium...")
            gir = self.importer.import_pcb_info(pcb_info_path)
            cir = self.importer.import_design_rules(design_rules_path)
            
            if not gir or not cir:
                result["errors"].append("Failed to import from Altium")
                return result
            
            # Create artifacts
            board_artifact = self.importer.create_pcb_board_artifact(gir, pcb_info_path)
            constraint_artifact = self.importer.create_constraint_ruleset_artifact(cir, design_rules_path)
            
            board_artifact = self.store.create(board_artifact)
            constraint_artifact = self.store.create(constraint_artifact)
            
            result["board_artifact_id"] = board_artifact.id
            result["constraint_artifact_id"] = constraint_artifact.id
            
            print(f"  Board artifact: {board_artifact.id}")
            print(f"  Constraint artifact: {constraint_artifact.id}")
            
            # Step 2: Generate routing suggestions with DRC validation
            print("\nStep 2: Generating routing suggestions with DRC validation...")
            routing_result = self.routing_module.generate_routing_with_drc_validation(
                artifact_id=board_artifact.id,
                constraint_artifact_id=constraint_artifact.id
            )
            
            result["routing_suggestions"] = routing_result.get("routing_suggestions", [])
            result["violations_artifact_id"] = routing_result.get("violations_artifact_id")
            
            print(f"  Generated {len(result['routing_suggestions'])} routing suggestions")
            if routing_result.get("filtered_count", 0) > 0:
                print(f"  Filtered {routing_result['filtered_count']} suggestions due to DRC violations")
            
            # Step 3: Run DRC on current board
            print("\nStep 3: Running DRC...")
            violations_artifact = self.drc_workflow.run_drc_workflow(
                board_artifact_id=board_artifact.id,
                constraint_artifact_id=constraint_artifact.id
            )
            
            if violations_artifact:
                print(f"  DRC found violations: {violations_artifact.data.get('violation_count', 0)}")
                self.drc_workflow.display_violations(violations_artifact.id)
            
            # Step 4: Export routing to Altium
            print("\nStep 4: Exporting routing to Altium...")
            if result["routing_suggestions"]:
                export_success = self.exporter.export_to_pcb_commands(
                    patches=result["routing_suggestions"],
                    output_path=output_path
                )
                
                if export_success:
                    result["export_path"] = output_path
                    print(f"  Exported to: {output_path}")
                else:
                    result["errors"].append("Failed to export routing commands")
            else:
                print("  No routing suggestions to export")
            
            result["success"] = True
            
        except Exception as e:
            result["errors"].append(str(e))
            print(f"Error in workflow: {e}")
            import traceback
            traceback.print_exc()
        
        return result
