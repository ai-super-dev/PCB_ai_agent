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
            self.base_path = Path(__file__).parent.parent
        
        self.command_file = self.base_path / "altium_command.json"
        self.result_file = self.base_path / "altium_result.json"
        self.timeout = 10  # seconds
    
    def _send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command and wait for result."""
        # Clear old result
        if self.result_file.exists():
            self.result_file.unlink()
        
        # Write command (small file, ~100 bytes)
        with open(self.command_file, 'w') as f:
            json.dump(command, f)
        
        # Wait for result
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            if self.result_file.exists():
                try:
                    with open(self.result_file, 'r') as f:
                        result = json.load(f)
                    # Clean up
                    self.result_file.unlink()
                    return result
                except:
                    pass
            time.sleep(0.2)
        
        return {"error": "Timeout waiting for Altium response"}
    
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


def test_server():
    """Test the script server connection."""
    print("Testing Altium Script Server Connection...")
    print()
    
    client = AltiumScriptClient()
    
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
        return False


if __name__ == "__main__":
    test_server()
