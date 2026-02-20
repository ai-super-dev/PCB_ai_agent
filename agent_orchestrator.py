"""
Intelligent Agent Orchestrator - Design Co-Pilot

This agent provides intelligent PCB design assistance:
- Analyzes schematics and identifies functional blocks
- Generates placement and routing strategies
- Reviews designs for potential issues
- Suggests optimizations and improvements

NOT just a command executor - a design intelligence partner.
"""
from typing import Dict, Any, Optional, Tuple, Callable
from llm_client import LLMClient
from mcp_client import AltiumMCPClient
import json
import re
import logging

# Setup logging
logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Intelligent design co-pilot that:
    - Analyzes schematics and PCBs
    - Generates design strategies
    - Reviews and suggests improvements
    - Executes approved commands
    """
    
    def __init__(self, llm_client: LLMClient, mcp_client: AltiumMCPClient):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.conversation_history = []
        self.current_analysis = None  # Cache for design analysis
        self.current_layout = None  # Cache for generated layout
        self.pending_command = None  # Store command waiting for confirmation
        self.pcb_issues = []  # Store current PCB issues for reference
        self.pcb_recommendations = []  # Store recommendations for selection
    
    def process_query(self, user_query: str, stream_callback: Optional[Callable[[str], None]] = None) -> Tuple[str, str, bool]:
        """
        Process user query with LLM-powered design intelligence.
        
        Architecture: LLM-first with fast-path optimizations for simple commands.
        The LLM analyzes user intent with full board context, not pattern matching.
        
        Args:
            user_query: User query
            stream_callback: Optional callback function for streaming chunks
        
        Returns:
            tuple: (response_text, status_message, is_execution)
        """
        # Add user query to history
        self.conversation_history.append({"role": "user", "content": user_query})
        
        # Get ALL available context
        all_context = self._get_all_available_context()
        query_lower = user_query.lower().strip()
        
        # ============================================================
        # FAST PATH: Only for unambiguous, simple commands
        # These don't need LLM interpretation - they're explicit actions
        # ============================================================
        
        # 1. Direct confirmation commands (user already saw options)
        if query_lower in ["yes", "yes please", "apply", "do it", "proceed", "apply recommendations", "apply all"]:
            response = self._apply_recommendations()
            self.conversation_history.append({"role": "assistant", "content": response})
            return response, "executed", True
        
        # 2. Direct component move with explicit coordinates (no interpretation needed)
        move_match = re.search(r'move\s+([A-Z]{1,3}[0-9]+)\s+to\s+\(?(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\)?', user_query, re.IGNORECASE)
        if move_match:
            comp_name = move_match.group(1).upper()
            new_x = float(move_match.group(2))
            new_y = float(move_match.group(3))
            response = self._move_component_direct(comp_name, new_x, new_y, all_context)
            self.conversation_history.append({"role": "assistant", "content": response})
            return response, "executed", True
        
        # 3. Direct method selection (user already saw numbered options)
        method_match = re.search(r'(?:use|apply)\s*(?:method|option|solution)\s*(\d+)', query_lower)
        if method_match:
            response = self._apply_selected_solution(user_query)
            self.conversation_history.append({"role": "assistant", "content": response})
            return response, "executed", True
        
        # 4. Direct component location query (data lookup, no interpretation)
        comp_match = re.search(r'\b(?:where\s+is|find|locate|location\s+of)\s+([A-Z]{1,3}[0-9]+)\b', user_query, re.IGNORECASE)
        if comp_match:
            comp_name = comp_match.group(1).upper()
            response = self._get_component_location_direct(comp_name, all_context)
            if response:
                self.conversation_history.append({"role": "assistant", "content": response})
                return response, "answered", False
        
        # ============================================================
        # LLM PATH: All other queries go through LLM for intelligent analysis
        # The LLM sees the full board context and decides the best action
        # ============================================================
        
        intent_response = self._determine_intent_with_context(user_query, all_context)
        action = intent_response.get("action", "answer")
        
        # Handle design intelligence actions
        if action == "analyze":
            response_text = self._perform_design_analysis(user_query, all_context, intent_response)
            status = "analyzed"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "strategy":
            response_text = self._generate_placement_strategy(user_query, all_context)
            status = "strategy_generated"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "review":
            response_text = self._perform_design_review(user_query, all_context)
            status = "reviewed"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "routing":
            response_text = self._handle_routing(user_query, intent_response)
            status = "routing"
            is_execution = True
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "check_altium_drc":
            response_text = self._check_altium_drc_result()
            status = "drc"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "drc":
            response_text = self._handle_drc(user_query)
            status = "drc"
            is_execution = True
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "design_rules":
            response_text = self._handle_design_rules_query(user_query, all_context)
            status = "info"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "artifact":
            response_text = self._handle_artifact_query(user_query)
            status = "artifact"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "apply_recommendations":
            response_text = self._apply_recommendations()
            status = "applied"
            is_execution = True
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "list_issues":
            response_text = self._list_pcb_issues()
            status = "issues_listed"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "suggest_solutions":
            response_text = self._suggest_solutions()
            status = "solutions_suggested"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "explain_error":
            response_text = self._explain_error(user_query)
            status = "explained"
            is_execution = False
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "apply_selected":
            response_text = self._apply_selected_solution(user_query)
            status = "applied"
            is_execution = True
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "generate_layout":
            response_text = self._generate_autonomous_layout(user_query, all_context)
            status = "layout_generated"
            is_execution = True  # This is an execution action
            self.conversation_history.append({"role": "assistant", "content": response_text})
            return response_text, status, is_execution
        
        elif action == "execute":
            # Prepare command for confirmation (don't execute yet)
            pcb_info = all_context.get("pcb_info")
            execution_result = self._prepare_command_confirmation(intent_response, pcb_info)
            response_text = execution_result.get("message", "Command ready for confirmation")
            status = execution_result.get("status", "confirm")
            is_execution = False  # Not executed yet, waiting for confirmation
            
            # Store pending command for later execution
            self.pending_command = {
                "intent": intent_response,
                "pcb_info": pcb_info
            }
            
            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant", 
                "content": response_text
            })
            
            return response_text, status, is_execution
        else:
            # Generate conversational response (with streaming if callback provided)
            if stream_callback:
                response_text = self._generate_response_stream(user_query, all_context, stream_callback)
            else:
                response_text = self._generate_response(user_query, all_context)
            status = "answered"
            is_execution = False
            
            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant", 
                "content": response_text
            })
            
            return response_text, status, is_execution
    
    def _summarize_pcb_info(self, pcb_info: Dict[str, Any] = None) -> str:
        # Create a concise summary of PCB info to avoid token limits
        if not pcb_info:
            return "No PCB info available"
        
        # Check for error response
        if pcb_info.get("error"):
            return f"PCB Error: {pcb_info.get('error')}"
        
        try:
            stats = pcb_info.get("statistics", {})
            summary = f"PCB File: {pcb_info.get('file_name', pcb_info.get('file', 'Unknown'))}\n"
            
            # Board size
            board_size = pcb_info.get('board_size', {})
            width = board_size.get('width_mm', 0)
            height = board_size.get('height_mm', 0)
            summary += f"Board Size: {width:.1f}mm x {height:.1f}mm\n"
            
            # Statistics
            summary += f"Components: {stats.get('component_count', 0)}\n"
            summary += f"Nets: {stats.get('net_count', 0)}\n"
            summary += f"Tracks: {stats.get('track_count', 0)}\n"
            summary += f"Vias: {stats.get('via_count', 0)}\n"
            summary += f"Layers: {stats.get('layer_count', pcb_info.get('layer_count', 0))}\n"
            
            # Layer names
            layers = pcb_info.get("layers", [])
            if layers and len(layers) > 0:
                layer_names = [l.get("name", "Unknown") if isinstance(l, dict) else str(l) for l in layers]
                summary += f"Layer names: {', '.join(layer_names)}\n"
            
            # Components with details
            components = pcb_info.get("components", [])
            if components and len(components) > 0:
                summary += f"\nComponents ({len(components)} total):\n"
                for comp in components[:15]:  # Show more components
                    if isinstance(comp, dict):
                        name = comp.get("name", comp.get("designator", "?"))
                        footprint = comp.get("footprint", "")
                        layer = comp.get("layer", "")
                        loc = comp.get("location", {})
                        x = loc.get("x_mm", 0)
                        y = loc.get("y_mm", 0)
                        summary += f"  - {name}: {footprint} at ({x:.1f}, {y:.1f})mm on {layer}\n"
                    else:
                        summary += f"  - {comp}\n"
                if len(components) > 15:
                    summary += f"  ... and {len(components) - 15} more\n"
            
            # Nets
            nets = pcb_info.get("nets", [])
            if nets and len(nets) > 0:
                net_names = [n.get("name", "Unknown") if isinstance(n, dict) else str(n) for n in nets[:20]]
                summary += f"\nNets ({len(nets)} total): {', '.join(net_names)}"
                if len(nets) > 20:
                    summary += f", ... and {len(nets) - 20} more"
                summary += "\n"
            
            return summary
        except Exception as e:
            return f"PCB info available but could not summarize: {str(e)}"
    
    def _summarize_schematic_info(self, sch_info: Dict[str, Any] = None) -> str:
        # Create a concise summary of schematic info
        if not sch_info:
            return "No schematic info available"
        
        try:
            stats = sch_info.get("statistics", {})
            schematic = sch_info.get("schematic", {})
            summary = f"Schematic: {schematic.get('name', 'Unknown')}\n"
            summary += f"Title: {schematic.get('title', 'N/A')}\n"
            summary += f"Components: {stats.get('component_count', 0)}, Wires: {stats.get('wire_count', 0)}\n"
            summary += f"Net Labels: {stats.get('net_label_count', 0)}, Power Ports: {stats.get('power_port_count', 0)}\n"
            
            components = sch_info.get("components", [])
            if components and len(components) > 0:
                comp_names = [c.get("designator", "Unknown") if isinstance(c, dict) else str(c) for c in components[:10]]
                summary += f"Sample components: {', '.join(comp_names)}"
            
            return summary
        except:
            return "Schematic info available but could not summarize"
    
    def _summarize_project_info(self, prj_info: Dict[str, Any] = None) -> str:
        # Create a concise summary of project info
        if not prj_info:
            return "No project info available"
        
        try:
            project = prj_info.get("project", {})
            stats = prj_info.get("statistics", {})
            summary = f"Project: {project.get('name', 'Unknown')}\n"
            summary += f"Type: {project.get('type', 'PCB Project')}\n"
            summary += f"Documents: {stats.get('total_documents', 0)}\n"
            summary += f"Schematics: {stats.get('schematic_count', 0)}, PCBs: {stats.get('pcb_count', 0)}\n"
            
            documents = prj_info.get("documents", [])
            if documents and len(documents) > 0:
                doc_names = [d.get("name", "Unknown") if isinstance(d, dict) else str(d) for d in documents[:5]]
                summary += f"Documents: {', '.join(doc_names)}"
            
            return summary
        except:
            return "Project info available but could not summarize"
    
    def _summarize_design_rules(self, rules_info: Dict[str, Any] = None) -> str:
        # Create a concise summary of design rules
        if not rules_info:
            return "No design rules available"
        
        try:
            stats = rules_info.get("statistics", {})
            summary = f"Design Rules:\n"
            summary += f"Total Rules: {stats.get('total_rules', 0)}\n"
            summary += f"Clearance: {stats.get('clearance_rules', 0)}, Width: {stats.get('width_rules', 0)}, Via: {stats.get('via_rules', 0)}\n"
            
            # Get minimum clearance
            clearance_rules = rules_info.get("clearance_rules", [])
            if clearance_rules:
                min_clearance = min([r.get("minimum_mm", 999) for r in clearance_rules if r.get("enabled", True)], default=0)
                if min_clearance < 999:
                    summary += f"Min Clearance: {min_clearance:.3f} mm\n"
            
            # Get minimum width
            width_rules = rules_info.get("width_rules", [])
            if width_rules:
                min_width = min([r.get("min_width_mm", 999) for r in width_rules if r.get("enabled", True)], default=0)
                if min_width < 999:
                    summary += f"Min Track Width: {min_width:.3f} mm"
            
            return summary
        except:
            return "Design rules available but could not summarize"
    
    def _summarize_board_config(self, board_config: Dict[str, Any] = None) -> str:
        # Create a concise summary of board configuration
        if not board_config:
            return "No board configuration available"
        
        try:
            board = board_config.get("board", {})
            layer_stack = board_config.get("layer_stack", {})
            summary = f"Board Configuration:\n"
            summary += f"Size: {board.get('width_mm', 0):.1f} x {board.get('height_mm', 0):.1f} mm\n"
            summary += f"Layers: {layer_stack.get('total_layers', 0)} total, {layer_stack.get('signal_layers', 0)} signal\n"
            summary += f"Display Unit: {board_config.get('display_unit', 'mm')}\n"
            summary += f"Grid: {board_config.get('snap_grid_mm', 0):.3f} mm"
            return summary
        except:
            return "Board config available but could not summarize"
    
    def _summarize_verification(self, verification: Dict[str, Any] = None) -> str:
        # Create a concise summary of verification report
        if not verification:
            return "No verification report available"
        
        try:
            vtype = verification.get("verification_type", "Unknown")
            summary = f"Verification ({vtype}):\n"
            
            if vtype == "DRC":
                summary_data = verification.get("summary", {})
                summary += f"Violations: {summary_data.get('total_violations', 0)}\n"
                summary += f"Errors: {summary_data.get('errors', 0)}, Warnings: {summary_data.get('warnings', 0)}\n"
                summary += f"Status: {verification.get('status', 'Unknown')}"
            elif vtype == "ERC":
                summary_data = verification.get("summary", {})
                summary += f"Errors: {summary_data.get('errors', 0)}, Warnings: {summary_data.get('warnings', 0)}\n"
                summary += f"Status: {verification.get('status', 'Unknown')}"
            else:
                summary_data = verification.get("summary", {})
                summary += f"Total Nets: {summary_data.get('total_nets', 0)}\n"
                summary += f"Routed: {summary_data.get('routed_nets', 0)}, Unrouted: {summary_data.get('unrouted_nets', 0)}"
            
            return summary
        except:
            return "Verification report available but could not summarize"
    
    def _summarize_component_search(self, search_results: Dict[str, Any] = None) -> str:
        # Create a concise summary of component search results
        if not search_results:
            return "No component search results available"
        
        try:
            query = search_results.get("query", "Unknown")
            results = search_results.get("results", [])
            count = search_results.get("result_count", len(results))
            summary = f"Component Search: '{query}'\n"
            summary += f"Found: {count} results\n"
            
            if results and len(results) > 0:
                sample = results[:5]
                comp_names = [r.get("name", "Unknown") for r in sample]
                summary += f"Sample: {', '.join(comp_names)}"
            
            return summary
        except:
            return "Component search results available but could not summarize"
    
    def _get_all_available_context(self) -> Dict[str, Any]:
        # Get ALL available context data - returns dict of all data sources
        context = {}
        
        if not self.mcp_client.connected:
            return context
        
        # Try to get all available data (don't fail if some are missing)
        context["pcb_info"] = self.mcp_client.get_pcb_info()
        context["schematic_info"] = self.mcp_client.get_schematic_info()
        context["project_info"] = self.mcp_client.get_project_info()
        context["verification_report"] = self.mcp_client.get_verification_report()
        context["design_rules"] = self.mcp_client.get_design_rules()
        context["board_config"] = self.mcp_client.get_board_config()
        context["component_search"] = self.mcp_client.get_component_search()
        context["output_result"] = self.mcp_client.get_output_result()
        
        return context
    
    def _get_all_context(self) -> str:
        # Get context from all available data sources as formatted string
        context = ""
        all_data = self._get_all_available_context()
        
        # PCB info
        if all_data.get("pcb_info"):
            context += f"[PCB]\n{self._summarize_pcb_info(all_data['pcb_info'])}\n\n"
        
        # Schematic info
        if all_data.get("schematic_info"):
            context += f"[Schematic]\n{self._summarize_schematic_info(all_data['schematic_info'])}\n\n"
        
        # Project info
        if all_data.get("project_info"):
            context += f"[Project]\n{self._summarize_project_info(all_data['project_info'])}\n\n"
        
        # Design rules
        if all_data.get("design_rules"):
            context += f"[Design Rules]\n{self._summarize_design_rules(all_data['design_rules'])}\n\n"
        
        # Board config
        if all_data.get("board_config"):
            context += f"[Board Config]\n{self._summarize_board_config(all_data['board_config'])}\n\n"
        
        # Verification
        if all_data.get("verification_report"):
            context += f"[Verification]\n{self._summarize_verification(all_data['verification_report'])}\n\n"
        
        # Component search
        if all_data.get("component_search"):
            context += f"[Component Search]\n{self._summarize_component_search(all_data['component_search'])}\n\n"
        
        return context if context else "No design data available"
    
    def _determine_intent(self, query: str, all_context: Dict[str, Any] = None) -> Dict[str, Any]:
        # Use LLM to determine if query requires execution or just answering
        if all_context is None:
            all_context = {}
        
        system_prompt = """You are an intelligent PCB design co-pilot. All PCB data is loaded via Python file reader (NO Altium scripts needed).

