"""
Trigger Altium PCB export via command_server.pas
This sends a command to the running Altium script to export PCB info
"""
import json
import time
from pathlib import Path

def send_export_command():
    """Send export command to Altium"""
    base_path = Path(".")
    command_file = base_path / "altium_command.json"
    result_file = base_path / "altium_result.json"
    
    print("Sending export command to Altium...")
    
    # Clear old result
    if result_file.exists():
        result_file.unlink()
    
    # Write command
    command = {"action": "export_pcb_info"}
    with open(command_file, 'w') as f:
        json.dump(command, f)
    
    print("Command sent. Waiting for Altium to respond...")
    
    # Wait for result (up to 30 seconds for large PCBs)
    timeout = 30
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if result_file.exists():
            try:
                with open(result_file, 'r') as f:
                    result = json.load(f)
                
                if result.get("success"):
                    print("\n✅ Export successful!")
                    print(f"Message: {result.get('message', 'Export completed')}")
                    
                    # Check for export file
                    export_files = sorted(
                        base_path.glob("altium_export_*.json"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True
                    )
                    
                    if export_files:
                        print(f"\nExport file: {export_files[0].name}")
                        
                        # Quick check for rules
                        with open(export_files[0], 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            rules = data.get('rules', [])
                            print(f"Rules exported: {len(rules)}")
                    
                    return True
                else:
                    print(f"\n❌ Export failed: {result.get('error', 'Unknown error')}")
                    return False
                    
            except Exception as e:
                print(f"Error reading result: {e}")
                time.sleep(0.5)
                continue
        
        time.sleep(0.5)
    
    print("\n❌ Timeout waiting for Altium response")
    print("\nPossible issues:")
    print("  1. command_server.pas is not running in Altium")
    print("  2. No PCB file is open in Altium")
    print("  3. Altium is busy or frozen")
    print("\nTo fix:")
    print("  1. Open Altium Designer")
    print("  2. Open your PCB file")
    print("  3. File → Run Script → command_server.pas")
    print("  4. Run 'StartServer' procedure")
    print("  5. Try this script again")
    return False

def main():
    print("=" * 60)
    print("Altium PCB Export Trigger")
    print("=" * 60)
    print()
    
    # Check if command_server.pas is running
    result_file = Path("altium_result.json")
    command_file = Path("altium_command.json")
    
    # Send ping first to check if server is running
    print("Checking if Altium script server is running...")
    
    if result_file.exists():
        result_file.unlink()
    
    with open(command_file, 'w') as f:
        json.dump({"action": "ping"}, f)
    
    time.sleep(1)
    
    if not result_file.exists():
        print("\n❌ Altium script server is not running!")
        print("\nPlease start it first:")
        print("  1. Open Altium Designer")
        print("  2. Open your PCB file")
        print("  3. File → Run Script → command_server.pas")
        print("  4. Run 'StartServer' procedure")
        print("  5. Wait for 'Server Started' message")
        print("  6. Run this script again")
        return
    
    print("✅ Script server is running")
    print()
    
    # Send export command
    if send_export_command():
        print("\n" + "=" * 60)
        print("✅ Export completed successfully!")
        print("=" * 60)
        print("\nYou can now:")
        print("  1. Run: python test_design_rules.py")
        print("  2. Or use 'View Design Rules' in the UI")
    else:
        print("\n" + "=" * 60)
        print("❌ Export failed")
        print("=" * 60)

if __name__ == "__main__":
    main()
