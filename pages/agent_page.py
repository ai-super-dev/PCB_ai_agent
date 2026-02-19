"""
Agent Page - Professional Chat Interface
Main interaction page for EagilinsED
"""
import customtkinter as ctk
import tkinter
from typing import Optional, Dict, Any
from mcp_client import AltiumMCPClient
from llm_client import LLMClient
from agent_orchestrator import AgentOrchestrator
from config import WINDOW_WIDTH, WINDOW_HEIGHT
import threading
import re


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text"""
    # Remove bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # Remove italic *text* or _text_
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    # Remove code blocks ```text```
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code `text`
    text = re.sub(r'`(.+?)`', r'\1', text)
    # Remove headers # ## ###
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    return text


class ChatMessage(ctk.CTkFrame):
    """Professional chat message bubble"""
    
    def __init__(self, parent, message: str = "", is_user: bool = True, colors: dict = None):
        super().__init__(parent, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.is_user = is_user
        
        # Default colors
        self.colors = colors or {
            "user_bg": "#3b82f6",
            "assistant_bg": "#1e293b",
            "border": "#334155",
            "text": "#f8fafc"
        }
        
        # Container for alignment
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="e" if is_user else "w")
        
        # Message bubble with improved styling
        bubble_color = self.colors["user_bg"] if is_user else self.colors["assistant_bg"]
        self.bubble = ctk.CTkFrame(
            container,
            fg_color=bubble_color,
            corner_radius=18,
            border_width=0 if is_user else 1,
            border_color=self.colors["border"]
        )
        self.bubble.grid(row=0, column=0, padx=(60 if is_user else 0, 0 if is_user else 60), pady=4)
        self.bubble.grid_columnconfigure(0, weight=1)
        
        # Message text with better typography
        self.msg_label = ctk.CTkLabel(
            self.bubble,
            text=message,
            font=ctk.CTkFont(size=14, family="Segoe UI"),
            text_color=self.colors["text"],
            anchor="w",
            justify="left",
            wraplength=WINDOW_WIDTH - 180
        )
        self.msg_label.grid(row=0, column=0, sticky="w", padx=18, pady=16)
    
    def append_text(self, text: str):
        """Append text for streaming"""
        current = self.msg_label.cget("text")
        self.msg_label.configure(text=current + text)
    
    def set_text(self, text: str):
        """Set complete text (strips markdown for assistant)"""
        if not self.is_user:
            text = strip_markdown(text)
        self.msg_label.configure(text=text)


class ConfirmationModal(ctk.CTkToplevel):
    """Confirmation modal dialog"""
    
    def __init__(self, parent, message: str, on_confirm, on_cancel):
        super().__init__(parent)
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.result = None
        
        self.title("Confirm Action")
        self.geometry("500x200")
        self.resizable(False, False)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (500 // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (200 // 2)
        self.geometry(f"500x200+{x}+{y}")
        
        # Colors
        colors = {
            "bg": "#1e293b",
            "text": "#f8fafc",
            "primary": "#3b82f6",
            "primary_hover": "#2563eb",
            "secondary": "#64748b"
        }
        
        self.configure(fg_color=colors["bg"])
        
        # Message label
        msg_label = ctk.CTkLabel(
            self,
            text=message,
            font=ctk.CTkFont(size=14),
            text_color=colors["text"],
            wraplength=450,
            justify="left"
        )
        msg_label.pack(pady=30, padx=20)
        
        # Buttons frame
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        # Yes button
        yes_btn = ctk.CTkButton(
            btn_frame,
            text="Yes",
            width=100,
            height=35,
            fg_color=colors["primary"],
            hover_color=colors["primary_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_yes
        )
        yes_btn.pack(side="left", padx=10)
        
        # No button
        no_btn = ctk.CTkButton(
            btn_frame,
            text="No",
            width=100,
            height=35,
            fg_color=colors["secondary"],
            hover_color="#475569",
            font=ctk.CTkFont(size=13),
            command=self._on_no
        )
        no_btn.pack(side="left", padx=10)
        
        # Focus on Yes button
        yes_btn.focus_set()
        
        # Bind Enter and Escape keys
        self.bind("<Return>", lambda e: self._on_yes())
        self.bind("<Escape>", lambda e: self._on_no())
    
    def _on_yes(self):
        self.result = True
        if self.on_confirm:
            self.on_confirm()
        self.destroy()
    
    def _on_no(self):
        self.result = False
        if self.on_cancel:
            self.on_cancel()
        self.destroy()


class AgentPage(ctk.CTkFrame):
    """Professional agent chat interface"""
    
    def __init__(self, parent, mcp_client: AltiumMCPClient, on_back=None):
        super().__init__(parent, width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        self.parent = parent
        self.mcp_client = mcp_client
        self.on_back = on_back
        self.messages = []
        self.is_loading = False
        self.is_destroyed = False  # Track if widget is destroyed
        self.pending_confirmation = None  # Store confirmation data
        self.current_drc_suggestions = []  # Store current DRC suggestions for fixing
        
        # Color scheme (matching welcome page)
        self.colors = {
            "bg_dark": "#0f172a",
            "bg_card": "#1e293b",
            "bg_input": "#334155",
            "bg_hover": "#475569",
            "border": "#475569",
            "primary": "#3b82f6",
            "primary_hover": "#2563eb",
            "success": "#10b981",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "text": "#f8fafc",
            "text_muted": "#94a3b8",
            "text_dim": "#64748b",
            "accent": "#06b6d4",
            "user_bg": "#3b82f6",
            "assistant_bg": "#1e293b"
        }
        
        self.configure(fg_color=self.colors["bg_dark"])
        
        # Initialize LLM
        try:
            self.llm_client = LLMClient()
            self.agent = AgentOrchestrator(self.llm_client, mcp_client)
        except Exception as e:
            self.llm_client = None
            self.agent = None
            print(f"LLM client error: {e}")
        
        # Rule management flags
        self.waiting_for_rule_input = False
        self.rule_action_type = None  # "add" or "update"
        
        self.setup_ui()
        self.add_welcome_message()
    
    def setup_ui(self):
        """Setup professional UI"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # === Header ===
        header = ctk.CTkFrame(self, fg_color=self.colors["bg_card"], height=60, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)  # Middle section expands
        header.grid_propagate(False)
        
        # Left section: Back + Brand
        left_frame = ctk.CTkFrame(header, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="w", padx=(12, 0), pady=10)
        
        back_btn = ctk.CTkButton(
            left_frame,
            text="←",
            font=ctk.CTkFont(size=16),
            width=36,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.colors["bg_input"],
            text_color=self.colors["text_muted"],
            command=self.go_back
        )
        back_btn.pack(side="left")
        
        brand = ctk.CTkLabel(
            left_frame,
            text="EagilinsED",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self.colors["text"]
        )
        brand.pack(side="left", padx=(8, 0))
        
        # Right section: Status + Menu
        right_frame = ctk.CTkFrame(header, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="e", padx=(0, 16), pady=10)
        
        self.status_dot = ctk.CTkLabel(
            right_frame,
            text="●",
            font=ctk.CTkFont(size=10),
            text_color=self.colors["success"]
        )
        self.status_dot.pack(side="left", padx=(0, 4))
        
        self.status_text = ctk.CTkLabel(
            right_frame,
            text="Connected",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_muted"]
        )
        self.status_text.pack(side="left", padx=(0, 12))
        
        # Clear button
        clear_btn = ctk.CTkButton(
            right_frame,
            text="Clear",
            font=ctk.CTkFont(size=11),
            width=56,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            hover_color=self.colors["bg_input"],
            border_width=1,
            border_color=self.colors["border"],
            text_color=self.colors["text_muted"],
            command=self.clear_chat
        )
        clear_btn.pack(side="left", padx=(0, 8))
        
        # Three-dot menu button
        self.menu_btn = ctk.CTkButton(
            right_frame,
            text="⋮",
            font=ctk.CTkFont(size=18, weight="bold"),
            width=36,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            hover_color=self.colors["bg_input"],
            text_color=self.colors["text"],
            command=self.show_menu
        )
        self.menu_btn.pack(side="left")
        
        # Create the dropdown menu (hidden initially)
        self.menu_visible = False
        self.menu_frame = None
        
        # === Chat Area ===
        self.chat_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=self.colors["bg_dark"],
            scrollbar_button_color=self.colors["bg_input"],
            scrollbar_button_hover_color=self.colors["border"]
        )
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.chat_frame.grid_columnconfigure(0, weight=1)
        
        # === Input Area ===
        input_container = ctk.CTkFrame(
            self, 
            fg_color=self.colors["bg_card"], 
            height=90,
            corner_radius=0,
            border_width=1,
            border_color=self.colors["border"]
        )
        input_container.grid(row=2, column=0, sticky="ew")
        input_container.grid_columnconfigure(0, weight=1)
        input_container.grid_propagate(False)
        
        # Input wrapper
        input_wrapper = ctk.CTkFrame(
            input_container,
            fg_color=self.colors["bg_input"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border"]
        )
        input_wrapper.grid(row=0, column=0, padx=20, pady=15, sticky="ew")
        input_wrapper.grid_columnconfigure(0, weight=1)
        
        # Input entry
        self.input_entry = ctk.CTkEntry(
            input_wrapper,
            placeholder_text="Ask about your design or request analysis...",
            font=ctk.CTkFont(size=14),
            height=40,
            border_width=0,
            fg_color="transparent",
            text_color=self.colors["text"],
            placeholder_text_color=self.colors["text_dim"]
        )
        self.input_entry.grid(row=0, column=0, padx=(15, 5), pady=5, sticky="ew")
        self.input_entry.bind("<Return>", lambda e: self.send_message())
        
        # Upload button
        self.upload_button = ctk.CTkButton(
            input_wrapper,
            text="📁",
            font=ctk.CTkFont(size=16),
            width=40,
            height=40,
            corner_radius=8,
            fg_color=self.colors["bg_hover"],
            hover_color=self.colors["border"],
            command=self.upload_file
        )
        self.upload_button.grid(row=0, column=1, padx=(0, 5), pady=5)
        
        # Send button
        self.send_button = ctk.CTkButton(
            input_wrapper,
            text="→",
            font=ctk.CTkFont(size=18, weight="bold"),
            width=40,
            height=40,
            corner_radius=8,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            command=self.send_message
        )
        self.send_button.grid(row=0, column=2, padx=(0, 5), pady=5)
    
    def show_menu(self):
        """Show/hide the three-dot menu dropdown"""
        if self.menu_visible and self.menu_frame:
            self.hide_menu()
            return
        
        # Create dropdown menu
        self.menu_frame = ctk.CTkFrame(
            self,
            fg_color=self.colors["bg_card"],
            corner_radius=8,
            border_width=1,
            border_color=self.colors["border"]
        )
        
        # Position below menu button
        self.menu_frame.place(relx=1.0, y=55, anchor="ne", x=-16)
        
        # Menu items
        menu_items = [
            ("Run DRC", "run_drc", "Run Design Rule Check in Altium"),
            ("View Design Rules", "view_design_rules", "View all design rules from Altium"),
            ("Auto-Generate DRC Rules", "auto_generate_rules", "Automatically generate DRC rules from PCB design"),
            ("Get DRC Suggestions", "get_drc_suggestions", "Get automatic suggestions based on DRC violations"),
            ("Update DRC Suggestions", "update_drc_suggestions", "Check for updated DRC suggestions"),
            ("Refresh Data", "refresh", "Reload PCB data (from .PcbDoc file or Altium export)"),
            ("Routing Suggestions", "routing", "Generate AI routing suggestions"),
            ("List Components", "list_components", "Show all components"),
            ("Altium Status", "altium_status", "Check Altium connection"),
        ]
        
        for i, (text, action, tooltip) in enumerate(menu_items):
            btn = ctk.CTkButton(
                self.menu_frame,
                text=text,
                font=ctk.CTkFont(size=13),
                width=180,
                height=36,
                anchor="w",
                corner_radius=0,
                fg_color="transparent",
                hover_color=self.colors["bg_input"],
                text_color=self.colors["text"],
                command=lambda a=action: self.menu_action(a)
            )
            btn.grid(row=i, column=0, padx=4, pady=2, sticky="ew")
        
        # Add separator
        sep = ctk.CTkFrame(self.menu_frame, height=1, fg_color=self.colors["border"])
        sep.grid(row=len(menu_items), column=0, sticky="ew", padx=8, pady=4)
        
        # View DRC Report button
        drc_btn = ctk.CTkButton(
            self.menu_frame,
            text="View DRC Report",
            font=ctk.CTkFont(size=13),
            width=180,
            height=36,
            anchor="w",
            corner_radius=0,
            fg_color="transparent",
            hover_color=self.colors["bg_input"],
            text_color=self.colors["accent"],
            command=lambda: self.menu_action("view_drc_report")
        )
        drc_btn.grid(row=len(menu_items)+1, column=0, padx=4, pady=2, sticky="ew")
        
        self.menu_visible = True
        
        # Bind click outside to close menu
        self.bind("<Button-1>", self._on_click_outside, add="+")
    
    def hide_menu(self):
        """Hide the dropdown menu"""
        if self.menu_frame:
            self.menu_frame.destroy()
            self.menu_frame = None
        self.menu_visible = False
        self.unbind("<Button-1>")
    
    def _on_click_outside(self, event):
        """Close menu if clicked outside"""
        if self.menu_frame:
            # Check if click is outside menu
            x, y = event.x_root, event.y_root
            menu_x = self.menu_frame.winfo_rootx()
            menu_y = self.menu_frame.winfo_rooty()
            menu_w = self.menu_frame.winfo_width()
            menu_h = self.menu_frame.winfo_height()
            
            if not (menu_x <= x <= menu_x + menu_w and menu_y <= y <= menu_y + menu_h):
                self.hide_menu()
    
    def menu_action(self, action: str):
        """Handle menu action"""
        self.hide_menu()
        
        if action == "run_drc":
            self._run_altium_drc()
        elif action == "refresh":
            self._refresh_from_altium()
        elif action == "routing":
            self._get_routing_suggestions()
        elif action == "list_components":
            self._list_components()
        elif action == "altium_status":
            self._check_altium_status()
        elif action == "view_drc_report":
            self._open_drc_report()
        elif action == "auto_generate_rules":
            self._auto_generate_drc_rules()
        elif action == "get_drc_suggestions":
            self._get_drc_suggestions()
        elif action == "update_drc_suggestions":
            self._update_drc_suggestions()
        elif action == "view_design_rules":
            self._view_design_rules()
    
    def _run_altium_drc(self):
        """Check for existing DRC report or provide simple instructions"""
        from pathlib import Path
        import time
        
        # First, check if DRC report already exists
        possible_dirs = [
            Path("PCB_Project/Project Outputs for PCB_Project"),
            Path("PCB_Project/Project Outputs"),
        ]
        
        report_found = None
        for dir_path in possible_dirs:
            if dir_path.exists():
                html_files = list(dir_path.glob("Design Rule Check*.html"))
                if html_files:
                    # Get the most recent one
                    report_found = max(html_files, key=lambda p: p.stat().st_mtime)
                    break
        
        if report_found:
            # Report exists - analyze it immediately
            self.add_message("Found DRC report! Analyzing results...", is_user=False)
            self.set_status("Analyzing DRC...", "warning")
            
            def analyze():
                try:
                    drc_summary = self.agent._check_altium_drc_result()
                    self._safe_after(0, lambda s=drc_summary: self.add_message(s, is_user=False))
                    self._safe_after(0, lambda: self.set_status("DRC Complete", "success"))
                except Exception as e:
                    self._safe_after(0, lambda: self.add_message(
                        f"Error analyzing DRC report: {str(e)}\n\n"
                        "Report found at: " + str(report_found),
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Analysis Error", "error"))
            
            threading.Thread(target=analyze, daemon=True).start()
        else:
            # No report found - provide simple instructions
            self.add_message(
                "**No DRC report found.**\n\n"
                "**To run DRC:**\n"
                "1. In Altium Designer: **Tools → Design Rule Check...**\n"
                "2. Click **'Run Design Rule Check'**\n"
                "3. After DRC completes, ask me: **`check DRC result`**\n\n"
                "I'll automatically analyze the results and provide AI-powered recommendations!",
                is_user=False
            )
            self.set_status("No DRC Report", "info")
        
        def run():
            try:
                # Try to run via script client
                from tools.altium_script_client import AltiumScriptClient
                client = AltiumScriptClient()
                
                # Check if server is running
                if not client.ping():
                    self._safe_after(0, lambda: self.add_message(
                        "**Altium Script Server not running.**\n\n"
                        "**Please run DRC manually:**\n"
                        "1. In Altium Designer: **Tools → Design Rule Check...**\n"
                        "2. Click **'Run Design Rule Check'** button\n"
                        "3. Wait for DRC to complete\n"
                        "4. Then ask me: **`check DRC result`**\n\n"
                        "I'll automatically analyze the results!",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Run DRC manually", "info"))
                    return
                
                # Send run_drc command
                result = client._send_command({"action": "run_drc"})
                
                if result.get("success"):
                    # Show initial message
                    self._safe_after(0, lambda: self.add_message(
                        "Running DRC in Altium Designer...\n"
                        "This may take a few seconds for large designs.",
                        is_user=False
                    ))
                    
                    # Poll for DRC report file (up to 60 seconds for large designs)
                    import time
                    from pathlib import Path
                    import os
                    
                    # Try multiple possible output directory locations
                    possible_dirs = [
                        Path("PCB_Project/Project Outputs for PCB_Project"),
                        Path("PCB_Project/Project Outputs"),
                        Path("Project Outputs for PCB_Project"),
                        Path("Project Outputs"),
                    ]
                    
                    # Also check if PCB_Project exists and find actual output directory
                    pcb_project = Path("PCB_Project")
                    if pcb_project.exists():
                        # Look for any "Project Outputs" directory
                        for item in pcb_project.iterdir():
                            if item.is_dir() and "Output" in item.name:
                                possible_dirs.insert(0, item)
                    
                    max_wait = 60  # seconds (DRC can take time for large designs)
                    check_interval = 1.0  # Check every second
                    start_time = time.time()
                    
                    # Get initial file list from all possible directories
                    initial_files = {}
                    for dir_path in possible_dirs:
                        if dir_path.exists():
                            files = list(dir_path.glob("Design Rule Check*.html"))
                            if files:
                                initial_files[str(dir_path)] = len(files)
                    
                    # Start polling in background
                    def poll_for_report():
                        waited_time = 0
                        last_counts = initial_files.copy()
                        
                        while waited_time < max_wait:
                            # Check all possible directories
                            for dir_path in possible_dirs:
                                if dir_path.exists():
                                    html_files = list(dir_path.glob("Design Rule Check*.html"))
                                    dir_str = str(dir_path)
                                    
                                    # Check if new file was created
                                    current_count = len(html_files)
                                    last_count = last_counts.get(dir_str, 0)
                                    
                                    report_found = False
                                    latest_file = None
                                    
                                    if current_count > last_count:
                                        # New file created
                                        latest_file = max(html_files, key=lambda p: p.stat().st_mtime)
                                        report_found = True
                                    elif current_count > 0:
                                        # Check if existing file was recently modified (within last 60 seconds)
                                        # This handles the case where DRC was run before clicking the menu
                                        latest_file = max(html_files, key=lambda p: p.stat().st_mtime)
                                        file_age = time.time() - latest_file.stat().st_mtime
                                        # Accept file if modified within last 60 seconds (DRC might have just completed)
                                        if file_age < 60.0:
                                            report_found = True
                                        # Also check if this is the first iteration and file exists (user ran DRC manually)
                                        elif waited_time < 2.0 and current_count > 0:
                                            # On first check, if file exists, use it (user might have run DRC before)
                                            report_found = True
                                    
                                    if report_found and latest_file:
                                        # Report found - analyze it
                                        self._safe_after(0, lambda: self.add_message(
                                            "DRC completed! Analyzing results...",
                                            is_user=False
                                        ))
                                        
                                        # Small delay to ensure file is fully written
                                        time.sleep(1.0)
                                        
                                        # Get AI analysis of DRC report
                                        try:
                                            # Update parser to use the found file
                                            # Use Python DRC instead of HTML parsing
                                            import requests
                                            drc_result = requests.get("http://localhost:8765/drc/run", timeout=30)
                                            if drc_result.status_code == 200:
                                                report_data = drc_result.json()
                                            else:
                                                report_data = {"error": "Failed to run DRC"}
                                            
                                            if "error" not in report_data:
                                                drc_summary = self.agent._check_altium_drc_result()
                                                self._safe_after(0, lambda s=drc_summary: self.add_message(
                                                    s,
                                                    is_user=False
                                                ))
                                                self._safe_after(0, lambda: self.set_status("DRC Complete", "success"))
                                            else:
                                                # Try with the found file path
                                                drc_summary = self.agent._check_altium_drc_result()
                                                self._safe_after(0, lambda s=drc_summary: self.add_message(
                                                    s,
                                                    is_user=False
                                                ))
                                                self._safe_after(0, lambda: self.set_status("DRC Complete", "success"))
                                        except Exception as e:
                                            import traceback
                                            # Fallback message
                                            self._safe_after(0, lambda: self.add_message(
                                                f"DRC completed! Report found at:\n{latest_file}\n\n"
                                                "Click 'View DRC Report' in the menu to open it.\n\n"
                                                f"Analysis error: {str(e)}",
                                                is_user=False
                                            ))
                                            self._safe_after(0, lambda: self.set_status("DRC Complete", "warning"))
                                        return
                                    
                                    last_counts[dir_str] = current_count
                            
                            time.sleep(check_interval)
                            waited_time += check_interval
                        
                        # Timeout - report not found, provide helpful debugging info
                        debug_info = []
                        for dir_path in possible_dirs:
                            exists = dir_path.exists()
                            debug_info.append(f"  • {dir_path}: {'exists' if exists else 'not found'}")
                            if exists:
                                files = list(dir_path.glob("*.html"))
                                debug_info.append(f"    Found {len(files)} HTML file(s)")
                        
                        self._safe_after(0, lambda: self.add_message(
                            "⏱️ DRC timeout - Report not found automatically\n\n"
                            "**Possible reasons:**\n"
                            "• DRC is still running in Altium Designer\n"
                            "• Report was saved to a different location\n"
                            "• DRC dialog needs confirmation\n\n"
                            "**Debugging info:**\n" + "\n".join(debug_info) + "\n\n"
                            "**Next steps:**\n"
                            "1. Check Altium Designer - is DRC still running?\n"
                            "2. Once DRC completes, ask me: `check DRC result`\n"
                            "3. Or manually find the report and tell me the path",
                            is_user=False
                        ))
                        self._safe_after(0, lambda: self.set_status("DRC Timeout", "warning"))
                    
                    # Start polling in background thread
                    threading.Thread(target=poll_for_report, daemon=True).start()
                else:
                    self._safe_after(0, lambda: self.add_message(
                        f"DRC Error: {result.get('error', 'Unknown error')}",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("DRC Failed", "error"))
                    
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"Error running DRC: {str(e)}\n\n"
                    "Run DRC manually in Altium: Tools -> Design Rule Check",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=run, daemon=True).start()
    
    def _export_pcb_info(self):
        """Export PCB info from Altium and reload"""
        self.add_message("Exporting comprehensive PCB data from Altium...", is_user=False)
        self.set_status("Exporting...", "warning")
        
        def export():
            try:
                from tools.altium_script_client import AltiumScriptClient
                from pathlib import Path
                import time
                
                client = AltiumScriptClient()
                
                if not client.ping():
                    self._safe_after(0, lambda: self.add_message(
                        "Altium Script Server not running!\n\n"
                        "1. Open Altium Designer\n"
                        "2. Open your PCB\n"
                        "3. Run: DXP -> Run Script -> command_server.pas -> StartServer\n"
                        "4. Then click 'Export PCB Info' again",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Not connected", "warning"))
                    return
                
                result = client.export_pcb_info()
                
                if result.get("success"):
                    # Wait a moment for file to be written
                    time.sleep(2.0)  # Increased from 0.5s to 2.0s
                    
                    # Load the exported file (check PCB_Project folder first)
                    pcb_info_file = Path("PCB_Project") / "altium_pcb_info.json"
                    if not pcb_info_file.exists():
                        pcb_info_file = Path("altium_pcb_info.json")
                    if pcb_info_file.exists():
                        self._safe_after(0, lambda: self.add_message(
                            "PCB data exported successfully!\n"
                            "Loading comprehensive data...",
                            is_user=False
                        ))
                        
                        # Load via MCP server
                        result = self.mcp_client.load_from_altium_export(str(pcb_info_file))
                        
                        if result.get("success"):
                            stats = result.get("statistics", {})
                            self._safe_after(0, lambda: self.add_message(
                                f"✅ Data loaded!\n\n"
                                f"Components: {stats.get('component_count', 0)}\n"
                                f"Nets: {stats.get('net_count', 0)}\n"
                                f"Tracks: {stats.get('track_count', 0)}\n"
                                f"Vias: {stats.get('via_count', 0)}\n"
                                f"Layers: {stats.get('layer_count', 0)}\n\n"
                                f"All features now have complete data!",
                                is_user=False
                            ))
                            self._safe_after(0, lambda: self.set_status("Data Loaded", "success"))
                        else:
                            self._safe_after(0, lambda: self.add_message(
                                f"Export successful but load failed: {result.get('error', 'Unknown')}",
                                is_user=False
                            ))
                    else:
                        self._safe_after(0, lambda: self.add_message(
                            "Export command sent, but file not found. Check Altium Designer.",
                            is_user=False
                        ))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        f"Export error: {result.get('error', 'Unknown')}",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Export Failed", "error"))
                    
            except Exception as e:
                import traceback
                self._safe_after(0, lambda: self.add_message(
                    f"Error exporting PCB: {str(e)}\n\n{traceback.format_exc()}",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=export, daemon=True).start()
    
    def _refresh_from_altium(self):
        """Refresh data - tries Python file reader first (extracts design rules!), then Altium export"""
        from pathlib import Path
        
        self.add_message("Refreshing PCB data...", is_user=False)
        self.set_status("Refreshing...", "warning")
        
        def refresh():
            try:
                # FIRST: Try to find .PcbDoc file and use Python file reader (extracts design rules!)
                pcb_files = list(Path(".").glob("**/*.PcbDoc"))
                pcb_files.extend(Path(".").glob("**/*.pcbdoc"))  # Case-insensitive
                
                if pcb_files:
                    # Use the first .PcbDoc file found
                    pcb_file = pcb_files[0]
                    self._safe_after(0, lambda: self.add_message(
                        f"Found PCB file: {pcb_file.name}\n"
                        "Loading directly from file (includes design rules!)...",
                        is_user=False
                    ))
                    
                    # Load via file reader (extracts design rules automatically!)
                    result = self.mcp_client.load_pcb_file(str(pcb_file))
                    
                    if result.get("success"):
                        stats = result.get("statistics", {})
                        design_rules = result.get("design_rules", {})
                        
                        msg = f"✅ PCB loaded from file!\n\n"
                        msg += f"**Components:** {stats.get('component_count', 0)}\n"
                        msg += f"**Nets:** {stats.get('net_count', 0)}\n"
                        msg += f"**Tracks:** {stats.get('track_count', 0)}\n"
                        msg += f"**Vias:** {stats.get('via_count', 0)}\n"
                        msg += f"**Layers:** {stats.get('layer_count', 0)}\n"
                        
                        if design_rules:
                            msg += f"\n**Design Rules Extracted:**\n"
                            msg += f"  • Clearance: {design_rules.get('clearance_rules', 0)} rule(s)\n"
                            msg += f"  • Width: {design_rules.get('width_rules', 0)} rule(s)\n"
                            msg += f"  • Via: {design_rules.get('via_rules', 0)} rule(s)\n"
                            msg += f"\nAsk: `\"what are the design rules?\"`"
                        else:
                            msg += f"\n⚠️ No design rules found in file"
                        
                        self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                        self._safe_after(0, lambda: self.set_status("Loaded", "success"))
                        return
                
                # FALLBACK: Check for auto-exported file from StartServer (check PCB_Project folder first)
                pcb_info_file = Path("PCB_Project") / "altium_pcb_info.json"
                if not pcb_info_file.exists():
                    pcb_info_file = Path("altium_pcb_info.json")
                
                # Also check for timestamped export files
                if not pcb_info_file.exists():
                    export_files = sorted(Path(".").glob("altium_export_*.json"), 
                                        key=lambda p: p.stat().st_mtime, reverse=True)
                    if export_files:
                        pcb_info_file = export_files[0]
                
                if pcb_info_file.exists():
                    # Load from Altium export (includes design rules!)
                    result = self.mcp_client.load_from_altium_export(str(pcb_info_file))
                    
                    if result.get("success"):
                        stats = result.get("statistics", {})
                        self._safe_after(0, lambda: self.add_message(
                            f"✅ Data refreshed from Altium export!\n\n"
                            f"**Components:** {stats.get('component_count', 0)}\n"
                            f"**Nets:** {stats.get('net_count', 0)}\n"
                            f"**Tracks:** {stats.get('track_count', 0)}\n"
                            f"**Vias:** {stats.get('via_count', 0)}\n"
                            f"**Layers:** {stats.get('layer_count', 0)}\n\n"
                            f"**Design rules are included!** Ask: `\"what are the design rules?\"`",
                            is_user=False
                        ))
                        self._safe_after(0, lambda: self.set_status("Refreshed", "success"))
                    else:
                        self._safe_after(0, lambda: self.add_message(
                            f"Refresh failed: {result.get('error', 'Unknown error')}\n\n"
                            "**Make sure:**\n"
                            "1. StartServer is running in Altium\n"
                            "2. PCB is open in Altium\n"
                            "3. StartServer has auto-exported the data",
                            is_user=False
                        ))
                        self._safe_after(0, lambda: self.set_status("Refresh Failed", "error"))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        "**No PCB file or export found.**\n\n"
                        "**Option 1 (Recommended):** Upload .PcbDoc file\n"
                        "  • Click 📁 button → Select your .PcbDoc file\n"
                        "  • Design rules are extracted automatically!\n\n"
                        "**Option 2:** Use Altium export\n"
                        "  1. Open Altium Designer\n"
                        "  2. Open your PCB\n"
                        "  3. Run: **DXP → Run Script → `command_server.pas` → `StartServer`**\n"
                        "  4. Then click **Refresh Data** again",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("No PCB Found", "warning"))
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"Error refreshing: {str(e)}",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=refresh, daemon=True).start()
    
    def _get_routing_suggestions(self):
        """Get AI routing suggestions"""
        self.add_message("Generating routing suggestions...", is_user=False)
        self.set_status("Analyzing...", "warning")
        
        def get_suggestions():
            try:
                result = self.mcp_client.get_routing_suggestions()
                
                if result.get("success"):
                    suggestions = result.get("suggestions", [])
                    if suggestions:
                        msg = "Routing Suggestions:\n\n"
                        for s in suggestions[:10]:
                            priority = s.get("priority", "normal").upper()
                            net = s.get("net", "Unknown")
                            rec = s.get("recommendation", "")
                            msg += f"[{priority}] {net}: {rec}\n"
                        
                        self._safe_after(0, lambda: self.add_message(msg, is_user=False))
                        self._safe_after(0, lambda: self.set_status("Suggestions Ready", "success"))
                    else:
                        self._safe_after(0, lambda: self.add_message(
                            "No routing suggestions. All nets may be routed.",
                            is_user=False
                        ))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        f"Error: {result.get('error', 'No PCB loaded')}",
                        is_user=False
                    ))
                    
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"Error: {str(e)}",
                    is_user=False
                ))
        
        threading.Thread(target=get_suggestions, daemon=True).start()
    
    def _list_components(self):
        """List all components from current PCB"""
        try:
            result = self.mcp_client.get_pcb_info()
            
            if result and not result.get("error"):
                components = result.get("components", [])
                if components:
                    msg = f"Components ({len(components)}):\n\n"
                    for c in components[:30]:
                        name = c.get("designator", c.get("name", "?"))
                        footprint = c.get("footprint", "")
                        msg += f"  {name}: {footprint}\n"
                    
                    if len(components) > 30:
                        msg += f"\n... and {len(components) - 30} more"
                    
                    self.add_message(msg, is_user=False)
                else:
                    self.add_message("No components found.", is_user=False)
            else:
                self.add_message("No PCB loaded.", is_user=False)
        except Exception as e:
            self.add_message(f"Error: {str(e)}", is_user=False)
    
    def _check_altium_status(self):
        """Check Altium script server status"""
        self.add_message("Checking Altium connection...", is_user=False)
        
        def check():
            try:
                from tools.altium_script_client import AltiumScriptClient
                client = AltiumScriptClient()
                
                if client.ping():
                    self._safe_after(0, lambda: self.add_message(
                        "Altium Script Server: CONNECTED\n\n"
                        "You can now:\n"
                        "- Run DRC from the menu\n"
                        "- Use chat commands to modify the PCB\n"
                        "- Export PCB info",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Altium Connected", "success"))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        "Altium Script Server: NOT CONNECTED\n\n"
                        "To connect:\n"
                        "1. Open Altium Designer\n"
                        "2. Open your PCB document\n"
                        "3. Run: DXP -> Run Script\n"
                        "4. Select: altium_scripts/command_server.pas\n"
                        "5. Run: StartServer or ExecuteNow",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Altium Not Connected", "warning"))
                    
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"Error checking Altium: {str(e)}",
                    is_user=False
                ))
        
        threading.Thread(target=check, daemon=True).start()
    
    def add_welcome_message(self):
        """Add professional welcome message"""
        welcome = """Hi! I'm EagilinsED, your PCB design assistant.

Use the menu (three dots) for actions like Run DRC, Export PCB, etc.

Chat with me to:
- Move, add, or delete components
- Get routing recommendations  
- Analyze your design"""
        
        self.add_message(welcome, is_user=False)
    
    def add_message(self, message: str, is_user: bool = True) -> ChatMessage:
        """Add message to chat"""
        # Strip markdown from assistant messages
        if not is_user:
            message = strip_markdown(message)
        msg = ChatMessage(self.chat_frame, message, is_user, self.colors)
        msg.grid(row=len(self.messages), column=0, sticky="ew", padx=20, pady=8)
        self.messages.append(msg)
        
        # Scroll to bottom
        self.chat_frame.update()
        self.chat_frame._parent_canvas.yview_moveto(1.0)
        
        return msg
    
    def send_message(self):
        """Send user message"""
        text = self.input_entry.get().strip()
        if not text or self.is_loading:
            return
        
        # Clear input
        self.input_entry.delete(0, "end")
        
        # Add user message
        self.add_message(text, is_user=True)
        
        # Check if we're waiting for rule input
        if self.waiting_for_rule_input:
            self.waiting_for_rule_input = False
            action_type = self.rule_action_type
            self.rule_action_type = None
            
            # Process rule creation/update
            self._process_rule_request(text, action_type)
            return
        
        if not self.agent:
            self.add_message("LLM not available. Check OpenAI API key.", is_user=False)
            return
        
        # Update status
        self.set_status("Processing...", "warning")
        self.set_loading(True)
        
        # Process in thread
        threading.Thread(target=self.process_message, args=(text,), daemon=True).start()
    
    def set_loading(self, loading: bool):
        """Set loading state"""
        self.is_loading = loading
        if loading:
            self.send_button.configure(text="◌", state="disabled", fg_color=self.colors["text_dim"])
            self.input_entry.configure(state="disabled")
        else:
            self.send_button.configure(text="→", state="normal", fg_color=self.colors["primary"])
            self.input_entry.configure(state="normal")
            self.input_entry.focus()
    
    def set_status(self, text: str, status: str = "success"):
        """Update status indicator"""
        colors = {
            "success": self.colors["success"],
            "warning": self.colors["warning"],
            "error": self.colors["error"],
            "info": self.colors["accent"]
        }
        color = colors.get(status, self.colors["success"])
        self.status_dot.configure(text_color=color)
        self.status_text.configure(text=text)
    
    def process_message(self, text: str):
        """Process message in background"""
        try:
            # Create streaming message
            streaming_msg = ChatMessage(self.chat_frame, "", False, self.colors)
            streaming_msg.grid(row=len(self.messages), column=0, sticky="ew", padx=20, pady=8)
            self.messages.append(streaming_msg)
            
            # Scroll
            self._safe_after(0, lambda: self.chat_frame._parent_canvas.yview_moveto(1.0))
            
            # Stream callback
            def on_chunk(chunk: str):
                if chunk and not self.is_destroyed:
                    self._safe_after(0, lambda c=chunk: streaming_msg.append_text(c))
                    self._safe_after(0, lambda: self.chat_frame._parent_canvas.yview_moveto(1.0))
            
            # Process
            response, status, is_exec = self.agent.process_query(text, stream_callback=on_chunk)
            
            # Update UI
            self._safe_after(0, lambda: self.on_response_complete(response, status, is_exec, streaming_msg))
            
        except Exception as ex:
            error_msg = str(ex)
            self._safe_after(0, lambda: self.on_response_complete(f"Error: {error_msg}", "error", False, None))
    
    def on_response_complete(self, response: str, status: str, is_exec: bool, msg: ChatMessage):
        """Handle response completion"""
        if msg and msg.msg_label.cget("text") != response:
            msg.set_text(response)
        elif not msg:
            self.add_message(response, is_user=False)
        
        # Always re-enable input first
        self.set_loading(False)
        
        # Add DRC helper button if DRC results shown
        if "DRC Results" in response or "View Violations" in response:
            self._add_drc_helper_button()
        
        # Check if this is a confirmation request
        if status == "confirm":
            # Store confirmation data
            self.pending_confirmation = {
                "message": response,
                "command": getattr(self.agent, 'pending_command', None)
            }
            # Show confirmation modal
            self._show_confirmation_modal(response)
            self.set_status("Waiting for confirmation", "info")
        elif status == "error":
            self.set_status("Error", "error")
        elif is_exec:
            self.set_status("Command Ready", "info")
        elif status in ["analyzed", "strategy_generated", "reviewed", "layout_generated"]:
            self.set_status("Analysis Complete", "success")
        else:
            self.set_status("Ready", "success")
        
        # Final scroll
        self.chat_frame.update()
        self.chat_frame._parent_canvas.yview_moveto(1.0)
    
    def _add_drc_helper_button(self):
        """Add button to run Python DRC check"""
        # Create button container
        btn_container = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        btn_container.grid(row=len(self.messages) + 100, column=0, sticky="w", pady=10, padx=10)
        
        # Run DRC Check button (replaces old HTML report viewer)
        report_btn = ctk.CTkButton(
            btn_container,
            text="🔍 Run DRC Check",
            width=220,
            height=40,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._open_drc_report
        )
        report_btn.pack(side="left", padx=5)
        
        # Scroll to show button
        self.chat_frame.update()
        self.chat_frame._parent_canvas.yview_moveto(1.0)
    
    def _open_drc_report(self, path: str = None):
        """Run Python DRC check (replaces old HTML report viewer)"""
        # This method now triggers a Python DRC check instead of opening HTML
        self._get_drc_suggestions()
    
    def _auto_generate_drc_rules(self):
        """Automatically generate DRC rules from PCB design"""
        self.add_message("Generating DRC rules automatically from PCB design...", is_user=False)
        self.set_status("Generating Rules...", "warning")
        
        def generate_rules():
            try:
                result = self.mcp_client.session.get("http://localhost:8765/drc/auto-generate-rules?update_existing=true")
                
                if result.status_code == 200:
                    data = result.json()
                    if data.get("success"):
                        rule_count = data.get("rule_count", 0)
                        msg = f"✅ **DRC Rules Generated Successfully!**\n\n"
                        msg += f"**Generated {rule_count} design rules** based on your PCB design:\n\n"
                        msg += "• Rules are automatically created based on:\n"
                        msg += "  - Net types (Power, Ground, High-Speed, etc.)\n"
                        msg += "  - Board size and complexity\n"
                        msg += "  - Component density\n"
                        msg += "  - Layer count\n\n"
                        msg += "**Next steps:**\n"
                        msg += "1. Run DRC to check for violations\n"
                        msg += "2. Get suggestions to see recommendations\n"
                        msg += "3. Rules will be used automatically in future DRC checks\n"
                        
                        self._safe_after(0, lambda: self.add_message(msg, is_user=False))
                        self._safe_after(0, lambda: self.set_status("Rules Generated", "success"))
                    else:
                        error_msg = data.get("error", "Unknown error")
                        self._safe_after(0, lambda: self.add_message(
                            f"❌ Error generating rules: {error_msg}\n\n"
                            "Make sure a PCB is loaded first (use Refresh Data).",
                            is_user=False
                        ))
                        self._safe_after(0, lambda: self.set_status("Error", "error"))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        "❌ Failed to connect to MCP server. Make sure mcp_server.py is running.",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Connection Error", "error"))
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"❌ Error: {str(e)}",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=generate_rules, daemon=True).start()
    
    def _get_drc_suggestions(self):
        """Run Python DRC check and display results with fix suggestions"""
        self.add_message("Running DRC check...", is_user=False)
        self.set_status("Checking...", "warning")
        
        def run_drc():
            try:
                # First, run DRC check
                result = self.mcp_client.session.get("http://localhost:8765/drc/run")
                
                if result.status_code == 200:
                    data = result.json()
                    if data.get("success"):
                        # Display DRC results in Altium-style format
                        summary = data.get("summary", {})
                        violations = data.get("violations", [])
                        warnings = data.get("warnings", [])
                        violations_by_rule = data.get("violations_by_rule", {})
                        drc_source = data.get("source", "python_fallback")
                        native_details_available = data.get("native_details_available", True)
                        supplemental_violations = data.get("supplemental_violations", [])
                        is_native_source = str(drc_source).startswith("altium_native")
                        
                        # Get additional data
                        all_rules = data.get("all_rules_checked", [])
                        filename = data.get("filename", "Unknown")
                        python_checked_rules = data.get("python_checked_rules", [])
                        total_rules = data.get("total_rules", 0)
                        rules_checked_count = data.get("rules_checked_count", 0)
                        # Main title with larger header
                        msg = "# 📊 Design Rule Check Report\n\n"
                        
                        # Filename with emphasis
                        msg += f"**PCB File:** `{filename}`\n\n"
                        msg += f"**DRC Source:** `{drc_source}`\n\n"
                        if drc_source == "altium_native_counts_report_details":
                            msg += "*Counts and detailed rows come from native Altium sources (DRC export + report parser).*\\n\\n"
                        elif drc_source == "altium_native_counts_with_python_supplemental":
                            msg += "*Counts come from native Altium DRC. Detailed rows below are supplemental Python DRC geometry details and may not map 1:1 to Altium entries.*\n\n"
                        msg += "---\n\n"
                        
                        # Summary section with visual emphasis
                        msg += "## 📈 Summary\n\n"
                        
                        warnings_count = summary.get('warnings', 0)
                        violations_count = summary.get('rule_violations', 0)
                        
                        # Use larger, bolder text for key metrics
                        if violations_count == 0 and warnings_count == 0:
                            msg += "### ✅ **All Checks Passed!**\n\n"
                            msg += "**Warnings:** `0`  |  **Rule Violations:** `0`\n\n"
                        else:
                            if violations_count > 0:
                                msg += f"### 🔴 **Rule Violations:** `{violations_count}`\n\n"
                            if warnings_count > 0:
                                msg += f"### ⚠️ **Warnings:** `{warnings_count}`\n\n"
                        
                        msg += "---\n\n"
                        
                        # Warnings section
                        msg += "## ⚠️ Warnings\n\n"
                        if warnings:
                            msg += f"**Total:** **{len(warnings)}** warning(s)\n\n"
                        else:
                            msg += "**Total:** **0** warnings\n\n"
                        
                        msg += "---\n\n"
                        
                        # Rule Violations section with better table formatting
                        msg += "## 📋 Rule Violations\n\n"
                        msg += "| **Rule Violations** | **Count** |\n"
                        msg += "|:-------------------|----------:|\n"
                        
                        if all_rules:
                            # Show all rules checked, even with 0 violations
                            for rule_info in all_rules:
                                formatted_name = rule_info.get("formatted_name", rule_info.get("rule_name", "Unknown"))
                                count = rule_info.get("count", 0)
                                msg += f"| {formatted_name} | {count} |\n"
                        elif violations_by_rule:
                            # Fallback: show only rules with violations
                            for rule_name, count in sorted(violations_by_rule.items()):
                                msg += f"| {rule_name} | {count} |\n"
                        else:
                            # No rules found - show placeholder
                            msg += "| No rules checked | 0 |\n"
                        
                        msg += f"\n**Total Violations:** **{summary.get('rule_violations', 0)}**\n\n"
                        
                        msg += "---\n\n"
                        
                        if (not is_native_source) and python_checked_rules:
                            msg += "### 📋 Rules Currently Checked\n\n"
                            
                            # Group by rule type
                            by_type = {}
                            for rule in python_checked_rules:
                                rule_type = rule.get("rule_type", "other")
                                if rule_type not in by_type:
                                    by_type[rule_type] = []
                                by_type[rule_type].append(rule.get("formatted_name", rule.get("rule_name")))
                            
                            # Show by category with better formatting
                            type_labels = {
                                'clearance': '🔲 Clearance Constraints',
                                'width': '📏 Width Constraints',
                                'via': '🔘 Via/Hole Size Constraints',
                                'hole_size': '🕳️ Hole Size Constraints',
                                'short_circuit': '⚡ Short-Circuit Constraints',
                                'unrouted_net': '🔌 Un-Routed Net Constraints',
                                'hole_to_hole_clearance': '📐 Hole To Hole Clearance',
                                'solder_mask_sliver': '🛡️ Minimum Solder Mask Sliver',
                                'silk_to_solder_mask': '🎨 Silk To Solder Mask',
                                'silk_to_silk': '🖨️ Silk to Silk',
                                'height': '📏 Height Constraints',
                                'modified_polygon': '🔷 Modified Polygon',
                                'net_antennae': '📡 Net Antennae',
                                'diff_pairs_routing': '⚖️ Differential Pair Routing',
                                'routing_topology': '🌐 Routing Topology',
                                'routing_via_style': '🔧 Via Style Constraints',
                                'routing_corners': '📐 Routing Corners',
                                'routing_layers': '📚 Routing Layers',
                                'routing_priority': '⭐ Routing Priority',
                                'plane_connect': '🔌 Power Plane Connect'
                            }
                            
                            # Create a cleaner table format for rules
                            msg += "| **Category** | **Count** | **Rules** |\n"
                            msg += "|:-------------|----------:|:----------|\n"
                            
                            for rule_type, rules_list in sorted(by_type.items()):
                                label = type_labels.get(rule_type, f"📌 {rule_type.replace('_', ' ').title()}")
                                count = len(rules_list)
                                
                                # Format rule names (show first 2, then count)
                                if count <= 2:
                                    rules_display = " • ".join([f"`{r}`" for r in rules_list])
                                else:
                                    rules_display = f"`{rules_list[0]}` • `{rules_list[1]}` • *+{count-2} more*"
                                
                                msg += f"| {label} | **{count}** | {rules_display} |\n"
                            
                            msg += "\n"
                        elif not is_native_source:
                            msg += "> ⚠️ **Note:** No rules were found in the PCB file. Using default rules for checking.\n\n"
                        else:
                            msg += "> ✅ **Native Altium DRC source in use.** Rule table above is from Altium export.\n\n"
                        
                        if not is_native_source:
                            msg += "---\n\n"
                            msg += "### ✅ **Engine Capabilities**\n\n"
                            msg += "The Python DRC engine performs comprehensive validation including:\n\n"
                            
                            # Use a cleaner two-column format for capabilities
                            capabilities = [
                                ("🔍 Clearance violations", "Pad-to-pad, via-to-pad spacing"),
                                ("📏 Track width constraints", "Min/max width validation"),
                                ("🔘 Via & hole size", "Diameter and drill size checks"),
                                ("⚡ Short-circuit detection", "Overlap detection between nets"),
                                ("🔌 Unrouted net detection", "With polygon connectivity support"),
                                ("📐 Hole-to-hole clearance", "Edge-to-edge distance validation"),
                                ("🛡️ Solder mask sliver", "Mask gap detection"),
                                ("🎨 Silk screen clearance", "Silk-to-silk and silk-to-mask"),
                                ("📏 Component height", "Height constraint validation"),
                                ("🔷 Modified polygon", "Polygon modification checks"),
                                ("📡 Net antennae", "Stub trace detection"),
                                ("⚖️ Differential pairs", "Width and gap validation"),
                                ("🌐 Routing topology", "Topology pattern validation"),
                                ("🔧 Via style", "Via dimension constraints"),
                                ("📐 Routing corners", "Corner angle validation"),
                                ("📚 Routing layers", "Layer restriction checks"),
                                ("⭐ Routing priority", "Priority-based validation"),
                                ("🔌 Power plane connect", "Plane connection style")
                            ]
                            
                            # Display in a clean two-column table
                            msg += "| **Feature** | **Description** |\n"
                            msg += "|:------------|:-----------------|\n"
                            for feature, desc in capabilities:
                                msg += f"| {feature} | {desc} |\n"
                            
                            msg += "\n"
                        
                        if summary.get("passed", False):
                            msg += "✅ **All checks passed!** No violations or warnings detected.\n\n"
                            self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                            self._safe_after(0, lambda: self.set_status("Passed", "success"))
                            return
                        
                        # Show detailed violations (first 10)
                        if violations:
                            msg += "---\n\n"
                            msg += "## 🔍 Detailed Violations\n\n"
                            for i, v in enumerate(violations[:10], 1):
                                rule_type = v.get("type", "unknown").replace("_", " ").title()
                                message = v.get("message", "")
                                location = v.get("location", {})
                                
                                msg += f"### **{i}. {rule_type}**\n"
                                if location.get("x_mm") is not None and location.get("y_mm") is not None:
                                    msg += f"- **Location:** `({location['x_mm']:.2f}, {location['y_mm']:.2f}) mm`\n"
                                if location.get("layer"):
                                    msg += f"- **Layer:** `{location['layer']}`\n"
                                if v.get("component_name"):
                                    msg += f"- **Component:** `{v['component_name']}`\n"
                                if v.get("net_name"):
                                    msg += f"- **Net:** `{v['net_name']}`\n"
                                if v.get("actual_value") is not None and v.get("required_value") is not None:
                                    msg += f"- **Actual:** `{v['actual_value']} mm` | **Required:** `{v['required_value']} mm`\n"
                                msg += f"\n*{message}*\n\n"
                            
                            if len(violations) > 10:
                                msg += f"---\n\n"
                                msg += f"*... and **{len(violations) - 10}** more violation(s).*\n\n"
                        elif drc_source == "altium_native_counts_with_python_supplemental" and supplemental_violations:
                            msg += "---\n\n"
                            msg += "## 🔍 Supplemental Detail (Python Geometry)\n\n"
                            msg += "*Native Altium counts are exact. The detailed rows below are supplemental and may differ from Altium’s exact violation listing order/content.*\n\n"
                            for i, v in enumerate(supplemental_violations[:10], 1):
                                rule_type = v.get("type", "unknown").replace("_", " ").title()
                                message = v.get("message", "")
                                location = v.get("location", {})
                                msg += f"### **{i}. {rule_type}**\n"
                                if location.get("x_mm") is not None and location.get("y_mm") is not None:
                                    msg += f"- **Location:** `({location['x_mm']:.2f}, {location['y_mm']:.2f}) mm`\n"
                                if location.get("layer"):
                                    msg += f"- **Layer:** `{location['layer']}`\n"
                                if v.get("net_name"):
                                    msg += f"- **Net:** `{v['net_name']}`\n"
                                msg += f"\n*{message}*\n\n"
                            if len(supplemental_violations) > 10:
                                msg += f"*... and **{len(supplemental_violations) - 10}** more supplemental detail rows.*\n\n"
                        elif drc_source == "altium_native_drc" and not native_details_available:
                            msg += "---\n\n"
                            msg += "## 🔍 Detailed Violations\n\n"
                            msg += "*Native Altium DRC details are not exposed by this Altium scripting API build.*\n"
                            msg += "*Rule counts above are exact from Altium; only per-violation message/coordinates are unavailable.*\n\n"
                        
                        # Get suggestions if violations exist
                        suggestions = []
                        has_actionable_suggestions = False
                        
                        if violations:
                            try:
                                suggestions_result = self.mcp_client.session.get("http://localhost:8765/drc/suggestions")
                                if suggestions_result.status_code == 200:
                                    suggestions_data = suggestions_result.json()
                                    if suggestions_data.get("success"):
                                        suggestions = suggestions_data.get("suggestions", [])
                                        if suggestions:
                                            msg += "### 💡 Suggestions\n\n"
                                            for s in suggestions[:5]:
                                                suggestion_msg = s.get('message', 'No message')
                                                msg += f"• {suggestion_msg}\n"
                                                # Check if this is an actionable suggestion (contains move/rotate commands)
                                                if any(keyword in suggestion_msg.lower() for keyword in ['move', 'rotate', 'place']):
                                                    has_actionable_suggestions = True
                                            if len(suggestions) > 5:
                                                msg += f"\n... and {len(suggestions) - 5} more suggestions.\n"
                            except Exception as e:
                                pass  # Suggestions are optional
                        
                        # If we have violations, always show the fix prompt (we can generate basic suggestions)
                        if violations:
                            has_actionable_suggestions = True
                            # If no suggestions from the engine, create basic ones from violations
                            if not suggestions:
                                suggestions = self._generate_basic_suggestions_from_violations(violations)
                        
                        # First, show the DRC results
                        self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                        self._safe_after(0, lambda: self.set_status("DRC Complete", "success" if summary.get("passed") else "warning"))
                        
                        # Then, if there are violations, show the fix prompt and buttons
                        if violations and has_actionable_suggestions:
                            # Store suggestions for later use
                            self.current_drc_suggestions = suggestions if suggestions else []
                            # Add the fix prompt as a separate message with a small delay to ensure proper ordering
                            self._safe_after(500, lambda: self._add_fix_prompt_and_buttons())
                    else:
                        error_msg = data.get("error", "Unknown error")
                        self._safe_after(0, lambda: self.add_message(
                            f"❌ DRC check failed: {error_msg}",
                            is_user=False
                        ))
                        self._safe_after(0, lambda: self.set_status("Error", "error"))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        "❌ Failed to connect to MCP server.",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Connection Error", "error"))
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._safe_after(0, lambda: self.add_message(
                    f"❌ Error: {str(e)}",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=run_drc, daemon=True).start()
    
    def _generate_basic_suggestions_from_violations(self, violations):
        """Generate intelligent actionable suggestions from actual DRC violations"""
        suggestions = []
        
        print(f"DEBUG: Generating suggestions for {len(violations)} violations")
        
        for i, violation in enumerate(violations):
            v_type = violation.get("type", "").lower()
            message = violation.get("message", "")
            location = violation.get("location", {})
            
            print(f"DEBUG: Violation {i+1}: {message}")
            
            # Handle unrouted net violations
            if "unrouted" in v_type.lower():
                net_name = violation.get("net_name", "")
                x = location.get("x_mm", 0)
                y = location.get("y_mm", 0)
                
                if net_name:
                    suggestions.append({
                        "type": "route_net",
                        "net": net_name,
                        "x": x,
                        "y": y,
                        "message": f"Route net '{net_name}' — add tracks to connect all pads on this net",
                        "reason": f"Un-Routed Net: {net_name}"
                    })
                continue
            
            # Handle net antennae violations
            if "antennae" in v_type.lower() or "antenna" in v_type.lower():
                net_name = violation.get("net_name", "")
                x = location.get("x_mm", 0)
                y = location.get("y_mm", 0)
                
                suggestions.append({
                    "type": "fix_antenna",
                    "net": net_name,
                    "x": x,
                    "y": y,
                    "message": f"Fix dead-end track on net '{net_name}' at ({x:.1f}, {y:.1f}) — extend to nearest pad or remove stub",
                    "reason": f"Net Antennae: dead-end track on {net_name}"
                })
                continue
            
            # Parse clearance violations more intelligently
            if "clearance" in v_type.lower() or "clearance" in message.lower():
                x = location.get("x_mm")
                y = location.get("y_mm")
                
                if x is not None and y is not None:
                    print(f"DEBUG: Clearance violation at ({x:.1f}, {y:.1f})")
                    
                    # Analyze the violation message to determine what objects are involved
                    message_lower = message.lower()
                    
                    # Check if this is a copper pour vs track violation
                    if "poured copper" in message_lower and "track" in message_lower:
                        print(f"DEBUG: Detected copper pour vs track violation - attempting AUTOMATIC fix")
                        
                        # Create automatic copper pour clearance adjustment suggestion
                        suggestions.append({
                            "type": "adjust_copper_pour_clearance",
                            "x": x,
                            "y": y,
                            "clearance_mm": 0.4,  # Increase clearance to 0.4mm
                            "message": f"Automatically adjust copper pour clearance to 0.4mm at ({x:.1f}, {y:.1f})",
                            "reason": f"Copper pour clearance violation at ({x:.1f}, {y:.1f})"
                        })
                        print(f"DEBUG: Created automatic copper pour fix suggestion")
                    
                    else:
                        # Handle other types of clearance violations (component-to-component, etc.)
                        nearby_components = self._find_components_near_location(x, y, 5.0)
                        
                        if nearby_components:
                            print(f"DEBUG: Found nearby components: {nearby_components}")
                            
                            comp_name = nearby_components[0]
                            move_distance = 2.0
                            new_x = x + move_distance if i % 2 == 0 else x - move_distance
                            new_y = y + move_distance * 0.5
                            
                            suggestion = {
                                "type": "move_component",
                                "component": comp_name,
                                "new_x": new_x,
                                "new_y": new_y,
                                "message": f"Move {comp_name} to [{new_x:.1f}, {new_y:.1f}] to resolve clearance violation",
                                "reason": f"Clearance violation at ({x:.1f}, {y:.1f})"
                            }
                            
                            suggestions.append(suggestion)
                            print(f"DEBUG: Created standard clearance fix suggestion: {suggestion}")
                        else:
                            print(f"DEBUG: No components found near violation at ({x:.1f}, {y:.1f})")
        
        print(f"DEBUG: Generated {len(suggestions)} actionable suggestions")
        return suggestions
    
    def _find_components_near_location(self, x, y, radius):
        """Find actual components near a specific location from the loaded PCB data"""
        try:
            # First try to get PCB info from MCP client
            pcb_info = self.mcp_client.get_pcb_info()
            components = []
            
            if pcb_info and not pcb_info.get("error"):
                components = pcb_info.get("components", [])
                print(f"DEBUG: Got {len(components)} components from MCP client")
            
            # If MCP client doesn't have good data, try direct file read
            if not components or (len(components) > 0 and components[0].get("designator") in ["U?", None]):
                print("DEBUG: MCP data seems incomplete, trying direct file read")
                try:
                    from pathlib import Path
                    import json
                    
                    # Try PCB_Project folder first, then root
                    altium_file = Path("PCB_Project") / "altium_pcb_info.json"
                    if not altium_file.exists():
                        altium_file = Path("altium_pcb_info.json")
                    
                    if altium_file.exists():
                        try:
                            with open(altium_file, 'r', encoding='utf-8') as f:
                                altium_data = json.load(f)
                        except UnicodeDecodeError:
                            with open(altium_file, 'r', encoding='latin-1') as f:
                                altium_data = json.load(f)
                        components = altium_data.get("components", [])
                        print(f"DEBUG: Got {len(components)} components from direct file read")
                    else:
                        print("DEBUG: No altium_pcb_info.json file found")
                except Exception as e:
                    print(f"DEBUG: Error reading altium_pcb_info.json: {e}")
            
            if not components:
                print("DEBUG: No components found in any data source")
                return []
            
            nearby = []
            print(f"DEBUG: Looking for components near ({x:.1f}, {y:.1f}) within {radius}mm")
            print(f"DEBUG: Found {len(components)} total components in PCB")
            
            for comp in components:
                # Handle different possible data structures
                comp_x = None
                comp_y = None
                comp_name = None
                
                # Try different ways to get component position
                if isinstance(comp, dict):
                    # Try direct x_mm, y_mm
                    comp_x = comp.get("x_mm")
                    comp_y = comp.get("y_mm")
                    comp_name = comp.get("designator") or comp.get("name") or comp.get("Name")
                    
                    # Try location sub-object
                    if comp_x is None and "location" in comp:
                        location = comp["location"]
                        comp_x = location.get("x_mm")
                        comp_y = location.get("y_mm")
                    
                    # Try other common field names
                    if comp_x is None:
                        comp_x = comp.get("X") or comp.get("x")
                        comp_y = comp.get("Y") or comp.get("y")
                
                if comp_x is not None and comp_y is not None and comp_name and comp_name != "U?":
                    # Calculate distance
                    distance = ((float(comp_x) - x) ** 2 + (float(comp_y) - y) ** 2) ** 0.5
                    print(f"DEBUG: Component {comp_name} at ({comp_x}, {comp_y}), distance: {distance:.2f}mm")
                    
                    if distance <= radius:
                        nearby.append(comp_name)
                        print(f"DEBUG: Added {comp_name} to nearby list")
            
            print(f"DEBUG: Found {len(nearby)} components within {radius}mm: {nearby}")
            
            if nearby:
                return nearby[:3]  # Return up to 3 nearby components
            else:
                # If no components found nearby, get some components from anywhere in the PCB
                all_component_names = []
                for comp in components[:10]:  # Check first 10 components
                    if isinstance(comp, dict):
                        comp_name = comp.get("designator") or comp.get("name") or comp.get("Name")
                        if comp_name and comp_name != "U?":
                            all_component_names.append(comp_name)
                
                print(f"DEBUG: No nearby components, using any available: {all_component_names[:3]}")
                return all_component_names[:3]
                
        except Exception as e:
            print(f"DEBUG: Error finding components: {e}")
            import traceback
            traceback.print_exc()
        
        # Fallback: return empty list instead of fake component names
        print("DEBUG: Returning empty list - no real components found")
        return []
    
    def _add_fix_prompt_and_buttons(self):
        """Add the fix prompt message and Yes/Ignore buttons as separate elements"""
        try:
            # First add the prompt message
            fix_prompt = "Want me to fix any of these?\n\nI can automatically move and rotate components to resolve violations."
            self.add_message(fix_prompt, is_user=False)
            
            # Then add the buttons with a small delay to ensure proper UI update
            self.after(200, self._add_drc_fix_buttons)
            
        except Exception as e:
            # Fallback: try to add buttons directly
            try:
                self._add_drc_fix_buttons()
            except:
                pass
    
    def _add_drc_fix_buttons(self):
        """Add Fix/Ignore buttons for DRC fix suggestions"""
        try:
            # Create button container
            btn_container = ctk.CTkFrame(
                self.chat_frame,
                fg_color=self.colors["bg_card"],
                corner_radius=12,
                border_width=1,
                border_color=self.colors["border"]
            )
            btn_container.grid(row=len(self.messages), column=0, sticky="ew", padx=20, pady=12)
            btn_container.grid_columnconfigure(0, weight=1)
            btn_container.grid_columnconfigure(1, weight=1)
            self.messages.append(btn_container)
            
            # Fix button (instead of Yes)
            fix_btn = ctk.CTkButton(
                btn_container,
                text="🔧 Fix",
                font=ctk.CTkFont(size=13, weight="bold"),
                height=42,
                corner_radius=10,
                fg_color=self.colors["success"],
                hover_color="#059669",
                text_color="#ffffff",
                command=self._handle_drc_fix_show_approach,
                border_width=0
            )
            fix_btn.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="ew")
            
            # Ignore button
            ignore_btn = ctk.CTkButton(
                btn_container,
                text="❌ Ignore",
                font=ctk.CTkFont(size=13, weight="bold"),
                height=42,
                corner_radius=10,
                fg_color=self.colors["text_dim"],
                hover_color="#475569",
                text_color="#ffffff",
                command=self._handle_drc_fix_ignore,
                border_width=0
            )
            ignore_btn.grid(row=0, column=1, padx=(8, 16), pady=16, sticky="ew")
            
            # Scroll to show buttons
            self.chat_frame.update()
            self.chat_frame._parent_canvas.yview_moveto(1.0)
            
        except Exception as e:
            print(f"Error in _add_drc_fix_buttons: {e}")
    
    def _handle_drc_fix_show_approach(self):
        """Handle Fix button — show fix plan, then Apply/Cancel."""
        self.add_message("🔧 Analyzing violations and creating fix plan...", is_user=False)
        
        if not hasattr(self, 'current_drc_suggestions') or not self.current_drc_suggestions:
            self.add_message("❌ No violations to fix.", is_user=False)
            return
        
        # Build fix plan from the suggestions
        plan_msg = "### 🔧 Fix Plan\n\n"
        
        antenna_fixes = [s for s in self.current_drc_suggestions if s.get('type') == 'fix_antenna']
        route_fixes = [s for s in self.current_drc_suggestions if s.get('type') == 'route_net']
        clearance_fixes = [s for s in self.current_drc_suggestions if s.get('type') in ('adjust_copper_pour_clearance', 'move_component')]
        
        step = 1
        if antenna_fixes:
            plan_msg += f"**Step {step}: Delete dead-end tracks ({len(antenna_fixes)} antenna tracks)**\n"
            for fix in antenna_fixes:
                net = fix.get('net', 'Unknown')
                x, y = fix.get('x', 0), fix.get('y', 0)
                plan_msg += f"  • Delete stub track on net **{net}** at ({x:.1f}, {y:.1f})\n"
            plan_msg += "\n"
            step += 1
        
        if route_fixes:
            plan_msg += f"**Step {step}: Route unconnected nets ({len(route_fixes)} nets)**\n"
            for fix in route_fixes:
                net = fix.get('net', 'Unknown')
                plan_msg += f"  • Add track to connect net **{net}**\n"
            plan_msg += "\n"
            step += 1
        
        if clearance_fixes:
            plan_msg += f"**Step {step}: Fix clearance violations ({len(clearance_fixes)} objects)**\n"
            for fix in clearance_fixes:
                plan_msg += f"  • {fix.get('message', 'Adjust clearance')}\n"
            plan_msg += "\n"
            step += 1
        
        if not antenna_fixes and not route_fixes and not clearance_fixes:
            plan_msg += "No automatic fixes available for these violations.\n"
            plan_msg += "They require manual work in Altium Designer.\n"
            self.add_message(plan_msg, is_user=False)
            return
        
        plan_msg += "**Click Apply to execute these fixes, or Cancel to skip.**"
        self.add_message(plan_msg, is_user=False)
        
        # Show Apply / Cancel buttons
        self._add_apply_cancel_buttons()
    
    def _handle_drc_fix_show_approach_OLD(self):
        """OLD: Handle Fix button click - show fix approach first (DEPRECATED)"""
        self.add_message("Analyzing violations and determining fix approach...", is_user=False)
        self.set_status("Analyzing fixes...", "warning")
        
        def show_approach():
            try:
                if not hasattr(self, 'current_drc_suggestions') or not self.current_drc_suggestions:
                    self._safe_after(0, lambda: self.add_message(
                        "❌ No actionable suggestions available.",
                        is_user=False
                    ))
                    return
                
                # Analyze suggestions and create fix approach description
                approach_msg = "🔧 **Proposed Fix Approach:**\n\n"
                
                copper_pour_fixes = [s for s in self.current_drc_suggestions if s.get("type") == "adjust_copper_pour_clearance"]
                component_fixes = [s for s in self.current_drc_suggestions if s.get("type") == "move_component"]
                manual_fixes = [s for s in self.current_drc_suggestions if s.get("type") == "manual_fix_needed"]
                route_fixes = [s for s in self.current_drc_suggestions if s.get("type") == "route_net"]
                antenna_fixes = [s for s in self.current_drc_suggestions if s.get("type") == "fix_antenna"]
                
                if route_fixes:
                    approach_msg += f"**⚠️ Unrouted Nets ({len(route_fixes)} nets) — Manual routing required:**\n"
                    for i, fix in enumerate(route_fixes, 1):
                        net = fix.get('net', 'Unknown')
                        approach_msg += f"{i}. Net **{net}** — use Altium's interactive router to connect pads\n"
                    approach_msg += "\n"
                
                if antenna_fixes:
                    approach_msg += f"**⚠️ Net Antennae ({len(antenna_fixes)} tracks) — Manual fix required:**\n"
                    for i, fix in enumerate(antenna_fixes, 1):
                        net = fix.get('net', 'Unknown')
                        x, y = fix.get('x', 0), fix.get('y', 0)
                        approach_msg += f"{i}. Dead-end track on net **{net}** at ({x:.1f}, {y:.1f}) — extend to nearest pad or delete stub\n"
                    approach_msg += "\n"
                
                if copper_pour_fixes:
                    approach_msg += f"**Automatic Copper Pour Clearance Adjustments ({len(copper_pour_fixes)} violations):**\n"
                    for i, fix in enumerate(copper_pour_fixes, 1):
                        x, y = fix.get('x', 0), fix.get('y', 0)
                        clearance = fix.get('clearance_mm', 0.4)
                        approach_msg += f"{i}. Increase copper pour clearance to {clearance}mm at location ({x:.1f}, {y:.1f})\n"
                    approach_msg += "\n"
                
                if component_fixes:
                    approach_msg += f"**Component Movements ({len(component_fixes)} components):**\n"
                    for i, fix in enumerate(component_fixes, 1):
                        comp = fix.get('component', 'Unknown')
                        x, y = fix.get('new_x', 0), fix.get('new_y', 0)
                        approach_msg += f"{i}. Move {comp} to position ({x:.1f}, {y:.1f})\n"
                    approach_msg += "\n"
                
                if manual_fixes:
                    approach_msg += f"**Manual Fixes Required ({len(manual_fixes)} violations):**\n"
                    for i, fix in enumerate(manual_fixes, 1):
                        approach_msg += f"{i}. {fix.get('message', 'Manual fix needed')}\n"
                    approach_msg += "\n"
                
                approach_msg += "**What will happen:**\n"
                approach_msg += "• Altium PCB will be automatically modified\n"
                approach_msg += "• Copper pours will be rebuilt with new clearances\n"
                approach_msg += "• DRC will be re-run to verify fixes\n"
                approach_msg += "• You'll see the actual results\n\n"
                approach_msg += "Do you want to proceed with these changes?"
                
                self._safe_after(0, lambda m=approach_msg: self.add_message(m, is_user=False))
                
                # Add Accept/Ignore buttons
                self._safe_after(200, lambda: self._add_accept_ignore_buttons())
                
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"❌ Error analyzing fix approach: {str(e)}",
                    is_user=False
                ))
        
        threading.Thread(target=show_approach, daemon=True).start()
    
    def _add_accept_ignore_buttons(self):
        """Add Accept/Ignore buttons after showing fix approach"""
        try:
            # Create button container
            btn_container = ctk.CTkFrame(
                self.chat_frame,
                fg_color=self.colors["bg_card"],
                corner_radius=12,
                border_width=1,
                border_color=self.colors["border"]
            )
            btn_container.grid(row=len(self.messages), column=0, sticky="ew", padx=20, pady=12)
            btn_container.grid_columnconfigure(0, weight=1)
            btn_container.grid_columnconfigure(1, weight=1)
            self.messages.append(btn_container)
            
            # Accept button
            accept_btn = ctk.CTkButton(
                btn_container,
                text="✅ Accept",
                font=ctk.CTkFont(size=13, weight="bold"),
                height=42,
                corner_radius=10,
                fg_color=self.colors["primary"],
                hover_color=self.colors["primary_hover"],
                text_color="#ffffff",
                command=self._handle_drc_fix_accept,
                border_width=0
            )
            accept_btn.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="ew")
            
            # Ignore button
            ignore_btn = ctk.CTkButton(
                btn_container,
                text="❌ Ignore",
                font=ctk.CTkFont(size=13, weight="bold"),
                height=42,
                corner_radius=10,
                fg_color=self.colors["text_dim"],
                hover_color="#475569",
                text_color="#ffffff",
                command=self._handle_drc_fix_ignore,
                border_width=0
            )
            ignore_btn.grid(row=0, column=1, padx=(8, 16), pady=16, sticky="ew")
            
            # Scroll to show buttons
            self.chat_frame.update()
            self.chat_frame._parent_canvas.yview_moveto(1.0)
            
        except Exception as e:
            print(f"Error in _add_accept_ignore_buttons: {e}")
    
    def _handle_drc_fix_accept(self):
        """Handle Accept button click - apply the fixes"""
        self.add_message("Applying fixes to PCB...", is_user=False)
        self.set_status("Applying fixes...", "warning")
        self.set_loading(True)
        
        def apply_fixes():
            try:
                # First, let's see what components actually exist in the PCB
                try:
                    pcb_info = self.mcp_client.get_pcb_info()
                    if pcb_info and not pcb_info.get("error"):
                        components = pcb_info.get("components", [])
                        component_names = []
                        for comp in components[:10]:  # Show first 10 components
                            if isinstance(comp, dict):
                                comp_name = comp.get("designator") or comp.get("name") or comp.get("Name")
                                if comp_name:
                                    component_names.append(comp_name)
                        
                        if component_names:
                            self._safe_after(0, lambda: self.add_message(
                                f"Found {len(components)} components in PCB. Sample: {', '.join(component_names[:5])}{'...' if len(component_names) > 5 else ''}",
                                is_user=False
                            ))
                        else:
                            self._safe_after(0, lambda: self.add_message(
                                "⚠️ No component names found in PCB data. This may cause fixes to fail.",
                                is_user=False
                            ))
                    else:
                        self._safe_after(0, lambda: self.add_message(
                            "⚠️ Could not load PCB component data. Fixes may target non-existent components.",
                            is_user=False
                        ))
                except Exception as e:
                    print(f"DEBUG: Error checking PCB components: {e}")
                
                if not hasattr(self, 'current_drc_suggestions') or not self.current_drc_suggestions:
                    self._safe_after(0, lambda: self.add_message(
                        "❌ No actionable suggestions available. These violations may require manual design changes.",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_loading(False))
                    return
                
                # Separate manual fixes from actionable fixes
                actionable_suggestions = [s for s in self.current_drc_suggestions if s.get("type") != "manual_fix_needed"]
                manual_suggestions = [s for s in self.current_drc_suggestions if s.get("type") == "manual_fix_needed"]
                
                if manual_suggestions and not actionable_suggestions:
                    # All suggestions require manual work
                    self._safe_after(0, lambda: self.add_message(
                        "🔧 **Manual Fixes Required**\n\n"
                        "These violations cannot be fixed automatically by moving components.\n"
                        "They require manual design changes in Altium Designer:",
                        is_user=False
                    ))
                    
                    for suggestion in manual_suggestions:
                        msg = f"\n**{suggestion.get('message', 'Manual fix needed')}**\n"
                        msg += f"Details: {suggestion.get('details', 'N/A')}\n"
                        msg += f"Reason: {suggestion.get('reason', 'N/A')}\n"
                        
                        if 'recommendations' in suggestion:
                            msg += "\nRecommended steps:\n"
                            for rec in suggestion['recommendations']:
                                msg += f"• {rec}\n"
                        
                        self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                    
                    self._safe_after(0, lambda: self.set_loading(False))
                    self._safe_after(0, lambda: self.set_status("Manual Fixes Needed", "warning"))
                    return
                
                if not actionable_suggestions:
                    self._safe_after(0, lambda: self.add_message(
                        "❌ No automatic fixes available for these violations.",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_loading(False))
                    return
                
                # Apply fixes one by one and track actual results
                fixes_attempted = 0
                fixes_successful = 0
                fix_details = []
                errors = []
                
                self._safe_after(0, lambda: self.add_message(
                    f"Attempting to fix {len(actionable_suggestions)} violation(s)...",
                    is_user=False
                ))
                
                for i, suggestion in enumerate(actionable_suggestions):
                    try:
                        fixes_attempted += 1
                        self._safe_after(0, lambda i=i: self.add_message(
                            f"Fix {i+1}: {suggestion.get('message', 'Applying fix...')}",
                            is_user=False
                        ))
                        
                        fix_result = self._apply_single_suggestion(suggestion)
                        
                        if fix_result.get("success"):
                            fixes_successful += 1
                            fix_details.append(f"✅ {fix_result.get('message', 'Fix applied')}")
                            self._safe_after(0, lambda msg=fix_result.get('message'): self.add_message(
                                f"✅ {msg}",
                                is_user=False
                            ))
                        else:
                            error_msg = fix_result.get("error", "Unknown error")
                            errors.append(error_msg)
                            fix_details.append(f"❌ {error_msg}")
                            self._safe_after(0, lambda msg=error_msg: self.add_message(
                                f"❌ {msg}",
                                is_user=False
                            ))
                        
                        # Longer delay between fixes to prevent file locking issues
                        # This gives Altium script server time to fully process each command
                        import time
                        time.sleep(2.0)  # Increased from 0.5s to 2.0s
                        
                    except Exception as e:
                        error_msg = f"Error applying fix {i+1}: {str(e)}"
                        errors.append(error_msg)
                        self._safe_after(0, lambda msg=error_msg: self.add_message(
                            f"❌ {msg}",
                            is_user=False
                        ))
                
                # Report final results honestly
                if fixes_successful > 0:
                    self._safe_after(0, lambda: self.add_message(
                        f"Applied {fixes_successful} out of {fixes_attempted} attempted fixes.",
                        is_user=False
                    ))
                    
                    # Wait longer for Altium to update, then re-run DRC
                    import time
                    time.sleep(3)  # Give Altium more time to process changes
                    self._safe_after(0, lambda: self._rerun_drc_after_fixes())
                else:
                    error_summary = "❌ No fixes could be applied successfully.\n\n"
                    if errors:
                        error_summary += "Issues encountered:\n"
                        for error in errors[:3]:
                            error_summary += f"• {error}\n"
                        if len(errors) > 3:
                            error_summary += f"• ... and {len(errors) - 3} more errors\n"
                    
                    error_summary += "\nThese violations may require:\n"
                    error_summary += "• Different component placement strategies\n"
                    error_summary += "• Design rule adjustments\n"
                    error_summary += "• Manual design changes"
                    
                    self._safe_after(0, lambda m=error_summary: self.add_message(m, is_user=False))
                    self._safe_after(0, lambda: self.set_loading(False))
                    self._safe_after(0, lambda: self.set_status("Fixes Failed", "error"))
                
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"❌ Error during fix process: {str(e)}",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_loading(False))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=apply_fixes, daemon=True).start()
    
    def _add_apply_cancel_buttons(self):
        """Add Apply/Cancel buttons after showing fix plan."""
        try:
            btn_container = ctk.CTkFrame(
                self.chat_frame, fg_color=self.colors["bg_card"],
                corner_radius=12, border_width=1, border_color=self.colors["border"]
            )
            btn_container.grid(row=len(self.messages), column=0, sticky="ew", padx=20, pady=12)
            btn_container.grid_columnconfigure(0, weight=1)
            btn_container.grid_columnconfigure(1, weight=1)
            self.messages.append(btn_container)
            
            apply_btn = ctk.CTkButton(
                btn_container, text="✅ Apply", font=ctk.CTkFont(size=13, weight="bold"),
                height=42, corner_radius=10, fg_color=self.colors["success"],
                hover_color="#059669", text_color="#ffffff",
                command=self._handle_apply_fixes, border_width=0
            )
            apply_btn.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="ew")
            
            cancel_btn = ctk.CTkButton(
                btn_container, text="❌ Cancel", font=ctk.CTkFont(size=13, weight="bold"),
                height=42, corner_radius=10, fg_color=self.colors["text_dim"],
                hover_color="#475569", text_color="#ffffff",
                command=self._handle_cancel_fixes, border_width=0
            )
            cancel_btn.grid(row=0, column=1, padx=(8, 16), pady=16, sticky="ew")
            
            self.chat_frame.update()
            self.chat_frame._parent_canvas.yview_moveto(1.0)
        except Exception as e:
            print(f"Error adding apply/cancel buttons: {e}")
    
    def _handle_apply_fixes(self):
        """Execute the fix plan via auto-fix engine."""
        self.add_message("🔧 Applying fixes...", is_user=False)
        self.set_status("Applying fixes...", "warning")
        self.set_loading(True)
        
        def execute_fixes():
            try:
                result = self.mcp_client.session.get(
                    "http://localhost:8765/drc/auto-fix", timeout=120
                )
                
                if result.status_code == 200:
                    data = result.json()
                    log = data.get('log', [])
                    
                    # Show log
                    if log:
                        log_msg = "### 📋 Fix Log\n\n"
                        for entry in log:
                            log_msg += f"• {entry}\n"
                        self._safe_after(0, lambda m=log_msg: self.add_message(m, is_user=False))
                    
                    fixed = data.get('violations_fixed', 0)
                    failed = data.get('total_failed', 0)
                    
                    if fixed > 0:
                        summary = f"### ✅ Fixes Applied\n\n"
                        summary += f"**Fixed:** {fixed} violation(s)\n"
                        if failed > 0:
                            summary += f"**Could not fix:** {failed} violation(s) — manual work needed in Altium\n"
                        self._safe_after(0, lambda m=summary: self.add_message(m, is_user=False))
                        
                        # Auto re-run DRC to verify
                        self._safe_after(500, lambda: self.add_message(
                            "🔄 Re-running DRC to verify fixes...", is_user=False
                        ))
                        import time
                        time.sleep(3)  # Let Altium process changes
                        self._safe_after(0, lambda: self._rerun_drc_after_fixes())
                        return  # _rerun_drc_after_fixes handles loading state
                    else:
                        summary = f"### ⚠️ Could not auto-fix\n\n"
                        summary += f"The violations require manual work in Altium Designer.\n"
                        summary += f"Please check that Altium's StartServer is running.\n"
                        self._safe_after(0, lambda m=summary: self.add_message(m, is_user=False))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        f"❌ Fix failed: server error", is_user=False
                    ))
            except Exception as ex:
                err_msg = str(ex)
                self._safe_after(0, lambda m=err_msg: self.add_message(
                    f"❌ Fix error: {m}", is_user=False
                ))
            finally:
                self._safe_after(0, lambda: self.set_loading(False))
                self._safe_after(0, lambda: self.set_status("Ready", "success"))
        
        threading.Thread(target=execute_fixes, daemon=True).start()
    
    def _handle_cancel_fixes(self):
        """Cancel fix plan — do nothing."""
        self.add_message("Fix cancelled. You can ask me other questions or run DRC again.", is_user=False)
        self.set_status("Ready", "success")
    
    def _handle_drc_fix_ignore(self):
        """Handle Ignore button click."""
        self.add_message("Ignoring violations. You can ask me other questions or run DRC again later.", is_user=False)
        self.set_status("Ready", "success")
    
    def _apply_single_suggestion(self, suggestion: dict) -> dict:
        """Apply a single DRC fix suggestion"""
        try:
            message = suggestion.get("message", "")
            suggestion_type = suggestion.get("type", "")
            
            # Handle manual fix needed cases
            if suggestion_type == "manual_fix_needed":
                return {
                    "success": False, 
                    "error": f"Manual fix required: {message}"
                }
            
            # Handle unrouted net — requires manual routing in Altium
            if suggestion_type == "route_net":
                net_name = suggestion.get("net", "")
                return {
                    "success": False,
                    "error": f"Unrouted net '{net_name}': Open Altium Designer → select net → use interactive router (Route > Interactive Routing) to connect all pads."
                }
            
            # Handle net antennae — suggest extending or removing stub
            if suggestion_type == "fix_antenna":
                net_name = suggestion.get("net", "")
                x = suggestion.get("x", 0)
                y = suggestion.get("y", 0)
                return {
                    "success": False, 
                    "error": f"Net Antennae on '{net_name}' at ({x:.1f}, {y:.1f}): In Altium Designer, either extend this dead-end track to the nearest pad, or delete the stub track."
                }
            
            # Handle copper pour clearance adjustments
            if suggestion_type == "adjust_copper_pour_clearance":
                x = float(suggestion.get("x"))
                y = float(suggestion.get("y"))
                clearance_mm = float(suggestion.get("clearance_mm", 0.4))
                
                from tools.altium_script_client import AltiumScriptClient
                client = AltiumScriptClient()
                
                result = client.adjust_copper_pour_clearance(x, y, clearance_mm)
                
                if result.get("success"):
                    return {"success": True, "message": f"Adjusted copper pour clearance to {clearance_mm}mm at ({x}, {y})"}
                else:
                    return {"success": False, "error": f"Failed to adjust copper pour clearance: {result.get('error', 'Unknown error')}"}
            
            # Check if this is a structured suggestion with direct component info
            if suggestion.get("component") and suggestion.get("new_x") is not None and suggestion.get("new_y") is not None:
                comp_name = suggestion.get("component")
                new_x = float(suggestion.get("new_x"))
                new_y = float(suggestion.get("new_y"))
                rotation = suggestion.get("rotation", 0)
                
                # Apply the movement using Altium script client
                from tools.altium_script_client import AltiumScriptClient
                client = AltiumScriptClient()
                
                if rotation != 0:
                    result = client.move_and_rotate_component(comp_name, new_x, new_y, rotation)
                    if result.get("success"):
                        return {"success": True, "message": f"Moved {comp_name} to ({new_x}, {new_y}) and rotated {rotation}°"}
                    else:
                        return {"success": False, "error": f"Failed to move and rotate {comp_name}: {result.get('error', 'Unknown error')}"}
                else:
                    result = client.move_component(comp_name, new_x, new_y)
                    if result.get("success"):
                        return {"success": True, "message": f"Moved {comp_name} to ({new_x}, {new_y})"}
                    else:
                        return {"success": False, "error": f"Failed to move {comp_name}: {result.get('error', 'Unknown error')}"}
            
            # Parse component movement suggestions from message text
            # Example: "Move C135 from [140.8, 34.3] to [125.2, 42.1] for better decoupling"
            import re
            
            # Pattern to match component movement suggestions
            move_pattern = r'move\s+([A-Z]+\d+)\s+.*?to\s+\[?(\d+\.?\d*),\s*(\d+\.?\d*)\]?'
            move_match = re.search(move_pattern, message, re.IGNORECASE)
            
            if move_match:
                comp_name = move_match.group(1).upper()
                new_x = float(move_match.group(2))
                new_y = float(move_match.group(3))
                
                # Apply the movement using Altium script client
                from tools.altium_script_client import AltiumScriptClient
                client = AltiumScriptClient()
                
                result = client.move_component(comp_name, new_x, new_y)
                
                if result.get("success"):
                    return {"success": True, "message": f"Moved {comp_name} to ({new_x}, {new_y})"}
                else:
                    return {"success": False, "error": f"Failed to move {comp_name}: {result.get('error', 'Unknown error')}"}
            
            # Pattern to match rotation suggestions
            # Example: "Rotate U1 by 90 degrees for better routing"
            rotate_pattern = r'rotate\s+([A-Z]+\d+)\s+.*?(\d+)\s*degrees?'
            rotate_match = re.search(rotate_pattern, message, re.IGNORECASE)
            
            if rotate_match:
                comp_name = rotate_match.group(1).upper()
                rotation = float(rotate_match.group(2))
                
                # Apply the rotation using Altium script client
                from tools.altium_script_client import AltiumScriptClient
                client = AltiumScriptClient()
                
                result = client.rotate_component(comp_name, rotation)
                
                if result.get("success"):
                    return {"success": True, "message": f"Rotated {comp_name} by {rotation} degrees"}
                else:
                    return {"success": False, "error": f"Failed to rotate {comp_name}: {result.get('error', 'Unknown error')}"}
            
            # Pattern to match move and rotate suggestions
            # Example: "Move C135 to [125.2, 42.1] and rotate 270° for shortest trace"
            move_rotate_pattern = r'move\s+([A-Z]+\d+)\s+.*?to\s+\[?(\d+\.?\d*),\s*(\d+\.?\d*)\]?.*?rotate\s+(\d+)°?'
            move_rotate_match = re.search(move_rotate_pattern, message, re.IGNORECASE)
            
            if move_rotate_match:
                comp_name = move_rotate_match.group(1).upper()
                new_x = float(move_rotate_match.group(2))
                new_y = float(move_rotate_match.group(3))
                rotation = float(move_rotate_match.group(4))
                
                # Apply the movement and rotation using Altium script client
                from tools.altium_script_client import AltiumScriptClient
                client = AltiumScriptClient()
                
                result = client.move_and_rotate_component(comp_name, new_x, new_y, rotation)
                
                if result.get("success"):
                    return {"success": True, "message": f"Moved {comp_name} to ({new_x}, {new_y}) and rotated {rotation}°"}
                else:
                    return {"success": False, "error": f"Failed to move and rotate {comp_name}: {result.get('error', 'Unknown error')}"}
            
            # If no specific action could be parsed, return as not applicable
            return {"success": False, "error": f"Could not parse suggestion: {message}"}
            
        except Exception as e:
            return {"success": False, "error": f"Error parsing suggestion: {str(e)}"}
    
    def _rerun_drc_after_fixes(self):
        """Re-run DRC check after applying fixes"""
        self.add_message("Re-running DRC to verify fixes...", is_user=False)
        self.set_status("Verifying fixes...", "warning")
        
        def rerun_drc():
            try:
                import time
                time.sleep(2)  # Give Altium more time to process changes
                
                # Run DRC again
                result = self.mcp_client.session.get("http://localhost:8765/drc/run")
                
                if result.status_code == 200:
                    data = result.json()
                    if data.get("success"):
                        summary = data.get("summary", {})
                        violations = data.get("violations", [])
                        
                        violations_count = summary.get('rule_violations', 0)
                        
                        # Just show the actual DRC results without claiming success
                        if violations_count == 0:
                            msg = "🎉 **DRC Results: CLEAN**\n\n"
                            msg += "No violations found. All fixes were successful!"
                            self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                            self._safe_after(0, lambda: self.set_status("DRC Clean", "success"))
                        else:
                            # Show the actual remaining violations
                            msg = f"📊 **DRC Results After Fixes**\n\n"
                            msg += f"Violations found: **{violations_count}**\n\n"
                            
                            if len(violations) > 0:
                                msg += "**Current violations:**\n"
                                for i, v in enumerate(violations[:5], 1):
                                    v_msg = v.get('message', 'Unknown violation')
                                    location = v.get('location', {})
                                    if location.get('x_mm') is not None:
                                        msg += f"{i}. {v_msg}\n"
                                        msg += f"   Location: ({location.get('x_mm', 0):.2f}, {location.get('y_mm', 0):.2f}) mm\n"
                                    else:
                                        msg += f"{i}. {v_msg}\n"
                                if len(violations) > 5:
                                    msg += f"... and {len(violations) - 5} more\n"
                            
                            # Add explanation for why violations might persist
                            msg += "\n**Note**: Some violations may persist because:\n"
                            msg += "• Copper pour vs track violations need track rerouting\n"
                            msg += "• Complex violations require design rule adjustments\n"
                            msg += "• Some fixes need manual intervention in Altium\n"
                            
                            self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                            
                            # Only offer to fix more if we have intelligent suggestions
                            remaining_suggestions = self._generate_basic_suggestions_from_violations(violations)
                            actionable_suggestions = [s for s in remaining_suggestions if s.get("type") != "manual_fix_needed"]
                            
                            if actionable_suggestions:
                                self.current_drc_suggestions = actionable_suggestions
                                self._safe_after(0, lambda: self.add_message(
                                    "Want me to try different approaches to fix these remaining violations?",
                                    is_user=False
                                ))
                                self._safe_after(500, lambda: self._add_drc_fix_buttons())
                            else:
                                self._safe_after(0, lambda: self.add_message(
                                    "These remaining violations require manual design changes or different approaches.",
                                    is_user=False
                                ))
                            
                            self._safe_after(0, lambda: self.set_status("Violations Remain", "warning"))
                    else:
                        self._safe_after(0, lambda: self.add_message(
                            f"❌ DRC re-run failed: {data.get('error', 'Unknown error')}",
                            is_user=False
                        ))
                        self._safe_after(0, lambda: self.set_status("Error", "error"))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        "❌ Failed to re-run DRC check.",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Error", "error"))
                
                self._safe_after(0, lambda: self.set_loading(False))
                
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"❌ Error re-running DRC: {str(e)}",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_loading(False))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=rerun_drc, daemon=True).start()
    
    def _update_drc_suggestions(self):
        """Check for updates to DRC suggestions"""
        self.add_message("Checking for suggestion updates...", is_user=False)
        self.set_status("Checking...", "warning")
        
        def check_updates():
            try:
                result = self.mcp_client.session.get("http://localhost:8765/drc/update-suggestions")
                
                if result.status_code == 200:
                    data = result.json()
                    if data.get("updated"):
                        msg = f"📊 **Suggestion Update**\n\n"
                        msg += f"{data.get('message', 'Suggestions updated')}\n\n"
                        msg += f"• Previous violations: {data.get('old_count', 0)}\n"
                        msg += f"• Current violations: {data.get('new_count', 0)}\n"
                        msg += f"• Fixed: {data.get('fixed_count', 0)}\n"
                        msg += f"• New issues: {data.get('new_issues_count', 0)}\n\n"
                        
                        if data.get("improvement"):
                            msg += "✅ Design is improving!\n"
                        else:
                            msg += "⚠️ Some new issues found.\n"
                        
                        msg += "\nUse 'Get DRC Suggestions' to see detailed recommendations."
                        
                        self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                        self._safe_after(0, lambda: self.set_status("Updated", "success"))
                    else:
                        self._safe_after(0, lambda: self.add_message(
                            data.get("message", "No updates available."),
                            is_user=False
                        ))
                        self._safe_after(0, lambda: self.set_status("No Updates", "info"))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        "❌ Failed to connect to MCP server.",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Connection Error", "error"))
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"❌ Error: {str(e)}",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=check_updates, daemon=True).start()
    
    def _view_design_rules(self):
        """View all design rules from Altium"""
        self.add_message("Loading design rules from Altium...", is_user=False)
        self.set_status("Loading Rules...", "warning")
        
        def load_rules():
            try:
                result = self.mcp_client.session.get("http://localhost:8765/drc/rules")
                
                if result.status_code == 200:
                    data = result.json()
                    if data.get("success"):
                        rules = data.get("rules", [])
                        stats = data.get("statistics", {})
                        rules_by_category = data.get("rules_by_category", {})
                        
                        if rules:
                            msg = f"📋 **Design Rules from Altium**\n\n"
                            msg += f"**Total Rules:** {stats.get('total', 0)} "
                            msg += f"(Enabled: {stats.get('enabled', 0)})\n\n"
                            
                            # Display rules grouped by category
                            for category in ["Electrical", "Routing", "Placement", "Mask", "Plane", "Other"]:
                                if category in rules_by_category:
                                    msg += f"**{category} Rules:**\n"
                                    for rule in rules_by_category[category]:
                                        name = rule.get('name', 'Unnamed')
                                        rule_type = rule.get('type', 'unknown')
                                        enabled = "✅" if rule.get('enabled', True) else "❌"
                                        
                                        msg += f"{enabled} **{name}** ({rule_type})\n"
                                        
                                        # Show rule-specific parameters
                                        if rule_type == "clearance":
                                            clearance = rule.get('clearance_mm', 0)
                                            msg += f"   • Minimum Clearance: {clearance:.3f}mm\n"
                                            if rule.get('scope_first'):
                                                msg += f"   • Scope: {rule.get('scope_first')}\n"
                                        elif rule_type == "width":
                                            min_w = rule.get('min_width_mm', 0)
                                            pref_w = rule.get('preferred_width_mm', 0)
                                            max_w = rule.get('max_width_mm', 0)
                                            msg += f"   • Min: {min_w:.3f}mm, Preferred: {pref_w:.3f}mm"
                                            if max_w > 0:
                                                msg += f", Max: {max_w:.3f}mm"
                                            msg += "\n"
                                            if rule.get('scope_first'):
                                                msg += f"   • Scope: {rule.get('scope_first')}\n"
                                        elif rule_type == "via":
                                            # Display all 6 parameters: Min/Max/Preferred for Hole and Diameter
                                            min_hole = rule.get('min_hole_mm', 0)
                                            max_hole = rule.get('max_hole_mm', 0)
                                            pref_hole = rule.get('preferred_hole_mm', 0)
                                            min_dia = rule.get('min_diameter_mm', 0)
                                            max_dia = rule.get('max_diameter_mm', 0)
                                            pref_dia = rule.get('preferred_diameter_mm', 0)
                                            via_style = rule.get('via_style', '')
                                            if via_style:
                                                msg += f"   • Via Style: {via_style}\n"
                                            msg += f"   • Via Hole Size: Min: {min_hole:.3f}mm"
                                            if pref_hole > 0:
                                                msg += f", Preferred: {pref_hole:.3f}mm"
                                            if max_hole > 0:
                                                msg += f", Max: {max_hole:.3f}mm"
                                            msg += "\n"
                                            msg += f"   • Via Diameter: Min: {min_dia:.3f}mm"
                                            if pref_dia > 0:
                                                msg += f", Preferred: {pref_dia:.3f}mm"
                                            if max_dia > 0:
                                                msg += f", Max: {max_dia:.3f}mm"
                                            msg += "\n"
                                        elif rule_type == "routing_corners":
                                            style = rule.get('corner_style', '')
                                            setback = rule.get('setback_mm', 0)
                                            setback_to = rule.get('setback_to_mm', 0)
                                            if style:
                                                msg += f"   • Style: {style}\n"
                                            if setback > 0:
                                                # Always show "to" parameter even if same value
                                                if setback_to > 0:
                                                    msg += f"   • Setback: {setback:.3f}mm to {setback_to:.3f}mm\n"
                                                else:
                                                    msg += f"   • Setback: {setback:.3f}mm\n"
                                        elif rule_type == "routing_topology":
                                            topology = rule.get('topology', '')
                                            if topology:
                                                msg += f"   • Topology: {topology}\n"
                                        elif rule_type == "diff_pairs_routing":
                                            min_w = rule.get('min_width_mm', 0)
                                            max_w = rule.get('max_width_mm', 0)
                                            pref_w = rule.get('preferred_width_mm', 0)
                                            min_gap = rule.get('min_gap_mm', 0)
                                            max_gap = rule.get('max_gap_mm', 0)
                                            pref_gap = rule.get('preferred_gap_mm', 0)
                                            max_unc = rule.get('max_uncoupled_length_mm', 0)
                                            msg += f"   • Min Width: {min_w:.3f}mm, Preferred: {pref_w:.3f}mm, Max: {max_w:.3f}mm\n"
                                            msg += f"   • Min Gap: {min_gap:.3f}mm, Preferred: {pref_gap:.3f}mm, Max: {max_gap:.3f}mm\n"
                                            if max_unc > 0:
                                                msg += f"   • Max Uncoupled Length: {max_unc:.3f}mm\n"
                                        elif rule_type == "plane_clearance":
                                            clearance = rule.get('clearance_mm', 0)
                                            msg += f"   • Clearance: {clearance:.3f}mm\n"
                                        elif rule_type == "plane_connect":
                                            style = rule.get('connect_style', '')
                                            expansion = rule.get('expansion_mm', 0)
                                            air_gap = rule.get('air_gap_mm', 0)
                                            conductor_width = rule.get('conductor_width_mm', 0)
                                            conductor_count = rule.get('conductor_count', 0)
                                            if style:
                                                msg += f"   • Connect Style: {style}\n"
                                            if expansion > 0:
                                                msg += f"   • Expansion: {expansion:.3f}mm\n"
                                            if air_gap > 0:
                                                msg += f"   • Air-Gap: {air_gap:.3f}mm\n"
                                            if conductor_width > 0:
                                                msg += f"   • Conductor Width: {conductor_width:.3f}mm\n"
                                            if conductor_count > 0:
                                                msg += f"   • Conductors: {conductor_count}\n"
                                        elif rule_type == "paste_mask":
                                            # Paste mask specific settings
                                            use_paste_smd = rule.get('use_paste_smd', None)
                                            use_top_paste_th = rule.get('use_top_paste_th', None)
                                            use_bottom_paste_th = rule.get('use_bottom_paste_th', None)
                                            measurement_method = rule.get('measurement_method', '')
                                            expansion = rule.get('expansion_mm', 0)
                                            expansion_bottom = rule.get('expansion_bottom_mm', 0)
                                            
                                            if use_paste_smd is not None:
                                                msg += f"   • SMD Pads - Use Paste: {'Yes' if use_paste_smd else 'No'}\n"
                                            if use_top_paste_th is not None:
                                                msg += f"   • TH Pads - Use Top Paste: {'Yes' if use_top_paste_th else 'No'}\n"
                                            if use_bottom_paste_th is not None:
                                                msg += f"   • TH Pads - Use Bottom Paste: {'Yes' if use_bottom_paste_th else 'No'}\n"
                                            if measurement_method:
                                                msg += f"   • Measurement Method: {measurement_method}\n"
                                            if expansion >= 0:  # Show even if 0
                                                if expansion_bottom > 0 and expansion_bottom != expansion:
                                                    msg += f"   • Expansion Top: {expansion:.3f}mm\n"
                                                    msg += f"   • Expansion Bottom: {expansion_bottom:.3f}mm\n"
                                                else:
                                                    msg += f"   • Expansion: {expansion:.3f}mm\n"
                                        elif rule_type == "solder_mask":
                                            expansion = rule.get('expansion_mm', 0)
                                            expansion_bottom = rule.get('expansion_bottom_mm', 0)
                                            if expansion > 0:
                                                if expansion_bottom > 0 and expansion_bottom != expansion:
                                                    msg += f"   • Expansion Top: {expansion:.3f}mm\n"
                                                    msg += f"   • Expansion Bottom: {expansion_bottom:.3f}mm\n"
                                                else:
                                                    msg += f"   • Expansion: {expansion:.3f}mm (top & bottom)\n"
                                            tented_top = rule.get('tented_top', False)
                                            tented_bottom = rule.get('tented_bottom', False)
                                            if tented_top or tented_bottom:
                                                tented_parts = []
                                                if tented_top:
                                                    tented_parts.append("top")
                                                if tented_bottom:
                                                    tented_parts.append("bottom")
                                                msg += f"   • Tented: {', '.join(tented_parts)}\n"
                                        
                                        priority = rule.get('priority', 0)
                                        if priority > 0:
                                            msg += f"   • Priority: {priority}\n"
                                        
                                        msg += "\n"
                                    msg += "\n"
                            
                            msg += "\n**Note:** These are the actual rules from your Altium PCB file.\n"
                            
                            self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                            # Add buttons for rule management
                            self._safe_after(0, lambda: self.add_rule_management_buttons())
                            self._safe_after(0, lambda: self.set_status("Rules Loaded", "success"))
                    elif not data.get("success"):
                        # Check if it's an error about missing export file
                        error_msg = data.get("error", "").lower()
                        message = data.get("message", "")
                        
                        if "export" in error_msg or "export" in message.lower():
                            self._safe_after(0, lambda: self.add_message(
                                "⚠️ **No Altium Export File Found**\n\n"
                                "**To get all design rules from Altium:**\n\n"
                                "1. **In Altium Designer:**\n"
                                "   - Open your PCB file\n"
                                "   - Run Script: `command_server.pas`\n"
                                "   - Execute: `ExportPCBInfo` procedure\n"
                                "   - This exports ALL rules to `altium_pcb_info.json`\n\n"
                                "2. **Then refresh:**\n"
                                "   - Click 'Refresh Data' in the menu\n"
                                "   - Or click 'View Design Rules' again\n\n"
                                "**Note:** The export includes ALL rules:\n"
                                "• Clearance rules (Clearance_1, LBBZHUANYONG, etc.)\n"
                                "• Routing rules (width, via)\n"
                                "• SMT rules\n"
                                "• Mask rules (PasteMaskExpansion, etc.)\n"
                                "• Plane rules\n"
                                "• And all other rule types",
                                is_user=False
                            ))
                        else:
                            self._safe_after(0, lambda: self.add_message(
                                "⚠️ No design rules found in PCB.\n\n"
                                "**To get rules:**\n"
                                "1. Export PCB info from Altium (run ExportPCBInfo in command_server.pas)\n"
                                "2. Then click 'Refresh Data' to reload",
                                is_user=False
                            ))
                        self._safe_after(0, lambda: self.set_status("No Rules", "warning"))
                    else:
                        error_msg = data.get("error", "Unknown error")
                        self._safe_after(0, lambda: self.add_message(
                            f"❌ Error loading rules: {error_msg}\n\n"
                            "Make sure a PCB is loaded first (use Refresh Data).",
                            is_user=False
                        ))
                        self._safe_after(0, lambda: self.set_status("Error", "error"))
                else:
                    self._safe_after(0, lambda: self.add_message(
                        "❌ Failed to connect to MCP server.",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_status("Connection Error", "error"))
            except Exception as e:
                self._safe_after(0, lambda: self.add_message(
                    f"❌ Error: {str(e)}",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=load_rules, daemon=True).start()
    
    def add_rule_management_buttons(self):
        """Add buttons for rule management after displaying rules"""
        # Create a modern card-style container for buttons
        card_frame = ctk.CTkFrame(
            self.chat_frame,
            fg_color=self.colors["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border"]
        )
        card_frame.grid(row=len(self.messages), column=0, sticky="ew", padx=20, pady=12)
        card_frame.grid_columnconfigure(0, weight=1)
        self.messages.append(card_frame)
        
        # Title section
        title_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="Rule Management",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text"]
        )
        title_label.pack(side="left")
        
        # Button container with better spacing
        button_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        button_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)
        
        # Add New Rule button - improved styling with icon and short text
        add_btn = ctk.CTkButton(
            button_frame,
            text="➕ Add",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42,
            corner_radius=10,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            text_color="#ffffff",
            command=self._handle_add_new_rule,
            border_width=0
        )
        add_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        
        # Update Existing Rule button - improved styling with icon and short text
        update_btn = ctk.CTkButton(
            button_frame,
            text="✏️ Update",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42,
            corner_radius=10,
            fg_color=self.colors["accent"],
            hover_color="#0891b2",
            text_color="#ffffff",
            command=self._handle_update_existing_rule,
            border_width=0
        )
        update_btn.grid(row=0, column=1, padx=3, sticky="ew")
        
        # Delete Rule button - improved styling with icon and short text
        delete_btn = ctk.CTkButton(
            button_frame,
            text="🗑️ Delete",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42,
            corner_radius=10,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            text_color="#ffffff",
            command=self._handle_delete_rule,
            border_width=0
        )
        delete_btn.grid(row=0, column=2, padx=(6, 0), sticky="ew")
        
        # Scroll to bottom
        self.chat_frame.update()
        self.chat_frame._parent_canvas.yview_moveto(1.0)
    
    def _handle_add_new_rule(self):
        """Handle Add New Rule button click"""
        self.add_message(
            "Please input what rule do you want to add in detail.\n\n"
            "**Examples:**\n"
            "• Add a clearance rule: 'Add clearance rule between +5V and +21V nets with 0.508mm clearance'\n"
            "• Add a width rule: 'Add width rule for power nets with min 0.5mm, preferred 0.8mm, max 1.0mm'\n"
            "• Add a via rule: 'Add via rule with min hole 0.3mm, max hole 0.5mm, min diameter 0.6mm'\n\n"
            "Type your rule requirements in the chat box below:",
            is_user=False
        )
        # Focus on input
        self.input_entry.focus()
        # Set flag to indicate we're waiting for rule input
        self.waiting_for_rule_input = True
        self.rule_action_type = "add"
    
    def _handle_update_existing_rule(self):
        """Handle Update Existing Rule button click"""
        self.add_message(
            "Please specify which rule you want to update and the new values.\n\n"
            "**Examples:**\n"
            "• 'Update PlaneClearance rule to 0.6mm'\n"
            "• 'Change Width rule preferred width to 1.0mm'\n"
            "• 'Update RoutingVias max hole size to 0.8mm'\n\n"
            "Type your rule update requirements in the chat box below:",
            is_user=False
        )
        # Focus on input
        self.input_entry.focus()
        # Set flag to indicate we're waiting for rule input
        self.waiting_for_rule_input = True
        self.rule_action_type = "update"
    
    def _handle_delete_rule(self):
        """Handle Delete Rule button click"""
        self.add_message(
            "Please specify which rule you want to delete.\n\n"
            "**Examples:**\n"
            "• 'Delete Clearance+5V+12V rule'\n"
            "• 'Remove PlaneClearance rule'\n"
            "• 'Delete Width rule'\n\n"
            "Type the rule name you want to delete in the chat box below:",
            is_user=False
        )
        # Focus on input
        self.input_entry.focus()
        # Set flag to indicate we're waiting for rule input
        self.waiting_for_rule_input = True
        self.rule_action_type = "delete"
    
    def _process_rule_request(self, user_input: str, action_type: str):
        """Process rule creation or update request"""
        self.set_status("Processing rule request...", "warning")
        self.set_loading(True)
        
        def process():
            try:
                from tools.altium_script_client import AltiumScriptClient
                import re
                
                # Create client - DO NOT ping before create_rule!
                # Sending ping immediately before create_rule causes a race condition:
                # The ping result file may not be fully deleted on Windows before
                # create_rule's _send_command checks for it, causing create_rule to
                # read the stale "pong" result and falsely report success.
                # If Altium isn't running, create_rule will timeout with a clear error.
                client = AltiumScriptClient()
                
                # Parse the rule request
                rule_data = self._parse_rule_request(user_input, action_type)
                
                # DEBUG: Log parsed rule data
                print(f"DEBUG: _process_rule_request - action_type={action_type}, rule_data={rule_data}")
                
                if not rule_data:
                    # Could not parse - use agent to help
                    if self.agent:
                        action_texts = {
                            "add": "add a new",
                            "update": "update an existing",
                            "delete": "delete an existing"
                        }
                        action_text = action_texts.get(action_type, "modify a")
                        prompt = f"User wants to {action_text} design rule. Request: {user_input}\n\n"
                        prompt += "Please help parse this rule request and provide clear instructions."
                        
                        response, status, _ = self.agent.process_query(prompt)
                        self._safe_after(0, lambda r=response: self.add_message(
                            f"**Could not automatically parse your rule request.**\n\n"
                            f"{r}\n\n"
                            f"**Please try again with a clearer format, for example:**\n"
                            f"• 'Add clearance rule between +5V and +21V nets with 0.508mm clearance'\n"
                            f"• 'Update PlaneClearance rule to 0.6mm'",
                            is_user=False
                        ))
                    else:
                        self._safe_after(0, lambda: self.add_message(
                            "❌ Could not parse rule request.\n\n"
                            "**Please use a clear format, for example:**\n"
                            "• 'Add clearance rule between +5V and +21V nets with 0.508mm clearance'\n"
                            "• 'Update PlaneClearance rule to 0.6mm'",
                            is_user=False
                        ))
                    self._safe_after(0, lambda: self.set_loading(False))
                    self._safe_after(0, lambda: self.set_status("Parse Error", "error"))
                    return
                
                # Apply the rule to Altium
                if action_type == "add":
                    result = client.create_rule(
                        rule_data["rule_type"],
                        rule_data["rule_name"],
                        rule_data["parameters"]
                    )
                elif action_type == "update":
                    result = client.update_rule(
                        rule_data["rule_name"],
                        rule_data["parameters"]
                    )
                elif action_type == "delete":
                    # DEBUG: Log the rule name being sent
                    rule_name_to_send = rule_data["rule_name"]
                    
                    # CRITICAL: Final cleanup - ensure "rule" word and punctuation are not in the name
                    rule_name_to_send = re.sub(r'\s+rule[.,\s]*$', '', rule_name_to_send, flags=re.IGNORECASE).strip()
                    rule_name_to_send = rule_name_to_send.rstrip('.,;:!?')
                    
                    print(f"DEBUG: About to call delete_rule with rule_name: [{rule_name_to_send}]")
                    print(f"DEBUG: Rule name length: {len(rule_name_to_send)}")
                    print(f"DEBUG: Rule name ends with 'rule': {rule_name_to_send.lower().endswith('rule')}")
                    print(f"DEBUG: Rule name ends with punctuation: {rule_name_to_send[-1] if rule_name_to_send else 'N/A'} in '.,;:!?'")
                    
                    result = client.delete_rule(rule_name_to_send)
                else:
                    self._safe_after(0, lambda: self.add_message(
                        f"❌ Unknown action type: {action_type}",
                        is_user=False
                    ))
                    self._safe_after(0, lambda: self.set_loading(False))
                    return
                
                if result.get("success"):
                    # Rule applied successfully - show Altium's actual response
                    altium_msg = result.get("message", "OK")
                    action_past = {
                        "add": "added",
                        "update": "updated",
                        "delete": "deleted"
                    }.get(action_type, f"{action_type}ed")
                    
                    msg = f"✅ Rule {action_past} successfully!\n\n"
                    msg += f"**Rule:** {rule_data.get('rule_name', 'Unknown')}\n"
                    if action_type != "delete":
                        msg += f"**Type:** {rule_data.get('rule_type', 'Unknown')}\n"
                        msg += f"**Parameters:** {rule_data.get('parameters', {})}\n"
                    msg += f"**Altium Response:** {altium_msg}\n\n"
                    if action_type != "delete":
                        msg += "Exporting updated PCB info and refreshing rules list..."
                    else:
                        msg += "Refreshing rules list..."
                    
                    self._safe_after(0, lambda m=msg: self.add_message(m, is_user=False))
                    
                    # Explicitly call export_pcb_info to ensure the rule change is exported
                    # Then refresh the UI
                    self._safe_after(0, lambda: self._export_and_refresh_after_rule_update())
                else:
                    error_msg = result.get("error", "Unknown error")
                    
                    # Check if it's a "rule not found" error (for delete or update)
                    if action_type in ["delete", "update"] and ("not found" in error_msg.lower() or "rule not found" in error_msg.lower()):
                        # Simple message for rule not found
                        self._safe_after(0, lambda: self.add_message(
                            f"❌ There is no rule like that. Please check the rule list again.",
                            is_user=False
                        ))
                        # Show rule management buttons again
                        self._safe_after(0, lambda: self.add_rule_management_buttons())
                    else:
                        # For other errors, show detailed troubleshooting
                        self._safe_after(0, lambda: self.add_message(
                            f"❌ Error {action_type}ing rule: {error_msg}\n\n"
                            "**Make sure:**\n"
                            "1. Altium Designer is open with your PCB\n"
                            "2. Script server is running (StartServer) in Altium\n"
                            "3. Rule parameters are valid and unique (for new rules)\n"
                            "4. File paths match between Python and Altium",
                            is_user=False
                        ))
                    self._safe_after(0, lambda: self.set_status("Error", "error"))
                
                self._safe_after(0, lambda: self.set_loading(False))
                
            except Exception as e:
                import traceback
                error_msg = f"Error processing rule request: {str(e)}"
                print(traceback.format_exc())
                self._safe_after(0, lambda: self.add_message(
                    f"❌ {error_msg}\n\n"
                    "**Troubleshooting:**\n"
                    "1. Check if Altium Script Server is running\n"
                    "2. Make sure PCB is open in Altium\n"
                    "3. Try a simpler rule request format",
                    is_user=False
                ))
                self._safe_after(0, lambda: self.set_loading(False))
                self._safe_after(0, lambda: self.set_status("Error", "error"))
        
        threading.Thread(target=process, daemon=True).start()
    
    def _parse_rule_request(self, user_input: str, action_type: str) -> Optional[Dict[str, Any]]:
        """Parse rule request from natural language.
        
        Uses a simple two-step approach:
        1. Extract the mm value from the input
        2. Extract net names (if present) using a separate regex
        
        This avoids complex combined regexes that break on word ordering.
        
        Supports:
        - "Add clearance rule between +5V and +21V nets with 0.508mm clearance"
        - "Add clearance rule 0.508mm"
        - "Add clearance 0.508mm between +5V and GND"
        - "Add width rule min 0.5mm, preferred 0.8mm, max 1.0mm"
        - "Add via rule min hole 0.3mm"
        - "Update PlaneClearance rule to 0.6mm"
        """
        import re
        
        user_input_lower = user_input.lower().strip()
        
        # ============================================================
        # DELETE RULES (check first, before update/add patterns)
        # ============================================================
        if action_type == "delete":
            # Pattern to match: "delete Clearance+5V+12V rule" or "remove PlaneClearance"
            original_input = user_input.strip()
            
            # Remove the action word (delete/remove/drop) and "rule" word if present
            # This is more robust than regex for edge cases
            temp = re.sub(r'^(?:delete|remove|drop)\s+', '', original_input, flags=re.IGNORECASE).strip()
            
            # Remove "rule" word (with optional punctuation after it like . or ,)
            # Match: "rule", "rule.", "rule,", "rule " etc.
            rule_name = re.sub(r'\s+rule[.,\s]*$', '', temp, flags=re.IGNORECASE).strip()
            
            # Also strip any trailing punctuation that might remain
            rule_name = rule_name.rstrip('.,;:!?')
            
            # DEBUG: Log before normalization
            print(f"DEBUG: Delete - original_input: [{original_input}]")
            print(f"DEBUG: Delete - after removing action word: [{temp}]")
            print(f"DEBUG: Delete - after removing 'rule' and punctuation: [{rule_name}]")
            
            # Validate we got something
            if not rule_name:
                print(f"DEBUG: Delete - empty rule name after parsing")
                return None
            
            # Normalize rule name to match Altium's format (same as update)
            # Handle case-insensitive matching for "Clearance"
            rule_name_lower = rule_name.lower()
            if rule_name_lower.startswith("clearance") and "+" in rule_name:
                # Always use "Clearance" with capital C (Altium format)
                prefix = "Clearance"
                
                # Find where "clearance" ends (case-insensitive)
                clearance_len = len("clearance")
                rest = rule_name[clearance_len:]
                
                # Normalize: add underscores before + signs
                if "_" not in rest or not re.search(r'_\+\w+_\+\w+', rest):
                    # Replace "Clearance+" with "Clearance_+"
                    if rest.startswith("+"):
                        rest = "_" + rest
                    # Replace remaining "+" with "_+"
                    rest = re.sub(r'(?<!_)\+', r'_+', rest)
                
                rule_name = prefix + rest
            
            # DEBUG: Log after normalization
            print(f"DEBUG: Delete - final normalized rule_name: [{rule_name}]")
            
            return {
                "rule_type": "unknown",  # Not needed for delete
                "rule_name": rule_name,
                "parameters": {}  # Not needed for delete
            }
        
        # ============================================================
        # UPDATE RULES (check before add patterns)
        # ============================================================
        if action_type == "update":
            # Pattern to match: "update Clearance+5V+12V rule to 0.127mm"
            # Rule name can contain: letters, numbers, +, -, _, and spaces
            # We need to capture until we see "rule" or "to/as/with/="
            
            # First, try to find the rule name in original case (preserve case)
            original_input = user_input
            # Match: "update/change/modify/set" + rule name (with special chars) + "rule" + "to/as/with/=" + value
            rule_name_match = re.search(
                r'(?:update|change|modify|set)\s+([^\s]+(?:\s+[^\s]+)*?)\s+(?:rule\s+)?(?:to|as|with|=)\s*(\d+\.?\d*)\s*mm',
                original_input,
                re.IGNORECASE
            )
            
            if rule_name_match:
                rule_name = rule_name_match.group(1).strip()
                value = float(rule_name_match.group(2))
                
                # Normalize rule name to match Altium's format
                # Rules created with net names use format: "Clearance_+5V_+12V" (with underscores)
                # But user might type: "Clearance+5V+12V" (with plus signs)
                # Convert: "Clearance+5V+12V" -> "Clearance_+5V_+12V"
                if rule_name.startswith("Clearance") and "+" in rule_name:
                    # Check if it already has underscores (correct format)
                    if "_" not in rule_name or not re.search(r'Clearance_\+\w+_\+\w+', rule_name):
                        # Need to normalize: "Clearance+5V+12V" -> "Clearance_+5V_+12V"
                        # Replace "Clearance+" with "Clearance_+", then replace remaining "+" with "_+"
                        rule_name = rule_name.replace("Clearance+", "Clearance_+", 1)
                        # Replace any remaining "+" that aren't already "_+" with "_+"
                        rule_name = re.sub(r'(?<!_)\+', r'_+', rule_name)
                
                # Determine parameter name based on rule name or input context
                rule_name_lower = rule_name.lower()
                user_input_lower = user_input.lower()
                
                if "clearance" in rule_name_lower or "clear" in rule_name_lower or "clearance" in user_input_lower:
                    param_name = "clearance_mm"
                elif "width" in rule_name_lower or "width" in user_input_lower:
                    param_name = "preferred_width_mm"
                elif "via" in rule_name_lower or "hole" in rule_name_lower or "via" in user_input_lower or "hole" in user_input_lower:
                    param_name = "min_hole_mm"
                else:
                    param_name = "clearance_mm"  # Default
                
                return {
                    "rule_type": "clearance",
                    "rule_name": rule_name,
                    "parameters": {param_name: value}
                }
            
            # Fallback: simpler pattern for basic rule names (no special chars)
            update_match = re.search(
                r'(?:update|change|modify|set)\s+(\w+)\s+(?:rule\s+)?(?:to|as|with|=)\s*(\d+\.?\d*)\s*mm',
                user_input_lower
            )
            if update_match:
                rule_name = update_match.group(1)
                rule_name = rule_name[0].upper() + rule_name[1:] if rule_name else "Clearance"
                value = float(update_match.group(2))
                
                if "clearance" in rule_name.lower():
                    param_name = "clearance_mm"
                elif "width" in rule_name.lower():
                    param_name = "preferred_width_mm"
                elif "via" in rule_name.lower() or "hole" in rule_name.lower():
                    param_name = "min_hole_mm"
                else:
                    param_name = "clearance_mm"
                
                return {
                    "rule_type": "clearance",
                    "rule_name": rule_name,
                    "parameters": {param_name: value}
                }
        
        # ============================================================
        # CLEARANCE RULES - Simple two-step approach
        # ============================================================
        if 'clearance' in user_input_lower or 'clear' in user_input_lower:
            # Step 1: Extract the mm value (required)
            value_match = re.search(r'(\d+\.?\d*)\s*mm', user_input_lower)
            if not value_match:
                return None
            clearance_mm = float(value_match.group(1))
            
            # Step 2: Extract net names (optional) - look for "X and Y" pattern
            nets_match = re.search(
                r'(?:between\s+)?([+\-]?\w+[\w.]*)\s+(?:and|&)\s+([+\-]?\w+[\w.]*)',
                user_input_lower
            )
            
            net1, net2 = "All", "All"
            if nets_match:
                candidate1 = nets_match.group(1).upper()
                candidate2 = nets_match.group(2).upper()
                # Filter out keywords that aren't net names
                keywords = {'MIN', 'MAX', 'MINIMUM', 'MAXIMUM', 'PREFERRED', 'PREF',
                           'RULE', 'CLEARANCE', 'CLEAR', 'ADD', 'UPDATE', 'WITH',
                           'BETWEEN', 'NETS', 'NET', 'THE', 'FOR', 'SET'}
                if candidate1 not in keywords and candidate2 not in keywords:
                    net1 = candidate1
                    net2 = candidate2
            
            if net1 == "All" and net2 == "All":
                rule_name = f"Clearance_{clearance_mm}mm"
            else:
                rule_name = f"Clearance_{net1}_{net2}"
            
            return {
                "rule_type": "clearance",
                "rule_name": rule_name,
                "parameters": {
                    "clearance_mm": clearance_mm,
                    "scope_first": net1,
                    "scope_second": net2
                }
            }
        
        # ============================================================
        # WIDTH RULES
        # ============================================================
        if 'width' in user_input_lower or 'trace' in user_input_lower:
            # Extract min/preferred/max values
            min_match = re.search(r'min(?:imum)?\s+(\d+\.?\d*)\s*mm', user_input_lower)
            pref_match = re.search(r'(?:preferred?|pref)\s+(\d+\.?\d*)\s*mm', user_input_lower)
            max_match = re.search(r'max(?:imum)?\s+(\d+\.?\d*)\s*mm', user_input_lower)
            
            # Fallback: just find any mm value
            any_val = re.search(r'(\d+\.?\d*)\s*mm', user_input_lower)
            
            if min_match or pref_match or max_match or any_val:
                min_w = float(min_match.group(1)) if min_match else (float(any_val.group(1)) if any_val else 0.254)
                pref_w = float(pref_match.group(1)) if pref_match else min_w
                max_w = float(max_match.group(1)) if max_match else pref_w * 2
                
                # Try to extract scope/net class - support net names with + and - signs
                scope_match = re.search(r'for\s+([+\-]?\w+[\w.]*)\s+(?:power\s+)?nets?', user_input_lower)
                if not scope_match:
                    # Try alternative patterns: "on X net" or "X net width"
                    scope_match = re.search(r'(?:on|to)\s+([+\-]?\w+[\w.]*)\s+nets?', user_input_lower)
                if not scope_match:
                    # Try pattern without "net" word: "for +5V" or "for VCC"
                    scope_match = re.search(r'for\s+([+\-]?\w+[\w.]*)', user_input_lower)
                
                scope = scope_match.group(1).upper() if scope_match else "All"
                
                # Map common power net names to actual net names
                # The Altium script will format these as InNet('VCC') etc.
                power_net_map = {
                    'power': 'VCC',  # Default power net name
                    'vcc': 'VCC',
                    'vdd': 'VDD',
                    'ground': 'GND',
                    'gnd': 'GND',
                    'vss': 'VSS'
                }
                
                # Normalize scope name - but preserve original if it starts with + or -
                scope_lower = scope.lower()
                if scope_lower in power_net_map:
                    scope = power_net_map[scope_lower]
                # If scope already starts with + or -, keep it as-is (it's likely a net name like +5V)
                # Otherwise, check if it needs mapping
                
                rule_name = f"Width_{scope}" if scope != "All" else "Width_Rule"
                return {
                    "rule_type": "width",
                    "rule_name": rule_name,
                    "parameters": {
                        "min_width_mm": min_w,
                        "preferred_width_mm": pref_w,
                        "max_width_mm": max_w,
                        "scope": scope  # Will be formatted as InNet('VCC') in Altium script
                    }
                }
        
        # ============================================================
        # VIA RULES
        # ============================================================
        if 'via' in user_input_lower:
            min_hole_match = re.search(r'min\s+hole\s+(\d+\.?\d*)\s*mm', user_input_lower)
            max_hole_match = re.search(r'max\s+hole\s+(\d+\.?\d*)\s*mm', user_input_lower)
            min_dia_match = re.search(r'min\s+diameter\s+(\d+\.?\d*)\s*mm', user_input_lower)
            max_dia_match = re.search(r'max\s+diameter\s+(\d+\.?\d*)\s*mm', user_input_lower)
            
            any_val = re.search(r'(\d+\.?\d*)\s*mm', user_input_lower)
            
            if min_hole_match or max_hole_match or min_dia_match or max_dia_match or any_val:
                min_hole = float(min_hole_match.group(1)) if min_hole_match else (float(any_val.group(1)) if any_val else 0.3)
                max_hole = float(max_hole_match.group(1)) if max_hole_match else min_hole * 1.5
                min_dia = float(min_dia_match.group(1)) if min_dia_match else min_hole * 2
                max_dia = float(max_dia_match.group(1)) if max_dia_match else min_dia * 1.5
                
                # Try to extract scope/net class - support net names with + and - signs
                scope_match = re.search(r'for\s+([+\-]?\w+[\w.]*)\s+nets?', user_input_lower)
                if not scope_match:
                    # Try alternative patterns: "on X net" or "X net via"
                    scope_match = re.search(r'(?:on|to)\s+([+\-]?\w+[\w.]*)\s+nets?', user_input_lower)
                if not scope_match:
                    # Try pattern without "net" word: "for +5V" or "for VCC"
                    scope_match = re.search(r'for\s+([+\-]?\w+[\w.]*)', user_input_lower)
                
                scope = scope_match.group(1).upper() if scope_match else "All"
                
                rule_name = f"RoutingVias_{scope}" if scope != "All" else "RoutingVias_Custom"
                
                return {
                    "rule_type": "via",
                    "rule_name": rule_name,
                    "parameters": {
                        "min_hole_mm": min_hole,
                        "max_hole_mm": max_hole,
                        "min_diameter_mm": min_dia,
                        "max_diameter_mm": max_dia,
                        "scope": scope
                    }
                }
        
        # ============================================================
        # FALLBACK: Extract ANY number with mm and guess rule type
        # ============================================================
        mm_match = re.search(r'(\d+\.?\d*)\s*mm', user_input_lower)
        if mm_match:
            value_mm = float(mm_match.group(1))
            # Default to clearance rule
            return {
                "rule_type": "clearance",
                "rule_name": f"Clearance_{value_mm}mm",
                "parameters": {
                    "clearance_mm": value_mm,
                    "scope_first": "All",
                    "scope_second": "All"
                }
            }
        
        return None
    
    def _export_and_refresh_after_rule_update(self):
        """Refresh rules display after rule update.
        
        The Altium server auto-exports after rule creation/update in silent mode.
        We just need to wait for the export to complete and then refresh the UI.
        No need to call export_pcb_info again (that would show a dialog and timeout).
        """
        try:
            import time
            
            # Wait for Altium's auto-export to complete
            # The create_rule command already triggers ExportPCBInfo in silent mode
            # We just need to wait for the file to be written
            self._safe_after(0, lambda: self.add_message(
                "Waiting for Altium export to complete...",
                is_user=False
            ))
            
            # Wait longer to ensure the export file is fully written
            # Altium needs time to: save PCB, refresh board, export JSON
            # Also wait for file to be fully flushed to disk
            import os
            from pathlib import Path
            
            # Check PCB_Project folder first, then root
            pcb_info_file = Path("PCB_Project") / "altium_pcb_info.json"
            if not pcb_info_file.exists():
                pcb_info_file = Path("altium_pcb_info.json")
            if pcb_info_file.exists():
                # Wait until file modification time is recent (within last 5 seconds)
                initial_mtime = pcb_info_file.stat().st_mtime
                for _ in range(10):  # Wait up to 5 seconds
                    time.sleep(2.0)  # Increased from 0.5s to 2.0s
                    current_mtime = pcb_info_file.stat().st_mtime
                    if current_mtime > initial_mtime:
                        # File was updated, wait a bit more for it to be fully written
                        time.sleep(1.0)
                        break
                else:
                    # File wasn't updated, wait anyway
                    time.sleep(2.0)
            else:
                # File doesn't exist yet, wait longer
                time.sleep(5.0)
            
            # Refresh rules display from the auto-exported file
            self._view_design_rules()
            
        except Exception as e:
            import traceback
            print(f"Error in _export_and_refresh_after_rule_update: {e}")
            print(traceback.format_exc())
            # Fallback: just try to refresh anyway
            try:
                time.sleep(2.0)
                self._view_design_rules()
            except:
                pass
    
    def _refresh_rules_after_update(self):
        """Refresh rules display after rule update.
        
        NOTE: The Altium server now auto-saves and auto-exports after
        rule creation/update, so we just need to reload the local JSON.
        No need to ping or re-export (that would block the server).
        """
        try:
            import time
            # Brief wait for the exported JSON file to be fully written
            time.sleep(1.0)
            
            # Refresh rules display from the already-exported file
            self._view_design_rules()
            
        except Exception as e:
            self.add_message(
                f"Rule applied but could not refresh automatically.\n"
                f"Please click 'View Design Rules' to see the updated rules.\n\n"
                f"Error: {str(e)}",
                is_user=False
            )
    
    def _show_confirmation_modal(self, message: str):
        """Show confirmation modal dialog"""
        def on_confirm():
            """User confirmed - execute the command"""
            if self.agent and self.agent.pending_command:
                # Execute the pending command
                self.set_loading(True)
                self.set_status("Executing command...", "info")
                
                # Execute in background thread
                def execute():
                    try:
                        result = self.agent.execute_pending_command()
                        response_text = result.get("message", "Command executed")
                        status = result.get("status", "success")
                        is_exec = (status == "success")
                        
                        self._safe_after(0, lambda: self.on_command_executed(response_text, status, is_exec))
                    except Exception as e:
                        self._safe_after(0, lambda: self.on_command_executed(f"Error: {e}", "error", False))
                
                threading.Thread(target=execute, daemon=True).start()
            else:
                self.set_status("No command to execute", "error")
                self.set_loading(False)
        
        def on_cancel():
            """User cancelled - just continue chatting"""
            self.set_status("Ready", "success")
            self.set_loading(False)
        
        # Show modal
        modal = ConfirmationModal(self, message, on_confirm, on_cancel)
    
    def on_command_executed(self, response: str, status: str, is_exec: bool):
        """Handle command execution result"""
        # Add execution result message
        self.add_message(response, is_user=False)
        
        # Update status
        self.set_loading(False)
        if status == "error":
            self.set_status("Error", "error")
        elif is_exec:
            self.set_status("Command Executed", "success")
        else:
            self.set_status("Ready", "success")
        
        # Clear pending confirmation
        self.pending_confirmation = None
        
        # Final scroll
        self.chat_frame.update()
        self.chat_frame._parent_canvas.yview_moveto(1.0)
    
    def clear_chat(self):
        """Clear chat history"""
        for msg in self.messages:
            msg.destroy()
        self.messages = []
        
        if self.agent:
            self.agent.clear_history()
        
        self.add_welcome_message()
        self.set_status("Ready", "success")
    
    def _safe_after(self, delay_ms: int, func):
        """Safely schedule after() callback, checking if widget is still alive"""
        if self.is_destroyed:
            return
        try:
            # Check if widget still exists and has valid tkinter window
            if hasattr(self, 'winfo_exists') and self.winfo_exists():
                self.after(delay_ms, func)
        except (AttributeError, RuntimeError, tkinter.TclError):
            # Widget is destroyed or invalid, ignore
            self.is_destroyed = True
            pass
    
    def upload_file(self):
        """Open file dialog to upload PCB/Schematic files"""
        from tkinter import filedialog
        
        filetypes = [
            ("All PCB Files", "*.PcbDoc;*.SchDoc;*.PrjPcb"),
            ("PCB Documents", "*.PcbDoc"),
            ("Schematic Documents", "*.SchDoc"),
            ("PCB Projects", "*.PrjPcb"),
            ("All Files", "*.*")
        ]
        
        filepath = filedialog.askopenfilename(
            title="Select PCB/Schematic File",
            filetypes=filetypes,
            initialdir="."
        )
        
        if filepath:
            # Determine file type
            if filepath.lower().endswith('.pcbdoc'):
                self.load_pcb_file(filepath)
            elif filepath.lower().endswith('.schdoc'):
                self.add_message(f"Selected schematic: {filepath}", is_user=True)
                self.add_message("Schematic analysis coming soon!", is_user=False)
            elif filepath.lower().endswith('.prjpcb'):
                self.add_message(f"Selected project: {filepath}", is_user=True)
                self.add_message("Project analysis coming soon!", is_user=False)
            else:
                self.add_message(f"Unknown file type: {filepath}", is_user=False)
    
    def load_pcb_file(self, filepath: str):
        """Load and analyze a PCB file via MCP server"""
        import os
        
        # Show loading message
        self.add_message(f"Loading: {os.path.basename(filepath)}", is_user=True)
        self.set_status("Loading PCB...", "warning")
        self.set_loading(True)
        
        # Process in background
        def load():
            try:
                # Load PCB via MCP client (updates the server!)
                result = self.mcp_client.load_pcb_file(filepath)
                
                if result.get("error"):
                    raise Exception(result.get("error"))
                
                # Get statistics from server response
                stats = result.get("statistics", {})
                artifact_id = result.get("artifact_id", "unknown")
                layers = result.get("layers", 0)
                analysis = result.get("analysis", {})
                
                # Build response with intelligent analysis
                response = f"""## PCB Loaded Successfully!

**File:** {os.path.basename(filepath)}
**Artifact ID:** {artifact_id[:8]}...

### Board Statistics
• **Components:** {stats.get('component_count', 0)}
• **Nets:** {stats.get('net_count', 0)}
• **Tracks:** {stats.get('track_count', 0)}
• **Vias:** {stats.get('via_count', 0)}
• **Layers:** {layers}
"""
                
                # Add intelligent analysis results
                if analysis:
                    summary = analysis.get("summary", {})
                    issues = analysis.get("issues", [])
                    recommendations = analysis.get("recommendations", [])
                    
                    if summary.get("total_issues", 0) > 0:
                        response += f"""
### ⚠️ Analysis Found {summary.get('total_issues', 0)} Issues

**Errors:** {summary.get('errors', 0)} | **Warnings:** {summary.get('warnings', 0)}

"""
                        # Show top issues
                        for issue in issues[:5]:
                            icon = "🔴" if issue.get("severity") == "error" else "🟡"
                            response += f"{icon} {issue.get('message', '')}\n"
                        
                        if len(issues) > 5:
                            response += f"\n... and {len(issues) - 5} more issues\n"
                        
                        # Show recommendations
                        if recommendations:
                            response += f"""
### 💡 Recommendations

"""
                            for i, rec in enumerate(recommendations[:3], 1):
                                priority = rec.get("priority", "normal").upper()
                                response += f"**{i}. [{priority}]** {rec.get('description', '')}\n"
                            
                            response += """
**Would you like me to apply these recommendations?** Reply "yes" to proceed.
"""
                    else:
                        response += """
### ✅ No Critical Issues Found

Your PCB looks good! You can still ask me to:
• Generate routing suggestions
• Run detailed DRC check
• Optimize component placement
"""
                
                self._safe_after(0, lambda: self.on_pcb_loaded(response, artifact_id))
                
            except Exception as e:
                import traceback
                error_msg = f"Error loading PCB: {str(e)}"
                print(traceback.format_exc())
                self._safe_after(0, lambda: self.on_pcb_load_error(error_msg))
        
        threading.Thread(target=load, daemon=True).start()
    
    def on_pcb_loaded(self, response: str, artifact_id: str):
        """Handle successful PCB load"""
        self.add_message(response, is_user=False)
        self.set_loading(False)
        self.set_status("PCB Loaded", "success")
        
        # Store artifact ID for future commands
        self.current_artifact_id = artifact_id
    
    def on_pcb_load_error(self, error: str):
        """Handle PCB load error"""
        self.add_message(error, is_user=False)
        self.set_loading(False)
        self.set_status("Error", "error")
    
    def go_back(self):
        """Go back to project setup page"""
        self.is_destroyed = True  # Mark as destroyed to prevent callbacks
        self.clear_chat()
        if self.on_back:
            self.on_back()
    
    def destroy(self):
        """Override destroy to mark as destroyed"""
        self.is_destroyed = True
        super().destroy()