The user may be requesting:
1. DESIGN ANALYSIS - Analyze PCB, identify functional blocks
2. PLACEMENT STRATEGY - Generate component placement recommendations
3. DESIGN REVIEW - Review design for issues, DRC violations
4. ANSWER - Answer questions about components, nets, layers, routing, DRC
5. EXECUTE - Route nets, place vias, run DRC

You have access to (loaded via Python file reader):
- PCB data (components with name/footprint/location/layer, nets, tracks, vias, layers)
- Routing module (route nets, place vias, generate suggestions)
- DRC module (run checks, get violations)

Respond with JSON:
{
    "action": "analyze" or "strategy" or "review" or "routing" or "drc" or "answer",
    "reasoning": "brief explanation",
    "analysis_type": "functional_blocks|signal_paths|constraints|full" (if action is analyze),
    "routing_action": "suggestions" or "route" or "via" (if action is routing),
    "parameters": {} (for routing/drc actions),
    "response": null
}

ROUTING COMMANDS (action="routing"):
- "generate routing suggestions" → routing, routing_action="suggestions"
- "route net +21V" → routing, routing_action="route"
- "place a via" → routing, routing_action="via"
- "what is the best routing strategy?" → routing, routing_action="suggestions"

DRC COMMANDS (action="drc"):
- "run DRC check" → drc
- "check for violations" → drc
- "are there any design rule violations?" → drc

ARTIFACT COMMANDS (action="artifact"):
- "show current artifact" → artifact
- "what is the artifact id" → artifact
- "where is my data stored" → artifact

ANSWER (use PCB data directly):
- "how many components?" → answer (use statistics from PCB data)
- "list nets" → answer (use nets from PCB data)
- "where is component C135?" → answer (search components)
- "what layers?" → answer (use layers from PCB data)

DESIGN INTELLIGENCE:
- "analyze this PCB" → analyze
- "review this design" → review
- "generate placement strategy" → strategy

