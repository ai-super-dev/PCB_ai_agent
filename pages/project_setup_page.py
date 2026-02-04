"""
Project Setup Page - Professional Design
Choose between existing project or create new
"""
import customtkinter as ctk
from config import WINDOW_WIDTH, WINDOW_HEIGHT
import logging

logger = logging.getLogger(__name__)


class ProjectSetupPage(ctk.CTkFrame):
    """Professional project setup page"""
    
    def __init__(self, parent, mcp_client, on_continue=None):
        super().__init__(parent, width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        self.parent = parent
        self.mcp_client = mcp_client
        self.on_continue = on_continue
        self.project_mode = None
        self.is_destroyed = False
        self.created_project_name = None  # Store project name for agent page
        
        # Color scheme
        self.colors = {
            "bg_dark": "#0f172a",
            "bg_card": "#1e293b",
            "bg_hover": "#334155",
            "border": "#475569",
            "border_selected": "#3b82f6",
            "primary": "#3b82f6",
            "primary_hover": "#2563eb",
            "success": "#10b981",
            "success_hover": "#059669",
            "text": "#f8fafc",
            "text_muted": "#94a3b8",
            "text_dim": "#64748b"
        }
        
        self.configure(fg_color=self.colors["bg_dark"])
        self.setup_ui()
    
    def setup_ui(self):
        """Setup professional UI"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        # === Header ===
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, pady=(60, 40), sticky="n")
        
        title = ctk.CTkLabel(
            header,
            text="Get Started",
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color=self.colors["text"]
        )
        title.pack()
        
        subtitle = ctk.CTkLabel(
            header,
            text="How would you like to begin?",
            font=ctk.CTkFont(size=14),
            text_color=self.colors["text_muted"]
        )
        subtitle.pack(pady=(8, 0))
        
        # === Cards Container ===
        cards_container = ctk.CTkFrame(self, fg_color="transparent")
        cards_container.grid(row=1, column=0, sticky="n")
        
        # Existing Project Card
        self.existing_card = self._create_card(
            cards_container,
            icon="📂",
            title="Open Existing Project",
            description="Import and analyze your current design",
            row=0,
            command=self.select_existing
        )
        
        # New Project Card
        self.new_card = self._create_card(
            cards_container,
            icon="✨",
            title="Start New Project",
            description="Create a fresh PCB design from scratch",
            row=1,
            command=self.select_new
        )
        
        # === Instructions Panel ===
        self.instructions = ctk.CTkFrame(
            self,
            fg_color=self.colors["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border"],
            width=WINDOW_WIDTH - 80,
            height=200  # Fixed height for consistent size
        )
        self.instructions.grid(row=2, column=0, pady=(30, 40), padx=40, sticky="n")
        self.instructions.grid_propagate(False)  # Prevent resizing
        self.instructions.grid_columnconfigure(0, weight=1)
        self.instructions.grid_rowconfigure(1, weight=1)  # Content area expands
        
        # Panel header
        self.instr_header = ctk.CTkLabel(
            self.instructions,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["primary"]
        )
        self.instr_header.grid(row=0, column=0, pady=(20, 8), padx=24)
        
        # Panel content
        self.instr_content = ctk.CTkLabel(
            self.instructions,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_muted"],
            justify="left",
            wraplength=WINDOW_WIDTH - 120
        )
        self.instr_content.grid(row=1, column=0, pady=(0, 12), padx=24, sticky="n")
        
        # Continue button
        self.continue_btn = ctk.CTkButton(
            self.instructions,
            text="Continue →",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            width=160,
            corner_radius=8,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            command=self.continue_to_agent
        )
        self.continue_btn.grid(row=2, column=0, pady=(8, 20), sticky="s")
        
        # Hide initially
        self.instructions.grid_remove()
    
    def _create_card(self, parent, icon, title, description, row, command):
        """Create a selection card"""
        card = ctk.CTkFrame(
            parent,
            width=340,
            height=72,
            corner_radius=10,
            fg_color=self.colors["bg_card"],
            border_width=1,
            border_color=self.colors["border"]
        )
        card.grid(row=row, column=0, pady=6)
        card.grid_propagate(False)
        card.grid_columnconfigure(1, weight=1)
        
        # Icon
        icon_lbl = ctk.CTkLabel(
            card,
            text=icon,
            font=ctk.CTkFont(size=22)
        )
        icon_lbl.grid(row=0, column=0, rowspan=2, padx=(18, 12), pady=14)
        
        # Title
        title_lbl = ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors["text"],
            anchor="w"
        )
        title_lbl.grid(row=0, column=1, sticky="sw", pady=(14, 0))
        
        # Description
        desc_lbl = ctk.CTkLabel(
            card,
            text=description,
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_dim"],
            anchor="w"
        )
        desc_lbl.grid(row=1, column=1, sticky="nw", pady=(2, 14))
        
        # Arrow
        arrow = ctk.CTkLabel(
            card,
            text="→",
            font=ctk.CTkFont(size=16),
            text_color=self.colors["text_dim"]
        )
        arrow.grid(row=0, column=2, rowspan=2, padx=(8, 18))
        
        # Bind clicks
        for widget in [card, icon_lbl, title_lbl, desc_lbl, arrow]:
            widget.bind("<Button-1>", lambda e, c=command: c())
            widget.bind("<Enter>", lambda e, cd=card: cd.configure(fg_color=self.colors["bg_hover"]))
            widget.bind("<Leave>", lambda e, cd=card: cd.configure(fg_color=self.colors["bg_card"]) 
                        if cd != self.existing_card or self.project_mode != "existing" else None)
        
        return card
    
    def _highlight_card(self, selected_card, color):
        """Highlight selected card"""
        self.existing_card.configure(border_color=self.colors["border"])
        self.new_card.configure(border_color=self.colors["border"])
        selected_card.configure(border_color=color)
    
    def select_existing(self):
        """Select existing project"""
        self.project_mode = "existing"
        self._highlight_card(self.existing_card, self.colors["primary"])
        
        # Check for existing projects/documents
        self._check_and_select_file()
    
    def select_new(self):
        """Select new project"""
        self.project_mode = "new"
        self._highlight_card(self.new_card, self.colors["success"])
        
        self.instr_header.configure(text="Enter Project Name", text_color=self.colors["success"])
        
        # Create input frame
        if hasattr(self, 'project_input_frame'):
            self.project_input_frame.destroy()
        
        self.project_input_frame = ctk.CTkFrame(
            self.instructions,
            fg_color="transparent"
        )
        self.project_input_frame.grid(row=1, column=0, pady=(0, 12), padx=24, sticky="ew")
        self.project_input_frame.grid_columnconfigure(0, weight=1)
        
        # Project name input
        self.project_name_entry = ctk.CTkEntry(
            self.project_input_frame,
            placeholder_text="Enter project name (e.g., MyDesign)",
            font=ctk.CTkFont(size=13),
            height=40,
            corner_radius=8,
            fg_color=self.colors["bg_dark"],
            border_color=self.colors["border"],
            border_width=1,
            text_color=self.colors["text"]
        )
        self.project_name_entry.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.project_name_entry.bind("<Return>", lambda e: self.create_and_continue())
        self.project_name_entry.focus()
        
        # Info text
        info_text = ctk.CTkLabel(
            self.project_input_frame,
            text="Enter the project name and click 'Create Project'. You'll be prompted to run a script in Altium Designer.",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_dim"],
            justify="left"
        )
        info_text.grid(row=1, column=0, sticky="w")
        
        self.continue_btn.configure(
            text="Create Project →",
            fg_color=self.colors["success"],
            hover_color=self.colors["success_hover"],
            command=self.create_and_continue
        )
        self.instructions.grid()
    
    def create_and_continue(self):
        """Create project and proceed to agent page"""
        if self.project_mode == "new":
            project_name = self.project_name_entry.get().strip()
            if not project_name:
                # Show error
                if hasattr(self, 'project_input_frame'):
                    error_label = ctk.CTkLabel(
                        self.project_input_frame,
                        text="Please enter a project name.",
                        font=ctk.CTkFont(size=11),
                        text_color="#ef4444"
                    )
                    error_label.grid(row=2, column=0, sticky="w", pady=(4, 0))
                    self.after(3000, lambda: error_label.destroy() if hasattr(self, 'winfo_exists') and self.winfo_exists() else None)
                return
            
            # Create project command
            self._create_project_command(project_name)
            
            # Pass project name to callback
            if self.on_continue:
                self.on_continue(self.project_mode, project_name)
        else:
            # Continue to agent page for existing projects
            if self.on_continue:
                self.on_continue(self.project_mode, None)
    
    def _create_project_command(self, project_name: str):
        """Create project by writing command to JSON file"""
        import json
        from pathlib import Path
        import time
        
        # Write project creation command to pcb_commands.json (main.pas router will show which script to run)
        commands_file = Path(__file__).parent.parent / "pcb_commands.json"
        
        command_data = {
            "command": "create_project",
            "parameters": {
                "project_name": project_name
            },
            "timestamp": time.time()
        }
        
        try:
            # Write command to JSON file
            with open(commands_file, 'w', encoding='utf-8') as f:
                json.dump([command_data], f, indent=2)
            
            logger.info(f"Project creation command written: {project_name}")
            
            # Store project name for agent page to show instructions
            self.created_project_name = project_name
            
        except Exception as e:
            logger.error(f"Failed to create project command: {e}")
            import tkinter.messagebox as msgbox
            msgbox.showerror("Error", f"Failed to create project command: {e}")
    
    def _check_and_select_file(self):
        """Check for existing projects and show file selection"""
        self.instr_header.configure(text="Select Working File", text_color=self.colors["primary"])
        
        # Check if MCP client is connected
        if not self.mcp_client or not self.mcp_client.connected:
            self.instr_content.configure(
                text="Please connect to Altium Designer first.\n"
                     "Go back to the welcome page and click 'Connect'."
            )
            self.continue_btn.grid_remove()
            self.instructions.grid()
            return
        
        # Try to get project info from MCP server
        try:
            project_info = self.mcp_client.get_project_info()
            if project_info and project_info.get("documents"):
                # Show file selection
                self._show_file_selection(project_info["documents"])
                return
        except Exception as e:
            logger.error(f"Error getting project info: {e}")
        
        # If no project info, show instructions to export first
        self.instr_content.configure(
            text="No project information found.\n\n"
                 "1. Open your project in Altium Designer\n"
                 "2. Go to File → Run Script\n"
                 "3. Run: altium_project_manager.pas → ExportProjectInfo\n\n"
                 "Then click 'Refresh' to see available files."
        )
        
        # Add refresh button
        if hasattr(self, 'refresh_btn'):
            self.refresh_btn.destroy()
        
        self.refresh_btn = ctk.CTkButton(
            self.instructions,
            text="Refresh",
            font=ctk.CTkFont(size=12),
            height=32,
            width=100,
            corner_radius=6,
            fg_color=self.colors["border"],
            hover_color=self.colors["bg_hover"],
            command=self._check_and_select_file
        )
        self.refresh_btn.grid(row=3, column=0, pady=(8, 20))
        
        self.continue_btn.grid_remove()
        self.instructions.grid()
    
    def _show_file_selection(self, documents):
        """Show file selection UI"""
        # Clear existing content
        self.instr_content.configure(text="")
        
        # Create scrollable frame for file list
        if hasattr(self, 'file_list_frame'):
            self.file_list_frame.destroy()
        
        self.file_list_frame = ctk.CTkScrollableFrame(
            self.instructions,
            fg_color=self.colors["bg_dark"],
            height=120
        )
        self.file_list_frame.grid(row=1, column=0, pady=(0, 12), padx=24, sticky="ew")
        self.file_list_frame.grid_columnconfigure(0, weight=1)
        
        # Filter PCB and Schematic documents
        pcb_files = [d for d in documents if d.get("type") == "PCB"]
        sch_files = [d for d in documents if d.get("type") == "SCH"]
        
        if not pcb_files and not sch_files:
            self.instr_content.configure(
                text="No PCB or Schematic files found in project.\n"
                     "Please open a project with .PcbDoc or .SchDoc files."
            )
            return
        
        # Show files
        self.selected_file = None
        row = 0
        
        if pcb_files:
            type_label = ctk.CTkLabel(
                self.file_list_frame,
                text="PCB Files:",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=self.colors["primary"]
            )
            type_label.grid(row=row, column=0, sticky="w", pady=(0, 4))
            row += 1
            
            for doc in pcb_files:
                self._create_file_button(doc, row)
                row += 1
        
        if sch_files:
            if pcb_files:
                # Separator
                sep = ctk.CTkFrame(self.file_list_frame, height=1, fg_color=self.colors["border"])
                sep.grid(row=row, column=0, sticky="ew", pady=8)
                row += 1
            
            type_label = ctk.CTkLabel(
                self.file_list_frame,
                text="Schematic Files:",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=self.colors["success"]
            )
            type_label.grid(row=row, column=0, sticky="w", pady=(0, 4))
            row += 1
            
            for doc in sch_files:
                self._create_file_button(doc, row)
                row += 1
        
        # Update continue button
        self.continue_btn.configure(
            text="Export & Continue →",
            command=self._export_and_continue,
            state="disabled"
        )
        self.continue_btn.grid(row=2, column=0, pady=(8, 20), sticky="s")
    
    def _create_file_button(self, doc, row):
        """Create a file selection button"""
        file_name = doc.get("name", "Unknown")
        file_type = doc.get("type", "")
        file_path = doc.get("path", "")
        
        # File button
        file_btn = ctk.CTkButton(
            self.file_list_frame,
            text=f"  {file_name}",
            font=ctk.CTkFont(size=11),
            height=32,
            anchor="w",
            corner_radius=6,
            fg_color=self.colors["bg_card"],
            hover_color=self.colors["bg_hover"],
            border_width=1,
            border_color=self.colors["border"],
            command=lambda: self._select_file(doc, file_btn)
        )
        file_btn.grid(row=row, column=0, sticky="ew", pady=2)
        
        # Store reference
        if not hasattr(self, '_file_buttons'):
            self._file_buttons = {}
        self._file_buttons[file_path] = file_btn
    
    def _select_file(self, doc, button):
        """Select a file"""
        # Deselect all
        if hasattr(self, '_file_buttons'):
            for btn in self._file_buttons.values():
                btn.configure(border_color=self.colors["border"], fg_color=self.colors["bg_card"])
        
        # Select this one
        button.configure(border_color=self.colors["primary"], fg_color=self.colors["primary"])
        self.selected_file = doc
        self.continue_btn.configure(state="normal")
    
    def _export_and_continue(self):
        """Export file info and continue to agent page"""
        if not self.selected_file:
            return
        
        file_type = self.selected_file.get("type")
        file_name = self.selected_file.get("name")
        
        # Show loading spinner
        self._show_loading(f"Exporting {file_name}...")
        
        # Determine which script to run
        if file_type == "PCB":
            script_name = "altium_export_pcb_info.pas"
            procedure = "ExportPCBInfo"
            info_file = "pcb_info.json"
        elif file_type == "SCH":
            script_name = "altium_export_schematic_info.pas"
            procedure = "ExportSchematicInfo"
            info_file = "schematic_info.json"
        else:
            self._hide_loading()
            import tkinter.messagebox as msgbox
            msgbox.showerror("Error", f"Unsupported file type: {file_type}")
            return
        
        # Store for use in wait function
        self.export_script_name = script_name
        self.export_procedure = procedure
        
        # Update instructions
        self.instr_content.configure(
            text=f"Please run the export script in Altium Designer:\n\n"
                 f"1. File → Run Script\n"
                 f"2. Select: {script_name}\n"
                 f"3. Choose: {procedure}\n"
                 f"4. Click OK\n\n"
                 f"Waiting for export to complete...",
            text_color=self.colors["text"]
        )
        
        # Wait for file in background
        self.after(100, lambda: self._wait_for_export(info_file, file_type))
    
    def _show_loading(self, message):
        """Show loading spinner"""
        if hasattr(self, 'loading_frame'):
            self.loading_frame.destroy()
        
        self.loading_frame = ctk.CTkFrame(
            self.instructions,
            fg_color="transparent"
        )
        self.loading_frame.grid(row=1, column=0, pady=(0, 12), padx=24, sticky="nsew")
        
        # Spinner (animated dots)
        self.loading_label = ctk.CTkLabel(
            self.loading_frame,
            text=message,
            font=ctk.CTkFont(size=12),
            text_color=self.colors["primary"]
        )
        self.loading_label.pack(pady=20)
        
        self.spinner_dots = 0
        self._animate_spinner()
        
        # Disable continue button
        self.continue_btn.configure(state="disabled")
    
    def _animate_spinner(self):
        """Animate loading spinner"""
        if self.is_destroyed or not hasattr(self, 'loading_label'):
            return
        
        dots = "." * (self.spinner_dots % 4)
        self.loading_label.configure(text=f"Exporting{''.join(dots)}")
        self.spinner_dots += 1
        
        if hasattr(self, 'loading_frame') and self.loading_frame.winfo_exists():
            self.after(500, self._animate_spinner)
    
    def _hide_loading(self):
        """Hide loading spinner"""
        if hasattr(self, 'loading_frame'):
            self.loading_frame.destroy()
        self.continue_btn.configure(state="normal")
    
    def _wait_for_export(self, info_file, file_type):
        """Wait for export file to be created"""
        from pathlib import Path
        from mcp_client import wait_for_pcb_info
        
        info_path = Path(__file__).parent.parent / info_file
        
        # Wait for file (with timeout)
        if file_type == "PCB":
            success = wait_for_pcb_info(str(info_path), timeout=60)
        else:
            # For schematic, use similar wait logic
            import time
            start_time = time.time()
            success = False
            while time.time() - start_time < 60:
                if info_path.exists() and info_path.stat().st_size > 1000:
                    try:
                        import json
                        with open(info_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, dict) and len(data) > 0:
                                success = True
                                break
                    except:
                        pass
                time.sleep(1)
        
        self._hide_loading()
        
        if success:
            # Navigate to agent page
            if self.on_continue:
                self.on_continue(self.project_mode, None)
        else:
            # Show error
            script_name = getattr(self, 'export_script_name', 'export script')
            procedure = getattr(self, 'export_procedure', 'procedure')
            self.instr_content.configure(
                text=f"Export timeout. Please ensure you ran:\n"
                     f"{script_name} → {procedure}\n\n"
                     f"Click 'Refresh' to try again.",
                text_color="#ef4444"
            )
            if hasattr(self, 'refresh_btn'):
                self.refresh_btn.grid(row=3, column=0, pady=(8, 20))
    
    def continue_to_agent(self):
        """Proceed to agent page (legacy method)"""
        if self.on_continue:
            self.on_continue(self.project_mode)
    
    def destroy(self):
        """Override destroy to mark as destroyed"""
        self.is_destroyed = True
        super().destroy()
