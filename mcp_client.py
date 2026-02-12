"""
MCP Client for Altium Designer Integration
"""
import requests
import json
import time
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from config import MCP_SERVER_URL, MCP_TIMEOUT
import json


def wait_for_pcb_info(info_file: str = None, timeout: int = 20) -> bool:
    """
    Wait for pcb_info.json to be created/updated with valid content
    
    Args:
        info_file: Path to pcb_info.json
        timeout: Maximum time to wait in seconds
    
    Returns:
        bool: True if file exists and is valid, False otherwise
    """
    if info_file is None:
        info_file = Path(__file__).parent / "pcb_info.json"
    else:
        info_file = Path(info_file)
    
    start_time = time.time()
    last_size = 0
    stable_count = 0
    
    while time.time() - start_time < timeout:
        if info_file.exists():
            try:
                current_size = info_file.stat().st_size
                
                if current_size > 1000:
                    if current_size == last_size:
                        stable_count += 1
                        if stable_count >= 2:
                            try:
                                with open(info_file, 'r', encoding='utf-8') as f:
                                    content = f.read().strip()
                                    if len(content) > 500:
                                        # Try to parse JSON
                                        try:
                                            data = json.loads(content)
                                        except json.JSONDecodeError:
                                            # Try to repair common JSON errors
                                            import re
                                            # Fix missing comma between closing brace and opening brace
                                            content = re.sub(r'\}\s*\{', '}, {', content)
                                            # Fix missing comma between closing bracket and opening brace
                                            content = re.sub(r'\]\s*\{', '], {', content)
                                            # Fix missing comma between closing brace and opening bracket
                                            content = re.sub(r'\}\s*\[', '}, [', content)
                                            # Fix missing comma between closing bracket and opening bracket
                                            content = re.sub(r'\]\s*\[', '], [', content)
                                            # Try parsing again
                                            try:
                                                data = json.loads(content)
                                            except json.JSONDecodeError:
                                                if time.time() - start_time < timeout - 3:
                                                    stable_count = 0
                                                    time.sleep(1.0)
                                                    continue
                                                else:
                                                    return False
                                        
                                        if isinstance(data, dict):
                                            if 'components' in data or 'file_name' in data:
                                                return True
                            except json.JSONDecodeError:
                                if time.time() - start_time < timeout - 3:
                                    stable_count = 0
                                    time.sleep(1.0)
                                    continue
                                else:
                                    return False
                            except Exception:
                                stable_count = 0
                                time.sleep(0.5)
                                continue
                    else:
                        last_size = current_size
                        stable_count = 0
                        time.sleep(0.5)
                        continue
                elif current_size > 0:
                    last_size = current_size
                    stable_count = 0
                    time.sleep(0.5)
                    continue
                else:
                    time.sleep(0.5)
                    continue
            except Exception:
                time.sleep(0.5)
                continue
        else:
            time.sleep(0.5)
    
    if info_file.exists():
        try:
            current_size = info_file.stat().st_size
            if current_size < 100:
                return False
            try:
                with open(info_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if len(content) > 100:
                        # Try to parse JSON
                        try:
                            data = json.loads(content)
                        except json.JSONDecodeError:
                            # Try to repair common JSON errors
                            import re
                            # Fix missing comma between closing brace and opening brace
                            content = re.sub(r'\}\s*\{', '}, {', content)
                            # Fix missing comma between closing bracket and opening brace
                            content = re.sub(r'\]\s*\{', '], {', content)
                            # Fix missing comma between closing brace and opening bracket
                            content = re.sub(r'\}\s*\[', '}, [', content)
                            # Fix missing comma between closing bracket and opening bracket
                            content = re.sub(r'\]\s*\[', '], [', content)
                            # Try parsing again
                            try:
                                data = json.loads(content)
                            except json.JSONDecodeError:
                                return False
                        
                        if isinstance(data, dict) and ('components' in data or 'file_name' in data):
                            return True
            except:
                pass
        except:
            pass
    
    return False


class AltiumMCPClient:
    """Client for communicating with Altium Designer via MCP"""
    
    # Document types
    DOC_PCB = "PCB"
    DOC_SCHEMATIC = "SCH"
    DOC_PROJECT = "PRJ"
    
    def __init__(self, server_url: str = None):
        self.server_url = server_url or MCP_SERVER_URL
        self.connected = False
        self.session = requests.Session()
        self.session.timeout = MCP_TIMEOUT
        self.active_document_type = self.DOC_PCB  # Default to PCB mode
        
        # Disable proxy for localhost connections (important for local MCP server)
        self.session.trust_env = False  # Don't use system proxy settings
        self.session.proxies = {
            'http': None,
            'https': None
        }
    
    def connect_simple(self) -> Tuple[bool, str]:
        """
        Simplified connection - just checks MCP server and Altium availability
        Doesn't require PCB info file (for creating projects from scratch)
        
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Test connection to MCP server
            print(f"Connecting to MCP server at {self.server_url}...")
            try:
                response = self.session.get(
                    f"{self.server_url}/health",
                    timeout=5
                )
                print(f"Server response: {response.status_code}")
            except requests.exceptions.ConnectionError:
                return False, "Cannot connect to MCP server. Please ensure the server is running on port 8080."
            except Exception as e:
                print(f"Server connection error: {e}")
                return False, f"Cannot connect to MCP server: {str(e)}"
            
            if response.status_code == 200:
                # MCP server is accessible
                self.connected = True
                return True, "Successfully connected to MCP server. Ready to work with Altium Designer."
            else:
                return False, f"MCP server not responding correctly: {response.status_code}"
                
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def connect(self) -> Tuple[bool, str]:
        """
        Connect to Altium Designer via MCP server
        Waits for user to manually run export script to get PCB info
        
        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # First, check if PCB info file already exists and is valid
            # This avoids unnecessary script execution attempts
            info_file = Path(__file__).parent / "pcb_info.json"
            file_exists_and_valid = False
            
            try:
                altium_check = self.session.get(
                    f"{self.server_url}/altium/status",
                    timeout=5
                )
                if altium_check.status_code == 200:
                    data = altium_check.json()
                    if data.get("connected", False):
                        # File exists and is valid - no need to run script
                        self.connected = True
                        return True, "Successfully connected (using existing PCB info)"
                    file_exists_and_valid = False
            except:
                pass  # Continue to try script execution if status check fails
            
            # Wait for user to manually run the export script (up to 60 seconds)
            # Check if file exists and is valid
            print("Waiting for PCB info file (please run export script in Altium Designer)...")
            if wait_for_pcb_info(str(info_file), timeout=60):
                # File was created successfully and is valid, verify connection
                time.sleep(0.5)
                print("PCB info file created successfully!")
            else:
                # Timeout or file is invalid
                if info_file.exists():
                    try:
                        file_size = info_file.stat().st_size
                        if file_size < 100:
                            return False, "PCB info file is empty. Please check Altium Designer for error messages after running the export script.\n\nPlease try running the export script again in Altium Designer."
                        else:
                            return False, "PCB info file is invalid or corrupted. Please try running the export script again in Altium Designer."
                    except:
                        return False, "PCB info file exists but cannot be read. Please check file permissions."
                else:
                    return False, "PCB info file was not created within 1 minute. Please make sure you ran the export script in Altium Designer:\n\nFile → Run Script → altium_export_pcb_info.pas → ExportPCBInfo"
            
            # Test connection to MCP server
            print(f"Connecting to MCP server at {self.server_url}...")
            try:
                response = self.session.get(
                    f"{self.server_url}/health",
                    timeout=5
                )
                print(f"Server response: {response.status_code}")
            except Exception as e:
                print(f"Server connection error: {e}")
                raise
            
            if response.status_code == 200:
                # Check if Altium Designer is available
                altium_check = self.session.get(
                    f"{self.server_url}/altium/status",
                    timeout=5
                )
                
                if altium_check.status_code == 200:
                    data = altium_check.json()
                    if data.get("connected", False):
                        self.connected = True
                        return True, "Successfully connected and loaded PCB info"
                    else:
                        # File might have errors
                        error_msg = data.get("message", "PCB info file has errors")
                        return False, f"Failed to load PCB info: {error_msg}"
                else:
                    return False, f"Failed to check Altium Designer status: {altium_check.status_code}"
            else:
                return False, f"MCP server not responding: {response.status_code}"
                
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to MCP server. Please ensure the server is running."
        except requests.exceptions.Timeout:
            return False, "Connection timeout. Please check your network settings."
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def disconnect(self):
        """Disconnect from Altium Designer"""
        self.connected = False
    
    def get_pcb_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current PCB"""
        if not self.connected:
            return None
        
        try:
            # Try new Python-based server endpoint first
            response = self.session.get(
                f"{self.server_url}/pcb/info",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                data = response.json()
                if not data.get("error"):
                    return data
            
            # Fallback to old endpoint
            response = self.session.get(
                f"{self.server_url}/altium/pcb/info",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting PCB info: {e}")
            return None
    
    def analyze_pcb(self, query: str) -> Optional[Dict[str, Any]]:
        """Analyze PCB based on query"""
        if not self.connected:
            return None
        
        try:
            response = self.session.post(
                f"{self.server_url}/altium/pcb/analyze",
                json={"query": query},
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error analyzing PCB: {e}")
            return None
    
    def modify_schematic(self, command: str, parameters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Modify Schematic through MCP
        Commands are queued to schematic_commands.json for manual script execution
        """
        if not self.connected:
            return {
                "success": False,
                "message": "Not connected to Altium Designer"
            }
        
        try:
            response = self.session.post(
                f"{self.server_url}/altium/schematic/modify",
                json={
                    "command": command,
                    "parameters": parameters
                },
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return {
                "success": False,
                "message": f"Server error: {response.status_code}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error modifying schematic: {str(e)}"
            }
    
    def modify_pcb(self, command: str, parameters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Modify PCB through MCP
        Commands are queued to pcb_commands.json for manual script execution
        """
        if not self.connected:
            return None
        
        try:
            response = self.session.post(
                f"{self.server_url}/altium/pcb/modify",
                json={"command": command, "parameters": parameters},
                timeout=MCP_TIMEOUT
            )
            # Return response even if status code is not 200 (like 501 for not supported)
            if response.status_code in [200, 501]:
                result = response.json()
                
                if isinstance(result, dict):
                    result["message"] = "Command queued. Please run main.pas → ShowCommand in Altium Designer to see which script to run."
                
                return result
            return None
        except Exception as e:
            print(f"Error modifying PCB: {e}")
            return None
    
    def get_schematic_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current schematic"""
        if not self.connected:
            return None
        
        try:
            response = self.session.get(
                f"{self.server_url}/altium/schematic/info",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting schematic info: {e}")
            return None
    
    def get_project_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the current project"""
        if not self.connected:
            return None
        
        try:
            response = self.session.get(
                f"{self.server_url}/altium/project/info",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting project info: {e}")
            return None
    
    def get_verification_report(self) -> Optional[Dict[str, Any]]:
        """Get verification (DRC/ERC) report - DEPRECATED: Use run_drc() instead"""
        # This endpoint doesn't exist - use run_drc() instead
        print("Warning: get_verification_report() is deprecated. Use run_drc() instead.")
        return None
    
    def get_output_result(self) -> Optional[Dict[str, Any]]:
        """Get output generation result"""
        if not self.connected:
            return None
        
        try:
            response = self.session.get(
                f"{self.server_url}/altium/output/result",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting output result: {e}")
            return None
    
    def get_design_rules(self) -> Optional[Dict[str, Any]]:
        """Get design rules information"""
        if not self.connected:
            return None
        
        try:
            response = self.session.get(
                f"{self.server_url}/altium/design/rules",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting design rules: {e}")
            return None
    
    def get_board_config(self) -> Optional[Dict[str, Any]]:
        """Get board configuration information"""
        if not self.connected:
            return None
        
        try:
            response = self.session.get(
                f"{self.server_url}/altium/board/config",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting board config: {e}")
            return None
    
    def get_component_search(self) -> Optional[Dict[str, Any]]:
        """Get component search results"""
        if not self.connected:
            return None
        
        try:
            response = self.session.get(
                f"{self.server_url}/altium/component/search",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting component search: {e}")
            return None
    
    def get_library_list(self) -> Optional[Dict[str, Any]]:
        """Get list of installed libraries"""
        if not self.connected:
            return None
        
        try:
            response = self.session.get(
                f"{self.server_url}/altium/libraries",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting library list: {e}")
            return None
    
    def get_files_status(self) -> Optional[Dict[str, Any]]:
        """Get status of all data files"""
        if not self.connected:
            return None
        
        try:
            response = self.session.get(
                f"{self.server_url}/altium/files",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting files status: {e}")
            return None
    
    def set_document_type(self, doc_type: str):
        """Set the active document type (PCB, SCH, PRJ)"""
        if doc_type in [self.DOC_PCB, self.DOC_SCHEMATIC, self.DOC_PROJECT]:
            self.active_document_type = doc_type
    
    def get_current_document_info(self) -> Optional[Dict[str, Any]]:
        """Get info for the currently active document type"""
        if self.active_document_type == self.DOC_PCB:
            return self.get_pcb_info()
        elif self.active_document_type == self.DOC_SCHEMATIC:
            return self.get_schematic_info()
        elif self.active_document_type == self.DOC_PROJECT:
            return self.get_project_info()
        return None
    
    # ==========================================
    # New Python-based MCP Server Methods
    # ==========================================
    
    def load_pcb_file(self, pcb_path: str) -> Optional[Dict[str, Any]]:
        """
        Load a PCB file directly using Python file reader
        NO Altium scripts needed!
        
        Args:
            pcb_path: Path to .PcbDoc file
            
        Returns:
            dict with loading result
        """
        try:
            response = self.session.post(
                f"{self.server_url}/pcb/load",
                json={"path": pcb_path},
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    self.connected = True
                return result
            return {"error": f"Server error: {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def load_from_altium_export(self, pcb_info_path: str = None) -> Optional[Dict[str, Any]]:
        """
        Load PCB data from Altium-exported JSON files
        
        Note: DRC violations are computed by the Python DRC engine via run_drc(),
        not loaded from pre-existing files.
        
        Args:
            pcb_info_path: Path to altium_pcb_info.json (optional, auto-detects)
            
        Returns:
            dict with loading result
        """
        try:
            payload = {}
            if pcb_info_path:
                payload["pcb_info_path"] = pcb_info_path
            
            response = self.session.post(
                f"{self.server_url}/pcb/load-altium-export",
                json=payload,
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    self.connected = True
                return result
            return {"error": f"Server error: {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_routing_suggestions(self) -> Optional[Dict[str, Any]]:
        """Get routing suggestions for the loaded PCB"""
        try:
            response = self.session.get(
                f"{self.server_url}/routing/suggestions",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error getting routing suggestions: {e}")
            return None
    
    def route_net(self, net_id: str, start: list, end: list, 
                  layer: str = "L1", width: float = 0.25) -> Optional[Dict[str, Any]]:
        """
        Route a net on the PCB
        
        Args:
            net_id: Net identifier
            start: Start position [x, y]
            end: End position [x, y]
            layer: Layer ID (default L1)
            width: Track width in mm
            
        Returns:
            dict with routing result
        """
        try:
            response = self.session.post(
                f"{self.server_url}/routing/route",
                json={
                    "net_id": net_id,
                    "start": start,
                    "end": end,
                    "layer": layer,
                    "width": width
                },
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return {"error": f"Server error: {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def place_via(self, net_id: str, position: list, 
                  layers: list = None, drill: float = 0.3) -> Optional[Dict[str, Any]]:
        """
        Place a via on the PCB
        
        Args:
            net_id: Net identifier
            position: Position [x, y]
            layers: Layer IDs (default ["L1", "L4"])
            drill: Drill size in mm
            
        Returns:
            dict with via placement result
        """
        try:
            response = self.session.post(
                f"{self.server_url}/routing/via",
                json={
                    "net_id": net_id,
                    "position": position,
                    "layers": layers or ["L1", "L4"],
                    "drill": drill
                },
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return {"error": f"Server error: {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def run_drc(self) -> Optional[Dict[str, Any]]:
        """
        Run DRC check on the loaded PCB
        
        Returns:
            dict with DRC violations
        """
        try:
            response = self.session.get(
                f"{self.server_url}/drc/run",
                timeout=MCP_TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error running DRC: {e}")
            return None