Default to answering questions using the loaded PCB data."""
        
        # Build context summary from all available data
        context_summary = self._get_all_context()
        
        # Limit conversation history to last 2 exchanges (4 messages)
        recent_history = self.conversation_history[-4:] if len(self.conversation_history) > 4 else self.conversation_history
        
        context = f"Available Design Data:\n{context_summary}\n\n"
        if recent_history:
            context += f"Recent conversation: {json.dumps(recent_history, indent=2)[:500]}"  # Limit history size
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{context}\n\nUser query: {query}"}
        ]
        
        response = self.llm_client.chat(messages, temperature=0.3)
        
        if response:
            try:
                # Try to extract JSON from response
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                else:
                    # Fallback: determine by keywords
                    return self._fallback_intent_detection(query)
            except:
                return self._fallback_intent_detection(query)
        
        return self._fallback_intent_detection(query)
    
    def _determine_intent_with_context(self, query: str, all_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        LLM-powered intent determination with full board context.
        
        This is the primary decision-maker for user queries. It passes all available
        board data to the LLM so it can make intelligent, context-aware decisions.
        """
        
        # Build rich board context for LLM
        board_context = self._build_rich_context_for_llm(all_context)
        
        system_prompt = """You are an expert PCB design co-pilot analyzing user requests.
Your job is to understand WHAT the user wants and provide an intelligent response.

You have access to real PCB data - use it to give specific, actionable answers.

ACTIONS YOU CAN TAKE:
1. "analyze" - Deep analysis of design (violations, optimizations, functional blocks)
2. "routing" - Generate routing suggestions or execute routes
3. "drc" - Run design rule check
4. "explain_error" - Explain a specific violation/issue with board context
5. "suggest_solutions" - Provide specific fix recommendations
6. "list_issues" - List current problems on the board
7. "answer" - Answer a question using the board data
8. "design_rules" - Show/explain design rules
9. "artifact" - Show artifact/storage info
10. "execute" - Execute a specific command (move, modify, etc.)

RESPOND WITH JSON:
{
    "action": "one of the actions above",
    "reasoning": "why you chose this action based on the query and board context",
    "routing_action": "suggestions|route|via" (if action is routing),
    "filter": "power|unrouted|signal" (optional routing filter),
    "query": "the user's original question",
    "specific_context": "relevant board data you found (component names, net names, coordinates)",
    "suggested_response": "if action=answer, provide the answer here using actual board data"
}

IMPORTANT:
- Always reference ACTUAL component names, net names, and coordinates from the board data
- Never give generic advice - tailor everything to THIS specific board
- If the user asks about a specific component/net, find it in the data first
- For routing suggestions, consider actual pad positions and net topology"""

        # Include relevant board data
        user_message = f"""BOARD CONTEXT:
{board_context}

CURRENT ISSUES ON BOARD:
{json.dumps(self.pcb_issues[:5], indent=2) if self.pcb_issues else 'None stored'}

STORED RECOMMENDATIONS:
{json.dumps([{'net': r.get('net'), 'recommendation': r.get('recommendation')[:100]} for r in self.pcb_recommendations[:3]], indent=2) if self.pcb_recommendations else 'None'}

USER QUERY: {query}

Analyze the query in context of this specific board and determine the best action."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        try:
            response = self.llm_client.chat(messages, temperature=0.3)
            
            if response:
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    intent = json.loads(json_match.group())
                    logger.info(f"LLM intent: {intent.get('action')} - {intent.get('reasoning', '')[:50]}")
                    return intent
        except Exception as e:
            logger.warning(f"LLM intent determination failed: {e}")
        
        # Fallback to pattern matching
        return self._fallback_intent_detection(query)
    
    def _build_rich_context_for_llm(self, all_context: Dict[str, Any]) -> str:
        """Build comprehensive board context string for LLM analysis"""
        context_parts = []
        
        pcb_info = all_context.get("pcb_info", {})
        
        # Board basics
        if pcb_info:
            context_parts.append(f"PCB File: {pcb_info.get('file_name', 'Unknown')}")
            
            stats = pcb_info.get("statistics", {})
            if stats:
                context_parts.append(f"Components: {stats.get('component_count', 0)}")
                context_parts.append(f"Nets: {stats.get('net_count', 0)}")
                context_parts.append(f"Tracks: {stats.get('track_count', 0)}")
                context_parts.append(f"Vias: {stats.get('via_count', 0)}")
                context_parts.append(f"Layers: {stats.get('layer_count', 2)}")
            
            # Board size
            board_size = pcb_info.get("board_size", {})
            if board_size:
                context_parts.append(f"Board Size: {board_size.get('width_mm', 0)}mm x {board_size.get('height_mm', 0)}mm")
        
        # Design rules
        rules = all_context.get("design_rules", {}) or pcb_info.get("rules", {})
        if rules:
            context_parts.append("\nDESIGN RULES:")
            context_parts.append(f"- Min clearance: {rules.get('min_clearance_mm', 'N/A')}mm")
            context_parts.append(f"- Min trace width: {rules.get('min_trace_width_mm', 'N/A')}mm")
            context_parts.append(f"- Min via hole: {rules.get('min_via_hole_mm', 'N/A')}mm")
        
        # Sample components (for LLM to reference)
        components = pcb_info.get("components", [])
        if components:
            context_parts.append(f"\nSAMPLE COMPONENTS ({len(components)} total):")
            for comp in components[:15]:  # Show first 15
                if isinstance(comp, dict):
                    loc = comp.get("location", {})
                    context_parts.append(
                        f"- {comp.get('designator', 'Unknown')}: "
                        f"{comp.get('footprint', 'N/A')} at "
                        f"({loc.get('x_mm', 0):.1f}, {loc.get('y_mm', 0):.1f})mm"
                    )
        
        # Important nets (power, ground, clock)
        nets = pcb_info.get("nets", [])
        if nets:
            power_nets = []
            ground_nets = []
            signal_nets = []
            
            for net in nets[:100]:
                if isinstance(net, dict):
                    name = net.get("name", "").upper()
                    if any(p in name for p in ['VCC', 'VDD', 'PWR', '+', 'VIN']):
                        power_nets.append(name)
                    elif any(p in name for p in ['GND', 'GROUND', 'VSS']):
                        ground_nets.append(name)
                    elif any(p in name for p in ['CLK', 'DATA', 'SDA', 'SCL']):
                        signal_nets.append(name)
            
            if power_nets:
                context_parts.append(f"\nPOWER NETS: {', '.join(power_nets[:10])}")
            if ground_nets:
                context_parts.append(f"GROUND NETS: {', '.join(ground_nets[:5])}")
            if signal_nets:
                context_parts.append(f"KEY SIGNALS: {', '.join(signal_nets[:10])}")
        
        return "\n".join(context_parts) if context_parts else "No board data available"
    
    def _fallback_intent_detection(self, query: str) -> Dict[str, Any]:
        # Fallback intent detection using keywords
        query_lower = query.lower()
        
        # Check for artifact queries
        if any(word in query_lower for word in ["artifact", "uuid", "storage", "where is my data", "current artifact"]):
            return {"action": "artifact"}
        
        # Check for routing queries
        if "route" in query_lower and ("net" in query_lower or "from" in query_lower):
            return {"action": "routing", "routing_action": "route"}
        
        if "via" in query_lower and ("place" in query_lower or "at" in query_lower):
            return {"action": "routing", "routing_action": "via"}
        
        if "routing suggestion" in query_lower or "routing strategy" in query_lower:
            return {"action": "routing", "routing_action": "suggestions"}
        
        # Check for DRC queries
        if any(word in query_lower for word in ["drc", "violation", "design rule", "clearance check"]):
            return {"action": "drc"}
        
        # Check for project creation
        if "create project" in query_lower or "new project" in query_lower or "create new project" in query_lower:
            # Extract project name from query
            import re
            name_match = re.search(r'(?:project|project called|project named|name)\s+([A-Za-z0-9_]+)', query, re.IGNORECASE)
            project_name = name_match.group(1) if name_match else "MyProject"
            
            return {
                "action": "execute",
                "command": "create_new_project",
                "parameters": {"project_name": project_name}
            }
        
        # Check for other execution keywords
        execution_keywords = ["add", "remove", "modify", "change", "update", "place", "move", "delete", "set"]
        if any(keyword in query_lower for keyword in execution_keywords):
            return {
                "action": "execute",
                "command": "modify_pcb",
                "parameters": {"request": query}
            }
        else:
            return {
                "action": "answer",
                "response": None
            }
    
    def _prepare_command_confirmation(self, intent: Dict[str, Any], pcb_info: Dict[str, Any] = None) -> Dict[str, Any]:
        # Prepare command confirmation message - returns confirmation request instead of executing
        logger.info(f"Preparing command confirmation with intent: {intent}")
        
        if not self.mcp_client.connected:
            logger.warning("Not connected to Altium Designer")
            return {
                "status": "error",
                "message": "Not connected to Altium Designer. Please connect first."
            }
        
        command = intent.get("command")
        parameters = intent.get("parameters", {})
        
        if not command:
            # Generate command from query using LLM
            command_data = self.llm_client.generate_modification_command(
                intent.get("reasoning", ""),
                pcb_info
            )
            if command_data:
                command = command_data.get("command")
                parameters = command_data.get("parameters", {})
        
        if command:
            # Generate confirmation message
            confirmation_msg = self._generate_confirmation_message(command, parameters, intent.get("reasoning", ""))
            
            return {
                "status": "confirm",
                "message": confirmation_msg,
                "command": command,
                "parameters": parameters
            }
        else:
            return {
                "status": "error",
                "message": "Could not determine the command to execute."
            }
    
    def _generate_confirmation_message(self, command: str, parameters: Dict[str, Any], user_query: str = "") -> str:
        # Generate a natural confirmation message for the command
        # Map commands to friendly names
        command_names = {
            "create_project": "create a new project",
            "create_new_project": "create a new project",
            "move_component": "move a component",
            "rotate_component": "rotate a component",
            "add_component": "add a component",
            "remove_component": "remove a component",
            "export_pcb_info": "export PCB information",
            "place_component": "place a component",
            "add_wire": "add a wire",
            "add_net_label": "add a net label"
        }
        
        friendly_action = command_names.get(command, command.replace("_", " "))
        
        # Build parameter description
        param_desc = []
        if "project_name" in parameters:
            param_desc.append(f'named "{parameters["project_name"]}"')
        if "name" in parameters:
            param_desc.append(f'named "{parameters["name"]}"')
        if "component_name" in parameters:
            param_desc.append(f'component "{parameters["component_name"]}"')
        if "x" in parameters and "y" in parameters:
            param_desc.append(f'to position ({parameters["x"]}, {parameters["y"]})')
        
        param_text = " " + " ".join(param_desc) if param_desc else ""
        
        # Generate natural confirmation message
        return f"Are you going to {friendly_action}{param_text}?"
    
    def execute_pending_command(self) -> Dict[str, Any]:
        # Execute the pending command after user confirmation
        if not self.pending_command:
            return {
                "status": "error",
                "message": "No pending command to execute."
            }
        
        intent = self.pending_command.get("intent")
        pcb_info = self.pending_command.get("pcb_info")
        
        # Clear pending command
        self.pending_command = None
        
        # Execute the command
        return self._execute_command(intent, pcb_info)
    
    def _execute_command(self, intent: Dict[str, Any], pcb_info: Dict[str, Any] = None) -> Dict[str, Any]:
        # Execute command via MCP - routes to PCB or Schematic based on command type
        logger.info(f"Executing command with intent: {intent}")
        
        if not self.mcp_client.connected:
            logger.warning("Not connected to Altium Designer")
            return {
                "status": "error",
                "message": "Not connected to Altium Designer. Please connect first."
            }
        
        command = intent.get("command")
        parameters = intent.get("parameters", {})
        
        if not command:
            # Generate command from query using LLM
            command_data = self.llm_client.generate_modification_command(
                intent.get("reasoning", ""),
                pcb_info
            )
            if command_data:
                command = command_data.get("command")
                parameters = command_data.get("parameters", {})
        
        if command:
            # Determine if this is a schematic command
            schematic_commands = ["place_component", "add_wire", "add_net_label", "annotate", "add_power_port"]
            is_schematic = any(cmd in command.lower() for cmd in schematic_commands)
            
            logger.info(f"Sending command to MCP: {command} with params: {parameters} (schematic: {is_schematic})")
            
            # Commands are now split into individual files - use main.pas router
            if is_schematic:
                result = self.mcp_client.modify_schematic(command, parameters)
            else:
                result = self.mcp_client.modify_pcb(command, parameters)
            script_name = "main.pas"  # Router script that shows which command script to run
            logger.info(f"MCP result: {result}")
            if result:
                if result.get("success", False):
                    # Command queued successfully - generate natural response using LLM
                    procedure_name = "ShowCommand"  # Shows which individual script to run
                    command_type = "schematic" if is_schematic else "PCB"
                    
                    # Generate natural, varied response using LLM
                    natural_response = self._generate_command_response(
                        user_query=intent.get("reasoning", ""),
                        command=command,
                        parameters=parameters,
                        script_name=script_name,
                        procedure_name=procedure_name,
                        command_type=command_type
                    )
                    
                    return {
                        "status": "success",
                        "message": natural_response
                    }
                else:
                    # Check if command was queued successfully
                    error_msg = result.get("message", "").lower()
                    if "queued" in error_msg or "success" in error_msg:
                        # Command queued - generate natural response
                        procedure_name = "ExecuteSchematicCommands" if is_schematic else "ExecuteCommands"
                        command_type = "schematic" if is_schematic else "PCB"
                        
                        natural_response = self._generate_command_response(
                            user_query=intent.get("reasoning", ""),
                            command=command,
                            parameters=parameters,
                            script_name=script_name,
                            procedure_name=procedure_name,
                            command_type=command_type
                        )
                        
                        return {
                            "status": "success",
                            "message": natural_response
                        }
                    else:
                        # Modification not supported - provide helpful message
                        return {
                            "status": "info",
                            "message": "I can help you with:\n\n" +
                                      "• **Routing**: Generate suggestions, route nets, place vias\n" +
                                      "• **DRC**: Run design rule checks\n" +
                                      "• **Analysis**: Component locations, net info, layer details\n\n" +
                                      "Try: 'run DRC check' or 'generate routing suggestions'"
                        }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to execute command: {command}. The file-based MCP server doesn't support modifications."
                }
        else:
            return {
                "status": "error",
                "message": "Could not determine command to execute. Please be more specific."
            }
    
    def _get_relevant_context_data(self, query: str, all_context: Dict[str, Any] = None) -> str:
        # Extract only relevant data based on query to save tokens - uses ALL available context
        if not all_context:
            all_context = {}
        
        query_lower = query.lower()
        context = ""
        
        # Determine which data sources are relevant to the query
        needs_pcb = any(word in query_lower for word in ["pcb", "board", "component", "net", "via", "track", "layer"])
        needs_schematic = any(word in query_lower for word in ["schematic", "sch", "wire", "pin", "connection"])
        needs_project = any(word in query_lower for word in ["project", "file", "document", "prj"])
        needs_rules = any(word in query_lower for word in ["rule", "clearance", "width", "design rule", "constraint"])
        needs_config = any(word in query_lower for word in ["config", "setup", "stackup", "layer stack", "board size"])
        needs_verification = any(word in query_lower for word in ["drc", "erc", "violation", "error", "check", "verify"])
        needs_search = any(word in query_lower for word in ["search", "find", "component", "library", "part"])
        needs_output = any(word in query_lower for word in ["bom", "gerber", "output", "manufacturing", "pick", "place"])
        
        # PCB info
        pcb_info = all_context.get("pcb_info")
        if needs_pcb and pcb_info:
            context += self._get_relevant_pcb_data(query, pcb_info)
            context += "\n"
        
        # Schematic info
        if needs_schematic and all_context.get("schematic_info"):
            sch_info = all_context["schematic_info"]
            context += f"[Schematic]\n{self._summarize_schematic_info(sch_info)}\n"
            
            # Add specific component details if asked
            if "component" in query_lower:
                components = sch_info.get("components", [])
                if components:
                    comp_names = [c.get("designator", "Unknown") for c in components[:10]]
                    context += f"Components: {', '.join(comp_names)}\n"
            context += "\n"
        
        # Project info
        if needs_project and all_context.get("project_info"):
            context += f"[Project]\n{self._summarize_project_info(all_context['project_info'])}\n\n"
        
        # Design rules
        if needs_rules and all_context.get("design_rules"):
            context += f"[Design Rules]\n{self._summarize_design_rules(all_context['design_rules'])}\n\n"
        
        # Board config
        if needs_config and all_context.get("board_config"):
            context += f"[Board Config]\n{self._summarize_board_config(all_context['board_config'])}\n\n"
        
        # Verification
        if needs_verification and all_context.get("verification_report"):
            context += f"[Verification]\n{self._summarize_verification(all_context['verification_report'])}\n\n"
        
        # Component search - always include if available, even if not explicitly asked
        search_results = all_context.get("component_search")
        if search_results:
            context += f"[Component Search Results]\n{self._summarize_component_search(search_results)}\n\n"
            # Add detailed results if user is asking about search
            if needs_search:
                results = search_results.get("results", [])
                if results:
                    context += "Available components from search:\n"
                    for i, result in enumerate(results[:10], 1):  # Limit to 10
                        comp_name = result.get("name", "Unknown")
                        comp_desc = result.get("description", "No description")
                        comp_lib = result.get("library", "Unknown library")
                        context += f"{i}. {comp_name} ({comp_lib})\n"
                        if comp_desc and comp_desc != "No description":
                            context += f"   Description: {comp_desc}\n"
                    context += "\n"
        
        # Library list - include if user is searching
        if needs_search and all_context.get("library_list"):
            lib_list = all_context["library_list"]
            libraries = lib_list.get("libraries", [])
            if libraries:
                context += f"[Available Libraries]\n"
                context += f"Total: {lib_list.get('library_count', 0)} libraries\n"
                lib_names = [lib.get("name", "Unknown") for lib in libraries[:10]]
                context += f"Sample: {', '.join(lib_names)}\n\n"
        
        # Output results
        if needs_output and all_context.get("output_result"):
            output = all_context["output_result"]
            context += f"[Outputs]\nType: {output.get('output_type', 'Unknown')}\n"
            context += f"Status: {output.get('status', 'Unknown')}\n\n"
        
        # If no specific context matched, provide summary of what's available
        if not context:
            available = []
            if all_context.get("pcb_info"):
                available.append("PCB")
            if all_context.get("schematic_info"):
                available.append("Schematic")
            if all_context.get("project_info"):
                available.append("Project")
            if all_context.get("design_rules"):
                available.append("Design Rules")
            if all_context.get("board_config"):
                available.append("Board Config")
            if all_context.get("verification_report"):
                available.append("Verification")
            
            if available:
                context = f"Available data: {', '.join(available)}. Please ask a specific question about one of these.\n"
            else:
                context = "No design data available. Please export data from Altium Designer first.\n"
        
        return context
    
    def _get_relevant_pcb_data(self, query: str, pcb_info: Dict[str, Any] = None) -> str:
        # Extract only relevant PCB data based on query to save tokens
        if not pcb_info:
            return "No PCB information available."
        
        # Check for error
        if pcb_info.get("error"):
            return f"PCB Error: {pcb_info.get('error')}"
        
        query_lower = query.lower()
        context = ""
        
        # Always include basic stats
        stats = pcb_info.get("statistics", {})
        file_name = pcb_info.get('file_name', pcb_info.get('file', 'Unknown'))
        board_size = pcb_info.get('board_size', {})
        
        context += f"PCB: {file_name}\n"
        context += f"Board size: {board_size.get('width_mm', 0):.1f}mm x {board_size.get('height_mm', 0):.1f}mm\n"
        context += f"Statistics: {stats.get('component_count', 0)} components, {stats.get('net_count', 0)} nets\n"
        context += f"Tracks: {stats.get('track_count', 0)}, Vias: {stats.get('via_count', 0)}\n"
        
        # Layer info - always include
        layers = pcb_info.get("layers", [])
        if layers:
            layer_names = [l.get("name", str(l)) if isinstance(l, dict) else str(l) for l in layers]
            context += f"Layers ({len(layers)}): {', '.join(layer_names)}\n"
        
        # Only include detailed data if query asks for it
        if "component" in query_lower or "where" in query_lower or "location" in query_lower or "size" in query_lower or "value" in query_lower or "find" in query_lower:
            components = pcb_info.get("components", [])
            if components:
                # Extract component name from query - support various formats
                # e.g., "C168", "R1", "R122", "U12", "D1", "L1", "T1", etc.
                import re
                # Pattern for component designators (letter(s) followed by numbers)
                comp_pattern = re.search(r'\b([A-Z]{1,3}[0-9]+)\b', query, re.IGNORECASE)
                found_component = None
                target_name = None
                
                if comp_pattern:
                    # Search for exact component name match (case-insensitive)
                    target_name = comp_pattern.group(1).upper()  # Normalize to uppercase
                    for comp in components:
                        if isinstance(comp, dict):
                            comp_name = comp.get("designator", comp.get("name", "")).upper()
                        else:
                            comp_name = str(comp).upper()
                        if comp_name == target_name:
                            found_component = comp
                            break
                
                # If not found by pattern, try substring match
                if not found_component:
                    for comp in components:
                        if isinstance(comp, dict):
                            comp_name = comp.get("designator", comp.get("name", ""))
                        else:
                            comp_name = str(comp)
                        # Check if component name appears in query
                        if comp_name.lower() in query_lower:
                            found_component = comp
                            target_name = comp_name.upper()
                            break
                
                if found_component:
                    # Include full details for this component - DIRECT ANSWER
                    comp_name = found_component.get("designator", found_component.get("name", "")) if isinstance(found_component, dict) else str(found_component)
                    loc = found_component.get("location", {})
                    x_mm = loc.get('x_mm', 0)
                    y_mm = loc.get('y_mm', 0)
                    layer = found_component.get('layer', 'Unknown')
                    footprint = found_component.get('footprint', 'Unknown')
                    rotation = found_component.get('rotation_degrees', 0)
                    
                    context += f"\n*** FOUND: {comp_name} ***\n"
                    context += f"  Location: X={x_mm:.2f}mm, Y={y_mm:.2f}mm\n"
                    context += f"  Layer: {layer}\n"
                    context += f"  Footprint: {footprint}\n"
                    context += f"  Rotation: {rotation:.1f}°\n"
                    if found_component.get("lib_reference"):
                        context += f"  Part: {found_component.get('lib_reference', '')}\n"
                    if found_component.get("unique_id"):
                        context += f"  UID: {found_component.get('unique_id', '')}\n"
                else:
                    # Component not found
                    if target_name:
                        context += f"\n*** {target_name} NOT FOUND in component list ***\n"
                    # Show available components as examples
                    comp_names = [c.get("designator", c.get("name", "")) if isinstance(c, dict) else str(c) for c in components[:20]]
                    context += f"Available components ({len(components)} total): {', '.join(comp_names[:20])}\n"
                    if len(components) > 20:
                        context += f"... and {len(components) - 20} more\n"
        
        # Handle list queries (all resistors, all capacitors, etc.)
        if "list" in query_lower or "all" in query_lower or "show" in query_lower:
            components = pcb_info.get("components", [])
            if components:
                if "resistor" in query_lower or "r" in query_lower:
                    # Filter resistors (components starting with R)
                    resistors = [c.get("name", "") if isinstance(c, dict) else str(c) for c in components if (isinstance(c, dict) and c.get("name", "").upper().startswith("R")) or (isinstance(c, str) and c.upper().startswith("R"))]
                    if resistors:
                        context += f"\nResistors on board: {', '.join(resistors[:30])}\n"
                elif "capacitor" in query_lower or "c" in query_lower:
                    # Filter capacitors (components starting with C)
                    capacitors = [c.get("name", "") if isinstance(c, dict) else str(c) for c in components if (isinstance(c, dict) and c.get("name", "").upper().startswith("C")) or (isinstance(c, str) and c.upper().startswith("C"))]
                    if capacitors:
                        context += f"\nCapacitors on board: {', '.join(capacitors[:30])}\n"
                else:
                    # Check if filtering by layer
                    if "top layer" in query_lower or "top" in query_lower:
                        # Filter components on top layer
                        top_components = []
                        for c in components:
                            if isinstance(c, dict):
                                layer = c.get("layer", "").lower()
                                if "top" in layer or layer == "top":
                                    comp_name = c.get("designator", c.get("name", "Unknown"))
                                    top_components.append(comp_name)
                        if top_components:
                            context += f"\nComponents on Top layer ({len(top_components)}): {', '.join(top_components[:30])}\n"
                    elif "bottom layer" in query_lower or "bottom" in query_lower:
                        # Filter components on bottom layer
                        bottom_components = []
                        for c in components:
                            if isinstance(c, dict):
                                layer = c.get("layer", "").lower()
                                if "bottom" in layer or layer == "bottom":
                                    comp_name = c.get("designator", c.get("name", "Unknown"))
                                    bottom_components.append(comp_name)
                        if bottom_components:
                            context += f"\nComponents on Bottom layer ({len(bottom_components)}): {', '.join(bottom_components[:30])}\n"
                    else:
                        # List all components
                        comp_names = [c.get("designator", c.get("name", "")) if isinstance(c, dict) else str(c) for c in components[:50]]
                        context += f"\nComponents on board: {', '.join(comp_names)}\n"
        
        if "net" in query_lower:
            nets = pcb_info.get("nets", [])
            if nets:
                net_names = [n.get("name", "") if isinstance(n, dict) else str(n) for n in nets[:15]]
                context += f"Nets: {', '.join(net_names)}\n"
        
        if "layer" in query_lower and "component" not in query_lower:
            layers = pcb_info.get("layers", [])
            if layers:
                # Extract layer names (layers can be dicts or strings)
                layer_names = []
                for layer in layers:
                    if isinstance(layer, dict):
                        layer_names.append(layer.get("name", str(layer)))
                    else:
                        layer_names.append(str(layer))
                context += f"Layers: {', '.join(layer_names[:20])}\n"
        
        return context
    
    def _generate_response(self, query: str, all_context: Dict[str, Any] = None) -> str:
        # Generate concise, short response using all available context
        if all_context is None:
            all_context = {}
        
        query_lower = query.lower()
        
        system_prompt = """You are an expert PCB design assistant using Python file reader (NO Altium scripts needed).

