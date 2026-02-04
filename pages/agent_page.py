"""
Agent Page - Professional Chat Interface
Main interaction page for EagilinsED
"""
import customtkinter as ctk
import tkinter
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
        
        # Message bubble
        bubble_color = self.colors["user_bg"] if is_user else self.colors["assistant_bg"]
        bubble = ctk.CTkFrame(
            container,
            fg_color=bubble_color,
            corner_radius=16,
            border_width=0 if is_user else 1,
            border_color=self.colors["border"]
        )
        bubble.grid(row=0, column=0, padx=(60 if is_user else 0, 0 if is_user else 60))
        
        # Message text
        self.msg_label = ctk.CTkLabel(
            bubble,
            text=message,
            font=ctk.CTkFont(size=13),
            text_color=self.colors["text"],
            anchor="w",
            justify="left",
            wraplength=WINDOW_WIDTH - 160
        )
        self.msg_label.grid(row=0, column=0, sticky="w", padx=16, pady=14)
    
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
        input_container = ctk.CTkFrame(self, fg_color=self.colors["bg_card"], height=80)
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
                                            from tools.drc_report_parser import parse_drc_report
                                            report_data = parse_drc_report(str(latest_file))
                                            
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
                    time.sleep(0.5)
                    
                    # Load the exported file
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
                
                # FALLBACK: Check for auto-exported file from StartServer
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
        
        if not self.agent:
            self.add_message("LLM not available. Check OpenAI API key.", is_user=False)
            return
        
        # Clear input
        self.input_entry.delete(0, "end")
        
        # Add user message
        self.add_message(text, is_user=True)
        
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
        """Add button to open DRC report in browser"""
        import os
        import webbrowser
        from pathlib import Path
        import glob
        
        # Find Altium DRC report in Project Outputs folder
        project_outputs = Path("PCB_Project/Project Outputs for PCB_Project")
        report_path = None
        
        if project_outputs.exists():
            # Find the latest DRC HTML report
            html_files = list(project_outputs.glob("Design Rule Check*.html"))
            if html_files:
                # Get the most recent one
                report_path = max(html_files, key=lambda p: p.stat().st_mtime)
        
        # Create button container
        btn_container = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        btn_container.grid(row=len(self.messages) + 100, column=0, sticky="w", pady=10, padx=10)
        
        # Open DRC Report button
        report_btn = ctk.CTkButton(
            btn_container,
            text="📄 View DRC Report in Browser",
            width=220,
            height=40,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._open_drc_report(str(report_path) if report_path else None)
        )
        report_btn.pack(side="left", padx=5)
        
        # Scroll to show button
        self.chat_frame.update()
        self.chat_frame._parent_canvas.yview_moveto(1.0)
    
    def _open_drc_report(self, path: str = None):
        """Open DRC report in default browser"""
        import webbrowser
        import os
        from pathlib import Path
        
        # Always search for the latest report
        project_outputs = Path("PCB_Project/Project Outputs for PCB_Project").absolute()
        report_path = None
        
        if project_outputs.exists():
            html_files = list(project_outputs.glob("Design Rule Check*.html"))
            if html_files:
                report_path = max(html_files, key=lambda p: p.stat().st_mtime)
        
        if report_path and report_path.exists():
            # Use os.startfile on Windows for reliable file opening
            try:
                os.startfile(str(report_path))
            except:
                # Fallback to webbrowser
                file_url = "file:///" + str(report_path).replace("\\", "/")
                webbrowser.open(file_url)
        else:
            # Show message if report doesn't exist
            self.add_message("DRC report not found. Run DRC in Altium Designer first (Tools → Design Rule Check).", is_user=False)
    
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
