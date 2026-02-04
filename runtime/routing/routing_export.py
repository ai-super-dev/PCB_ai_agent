"""
Routing Export to Altium
Per Week 1 Task 13: Build Routing Export to Altium

Converts routing suggestions (patches) to Altium commands
"""
from typing import List, Dict, Any, Optional
from core.patch.schema import Patch
from core.artifacts.store import ArtifactStore
import json
from pathlib import Path


class RoutingExporter:
    """
    Export routing suggestions to Altium format
    """
    
    def __init__(self, artifact_store: Optional[ArtifactStore] = None):
        """
        Initialize routing exporter
        
        Args:
            artifact_store: Artifact store instance
        """
        self.store = artifact_store or ArtifactStore()
    
    def export_patches_to_altium(self, patches: List[Patch], output_path: str) -> bool:
        """
        Export routing patches to Altium commands JSON
        
        Args:
            patches: List of routing patches
            output_path: Output file path (pcb_commands.json format)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            commands = []
            
            for patch in patches:
                for op in patch.ops:
                    command = self._patch_op_to_altium_command(op, patch)
                    if command:
                        commands.append(command)
            
            # Write to JSON file (compatible with existing pcb_commands.json format)
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(commands, f, indent=2)
            
            return True
            
        except Exception as e:
            print(f"Error exporting routing to Altium: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _patch_op_to_altium_command(self, op: Any, patch: Patch) -> Optional[Dict[str, Any]]:
        """
        Convert patch operation to Altium command format
        
        Args:
            op: PatchOp object
            patch: Parent patch
            
        Returns:
            Altium command dict or None
        """
        op_type = op.op
        
        if op_type == "AddTrackSegment":
            payload = op.payload
            return {
                "command": "add_track",
                "parameters": {
                    "net": payload.get("net_id", ""),
                    "layer": payload.get("layer_id", ""),
                    "start": {
                        "x_mm": payload.get("from_pos", [0, 0])[0],
                        "y_mm": payload.get("from_pos", [0, 0])[1]
                    },
                    "end": {
                        "x_mm": payload.get("to_pos", [0, 0])[0],
                        "y_mm": payload.get("to_pos", [0, 0])[1]
                    },
                    "width_mm": payload.get("width_mm", 0.25)
                },
                "explanation": patch.meta.explain or "Routing suggestion"
            }
        
        elif op_type == "AddVia":
            payload = op.payload
            return {
                "command": "add_via",
                "parameters": {
                    "net": payload.get("net_id", ""),
                    "x_mm": payload.get("position", [0, 0])[0],
                    "y_mm": payload.get("position", [0, 0])[1],
                    "drill_mm": payload.get("drill_mm", 0.3),
                    "layers": payload.get("layers", [])
                },
                "explanation": patch.meta.explain or "Via placement suggestion"
            }
        
        elif op_type == "MoveComponent":
            payload = op.payload
            return {
                "command": "move_component",
                "parameters": {
                    "designator": payload.get("component_ref", ""),
                    "x": payload.get("new_position_mm", [0, 0])[0],
                    "y": payload.get("new_position_mm", [0, 0])[1],
                    "rotation": payload.get("new_rotation_deg", 0.0),
                    "layer": payload.get("layer")
                },
                "explanation": patch.meta.explain or "Component placement optimization"
            }
        
        # Unknown operation type
        return None
    
    def export_to_pcb_commands(self, patches: List[Patch], output_path: str = "pcb_commands.json") -> bool:
        """
        Export patches to pcb_commands.json format (for compatibility)
        
        Args:
            patches: List of routing patches
            output_path: Output file path
            
        Returns:
            True if successful
        """
        return self.export_patches_to_altium(patches, output_path)