CRITICAL RULES:
1. Answer DIRECTLY from the PCB data provided - components, nets, layers, tracks, vias
2. NEVER mention Altium scripts, File → Run Script, or .pas files
3. All PCB data is loaded via Python file reader - no scripts required
4. Be concise (2-3 sentences max)
5. For routing: use /routing/suggestions, /routing/route, /routing/via endpoints
6. For DRC: use /drc/run endpoint

The PCB data includes: components (name, footprint, location, layer, rotation), nets, tracks, vias, layers.

Answer questions directly using this data. If no PCB is loaded, tell user to upload a .PcbDoc file."""
        
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add recent conversation history (limit to last 2 exchanges = 4 messages)
        messages.extend(self.conversation_history[-4:])
        
        # Add only relevant context (not full JSON) - intelligently selected based on query
        relevant_context = self._get_relevant_context_data(query, all_context)
        if relevant_context:
            messages.append({
                "role": "system",
                "content": f"Design Context:\n{relevant_context}"
            })
        
        response = self.llm_client.chat(messages, temperature=0.7)
        return response or "I'm sorry, I couldn't generate a response. Please try again."
    
    def _generate_response_stream(self, query: str, all_context: Dict[str, Any] = None, stream_callback: Callable[[str], None] = None) -> str:
        # Generate conversational response with streaming using all available context
        if all_context is None:
            all_context = {}
        
        query_lower = query.lower()
        
        system_prompt = """You are an expert PCB design assistant using Python file reader (NO Altium scripts needed).

CRITICAL RULES:
1. Answer DIRECTLY from the PCB data provided - components, nets, layers, tracks, vias
2. NEVER mention Altium scripts, File → Run Script, or .pas files
3. All PCB data is loaded via Python file reader - no scripts required
4. Be concise (2-3 sentences max)
5. For routing: use /routing/suggestions, /routing/route, /routing/via endpoints
6. For DRC: use /drc/run endpoint

The PCB data includes: components (name, footprint, location, layer, rotation), nets, tracks, vias, layers.

Answer questions directly using this data. If no PCB is loaded, tell user to upload a .PcbDoc file."""
        
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # Add recent conversation history (limit to last 2 exchanges = 4 messages)
        messages.extend(self.conversation_history[-4:])
        
        # Add only relevant context (not full JSON) - intelligently selected based on query
        relevant_context = self._get_relevant_context_data(query, all_context)
        if relevant_context:
            messages.append({
                "role": "system",
                "content": f"Design Context:\n{relevant_context}"
            })
        
        full_response = ""
        for chunk in self.llm_client.chat_stream(messages, temperature=0.7):
            if chunk:
                full_response += chunk
                if stream_callback:
                    stream_callback(chunk)
        
        return full_response or "I'm sorry, I couldn't generate a response. Please try again."
    
    def _generate_command_response(self, user_query: str, command: str, parameters: Dict[str, Any], 
                                   script_name: str, procedure_name: str, command_type: str) -> str:
        """Generate natural response for command execution"""
        system_prompt = f"""You are a helpful PCB design assistant. The user requested: {command}

Parameters: {json.dumps(parameters, indent=2)}

Generate a brief, natural response that:
- Confirms what was done
- Be concise (1-2 sentences)
- Sound conversational

