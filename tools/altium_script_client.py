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
        # Method 1: Start from script location and go up (most reliable)
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
        
        # Method 2: Use current working directory
        cwd = Path.cwd().resolve()
        if (cwd / "altium_scripts").exists() or (cwd / "main.py").exists():
            return cwd
        
        # Method 3: Try known workspace path (last resort)
        known_paths = [
            Path(r"E:\Altium_Project\PCB_ai_agent"),
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
        # Exporting full PCB JSON can be heavy on large boards.
        if action == "export_pcb_info":
            timeout = max(self.timeout, 120)
        # Rule creation/update/delete can take longer due to SavePCBFile + ExportPCBInfo
        elif action in ("create_rule", "update_rule", "delete_rule"):
            timeout = max(self.timeout, 45)
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
        
        # STEP 2: Write command ATOMICALLY with retry logic for file locking
        # This prevents Altium from reading a partially-written or locked file
        temp_command = Path(str(self.command_file) + '.tmp')
        
        # Retry writing the command file if it's locked
        max_write_attempts = 10
        for write_attempt in range(max_write_attempts):
            try:
                # Clean up any existing temp file first
                if temp_command.exists():
                    try:
                        temp_command.unlink()
                    except:
                        pass
                
                # Write to temp file
                with open(temp_command, 'w') as f:
                    json.dump(command, f)
                    f.flush()
                    os.fsync(f.fileno())
                
                # Remove old command file if it exists (with retry)
                if self.command_file.exists():
                    for del_attempt in range(5):
                        try:
                            self.command_file.unlink()
                            break
                        except PermissionError:
                            if del_attempt < 4:
                                time.sleep(0.2 * (del_attempt + 1))  # Exponential backoff
                            else:
                                raise  # Give up after 5 attempts
                        except:
                            break  # File doesn't exist anymore
                
                # Atomic rename (temp -> real) with retry
                for rename_attempt in range(5):
                    try:
                        os.rename(str(temp_command), str(self.command_file))
                        break
                    except PermissionError:
                        if rename_attempt < 4:
                            time.sleep(0.2 * (rename_attempt + 1))  # Exponential backoff
                        else:
                            raise  # Give up after 5 attempts
                
                time.sleep(0.1)  # Brief filesystem settle
                break  # Success - exit retry loop
                
            except Exception as e:
                # Clean up temp file on error
                if temp_command.exists():
                    try:
                        temp_command.unlink()
                    except:
                        pass
                
                if write_attempt < max_write_attempts - 1:
                    # Wait longer before retrying, with exponential backoff
                    wait_time = 0.5 * (2 ** write_attempt)  # 0.5s, 1s, 2s, 4s, etc.
                    print(f"  Command file write attempt {write_attempt + 1} failed: {str(e)}")
                    print(f"  Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    # Final attempt failed
                    return {"success": False, "error": f"Failed to write command file after {max_write_attempts} attempts: {str(e)}"}
        
        # Do NOT fail if command file is missing here.
        # Altium may consume/delete it immediately after we write it, which is expected.
        if not self.command_file.exists():
            print(f"  Note: command file for '{action}' is already gone (likely consumed by Altium)")
        
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
                    result_msg = result.get("message", result.get("error", ""))
                    
                    # Check if this is a stale result
                    if result_action and result_action != action:
                        # This is a stale result from a PREVIOUS command!
                        stale_count += 1
                        print(f"  WARNING: Stale result detected! Expected action='{action}', got '{result_action}' (stale #{stale_count})")
                        print(f"  Stale result message: '{result_msg[:100]}...'")
                        try:
                            self.result_file.unlink()
                        except:
                            pass
                        if stale_count >= 5:
                            print(f"  ERROR: Too many stale results, giving up")
                            return {"success": False, "error": f"Received {stale_count} stale results from previous commands. Altium may not be processing '{action}'. Last stale result: {result_msg[:100]}"}
                        time.sleep(0.5)  # Wait longer before retrying
                        continue
                    
                    # Also check message content for common stale result patterns
                    if not result_action and result_msg:
                        # No action field but has message - might be old format or stale
                        if "Schematic info exported" in result_msg and action != "export_schematic_info":
                            stale_count += 1
                            print(f"  WARNING: Detected stale export_schematic_info result (no action field)")
                            try:
                                self.result_file.unlink()
                            except:
                                pass
                            if stale_count >= 5:
                                return {"success": False, "error": f"Received stale export_schematic_info result when expecting '{action}'. Clear result file and try again."}
                            time.sleep(0.5)
                            continue
                    
                    # Valid result - clean up and return
                    # CRITICAL: Delete result file multiple times to ensure it's gone
                    result_deleted = False
                    for del_attempt in range(5):
                        try:
                            if self.result_file.exists():
                                self.result_file.unlink()
                                # Verify it's actually deleted
                                time.sleep(0.1)
                                if not self.result_file.exists():
                                    result_deleted = True
                                    if del_attempt > 0:
                                        print(f"  Result file deleted on attempt {del_attempt + 1}")
                                    break
                            else:
                                result_deleted = True
                                break
                        except Exception as e:
                            if del_attempt < 4:
                                time.sleep(0.2 * (del_attempt + 1))
                            else:
                                print(f"  WARNING: Could not delete result file after {del_attempt + 1} attempts: {e}")
                    
                    if not result_deleted and self.result_file.exists():
                        print(f"  ERROR: Result file still exists after deletion attempts - stale results may occur!")
                    
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
    
    def rotate_component(self, designator: str, rotation: float) -> Dict[str, Any]:
        """
        Rotate a component.
        
        Args:
            designator: Component designator (e.g., "U1")
            rotation: New rotation in degrees
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "rotate_component",
            "designator": designator,
            "rotation": rotation
        })
    
    def move_and_rotate_component(self, designator: str, x: float, y: float, 
                                  rotation: float) -> Dict[str, Any]:
        """
        Move and rotate a component in one operation.
        
        Args:
            designator: Component designator (e.g., "U1")
            x, y: New position in mm
            rotation: New rotation in degrees
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "move_and_rotate_component",
            "designator": designator,
            "x": x,
            "y": y,
            "rotation": rotation
        })
    
    def adjust_copper_pour_clearance(self, x: float, y: float, clearance_mm: float = 0.4) -> Dict[str, Any]:
        """
        Adjust copper pour clearance near a specific location.
        
        Args:
            x, y: Location in mm where violation occurred
            clearance_mm: New clearance value in mm (default 0.4mm)
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "adjust_copper_pour_clearance",
            "x": x,
            "y": y,
            "clearance_mm": clearance_mm
        })
    
    def adjust_copper_pour_clearance_by_net(self, net: str, clearance_mm: float = 0.4) -> Dict[str, Any]:
        """
        Adjust copper pour clearance for all pours on a specific net.
        
        Args:
            net: Net name (e.g., "GND", "VCC")
            clearance_mm: New clearance value in mm (default 0.4mm)
            
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "adjust_copper_pour_clearance_by_net",
            "net": net,
            "clearance_mm": clearance_mm
        })
    
    def rebuild_polygons(self) -> Dict[str, Any]:
        """
        Rebuild all polygons/copper pours on the PCB.
        
        Returns:
            Result dict with success/error
        """
        return self._send_command({
            "action": "rebuild_polygons"
        })
    
    def repour_polygons(self) -> Dict[str, Any]:
        """
        Force repour of all polygons with updated clearances.
        
        Returns:
            Result dict with success/error
        """
        return self._send_command({"action": "repour_polygons"})
    
    def export_copper_primitives(self) -> Dict[str, Any]:
        """
        Export actual poured copper primitives to copper_primitives.json.
        
        Returns:
            Result dict with success/error
        """
        return self._send_command({"action": "export_copper_primitives"})
    
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
    
    # ==================================================================
    # SCHEMATIC-TO-PCB COMMANDS
    # These commands are used with the schematic_PCB.pas script
    # ==================================================================
    
    def export_schematic_info(self) -> Dict[str, Any]:
        """
        Export schematic info from Altium to JSON file.
        Requires schematic_PCB.pas to be running in Altium.
        
        Returns:
            Result dict with success/error
        """
        # Large schematics can take time to export - use longer timeout
        old_timeout = self.timeout
        self.timeout = max(self.timeout, 60)  # At least 60 seconds for large schematics
        try:
            result = self._send_command({"action": "export_schematic_info"})
            return result
        finally:
            self.timeout = old_timeout
    
    def create_pcb_from_schematic(self) -> Dict[str, Any]:
        """
        Create a PCB document from the current schematic.
        Uses direct build method to create components and nets from schematic data.
        
        Result message format:
            PCB_BUILT|<comp_count>|<net_count>|<path> - Direct build succeeded
            PCB_EMPTY|0|<path>                        - PCB created but empty
        
        Returns:
            Result dict with success/error
        """
        # CRITICAL: Clear result file before sending command to prevent stale reads
        print(f"  [create_pcb] Pre-command: Clearing result file...")
        for clear_attempt in range(10):
            try:
                if self.result_file.exists():
                    self.result_file.unlink()
                time.sleep(0.2)
                if not self.result_file.exists():
                    print(f"  [create_pcb] Result file cleared (attempt {clear_attempt + 1})")
                    # Verify it stays cleared
                    time.sleep(0.5)
                    if not self.result_file.exists():
                        print(f"  [create_pcb] Result file confirmed cleared")
                        break
                    else:
                        print(f"  [create_pcb] WARNING: Result file reappeared!")
                else:
                    print(f"  [create_pcb] Result file still exists (attempt {clear_attempt + 1})")
            except Exception as e:
                print(f"  [create_pcb] Clear attempt {clear_attempt + 1} failed: {e}")
            time.sleep(0.3)
        
        # PCB creation can take a long time
        old_timeout = self.timeout
        self.timeout = max(self.timeout, 300)
        result = self._send_command({"action": "create_pcb"})
        self.timeout = old_timeout
        return result
    
    def check_eco_status(self) -> Dict[str, Any]:
        """
        Check if the current PCB has components (ECO completed).
        
        Result message format:
            ECO_OK|<count>|<path>   - PCB has components
            ECO_EMPTY|0|<path>      - PCB is still empty
        
        Returns:
            Result dict with success/error
        """
        return self._send_command({"action": "check_eco"})
    
    def auto_place_components(self) -> Dict[str, Any]:
        """
        Auto-place all components on the PCB.
        Requires a PCB document to be open in Altium.
        
        Returns:
            Result dict with success/error
        """
        old_timeout = self.timeout
        self.timeout = max(self.timeout, 120)
        result = self._send_command({"action": "auto_place"})
        self.timeout = old_timeout
        return result
    
    def auto_route(self) -> Dict[str, Any]:
        """
        Auto-route all nets on the PCB.
        Requires a PCB document to be open in Altium.
        
        Returns:
            Result dict with success/error
        """
        old_timeout = self.timeout
        self.timeout = max(self.timeout, 180)
        result = self._send_command({"action": "auto_route"})
        self.timeout = old_timeout
        return result
    
    def create_pcb_libraries(self) -> Dict[str, Any]:
        """
        Create Altium PCB library files from generated footprint specifications.
        Reads footprint_libraries.json and creates .PcbLib files.
        
        Result message format:
            PCB_LIBRARIES_CREATED|<count>|<path>   - Libraries created successfully
        
        Returns:
            Result dict with success/error
        """
        old_timeout = self.timeout
        self.timeout = max(self.timeout, 300)  # Library creation can take time
        result = self._send_command({"action": "create_libraries"})
        self.timeout = old_timeout
        return result


