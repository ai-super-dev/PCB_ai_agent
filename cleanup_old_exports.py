"""
Cleanup script to remove old timestamped export files.
Keeps only the latest altium_pcb_info.json file.
"""
import os
from pathlib import Path

def cleanup_old_exports():
    """Remove old timestamped export files"""
    base_path = Path(".")
    project_path = Path("PCB_Project")
    
    removed_count = 0
    
    # Remove timestamped files in root
    for file in base_path.glob("altium_export_*.json"):
        try:
            file.unlink()
            print(f"Removed: {file.name}")
            removed_count += 1
        except Exception as e:
            print(f"Error removing {file.name}: {e}")
    
    # Remove timestamped files in project directory
    if project_path.exists():
        for file in project_path.glob("altium_export_*.json"):
            try:
                file.unlink()
                print(f"Removed: {file.name}")
                removed_count += 1
            except Exception as e:
                print(f"Error removing {file.name}: {e}")
    
    print(f"\nCleanup complete! Removed {removed_count} old export files.")
    print("Kept: altium_pcb_info.json (if it exists)")

if __name__ == "__main__":
    cleanup_old_exports()