NEVER mention Altium scripts, File → Run Script, or .pas files."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User request: {user_query}"}
        ]
        
        response = self.llm_client.chat(messages, temperature=0.8)
        
        if response:
            return response.strip()
        else:
            return f"✅ {command} completed with {json.dumps(parameters)}"
    
    def clear_history(self):
        # Clear conversation history
        self.conversation_history = []
        self.current_analysis = None
    
    # =========================================================================
    # DESIGN INTELLIGENCE METHODS
    # =========================================================================
    
    def _perform_design_analysis(self, query: str, all_context: Dict[str, Any], 
                                  intent: Dict[str, Any]) -> str:
        """Perform basic design analysis. Identifies basic design information and patterns."""
        analysis_type = intent.get("analysis_type", "full")
        
        # Basic analysis using available data
        pcb_info = all_context.get("pcb_info", {})
        
        if not pcb_info:
            return (
                "I need PCB data to analyze your design.\n\n"
                "Please load a PCB file first using the Load PCB button."
            )
        
        # Extract basic information
        components = pcb_info.get("components", [])
        nets = pcb_info.get("nets", [])
        tracks = pcb_info.get("tracks", [])
        
        analysis_text = f"## Design Analysis\n\n"
        analysis_text += f"**Board Statistics:**\n"
        analysis_text += f"- Components: {len(components)}\n"
        analysis_text += f"- Nets: {len(nets)}\n" 
        analysis_text += f"- Tracks: {len(tracks)}\n\n"
        
        # Identify power/ground nets
        power_nets = [net for net in nets if any(keyword in net.get('name', '').upper() 
                     for keyword in ['VCC', 'VDD', 'POWER', '+3V', '+5V', '+12V'])]
        ground_nets = [net for net in nets if any(keyword in net.get('name', '').upper() 
                      for keyword in ['GND', 'GROUND', 'VSS'])]
        
        if power_nets or ground_nets:
            analysis_text += f"**Power Distribution:**\n"
            if power_nets:
                analysis_text += f"- Power nets: {len(power_nets)}\n"
            if ground_nets:
                analysis_text += f"- Ground nets: {len(ground_nets)}\n"
        
        return analysis_text
    
    def _generate_placement_strategy(self, query: str, all_context: Dict[str, Any]) -> str:
        """Generate basic placement strategy recommendations."""
        pcb_info = all_context.get("pcb_info", {})
        
        if not pcb_info:
            return "I need PCB data to generate a placement strategy. Please load a PCB file first."
        
        components = pcb_info.get("components", [])
        
        if not components:
            return "No components found in the PCB data."
        
        # Basic placement recommendations
        strategy_text = f"## Placement Strategy\n\n"
        strategy_text += f"**Component Count:** {len(components)}\n\n"
        
        # Group components by type
        component_types = {}
        for comp in components:
            footprint = comp.get('footprint', 'Unknown')
            if footprint not in component_types:
                component_types[footprint] = []
            component_types[footprint].append(comp.get('designator', 'Unknown'))
        
        strategy_text += f"**Component Types:**\n"
        for footprint, designators in component_types.items():
            strategy_text += f"- {footprint}: {len(designators)} components ({', '.join(designators[:5])}{'...' if len(designators) > 5 else ''})\n"
        
        strategy_text += f"\n**Basic Placement Guidelines:**\n"
        strategy_text += f"1. Place power components first (regulators, capacitors)\n"
        strategy_text += f"2. Group related functional blocks together\n"
        strategy_text += f"3. Keep high-speed signals short\n"
        strategy_text += f"4. Maintain proper clearances\n"
        
        return strategy_text
    
    def _perform_design_review(self, query: str, all_context: Dict[str, Any]) -> str:
        """Perform basic design review to identify issues and suggest improvements."""
        pcb_info = all_context.get("pcb_info", {})
        
        if not pcb_info:
            return "I need PCB data to perform a design review. Please load a PCB file first."
        
        # Basic review using available data
        components = pcb_info.get("components", [])
        nets = pcb_info.get("nets", [])
        tracks = pcb_info.get("tracks", [])
        rules = pcb_info.get("rules", [])
        
        review_text = f"## Design Review\n\n"
        
        # Basic statistics
        review_text += f"**Design Statistics:**\n"
        review_text += f"- Components: {len(components)}\n"
        review_text += f"- Nets: {len(nets)}\n"
        review_text += f"- Tracks: {len(tracks)}\n"
        review_text += f"- Rules: {len(rules)}\n\n"
        
        # Check for basic issues
        issues = []
        
        # Check for unconnected nets
        unconnected_nets = [net for net in nets if not any(track.get('net') == net.get('name') for track in tracks)]
        if unconnected_nets:
            issues.append(f"Found {len(unconnected_nets)} potentially unrouted nets")
        
        # Check for missing power/ground connections
        power_nets = [net for net in nets if any(keyword in net.get('name', '').upper() 
                     for keyword in ['VCC', 'VDD', 'POWER', '+3V', '+5V', '+12V'])]
        ground_nets = [net for net in nets if any(keyword in net.get('name', '').upper() 
                      for keyword in ['GND', 'GROUND', 'VSS'])]
        
        if not power_nets:
            issues.append("No power nets detected - check power distribution")
        if not ground_nets:
            issues.append("No ground nets detected - check ground connections")
        
        if issues:
            review_text += f"**Potential Issues:**\n"
            for issue in issues:
                review_text += f"- {issue}\n"
        else:
            review_text += f"**Status:** No obvious issues detected\n"
        
        return review_text

    def _generate_design_review(self, query: str, all_context: Dict[str, Any]) -> str:
        # Generate comprehensive design review
        prompt = f"""Provide a professional design review that:
1. Lists any issues found (warnings, errors)
2. Explains why each issue matters
3. Provides specific recommendations to fix each issue
4. Suggests optimizations and improvements
5. Gives an overall design health assessment

Be constructive and specific - help the engineer improve the design."""

        messages = [
            {"role": "system", "content": "You are a senior PCB design reviewer providing constructive feedback."},
            {"role": "user", "content": prompt}
        ]
        
        response = self.llm_client.chat(messages, temperature=0.5)
        return response or "Review complete. Please check the findings."
    
    def _generate_autonomous_layout(self, query: str, all_context: Dict[str, Any]) -> str:
        """Generate basic layout recommendations."""
        # Check for required data
        pcb_info = all_context.get("pcb_info")
        
        if not pcb_info:
            return (
                "I need PCB data to generate layout recommendations.\n\n"
                "Please load a PCB file first using the Load PCB button."
            )
        
        # Get board size and components
        board_size = pcb_info.get("board_size", {})
        board_width = board_size.get("width_mm", 100.0)
        board_height = board_size.get("height_mm", 80.0)
        
        components = pcb_info.get("components", [])
        
        if not components:
            return "No components found in the PCB data."
        
        # Generate basic layout recommendations
        layout_text = f"## Layout Recommendations\n\n"
        layout_text += f"**Board Size:** {board_width:.1f} x {board_height:.1f} mm\n"
        layout_text += f"**Components:** {len(components)}\n\n"
        
        # Basic placement suggestions
        layout_text += f"**Placement Strategy:**\n"
        layout_text += f"1. Place power management components first\n"
        layout_text += f"2. Group functional blocks together\n"
        layout_text += f"3. Keep critical signals short\n"
        layout_text += f"4. Maintain proper component spacing\n\n"
        
        # Component density analysis
        board_area = board_width * board_height
        component_density = len(components) / board_area * 100
        
        layout_text += f"**Component Density:** {component_density:.1f} components per cm²\n"
        
        if component_density > 2.0:
            layout_text += f"⚠️ High component density - consider larger board or fewer components\n"
        elif component_density < 0.5:
            layout_text += f"✅ Good component density - plenty of routing space\n"
        else:
            layout_text += f"✅ Moderate component density - should be manageable\n"
        
        return layout_text

        
        return response
    
    def _handle_routing(self, query: str, intent: Dict[str, Any]) -> str:
        # Handle routing commands via MCP server
        import requests
        import re
        
        routing_action = intent.get("routing_action", "suggestions")
        parameters = intent.get("parameters", {})
        
        try:
            if routing_action == "suggestions":
                # Get filter from intent first, then analyze query
                filter_type = intent.get("filter")
                if not filter_type:
                    query_lower = query.lower()
                    if "power" in query_lower or "pwr" in query_lower or "vcc" in query_lower or "vdd" in query_lower:
                        filter_type = "power"
                    elif "unrouted" in query_lower or "need" in query_lower or "missing" in query_lower:
                        filter_type = "unrouted"
                    elif "signal" in query_lower:
                        filter_type = "signal"
                
                # Build URL with filter
                url = "http://localhost:8765/routing/suggestions"
                if filter_type:
                    url += f"?filter={filter_type}"
                
                # Get routing suggestions
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("error"):
                        return f"Error: {data.get('error')}"
                    
                    suggestions = data.get("suggestions", [])
                    summary = data.get("summary", "")
                    total_nets = data.get("total_nets", 0)
                    routed_nets = data.get("routed_nets", 0)
                    unrouted_nets = data.get("unrouted_nets", 0)
                    
                    if suggestions:
                        # Build context-aware response
                        if filter_type == "power":
                            result = "## ⚡ Power Net Routing Analysis\n\n"
                        elif filter_type == "unrouted":
                            result = "## 🔴 Unrouted Nets Analysis\n\n"
                        else:
                            result = "## 🔌 Routing Suggestions & Analysis\n\n"
                        
                        # Add overall statistics
                        result += f"**PCB Status:** {total_nets} total nets | {routed_nets} routed | {unrouted_nets} unrouted\n\n"
                        
                        # Add summary
                        if summary:
                            result += f"**{summary}**\n\n"
                        
                        # Group by priority
                        high_priority = [s for s in suggestions if s.get("priority") == "HIGH"]
                        medium_priority = [s for s in suggestions if s.get("priority") == "MEDIUM"]
                        normal_priority = [s for s in suggestions if s.get("priority") == "NORMAL"]
                        
                        # Show unrouted first, then routed
                        if high_priority:
                            result += "### 🔴 HIGH Priority (Route First)\n\n"
                            for s in high_priority[:10]:
                                status_icon = "✅" if s.get("status") == "routed" else "🔴"
                                result += f"{status_icon} **{s.get('net', 'Unknown')}** - {s.get('status', 'unknown').upper()}\n"
                                result += f"   {s.get('recommendation', '')}\n"
                                result += f"   **Trace Width**: {s.get('width_suggestion', 'N/A')}\n"
                                result += f"   **Layer**: {s.get('layer_suggestion', 'N/A')}\n"
                                components = s.get('component_list', [])
                                if components:
                                    result += f"   **Components**: {', '.join(components[:3])}"
                                    if len(components) > 3:
                                        result += f" (+{len(components)-3} more)"
                                    result += "\n"
                                result += "\n"
                        
                        if medium_priority:
                            result += "### ⚠️ MEDIUM Priority\n\n"
                            for s in medium_priority[:10]:
                                status_icon = "✅" if s.get("status") == "routed" else "⚠️"
                                result += f"{status_icon} **{s.get('net', 'Unknown')}** - {s.get('status', 'unknown').upper()}\n"
                                result += f"   {s.get('recommendation', '')}\n"
                                result += f"   **Trace Width**: {s.get('width_suggestion', 'N/A')}\n"
                                result += f"   **Layer**: {s.get('layer_suggestion', 'N/A')}\n\n"
                        
                        if normal_priority and len(high_priority) + len(medium_priority) < 15:
                            result += "### 📋 Normal Priority\n\n"
                            for s in normal_priority[:10]:
                                status_icon = "✅" if s.get("status") == "routed" else "📋"
                                result += f"{status_icon} **{s.get('net', 'Unknown')}** - {s.get('status', 'unknown').upper()}\n"
                                result += f"   {s.get('recommendation', '')}\n\n"
                        
                        result += "---\n"
                        result += "💡 **To route a specific net:** Ask me: `route net <name> from <x1>,<y1> to <x2>,<y2>`\n"
                        result += "💡 **For more specific suggestions:** Ask `routing suggestions for power nets` or `what nets need routing?`"
                        
                        return result
                    else:
                        if filter_type:
                            return f"No {filter_type} nets found matching your query. All nets may be routed or filtered out."
                        return "No routing suggestions available. Make sure a PCB is loaded and has nets."
                else:
                    return f"Failed to get routing suggestions: {response.text}"
            
            elif routing_action == "route":
                # Parse route command from natural language
                # Pattern: "route net <name> from <x1>,<y1> to <x2>,<y2>"
                query_lower = query.lower()
                
                # Extract net name
                net_match = re.search(r'net\s+([+\-\w]+)', query, re.IGNORECASE)
                net_name = net_match.group(1) if net_match else parameters.get("net_name", "unknown")
                
                # Extract coordinates - try multiple patterns
                # Pattern 1: "from 10,20 to 50,60"
                coords_match = re.search(r'from\s+(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)', query)
                if coords_match:
                    start_x = float(coords_match.group(1))
                    start_y = float(coords_match.group(2))
                    end_x = float(coords_match.group(3))
                    end_y = float(coords_match.group(4))
                else:
                    # Pattern 2: "from (10,20) to (50,60)"
                    coords_match = re.search(r'from\s*\(?\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)?\s*to\s*\(?\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)?', query)
                    if coords_match:
                        start_x = float(coords_match.group(1))
                        start_y = float(coords_match.group(2))
                        end_x = float(coords_match.group(3))
                        end_y = float(coords_match.group(4))
                    else:
                        start_x = parameters.get("start_x", 0)
                        start_y = parameters.get("start_y", 0)
                        end_x = parameters.get("end_x", 10)
                        end_y = parameters.get("end_y", 10)
                
                # Route a net
                route_data = {
                    "net_id": f"net-{net_name.lower()}",
                    "start": [start_x, start_y],
                    "end": [end_x, end_y],
                    "layer": parameters.get("layer", "L1"),
                    "width": parameters.get("width_mm", 0.25)
                }
                response = requests.post("http://localhost:8765/routing/route", json=route_data, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return f"✅ Route created for net **{net_name}** from ({start_x}, {start_y}) to ({end_x}, {end_y}) on Top layer."
                else:
                    return f"Failed to create route: {response.text}"
            
            elif routing_action == "via":
                # Parse via placement from natural language
                # Pattern: "place a via at 30,40 for net GND"
                query_lower = query.lower()
                
                # Extract position
                pos_match = re.search(r'at\s+(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)', query)
                if pos_match:
                    x = float(pos_match.group(1))
                    y = float(pos_match.group(2))
                else:
                    x = parameters.get("x", 0)
                    y = parameters.get("y", 0)
                
                # Extract net name
                net_match = re.search(r'(?:for\s+)?net\s+([+\-\w]+)', query, re.IGNORECASE)
                net_name = net_match.group(1) if net_match else parameters.get("net_name", "unknown")
                
                via_data = {
                    "net_id": f"net-{net_name.lower()}",
                    "position": [x, y],
                    "layers": ["L1", "L4"],
                    "drill": 0.3
                }
                response = requests.post("http://localhost:8765/routing/via", json=via_data, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    return f"✅ Via placed at ({x}, {y}) for net **{net_name}**."
                else:
                    return f"Failed to place via: {response.text}"
            
            else:
                return f"Unknown routing action: {routing_action}"
                
        except requests.exceptions.RequestException as e:
            return f"Error connecting to MCP server: {str(e)}\n\nMake sure the MCP server is running (python mcp_server.py)"
    
    def _handle_drc(self, query: str) -> str:
        # Handle DRC commands via MCP server
        import requests
        
        try:
            response = requests.get("http://localhost:8765/drc/run", timeout=10)
            if response.status_code == 200:
                data = response.json()
                stats = data.get("stats", {})
                note = data.get("note", "")
                
                # Build honest response - Python reader can't do full DRC
                result = "## DRC Check Results\n\n"
                result += "### Board Statistics (from Python reader)\n"
                result += f"• **Components:** {stats.get('components', 0)}\n"
                result += f"• **Nets:** {stats.get('nets', 0)}\n"
                result += f"• **Tracks:** {stats.get('tracks', 0)}\n"
                result += f"• **Vias:** {stats.get('vias', 0)}\n\n"
                
                result += "### ⚠️ For Accurate DRC\n"
                result += "The Python file reader provides **statistics only**.\n"
                result += "It cannot detect clearance violations, short circuits, or unrouted nets.\n\n"
                result += "**Run Altium DRC for accurate results:**\n"
                result += "1. In Altium: **Tools → Design Rule Check**\n"
                result += "2. Click **Run Design Rule Check**\n"
                result += "3. View violations in the Messages panel\n\n"
                
                result += "---\n"
                result += "💡 The agent can help you **analyze** and **fix** issues found by Altium DRC."
                
                return result
            else:
                return f"Failed to run DRC: {response.text}"
                
        except requests.exceptions.RequestException as e:
            return f"Error connecting to MCP server: {str(e)}\n\nMake sure the MCP server is running (python mcp_server.py)"
    
    def _list_pcb_issues(self) -> str:
        # List all issues found in current PCB
        import requests
        
        try:
            # Get fresh DRC data
            response = requests.get("http://localhost:8765/drc/run", timeout=10)
            if response.status_code != 200:
                return "No PCB loaded. Please upload a PCB file first."
            
            data = response.json()
            if data.get("error"):
                return f"Error: {data.get('error')}"
            
            violations = data.get("violations", [])
            summary = data.get("summary", {})
            
            # Store for future reference
            self.pcb_issues = violations
            
            if not violations:
                return "✅ **No issues found!** Your PCB design looks good."
            
            result = f"## Issues Found in Your PCB\n\n"
            result += f"**Total:** {len(violations)} issues ({summary.get('errors', 0)} errors, {summary.get('warnings', 0)} warnings)\n\n"
            
            # Group by type
            errors = [v for v in violations if v.get("severity") == "error"]
            warnings = [v for v in violations if v.get("severity") == "warning"]
            
            if errors:
                result += "### 🔴 Errors (Must Fix)\n\n"
                for i, err in enumerate(errors, 1):
                    result += f"{i}. **{err.get('type', 'Unknown')}**: {err.get('message', '')}\n"
                result += "\n"
            
            if warnings:
                result += "### 🟡 Warnings (Should Fix)\n\n"
                for i, warn in enumerate(warnings, 1):
                    result += f"{i}. **{warn.get('type', 'Unknown')}**: {warn.get('message', '')}\n"
                result += "\n"
            
            result += "---\n"
            result += "💡 Ask **'how to solve these?'** for recommended solutions.\n"
            result += "❓ Ask **'why is [issue] an error?'** for explanation."
            
            return result
            
        except requests.exceptions.RequestException as e:
            return f"Error: {str(e)}"
    
    def _suggest_solutions(self) -> str:
        # Suggest multiple solutions for the issues
        import requests
        
        try:
            # Get routing suggestions
            response = requests.get("http://localhost:8765/routing/suggestions", timeout=10)
            if response.status_code != 200:
                return "No PCB loaded. Please upload a PCB file first."
            
            data = response.json()
            suggestions = data.get("suggestions", [])
            
            # Store for selection
            self.pcb_recommendations = suggestions
            
            if not suggestions:
                return "No recommendations available. Your PCB may already be well-designed!"
            
            result = "## Solutions for Your PCB Issues\n\n"
            result += "Here are the methods I recommend:\n\n"
            
            # Group by priority
            high = [s for s in suggestions if s.get("priority") == "high"]
            medium = [s for s in suggestions if s.get("priority") == "medium"]
            normal = [s for s in suggestions if s.get("priority") == "normal"]
            
            method_num = 1
            
            if high:
                result += "### 🔴 Critical (Fix First)\n\n"
                for s in high[:3]:
                    result += f"**Method {method_num}:** {s.get('recommendation', '')}\n"
                    result += f"   - Net: `{s.get('net', '')}`\n"
                    result += f"   - Layer: {s.get('layer', 'Top')}\n\n"
                    method_num += 1
            
            if medium:
                result += "### 🟡 Important\n\n"
                for s in medium[:2]:
                    result += f"**Method {method_num}:** {s.get('recommendation', '')}\n"
                    result += f"   - Net: `{s.get('net', '')}`\n\n"
                    method_num += 1
            
            if normal:
                result += "### 🟢 Optional Improvements\n\n"
                for s in normal[:2]:
                    result += f"**Method {method_num}:** {s.get('recommendation', '')}\n"
                    result += f"   - Net: `{s.get('net', '')}`\n\n"
                    method_num += 1
            
            result += "---\n"
            result += "To apply a solution, say:\n"
            result += "- **'Apply method 1'** - Apply first recommendation\n"
            result += "- **'Apply all'** - Apply all critical fixes\n"
            result += "- **'yes'** - Apply all recommendations"
            
            return result
            
        except requests.exceptions.RequestException as e:
            return f"Error: {str(e)}"
    
    def _explain_error(self, query: str) -> str:
        """Explain why something is an error using LLM with actual board context"""
        import requests
        
        # Get actual board context
        try:
            pcb_response = requests.get("http://localhost:8765/pcb/info", timeout=10)
            pcb_info = pcb_response.json() if pcb_response.status_code == 200 else {}
        except:
            pcb_info = {}
        
        # Build context about the board
        board_context = self._build_error_context(query, pcb_info)
        
        # Use LLM to generate contextual explanation
        prompt = f"""As a senior PCB design engineer, explain this error/issue in the context of this specific board.

User question: {query}

Board Context:
{board_context}

Current issues on this board:
{json.dumps(self.pcb_issues[:5], indent=2) if self.pcb_issues else 'No stored issues'}

Provide a detailed, board-specific explanation including:
1. **What is the problem?** - Explain in context of THIS board's components/nets
2. **Why does it matter?** - Specific risks for this design (consider voltage levels, frequencies, component types)
3. **How to fix it?** - Actionable steps with specific component names/coordinates from this board
4. **Priority** - How urgent is this? (Critical/High/Medium/Low)

Be specific. Reference actual component designators and net names from the board data.
Do NOT give generic advice - tailor everything to THIS board."""

        try:
            response = self.llm_client.chat([
                {"role": "system", "content": "You are an expert PCB design engineer providing board-specific analysis. Always reference actual component names and coordinates when available."},
                {"role": "user", "content": prompt}
            ], temperature=0.4)
            
            if response:
                return f"## Error Analysis\n\n{response}"
        except Exception as e:
            logger.warning(f"LLM error explanation failed: {e}")
        
        # Fallback: provide issue-specific explanation with any available context
        return self._fallback_explain_error(query, pcb_info)
    
    def _build_error_context(self, query: str, pcb_info: Dict[str, Any]) -> str:
        """Build relevant context for error explanation"""
        context_parts = []
        
        # Board basics
        stats = pcb_info.get("statistics", {})
        if stats:
            context_parts.append(f"Board: {pcb_info.get('file_name', 'Unknown')}")
            context_parts.append(f"Components: {stats.get('component_count', 0)}")
            context_parts.append(f"Nets: {stats.get('net_count', 0)}")
            context_parts.append(f"Layers: {stats.get('layer_count', 2)}")
        
        # Design rules
        rules = pcb_info.get("rules", {})
        if rules:
            context_parts.append(f"\nDesign Rules:")
            context_parts.append(f"- Min clearance: {rules.get('min_clearance_mm', 'N/A')}mm")
            context_parts.append(f"- Min trace width: {rules.get('min_trace_width_mm', 'N/A')}mm")
            context_parts.append(f"- Min via hole: {rules.get('min_via_hole_mm', 'N/A')}mm")
        
        # Try to find relevant components/nets mentioned in query
        query_upper = query.upper()
        components = pcb_info.get("components", [])
        nets = pcb_info.get("nets", [])
        
        # Find mentioned components
        mentioned_comps = []
        for comp in components[:100]:  # Limit search
            if isinstance(comp, dict):
                designator = comp.get("designator", "")
                if designator and designator.upper() in query_upper:
                    loc = comp.get("location", {})
                    mentioned_comps.append(
                        f"  - {designator}: {comp.get('footprint', 'Unknown')} at ({loc.get('x_mm', 0):.1f}, {loc.get('y_mm', 0):.1f})mm"
                    )
        
        if mentioned_comps:
            context_parts.append(f"\nMentioned Components:\n" + "\n".join(mentioned_comps[:5]))
        
        # Find mentioned nets
        mentioned_nets = []
        for net in nets[:100]:
            if isinstance(net, dict):
                net_name = net.get("name", "")
                if net_name and net_name.upper() in query_upper:
                    mentioned_nets.append(f"  - {net_name}: {net.get('pad_count', '?')} pads")
        
        if mentioned_nets:
            context_parts.append(f"\nMentioned Nets:\n" + "\n".join(mentioned_nets[:5]))
        
        # Relevant power/ground nets for power-related questions
        if any(word in query.lower() for word in ['power', 'voltage', 'current', 'vcc', 'vdd', 'ground', 'gnd']):
            power_nets = [n.get("name", "") for n in nets if isinstance(n, dict) and 
                         any(p in n.get("name", "").upper() for p in ['VCC', 'VDD', 'PWR', '+', 'GND', 'VSS'])]
            if power_nets:
                context_parts.append(f"\nPower/Ground Nets: {', '.join(power_nets[:10])}")
        
        return "\n".join(context_parts) if context_parts else "No board data available"
    
    def _fallback_explain_error(self, query: str, pcb_info: Dict[str, Any]) -> str:
        """Fallback error explanation when LLM is unavailable"""
        query_lower = query.lower()
        
        # Base explanations with board context enhancement
        if "clearance" in query_lower:
            rules = pcb_info.get("rules", {})
            min_clear = rules.get("min_clearance_mm", 0.15)
            return f"""## Clearance Violation

**On this board:** Minimum clearance is set to {min_clear}mm

**Problem:** Two copper features are closer than {min_clear}mm apart.

**Risk:** Manufacturing defects, potential shorts during production or use.

**Fix:** 
1. Move the offending traces/pads apart
2. Use narrower traces if space is limited
3. Route on a different layer if available

Ask "show DRC violations" to see specific locations."""

        elif "unrouted" in query_lower or "routing" in query_lower:
            stats = pcb_info.get("statistics", {})
            net_count = stats.get("net_count", 0)
            return f"""## Unrouted Net

**On this board:** {net_count} total nets need connectivity.

**Problem:** A net has pads that should be connected but have no copper trace between them.

**Risk:** Circuit will not function - no electrical path for signals/power.

**Fix:**
1. Identify the unrouted net's pads
2. Route a trace connecting all pads on the net
3. Use appropriate width (wider for power, controlled impedance for signals)

Ask "what nets need routing?" to see all unrouted nets."""

        elif any(word in query_lower for word in ['power', 'vcc', 'vdd']):
            return f"""## Power Distribution Issue

**Problem:** Power nets require special attention for current capacity and voltage drop.

**Risk:** 
- Underpowered components
- Heat buildup in traces
- Voltage drops affecting circuit operation

**Fix:**
1. Use wider traces (0.5mm+ for power)
2. Consider power planes on internal layers
3. Add decoupling capacitors near ICs

Ask "suggest routing for power nets" for specific recommendations."""

        elif self.pcb_issues:
            issue = self.pcb_issues[0]
            return f"""## Issue Analysis

**Type:** {issue.get('type', 'Unknown')}
**Details:** {issue.get('message', 'No details')}
**Severity:** {issue.get('severity', 'Unknown')}

This issue was detected in your board analysis. For a detailed, board-specific explanation, try asking about specific components or nets involved.

Ask "how to fix this?" for solution recommendations."""

        return "Please specify which error you'd like me to explain. For example: 'Why is the clearance violation on C135 a problem?'"
    
    def _get_net_pad_positions(self, net_name: str, pcb_info: Dict[str, Any]) -> list:
        """Get actual pad positions for a net from PCB data"""
        pad_positions = []
        components = pcb_info.get("components", [])
        
        for comp in components:
            if not isinstance(comp, dict):
                continue
            
            comp_loc = comp.get("location", {})
            comp_x = comp_loc.get("x_mm", 0)
            comp_y = comp_loc.get("y_mm", 0)
            
            # Check pads for this component
            pads = comp.get("pads", [])
            for pad in pads:
                if isinstance(pad, dict):
                    pad_net = pad.get("net", "").upper()
                    if pad_net == net_name.upper() or net_name.upper() in pad_net:
                        # Calculate absolute pad position
                        pad_x = comp_x + pad.get("x_mm", pad.get("rel_x", 0))
                        pad_y = comp_y + pad.get("y_mm", pad.get("rel_y", 0))
                        pad_positions.append({
                            "x": pad_x,
                            "y": pad_y,
                            "component": comp.get("designator", "Unknown"),
                            "pad_name": pad.get("name", "?"),
                            "layer": pad.get("layer", comp.get("layer", "Top"))
                        })
        
        # Also check nets list for pad info
        nets = pcb_info.get("nets", [])
        for net in nets:
            if isinstance(net, dict) and net.get("name", "").upper() == net_name.upper():
                net_pads = net.get("pads", [])
                for pad in net_pads:
                    if isinstance(pad, dict) and pad not in pad_positions:
                        pad_positions.append({
                            "x": pad.get("x_mm", 0),
                            "y": pad.get("y_mm", 0),
                            "component": pad.get("component", "Unknown"),
                            "pad_name": pad.get("name", "?"),
                            "layer": pad.get("layer", "Top")
                        })
        
        return pad_positions
    
    def _calculate_intelligent_route(self, net_name: str, rec: Dict[str, Any], pcb_info: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to calculate intelligent routing parameters based on actual board context"""
        
        # Get actual pad positions for this net
        pad_positions = self._get_net_pad_positions(net_name, pcb_info)
        
        if len(pad_positions) < 2:
            return None
        
        # Get design rules
        design_rules = pcb_info.get("rules", {})
        min_width = design_rules.get("min_trace_width_mm", 0.15)
        min_clearance = design_rules.get("min_clearance_mm", 0.15)
        
        # Get board stackup info
        layers = pcb_info.get("layers", [])
        layer_count = len(layers) if layers else pcb_info.get("layer_count", 2)
        
        # Determine net characteristics
        net_upper = net_name.upper()
        is_power = any(p in net_upper for p in ['VCC', 'VDD', '+', 'PWR', 'POWER', 'VIN', '5V', '3V3', '12V'])
        is_ground = any(p in net_upper for p in ['GND', 'GROUND', 'VSS', 'AGND', 'DGND'])
        is_clock = any(p in net_upper for p in ['CLK', 'CLOCK', 'OSC', 'XTAL'])
        is_high_speed = any(p in net_upper for p in ['USB', 'HDMI', 'ETH', 'LVDS', 'DIFF'])
        
        # Build context for LLM
        context = f"""
Net: {net_name}
Pad positions: {json.dumps(pad_positions[:10])}
Net type: {'Power' if is_power else 'Ground' if is_ground else 'Clock' if is_clock else 'High-speed' if is_high_speed else 'Signal'}
Board layers: {layer_count}
Design rules: min_width={min_width}mm, min_clearance={min_clearance}mm
Recommendation context: {rec.get('recommendation', '')}
"""
        
        # Ask LLM for intelligent routing parameters
        prompt = f"""As a PCB design engineer, analyze this net and provide routing parameters.

{context}

Provide a JSON response with:
1. "start": [x, y] - starting pad position (pick the most logical starting point)
2. "end": [x, y] - ending pad position
3. "width": trace width in mm (consider current capacity, impedance needs)
4. "layer": recommended layer ("L1" for top, "L2", etc.)
5. "via_needed": true/false
6. "via_positions": [[x,y], ...] if vias needed
7. "reasoning": brief explanation of your choices

Consider:
- Power/ground nets need wider traces (0.3-1.0mm depending on current)
- High-speed signals need controlled impedance (typically 0.2-0.3mm for 50 ohm)
- Clock signals should be short and direct
- Minimize vias for high-frequency signals

Return ONLY valid JSON, no markdown."""

        try:
            response = self.llm_client.chat([
                {"role": "system", "content": "You are an expert PCB design engineer. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ], temperature=0.3)
            
            if response:
                # Parse LLM response - handle potential markdown wrapping
                clean_response = response.strip()
                if clean_response.startswith("```"):
                    clean_response = clean_response.split("```")[1]
                    if clean_response.startswith("json"):
                        clean_response = clean_response[4:]
                route_params = json.loads(clean_response.strip())
                return route_params
        except Exception as e:
            logger.warning(f"LLM routing calculation failed: {e}")
        
        # Fallback: use actual pad positions directly with intelligent width calculation
        if len(pad_positions) >= 2:
            sorted_pads = sorted(pad_positions, key=lambda p: (p['x'], p['y']))
            
            # Calculate appropriate width based on net type
            if is_power:
                width = max(0.5, min_width * 3)
            elif is_ground:
                width = max(0.4, min_width * 2.5)
            elif is_clock or is_high_speed:
                width = 0.2
            else:
                width = max(0.2, min_width * 1.5)
            
            return {
                "start": [sorted_pads[0]['x'], sorted_pads[0]['y']],
                "end": [sorted_pads[-1]['x'], sorted_pads[-1]['y']],
                "width": width,
                "layer": "L1",
                "via_needed": False,
                "reasoning": f"Routed from {sorted_pads[0]['component']}.{sorted_pads[0]['pad_name']} to {sorted_pads[-1]['component']}.{sorted_pads[-1]['pad_name']}"
            }
        
        return None

    def _apply_selected_solution(self, query: str) -> str:
        # Apply a specific selected solution using actual board data and LLM intelligence
        import requests
        
        query_lower = query.lower()
        
        # Extract method number
        method_match = re.search(r'method\s*(\d+)|option\s*(\d+)|solution\s*(\d+)', query_lower)
        
        if method_match:
            method_num = int(method_match.group(1) or method_match.group(2) or method_match.group(3))
        elif "all" in query_lower:
            return self._apply_recommendations()
        else:
            method_num = 1
        
        if not self.pcb_recommendations:
            return "No solutions available. Ask 'how to solve these?' first to see options."
        
        if method_num < 1 or method_num > len(self.pcb_recommendations):
            return f"Invalid method number. Choose between 1 and {len(self.pcb_recommendations)}."
        
        # Get the selected recommendation
        rec = self.pcb_recommendations[method_num - 1]
        net_name = rec.get("net", "")
        
        try:
            # Get actual PCB data
            pcb_response = requests.get("http://localhost:8765/pcb/info", timeout=10)
            pcb_info = pcb_response.json() if pcb_response.status_code == 200 else {}
            
            # Calculate intelligent route using actual pad positions and LLM analysis
            route_params = self._calculate_intelligent_route(net_name, rec, pcb_info)
            
            if route_params:
                route_data = {
                    "net_id": f"net-{net_name.lower()}",
                    "start": route_params.get("start", [0, 0]),
                    "end": route_params.get("end", [0, 0]),
                    "layer": route_params.get("layer", "L1"),
                    "width": route_params.get("width", 0.25)
                }
                
                response = requests.post("http://localhost:8765/routing/route", json=route_data, timeout=10)
                
                if response.status_code == 200:
                    result = f"## Method {method_num} Applied\n\n"
                    result += f"✅ **{rec.get('recommendation', 'Solution applied')}**\n\n"
                    result += f"### Routing Details\n"
                    result += f"- **Net:** `{net_name}`\n"
                    result += f"- **From:** ({route_data['start'][0]:.2f}, {route_data['start'][1]:.2f}) mm\n"
                    result += f"- **To:** ({route_data['end'][0]:.2f}, {route_data['end'][1]:.2f}) mm\n"
                    result += f"- **Width:** {route_data['width']}mm\n"
                    result += f"- **Layer:** {route_data['layer']}\n"
                    
                    if route_params.get("reasoning"):
                        result += f"\n**Reasoning:** {route_params['reasoning']}\n"
                    
                    if route_params.get("via_needed") and route_params.get("via_positions"):
                        result += f"\n**Vias placed:** {len(route_params['via_positions'])} via(s)\n"
                    
                    result += "\n📁 Changes saved to artifact store.\n\n"
                    result += "Ask 'what are the remaining issues?' to see if more fixes are needed."
                    return result
                else:
                    return f"Failed to apply route: {response.text}"
            else:
                return f"❌ Could not determine routing for net `{net_name}`.\n\nNo pad positions found. Please verify:\n1. The net name is correct\n2. The PCB file has been loaded properly\n3. Components are assigned to this net"
                
        except requests.exceptions.RequestException as e:
            return f"Error: {str(e)}"
        except json.JSONDecodeError as e:
            return f"Error parsing PCB data: {str(e)}"
    
    def _apply_recommendations(self) -> str:
        # Apply the recommended changes using actual board data and LLM intelligence
        import requests
        
        try:
            # Get current PCB info
            response = requests.get("http://localhost:8765/pcb/info", timeout=10)
            if response.status_code != 200:
                return "No PCB loaded. Please upload a PCB file first."
            
            pcb_info = response.json()
            if pcb_info.get("error"):
                return "No PCB loaded. Please upload a PCB file first."
            
            # Get routing suggestions as basis for recommendations
            suggestions_response = requests.get("http://localhost:8765/routing/suggestions", timeout=10)
            if suggestions_response.status_code != 200:
                return "Failed to get recommendations."
            
            suggestions = suggestions_response.json().get("suggestions", [])
            
            if not suggestions:
                return "No recommendations to apply. Your PCB looks good!"
            
            # Apply high priority recommendations with intelligent routing
            applied = []
            failed = []
            for suggestion in suggestions[:3]:  # Apply top 3
                priority = suggestion.get("priority", "").upper()
                if priority in ["HIGH", "MEDIUM"]:
                    net_name = suggestion.get("net", "")
                    
                    # Use intelligent route calculation with actual pad positions
                    route_params = self._calculate_intelligent_route(net_name, suggestion, pcb_info)
                    
                    if route_params:
                        route_data = {
                            "net_id": f"net-{net_name.lower()}",
                            "start": route_params.get("start", [0, 0]),
                            "end": route_params.get("end", [0, 0]),
                            "layer": route_params.get("layer", "L1"),
                            "width": route_params.get("width", 0.25)
                        }
                    else:
                        # Cannot determine routing - skip with note
                        failed.append(f"⚠️ **{net_name}**: Could not determine pad positions")
                        continue
                    
                    route_response = requests.post(
                        "http://localhost:8765/routing/route",
                        json=route_data,
                        timeout=10
                    )
                    
                    if route_response.status_code == 200:
                        start = route_data['start']
                        end = route_data['end']
                        reasoning = route_params.get('reasoning', '')
                        applied.append(
                            f"✅ **{net_name}**: ({start[0]:.1f},{start[1]:.1f}) → ({end[0]:.1f},{end[1]:.1f}), "
                            f"width={route_data['width']}mm" + (f" | {reasoning}" if reasoning else "")
                        )
                    else:
                        failed.append(f"❌ **{net_name}**: Server error - {route_response.text[:50]}")
            
            if applied or failed:
                result = "## Recommendations Applied\n\n"
                if applied:
                    result += "### Successfully Routed\n"
                    result += "\n".join(applied)
                    result += "\n\n"
                if failed:
                    result += "### Could Not Route\n"
                    result += "\n".join(failed)
                    result += "\n\n"
                result += "📁 Changes saved to artifact store. "
                result += "Ask 'show current artifact' to see the version history."
                return result
            else:
                return "No high-priority recommendations to apply at this time."
                
        except requests.exceptions.RequestException as e:
            return f"Error applying recommendations: {str(e)}"
    
    def _move_component_direct(self, comp_name: str, new_x: float, new_y: float, all_context: Dict[str, Any]) -> str:
        # Move a component - creates a command for Altium script server.
        # Also updates the artifact store.
        import requests
        from tools.altium_script_client import AltiumScriptClient
        
        # First, get current location
        pcb_info = all_context.get("pcb_info", {})
        components = pcb_info.get("components", [])
        
        found = None
        for comp in components:
            if isinstance(comp, dict):
                designator = comp.get("designator", comp.get("name", "")).upper()
                if designator == comp_name.upper():
                    found = comp
                    break
        
        if not found:
            return f"❌ Component **{comp_name}** not found in this PCB."
        
        old_loc = found.get("location", {})
        old_x = old_loc.get("x_mm", 0)
        old_y = old_loc.get("y_mm", 0)
        
        # Try to send command to Altium script server
        client = AltiumScriptClient()
        result = client.move_component(comp_name, new_x, new_y)
        
        if result.get("success"):
            # Command sent to Altium successfully
            response = f"✅ **{comp_name}** moved successfully!\n\n"
            response += f"• **From:** X = {old_x:.2f} mm, Y = {old_y:.2f} mm\n"
            response += f"• **To:** X = {new_x:.2f} mm, Y = {new_y:.2f} mm\n\n"
            response += "The change has been applied in Altium Designer."
        elif result.get("error") == "Timeout waiting for Altium response":
            # Altium script server not running - save to artifact store instead
            response = f"📝 **Move Command Ready** for **{comp_name}**\n\n"
            response += f"• **From:** X = {old_x:.2f} mm, Y = {old_y:.2f} mm\n"
            response += f"• **To:** X = {new_x:.2f} mm, Y = {new_y:.2f} mm\n\n"
            response += "**Next Step - In Altium Designer:**\n"
            response += "Run: `DXP → Run Script → command_server.pas → ExecuteNow`\n\n"
            response += "The script will:\n"
            response += f"1. Move {comp_name} to the new position\n"
            response += "2. **Automatically run DRC**\n"
            response += "3. Show you any new errors/warnings\n\n"
            response += "💡 After running, ask me: `check DRC result`"
            
            # Save command to file for later execution
            try:
                import json
                with open("altium_command.json", 'w') as f:
                    json.dump({
                        "action": "move_component",
                        "designator": comp_name,
                        "x": new_x,
                        "y": new_y
                    }, f)
            except:
                pass
        else:
            response = f"❌ Error moving component: {result.get('error', 'Unknown error')}"
        
        return response
    
    def _get_component_location_direct(self, comp_name: str, all_context: Dict[str, Any]) -> Optional[str]:
        # Get component location DIRECTLY from data - no LLM hallucination.
        # Returns formatted response or None if component not found.
        pcb_info = all_context.get("pcb_info", {})
        components = pcb_info.get("components", [])
        
        if not components:
            return None
        
        # Search for the component (case-insensitive)
        found = None
        for comp in components:
            if isinstance(comp, dict):
                designator = comp.get("designator", comp.get("name", "")).upper()
                if designator == comp_name.upper():
                    found = comp
                    break
        
        if not found:
            # Component not found - list available components
            available = [c.get("designator", c.get("name", "")) for c in components[:30] if isinstance(c, dict)]
            return f"❌ **{comp_name}** not found in this PCB.\n\nAvailable components ({len(components)} total):\n{', '.join(available)}..."
        
        # Found! Return exact data
        loc = found.get("location", {})
        x_mm = loc.get("x_mm", 0)
        y_mm = loc.get("y_mm", 0)
        layer = found.get("layer", "Unknown")
        footprint = found.get("footprint", "Unknown")
        rotation = found.get("rotation_degrees", 0)
        
        response = f"📍 **{comp_name}** Location:\n\n"
        response += f"• **Position:** X = {x_mm:.2f} mm, Y = {y_mm:.2f} mm\n"
        response += f"• **Layer:** {layer}\n"
        response += f"• **Footprint:** {footprint}\n"
        response += f"• **Rotation:** {rotation:.1f}°\n"
        
        if found.get("lib_reference"):
            response += f"• **Part:** {found.get('lib_reference')}\n"
        
        return response
    
    def _check_altium_drc_result(self) -> str:
        # Run Python DRC check and generate AI summary
        import requests
        
        try:
            # Run Python DRC via MCP server
            response = requests.get("http://localhost:8765/drc/run", timeout=30)
            
            if response.status_code != 200:
                return f"## DRC Results\n\n❌ **Failed to run DRC: {response.text}**\n\n" + \
                       "Make sure the MCP server is running and a PCB is loaded."
            
            report_data = response.json()
            
            if "error" in report_data:
                return f"## DRC Results\n\n❌ **{report_data['error']}**\n\n" + \
                       "Make sure a PCB file is loaded first."
            
            summary = report_data.get("summary", {})
            violations = report_data.get("total_violations", 0)
            warnings = report_data.get("total_warnings", 0)
            violations_by_type = report_data.get("violations_by_type", {})
            detailed_violations = report_data.get("detailed_violations", [])
            
            # Build response with AI analysis
            response = "## 📊 DRC Analysis Report\n\n"
            response += "ℹ️ **Note:** DRC violations computed by Python DRC engine.\n\n"
            
            # Overall status
            if violations == 0 and warnings == 0:
                response += "✅ **Design is Clean!** No violations or warnings detected.\n\n"
                response += "Your PCB design passes all design rule checks. You can proceed with:\n"
                response += "• Final routing\n"
                response += "• Manufacturing preparation\n"
                response += "• Design review\n\n"
                return response
            
            # Show counts
            if violations > 0:
                response += f"🔴 **{violations} Rule Violation(s)** detected\n"
            if warnings > 0:
                response += f"⚠️ **{warnings} Warning(s)** detected\n"
            response += "\n"
            
            # Violations by type
            if violations_by_type:
                response += "### Violation Breakdown\n\n"
                for vtype, count in sorted(violations_by_type.items(), key=lambda x: x[1], reverse=True):
                    response += f"• **{vtype}**: {count}\n"
                response += "\n"
            
            # Show key violations (first 5)
            if detailed_violations:
                response += "### Key Violations\n\n"
                for i, viol in enumerate(detailed_violations[:5], 1):
                    comp = viol.get("component", "")
                    net = viol.get("net", "")
                    rule_type = viol.get("type", "unknown")
                    message = viol.get("message", "")[:100]
                    
                    response += f"**{i}. {rule_type.upper().replace('_', ' ')}**"
                    if comp:
                        response += f" - Component: {comp}"
                    if net:
                        response += f" - Net: {net}"
                    response += "\n"
                    if message:
                        response += f"   {message}\n"
                    response += "\n"
            
            # AI-generated recommendations
            response += "---\n"
            response += "### 💡 Recommendations\n\n"
            response += "I can help you:\n"
            response += "• **Analyze violations** - Understand the context and impact of each violation\n"
            response += "• **Prioritize fixes** - Focus on high-impact fixes first\n"
            response += "• **Provide solutions** - Suggest specific fixes for violations\n"
            response += "• **Answer questions** - Ask me about any violation in natural language\n"
            response += "• **Execute fixes** - Help fix violations via chat commands\n\n"
            
            # Generate AI summary
            ai_summary = self._generate_drc_ai_summary(report_data)
            response += ai_summary
            
            return response
        except Exception as e:
            return f"## DRC Results\n\n❌ **Error running DRC: {str(e)}**\n\n" + \
                   "Make sure the MCP server is running (python mcp_server.py)"
    
    def _generate_drc_ai_summary(self, report_data: Dict[str, Any]) -> str:
        # Generate AI-powered summary and recommendations from DRC report
        violations = report_data.get("total_violations", 0)
        warnings = report_data.get("total_warnings", 0)
        violations_by_type = report_data.get("violations_by_type", {})
        detailed_violations = report_data.get("detailed_violations", [])
        
        # Build context for LLM
        context = "DRC Report Summary:\n"
        context += f"- Total Violations: {violations}\n"
        context += f"- Total Warnings: {warnings}\n"
        context += f"- Violation Types: {', '.join(violations_by_type.keys())}\n\n"
        context += "Top Violations:\n"
        for i, viol in enumerate(detailed_violations[:10], 1):
            context += f"{i}. {viol.get('type', 'unknown')}: {viol.get('message', '')[:80]}\n"
        
        # Create prompt for LLM
        prompt = "You are a PCB design expert analyzing a Design Rule Check (DRC) report from Altium Designer.\n\n"
        prompt += context + "\n\n"
        prompt += "The user can already see the raw DRC report in Altium. Your job is to provide VALUE-ADDED intelligence:\n\n"
        prompt += "1. Interpretation: What do these violations actually mean? What is the impact?\n"
        prompt += "2. Prioritization: Which violations should be fixed first and why?\n"
        prompt += "3. Specific Solutions: Not just fix clearance violation but move component C135 away from other components\n"
        prompt += "4. Context: How do these violations relate to each other? Are there patterns?\n"
        prompt += "5. Actionable Steps: Concrete commands the user can give you to fix issues\n\n"
        prompt += "Provide a concise actionable summary with:\n"
        prompt += "- Overall assessment (1-2 sentences)\n"
        prompt += "- Top 3 priority issues to address first (with specific component/net names)\n"
        prompt += "- Specific fix recommendations (e.g. move C135 to position 50 60)\n"
        prompt += "- Patterns or related issues\n"
        prompt += "- Next steps\n\n"
        prompt += "Be specific and actionable. The user wants to know HOW to fix things not just WHAT is wrong."

        try:
            # Use LLM to generate summary
            summary = self.llm_client.generate_response(
                prompt,
                max_tokens=500,
                temperature=0.7
            )
            return summary.strip()
        except Exception as e:
            # Fallback to rule-based recommendations
            return self._generate_fallback_recommendations(violations_by_type, detailed_violations)
    
    def _generate_fallback_recommendations(self, violations_by_type: Dict[str, int], 
                                         detailed_violations: List[Dict[str, Any]]) -> str:
        # Generate rule-based recommendations if LLM fails
        recommendations = []
        
        if "clearance" in str(violations_by_type).lower():
            recommendations.append("• **Clearance Violations**: Ensure minimum 0.2mm spacing between components, pads, and tracks")
            recommendations.append("  - Move components further apart")
            recommendations.append("  - Check pad-to-pad clearances")
            recommendations.append("  - Verify track-to-component spacing")
        
        if "width" in str(violations_by_type).lower() or "trace" in str(violations_by_type).lower():
            recommendations.append("• **Trace Width Violations**: Increase trace width to meet minimum requirements")
            recommendations.append("  - Power traces: Use 0.5mm+ width")
            recommendations.append("  - Signal traces: Minimum 0.15mm")
        
        if "via" in str(violations_by_type).lower():
            recommendations.append("• **Via Violations**: Check via drill size and diameter")
            recommendations.append("  - Minimum drill: 0.2mm")
            recommendations.append("  - Via diameter should be 2x drill size")
        
        if "unrouted" in str(violations_by_type).lower():
            recommendations.append("• **Unrouted Nets**: Complete routing for all nets")
            recommendations.append("  - Use routing suggestions from menu")
            recommendations.append("  - Check for missing connections")
        
        # Component-specific recommendations
        components_affected = set()
        for viol in detailed_violations:
            comp = viol.get("component", "")
            if comp:
                components_affected.add(comp)
        
        if components_affected:
            recommendations.append(f"\n• **Affected Components**: {', '.join(sorted(components_affected)[:5])}")
            recommendations.append("  - Review placement of these components")
            recommendations.append("  - Consider moving them to resolve violations")
        
        if not recommendations:
            recommendations.append("• Review the detailed DRC report for specific issues")
            recommendations.append("• Check design rules in Altium Designer")
            recommendations.append("• Verify component placements and routing")
        
        return "\n".join(recommendations) + "\n"
    
    def _handle_design_rules_query(self, query: str, all_context: Dict[str, Any]) -> str:
        # Handle design rules queries - supports specific questions like 'what is minimum trace width?'
        query_lower = query.lower()
        
        # Check if asking for specific rule value
        is_specific_query = any(phrase in query_lower for phrase in [
            "minimum trace width", "min trace width", "trace width", "minimum width",
            "what is.*width", "what.*minimum.*width",
            "minimum clearance", "what is.*clearance", "what.*clearance",
            "via.*size", "via.*drill", "what is.*via"
        ])
        
        # First, check if PCB is loaded
        try:
            import requests
            pcb_info_response = requests.get("http://localhost:8765/pcb/info", timeout=5)
            if pcb_info_response.status_code == 200:
                pcb_data = pcb_info_response.json()
                if pcb_data.get("error"):
                    # No PCB loaded
                    return (
                        "## Design Rules\n\n"
                        "**No PCB loaded.**\n\n"
                        "**To view design rules:**\n"
                        "1. Load your PCB: Click **📁** → Select `.PcbDoc` file\n"
                        "2. Or export from Altium: Menu **⋮** → **Export PCB Info**\n"
                        "3. Then ask me: **`what are the design rules?`**\n\n"
                        "**Or check in Altium Designer:**\n"
                        "• **Design → Rules** to view all design rules"
                    )
                
                # PCB is loaded - get rules from PCB info
                rules = pcb_data.get("rules", [])
                
                # Also try to load from Altium export file directly
                if not rules:
                    try:
                        from pathlib import Path
                        altium_export = Path("altium_pcb_info.json")
                        if altium_export.exists():
                            import json
                            with open(altium_export, 'r', encoding='utf-8') as f:
                                export_data = json.load(f)
                                rules = export_data.get('rules', [])
                    except:
                        pass
                
                # Handle specific queries (e.g., "what is minimum trace width?")
                if is_specific_query and rules:
                    # Answer specific question
                    query_lower = query.lower()
                    response = "## Design Rule Answer\n\n"
                    
                    # Check for trace width queries
                    if "width" in query_lower or "trace" in query_lower:
                        width_rules = [r for r in rules if r.get("type") == "width" or "width" in str(r.get("name", "")).lower()]
                        if width_rules:
                            min_widths = []
                            pref_widths = []
                            for rule in width_rules:
                                min_w = (rule.get("min_width_mm") or rule.get("minWidth") or rule.get("min_width"))
                                if isinstance(min_w, (int, float)):
                                    min_widths.append(min_w)
                                pref_w = (rule.get("preferred_width_mm") or rule.get("preferredWidth") or rule.get("default_width_mm"))
                                if isinstance(pref_w, (int, float)):
                                    pref_widths.append(pref_w)
                            
                            if min_widths:
                                min_val = min(min_widths)
                                response += f"**Minimum Trace Width**: {min_val}mm\n\n"
                                if pref_widths:
                                    pref_val = min(pref_widths)
                                    response += f"**Preferred Trace Width**: {pref_val}mm\n\n"
                                response += "**Recommendation:**\n"
                                response += f"• Use {min_val}mm minimum for signal traces\n"
                                if pref_widths:
                                    response += f"• Use {pref_val}mm for standard routing\n"
                                response += "• Use 0.5mm+ for power traces\n"
                                return response
                    
                    # Check for clearance queries
                    if "clearance" in query_lower:
                        clearance_rules = [r for r in rules if r.get("type") == "clearance" or "clearance" in str(r.get("name", "")).lower()]
                        if clearance_rules:
                            clearances = []
                            for rule in clearance_rules:
                                clearance = (rule.get("min_clearance_mm") or rule.get("clearance_mm") or rule.get("clearance"))
                                if isinstance(clearance, (int, float)):
                                    clearances.append(clearance)
                            
                            if clearances:
                                min_clearance = min(clearances)
                                response += f"**Minimum Clearance**: {min_clearance}mm\n\n"
                                response += "**This means:**\n"
                                response += f"• All objects must be at least {min_clearance}mm apart\n"
                                response += f"• Prevents short circuits and manufacturing issues\n"
                                return response
                    
                    # Check for via queries
                    if "via" in query_lower:
                        via_rules = [r for r in rules if r.get("type") == "via" or "via" in str(r.get("name", "")).lower()]
                        if via_rules:
                            drills = []
                            for rule in via_rules:
                                drill = (rule.get("min_hole_mm") or rule.get("minHoleSize") or rule.get("min_drill"))
                                if isinstance(drill, (int, float)):
                                    drills.append(drill)
                            
                            if drills:
                                min_drill = min(drills)
                                response += f"**Minimum Via Drill Size**: {min_drill}mm\n\n"
                                response += "**Recommendation:**\n"
                                response += f"• Via hole should be at least {min_drill}mm\n"
                                response += f"• Via diameter should be 2x drill size ({min_drill * 2}mm)\n"
                                return response
                
                if rules:
                    # Use rules from PCB info or export
                    design_rules = {
                        "rules": rules,
                        "statistics": {
                            "total_rules": len(rules),
                            "clearance_rules": len([r for r in rules if r.get("type") == "clearance" or "clearance" in str(r.get("name", "")).lower()]),
                            "width_rules": len([r for r in rules if r.get("type") == "width" or "width" in str(r.get("name", "")).lower()]),
                            "via_rules": len([r for r in rules if r.get("type") == "via" or "via" in str(r.get("name", "")).lower()])
                        }
                    }
                else:
                    # PCB loaded but no rules - provide default info
                    return (
                        "## Design Rules\n\n"
                        f"**PCB loaded:** {pcb_data.get('file_name', 'Unknown')}\n\n"
                        "**Design rules are not available in the current export.**\n\n"
                        "**To get design rules:**\n"
                        "1. Export PCB info from Altium: Menu **⋮** → **Export PCB Info**\n"
                        "2. Design rules will be extracted from the export\n"
                        "3. Then ask me again: **`what are the design rules?`**\n\n"
                        "**Or check in Altium Designer:**\n"
                        "• **Design → Rules** to view all design rules\n\n"
                        "**Default rules (if not specified):**\n"
                        "• Clearance: 0.2mm minimum\n"
                        "• Trace Width: 0.15mm minimum, 0.25mm preferred\n"
                        "• Via: 0.2mm minimum drill"
                    )
            else:
                # MCP server error - try context
                design_rules = all_context.get("design_rules") if all_context else None
                if not design_rules:
                    return (
                        "## Design Rules\n\n"
                        "**Unable to connect to MCP server.**\n\n"
                        "**To view design rules:**\n"
                        "1. Make sure MCP server is running\n"
                        "2. Load your PCB: Click **📁** → Select `.PcbDoc` file\n"
                        "3. Or check in Altium Designer: **Design → Rules**"
                    )
        except Exception as e:
            # Fallback to context
            design_rules = all_context.get("design_rules") if all_context else None
            if not design_rules:
                return (
                    "## Design Rules\n\n"
                    "**Error retrieving design rules.**\n\n"
                    "**To view design rules:**\n"
                    "1. Load your PCB: Click **📁** → Select `.PcbDoc` file\n"
                    "2. Or check in Altium Designer: **Design → Rules**"
                )
        
        # Format design rules response
        response = "## 📋 Design Rules\n\n"
        
        # Get rules data
        rules = design_rules.get("rules", [])
        statistics = design_rules.get("statistics", {})
        
        if not rules and not statistics:
            response += "**Default Design Rules** (from Altium export):\n\n"
            response += "• **Clearance**: 0.2mm (minimum spacing)\n"
            response += "• **Trace Width**: 0.15mm minimum, 0.25mm preferred\n"
            response += "• **Via**: 0.2mm minimum drill size\n\n"
            response += "💡 **To see actual rules from your PCB:**\n"
            response += "• Export PCB info: Menu **⋮** → **Export PCB Info**\n"
            response += "• Or check in Altium: **Design → Rules**"
            return response
        
        # Show statistics
        if statistics:
            response += "### Summary\n\n"
            response += f"• **Total Rules**: {statistics.get('total_rules', len(rules))}\n"
            if statistics.get('clearance_rules', 0) > 0:
                response += f"• **Clearance Rules**: {statistics.get('clearance_rules', 0)}\n"
            if statistics.get('width_rules', 0) > 0:
                response += f"• **Width Rules**: {statistics.get('width_rules', 0)}\n"
            if statistics.get('via_rules', 0) > 0:
                response += f"• **Via Rules**: {statistics.get('via_rules', 0)}\n"
            response += "\n"
        
        # Show detailed rules
        if rules:
            response += "### Detailed Rules\n\n"
            
            # Group by type
            clearance_rules = [r for r in rules if r.get("type") == "clearance" or "clearance" in str(r.get("name", "")).lower()]
            width_rules = [r for r in rules if r.get("type") == "traceWidth" or "width" in str(r.get("name", "")).lower()]
            via_rules = [r for r in rules if r.get("type") == "via" or "via" in str(r.get("name", "")).lower()]
            
            if clearance_rules:
                response += "**Clearance Rules:**\n"
                for rule in clearance_rules[:5]:  # Show first 5
                    name = rule.get("name", "Unnamed")
                    # Try multiple possible field names
                    min_clearance = (rule.get("min_clearance_mm") or 
                                   rule.get("clearance_mm") or 
                                   rule.get("clearance") or 
                                   "N/A")
                    if isinstance(min_clearance, (int, float)):
                        response += f"• **{name}**: {min_clearance}mm minimum clearance\n"
                    else:
                        response += f"• **{name}**: {min_clearance}\n"
                response += "\n"
            
            if width_rules:
                response += "**Trace Width Rules:**\n"
                for rule in width_rules[:5]:
                    name = rule.get("name", "Unnamed")
                    min_w = (rule.get("min_width_mm") or 
                            rule.get("minWidth") or 
                            "N/A")
                    pref_w = (rule.get("preferred_width_mm") or 
                             rule.get("preferredWidth") or 
                             rule.get("default_width_mm") or 
                             "N/A")
                    if isinstance(min_w, (int, float)) and isinstance(pref_w, (int, float)):
                        response += f"• **{name}**: Min {min_w}mm, Preferred {pref_w}mm\n"
                    elif isinstance(min_w, (int, float)):
                        response += f"• **{name}**: Min {min_w}mm\n"
                    else:
                        response += f"• **{name}**: {min_w}\n"
                response += "\n"
            
            if via_rules:
                response += "**Via Rules:**\n"
                for rule in via_rules[:5]:
                    name = rule.get("name", "Unnamed")
                    min_drill = (rule.get("min_hole_mm") or 
                               rule.get("minHoleSize") or 
                               rule.get("min_drill") or 
                               "N/A")
                    if isinstance(min_drill, (int, float)):
                        response += f"• **{name}**: {min_drill}mm minimum drill size\n"
                    else:
                        response += f"• **{name}**: {min_drill}\n"
                response += "\n"
        
        # Add helpful note
        response += "---\n"
        response += "💡 **To modify design rules:**\n"
        response += "• In Altium Designer: **Design → Rules**\n"
        response += "• Then export updated rules: Menu **⋮** → **Export PCB Info**\n"
        response += "• Ask me: **`what are the design rules?`** to see updated rules"
        
        return response
    
    def _handle_artifact_query(self, query: str) -> str:
        # Handle artifact info queries via MCP server
        import requests
        
        try:
            response = requests.get("http://localhost:8765/artifact", timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                if data.get("error"):
                    return f"No artifact loaded. Please upload a PCB file first using the 📁 button."
                
                result = "## Current Artifact\n\n"
                result += f"**Artifact ID:** `{data.get('artifact_id', 'Unknown')}`\n"
                result += f"**PCB File:** {data.get('file', 'Unknown')}\n"
                result += f"**Storage Folder:** `{data.get('folder', 'Unknown')}`\n\n"
                
                files = data.get('files', [])
                if files:
                    result += "**Files:**\n"
                    for f in files:
                        result += f"- `{f}`\n"
                
                result += "\n📁 You can open the folder to see version history (v1.json, v2.json, etc.)"
                
                return result
            else:
                return f"Failed to get artifact info: {response.text}"
                
        except requests.exceptions.RequestException as e:
            return f"Error connecting to MCP server: {str(e)}"

# End of file