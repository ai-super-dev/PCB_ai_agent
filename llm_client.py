"""
OpenAI LLM Client for Agent Capabilities
"""
from openai import OpenAI
import httpx
from typing import Optional, Dict, Any, Iterator
from config import OPENAI_API_KEY, OPENAI_MODEL
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class LLMClient:
    """Client for OpenAI API integration"""
    
    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in environment variables")
        
        # Create custom HTTP client that bypasses system proxy
        http_client = httpx.Client(
            trust_env=False,  # Don't use system proxy settings
            timeout=60.0,     # 60 second timeout
        )
        
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            http_client=http_client
        )
        self.model = OPENAI_MODEL
        logger.info(f"LLM Client initialized with model: {self.model}")
    
    def chat(self, messages: list, temperature: float = 0.7) -> Optional[str]:
        """
        Send chat messages to OpenAI
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Sampling temperature (0-2)
        
        Returns:
            Response text or None if error
        """
        try:
            logger.info(f"Sending request to OpenAI ({len(messages)} messages)")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature
            )
            logger.info("OpenAI response received successfully")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            print(f"Error calling OpenAI API: {e}")
            return None
    
    def chat_stream(self, messages: list, temperature: float = 0.7) -> Iterator[str]:
        """
        Send chat messages to OpenAI with streaming
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Sampling temperature (0-2)
        
        Yields:
            Text chunks as they arrive
        """
        try:
            logger.info(f"Sending streaming request to OpenAI ({len(messages)} messages)")
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=True
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            logger.info("OpenAI streaming response completed")
        except Exception as e:
            logger.error(f"Error calling OpenAI API (streaming): {e}")
            print(f"Error calling OpenAI API (streaming): {e}")
            yield None
    
    def analyze_pcb_query(self, user_query: str, pcb_info: Dict[str, Any] = None) -> Optional[str]:
        """
        Analyze user query about PCB and provide response
        
        Args:
            user_query: User's question or request
            pcb_info: Optional PCB information from MCP
        
        Returns:
            Analysis response or None
        """
        system_prompt = """You are an expert PCB design assistant. You help users analyze and modify PCB designs in Altium Designer.
        Provide clear, technical, and helpful responses about PCB design questions."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]
        
        if pcb_info:
            # Summarize PCB info to avoid token limits
            stats = pcb_info.get("statistics", {})
            summary = f"PCB: {pcb_info.get('file_name', 'Unknown')}, "
            summary += f"{stats.get('component_count', 0)} components, "
            summary += f"{stats.get('net_count', 0)} nets, "
            summary += f"{stats.get('layer_count', 0)} layers"
            messages.append({
                "role": "assistant",
                "content": f"PCB Summary: {summary}"
            })
        
        return self.chat(messages)
    
    def generate_modification_command(self, user_request: str, pcb_info: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """
        Generate MCP command from user's modification request
        
        Args:
            user_request: User's modification request
            pcb_info: Optional PCB information
        
        Returns:
            Dictionary with 'command' and 'parameters' or None
        """
        system_prompt = """You are a PCB design assistant that converts user requests into structured MCP commands for Altium Designer.
        Return your response as a JSON object with 'command' (string) and 'parameters' (dict) fields.
        
        Available commands:
        
        1. move_component - Move a component to a new position
           {"command": "move_component", "parameters": {"component_id": "R1", "x_position": 100.0, "y_position": 200.0}}
        
        2. rotate_component - Rotate a component
           {"command": "rotate_component", "parameters": {"component_id": "R1", "rotation": 90}}
        
        3. remove_component - Remove a component from PCB
           {"command": "remove_component", "parameters": {"component_id": "R1"}}
        
        4. change_component_value (also accepts modify_component_value) - Change component value/parameter
           {"command": "change_component_value", "parameters": {"component_id": "R1", "value": "22k"}}
           Note: Use "component_id" or "component_name" for component identifier
        
        5. add_track - Add a track between two points
           {"command": "add_track", "parameters": {"start_x": 10.0, "start_y": 20.0, "end_x": 50.0, "end_y": 20.0, "layer": "Top Layer", "width": 0.2}}
        
        6. add_via - Add a via at a location
           {"command": "add_via", "parameters": {"x_position": 25.0, "y_position": 30.0, "size": 0.5, "hole_size": 0.2}}
        
        7. change_layer - Move component to different layer
           {"command": "change_layer", "parameters": {"component_id": "R1", "layer": "Bottom Layer"}}
        
        8. add_component - Add a new component to PCB
           {"command": "add_component", "parameters": {"component_id": "R200", "footprint": "RES-0805", "value": "10k", "x_position": 100.0, "y_position": 200.0, "layer": "Top Layer", "rotation": 0}}
        
        9. connect_net - Connect component pin to net
           {"command": "connect_net", "parameters": {"component_id": "R1", "pin": "1", "net_name": "VCC"}}
        
        10. set_board_size - Change board dimensions
            {"command": "set_board_size", "parameters": {"width_mm": 100.0, "height_mm": 80.0}}
        
        All coordinates are in millimeters (mm). Rotations are in degrees. Layer names: "Top Layer" or "Bottom Layer".
        Always use "component_id" for component names. Use "x_position" and "y_position" for coordinates."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request}
        ]
        
        if pcb_info:
            # Summarize PCB info to avoid token limits
            stats = pcb_info.get("statistics", {})
            summary = f"PCB: {pcb_info.get('file_name', 'Unknown')}, "
            summary += f"{stats.get('component_count', 0)} components, "
            summary += f"{stats.get('net_count', 0)} nets"
            messages.append({
                "role": "assistant",
                "content": f"PCB Summary: {summary}"
            })
        
        response = self.chat(messages, temperature=0.3)
        
        if response:
            try:
                import json
                return json.loads(response)
            except:
                return None
        return None

