"""
Altium Script Client

Sends small commands to Altium via the command_server.pas script.
Commands are ~100 bytes each - NO memory issues.

Usage:
    1. Start command_server.pas in Altium Designer
    2. Use this client to send commands

Example:
    client = AltiumScriptClient()
    client.add_track("VCC", 10, 20, 50, 60)
"""

import json
import time
import os
from pathlib import Path
from typing import Optional, Dict, Any


class AltiumScriptClient:
    """
    Client for Altium Script Server.
    Sends small commands, waits for results.
    """
    
    def __init__(self, base_path: str = None):
        if base_path:
            self.base_path = Path(base_path)
        else:
            # Try multiple methods to find the project root
            self.base_path = self._find_project_root()
        
        # Normalize path to handle case sensitivity and resolve any symlinks
        self.base_path = self.base_path.resolve()
        
        self.command_file = self.base_path / "altium_command.json"
        self.result_file = self.base_path / "PCB_Project" / "altium_result.json"
        self.timeout = 10  # seconds
        
        # Debug: Print detected path (can be removed in production)
        # print(f"[DEBUG] AltiumScriptClient base_path: {self.base_path}")
        # print(f"[DEBUG] Command file: {self.command_file}")
        # print(f"[DEBUG] Result file: {self.result_file}")
    
    def _find_project_root(self) -> Path:
        """Find the project root directory by looking for project markers."""
        # Method 1: Try known workspace path (most reliable)
        known_paths = [
            Path(r"E:\Altium_Project\PCB_ai_agent"),
            Path(r"E:\AltiumProject\PCBaiagent"),  # Fallback for old path
        ]
        
        for path in known_paths:
            if path.exists() and (path / "altium_scripts").exists():
                return path
        
        # Method 2: Start from script location and go up
        script_path = Path(__file__).resolve()
        current = script_path.parent  # tools directory
        
        # Go up until we find altium_scripts folder or project root markers
        for _ in range(5):  # Max 5 levels up
            if (current / "altium_scripts").exists():
                return current
            if (current / "altium_pcb_info.json").exists():
                return current
            if (current / "main.py").exists():
                return current
            current = current.parent
        
        # Method 3: Use current working directory
        cwd = Path(os.getcwd()).resolve()
        if (cwd / "altium_scripts").exists():
            return cwd
        
        # Method 4: Fallback to script's parent (original behavior)
        return script_path.parent.parent
    
    def _send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command and wait for result.
        
        CRITICAL: Uses robust file handling to avoid race conditions.
        - Waits for any previous command to be consumed by Altium first
        - Aggressively clears stale result files (retries if locked)
        - Validates 'action' field in result matches the sent command
        - Discards stale results from previous commands
        - Uses longer timeout for rule creation commands
        """
        action = command.get("action", "unknown")
        
        # Determine timeout based on action
        # Rule creation/update/delete can take longer due to SavePCBFile + ExportPCBInfo
        if action in ("create_rule", "update_rule", "delete_rule", "export_pcb_info"):
            timeout = max(self.timeout, 30)  # At least 30 seconds for heavy operations
        else:
            timeout = self.timeout
        
        # STEP 0: Wait for any previous command file to be consumed by Altium
        # This prevents overwriting a command that Altium hasn't read yet
        for i in range(50):  # Up to 5 seconds
            if not self.command_file.exists():
                break
            time.sleep(0.1)
        else:
            print(f"  WARNING: Previous command file still exists after 5s, overwriting")
        
        # STEP 1: Aggressively clear old result file to prevent stale reads
        for attempt in range(10):
            if self.result_file.exists():
                try:
                    self.result_file.unlink()
                    time.sleep(0.05)
                    # Verify it's actually gone
                    if not self.result_file.exists():
                        break
                except PermissionError:
                    time.sleep(0.3)  # File locked, wait longer and retry
                except Exception:
                    break
            else:
                break
        
        # Also clear the temp result file
        temp_result = Path(str(self.result_file) + '.tmp')
        if temp_result.exists():
            try:
                temp_result.unlink()
            except:
                pass
        
        # Verify result file is actually gone - CRITICAL for avoiding stale reads
        if self.result_file.exists():
            print(f"  WARNING: Could not delete old result file after 10 attempts!")
            try:
                with open(self.result_file, 'r') as f:
                    stale = f.read()
                print(f"  Stale result content: {stale[:200]}")
                # Try one more time with a longer pause
                time.sleep(0.5)
                self.result_file.unlink()
                print(f"  Successfully deleted stale result on final attempt")
            except:
                print(f"  CRITICAL: Stale result file persists - action validation will handle it")
        
        # Verify command file directory exists
        if not self.command_file.parent.exists():
            return {"success": False, "error": f"Command file directory does not exist: {self.command_file.parent}"}
        
        # STEP 2: Write command ATOMICALLY: write to temp file, then rename
        # This prevents Altium from reading a partially-written or locked file
        temp_command = Path(str(self.command_file) + '.tmp')
        try:
            # Write to temp file
            with open(temp_command, 'w') as f:
                json.dump(command, f)
                f.flush()
                os.fsync(f.fileno())
            
            # Remove old command file if it exists
            if self.command_file.exists():
                try:
                    self.command_file.unlink()
                except:
                    time.sleep(0.1)
                    try:
                        self.command_file.unlink()
                    except:
                        pass
            
            # Atomic rename (temp -> real)
            os.rename(str(temp_command), str(self.command_file))
            
            time.sleep(0.1)  # Brief filesystem settle
            
        except Exception as e:
            # Clean up temp file on error
            if temp_command.exists():
                try:
                    temp_command.unlink()
                except:
                    pass
            return {"success": False, "error": f"Failed to write command file: {str(e)}"}
        
        # STEP 2b: Double-check no stale result appeared between our clear and command write
        if self.result_file.exists():
            try:
                self.result_file.unlink()
                print(f"  Cleared stale result file that appeared during command write")
            except:
                pass
        
        print(f"  Command sent: {action} (timeout={timeout}s)")
        
        # STEP 3: Wait for result with action validation
        start_time = time.time()
        check_count = 0
        stale_count = 0
        while time.time() - start_time < timeout:
            if self.result_file.exists():
                try:
                    time.sleep(0.15)  # Let file finish writing
                    with open(self.result_file, 'r') as f:
                        content = f.read().strip()
                    
                    if not content:
                        time.sleep(0.2)
                        continue
                    
                    result = json.loads(content)
                    
                    # CRITICAL: Validate the result matches our command using 'action' field
                    # Altium's WriteRes now includes the action name in every result
                    result_action = result.get("action", "")
                    if result_action and result_action != action:
                        # This is a stale result from a PREVIOUS command!
                        stale_count += 1
                        print(f"  WARNING: Stale result detected! Expected action='{action}', got '{result_action}' (stale #{stale_count})")
                        try:
                            self.result_file.unlink()
                        except:
                            pass
                        if stale_count >= 5:
                            print(f"  ERROR: Too many stale results, giving up")
                            return {"success": False, "error": f"Received {stale_count} stale results from previous commands. Altium may not be processing '{action}'."}
                        time.sleep(0.3)
                        continue
                    
                    # Valid result - clean up and return
                    try:
                        self.result_file.unlink()
                    except:
                        pass
                    
                    return result
                except json.JSONDecodeError:
                    time.sleep(0.2)  # File still being written
                    continue
                except Exception:
                    time.sleep(0.2)
                    continue
            
            time.sleep(0.2)
            check_count += 1
            if check_count % 10 == 0:
                elapsed = time.time() - start_time
                print(f"  Waiting for Altium response... ({elapsed:.1f}s)")
                # Check if command file was consumed (Altium read it)
                if not self.command_file.exists():
                    print(f"    Command file consumed by Altium (processing...)")
        
        # Timeout
        cmd_exists = self.command_file.exists()
        res_exists = self.result_file.exists()
        
        print(f"DEBUG: Command '{action}' timed out after {timeout}s")
        print(f"  Command file exists: {cmd_exists}")
        print(f"  Result file exists: {res_exists}")
        print(f"  Stale results discarded: {stale_count}")
        
        if cmd_exists:
            hint = "Altium did NOT read the command. Check that StartServer is running."
        elif res_exists:
            hint = "Result file appeared but couldn't be read. Check file permissions."
        else:
            hint = "Command was consumed but no result returned. Altium may have crashed or is showing a dialog."
        
        error_msg = (
            f"Timeout waiting for Altium response after {timeout}s\n"
            f"Action: {action}\n"
            f"Hint: {hint}\n"
            f"Command file: {self.command_file}\n"
            f"Result file: {self.result_file}\n"
            f"Make sure StartServer is running in Altium!"
        )
        return {"success": False, "error": error_msg}
    
    def ping(self) -> bool:
        """Test if script server is running."""
        result = self._send_command({"action": "ping"})
        return result.get("success", False)
    
    def add_track(self, net: str, x1: float, y1: float, x2: float, y2: float,
                  width: float = 0.25, layer: str = "Top") -> Dict[str, Any]:
        """
        Add a track to the PCB.
        
        Args:
            net: Net name
            x1, y1: Start position in mm
            x2, y2: End position in mm
            width: Track width in mm
            layer: Layer name
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "add_track",
            "net": net,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "width": width,
            "layer": layer
        })
    
    def add_via(self, x: float, y: float, net: str = "",
                hole: float = 0.3, diameter: float = 0.6) -> Dict[str, Any]:
        """
        Add a via to the PCB.
        
        Args:
            x, y: Position in mm
            net: Net name (optional)
            hole: Hole diameter in mm
            diameter: Via diameter in mm
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "add_via",
            "x": x,
            "y": y,
            "net": net,
            "hole": hole,
            "diameter": diameter
        })
    
    def move_component(self, designator: str, x: float, y: float,
                       rotation: float = 0) -> Dict[str, Any]:
        """
        Move a component.
        
        Args:
            designator: Component designator (e.g., "U1")
            x, y: New position in mm
            rotation: New rotation in degrees (0 = keep current)
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "move_component",
            "designator": designator,
            "x": x,
            "y": y,
            "rotation": rotation
        })
    
    def run_drc(self) -> Dict[str, Any]:
        """
        Run Design Rule Check in Altium.
        
        Returns:
            Result dict with success/error
        """
        return self._send_command({"action": "run_drc"})
    
    def export_pcb_info(self) -> Dict[str, Any]:
        """
        Export PCB info from Altium to JSON file.
        
        Returns:
            Result dict with success/error
        """
        return self._send_command({"action": "export_pcb_info"})
    
    def delete_component(self, designator: str) -> Dict[str, Any]:
        """
        Delete a component from the PCB.
        
        Args:
            designator: Component designator (e.g., "U1")
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "delete_component",
            "designator": designator
        })
    
    def delete_track(self, net: str = "", layer: str = "Top") -> Dict[str, Any]:
        """
        Delete tracks on a layer (optionally filter by net).
        
        Args:
            net: Net name (empty = all tracks on layer)
            layer: Layer name
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "delete_track",
            "net": net,
            "layer": layer
        })
    
    def create_rule(self, rule_type: str, rule_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new design rule in Altium.
        
        Args:
            rule_type: Type of rule (e.g., "clearance", "width", "via")
            rule_name: Name for the rule
            parameters: Rule-specific parameters (e.g., {"clearance_mm": 0.508, "scope": "All"})
            
        Returns:
            Result dict with success/error
        """
        # Flatten parameters for easier parsing in DelphiScript
        command = {
            "action": "create_rule",
            "rule_type": rule_type,
            "rule_name": rule_name
        }
        # Add parameters as individual fields with param_ prefix
        for key, value in parameters.items():
            command[f"param_{key}"] = value
        
        # DEBUG: Log the command being sent
        print(f"DEBUG: Sending create_rule command:")
        print(f"  Rule type: {rule_type}")
        print(f"  Rule name: {rule_name}")
        print(f"  Parameters: {parameters}")
        print(f"  Full command: {command}")
        print(f"  Command file: {self.command_file}")
        
        return self._send_command(command)
    
    def update_rule(self, rule_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing design rule in Altium.
        
        Args:
            rule_name: Name of the rule to update
            parameters: Parameters to update (e.g., {"clearance_mm": 0.6})
            
        Returns:
            Result dict with success/error
        """
        # Flatten parameters for easier parsing in DelphiScript
        command = {
            "action": "update_rule",
            "rule_name": rule_name
        }
        # Add parameters as individual fields with param_ prefix
        for key, value in parameters.items():
            command[f"param_{key}"] = value
        return self._send_command(command)
    
    def delete_rule(self, rule_name: str) -> Dict[str, Any]:
        """
        Delete an existing design rule in Altium.
        
        Args:
            rule_name: Name of the rule to delete
            
        Returns:
            Result dict with success/error
        """
        # DEBUG: Log the rule name being sent
        print(f"DEBUG: delete_rule called with rule_name: [{rule_name}]")
        
        command = {
            "action": "delete_rule",
            "rule_name": rule_name
        }
        return self._send_command(command)


def test_server():
    """Test the script server connection."""
    print("Testing Altium Script Server Connection...")
    print()
    
    client = AltiumScriptClient()
    
    # Show detected paths
    print(f"Detected base path: {client.base_path}")
    print(f"Command file: {client.command_file}")
    print(f"Result file: {client.result_file}")
    print(f"Command file exists: {client.command_file.exists()}")
    print(f"Result file exists: {client.result_file.exists()}")
    print()
    
    print("Sending ping command...")
    if client.ping():
        print("✓ Script server is running!")
        return True
    else:
        print("✗ Script server not responding")
        print()
        print("Make sure you:")
        print("1. Open Altium Designer")
        print("2. Open a PCB document")
        print("3. Run: DXP → Run Script → command_server.pas → StartServer")
        print()
        print("IMPORTANT: Check that the file paths shown above match")
        print("the paths shown in Altium's StartServer message dialog!")
        return False


if __name__ == "__main__":
    test_server()
