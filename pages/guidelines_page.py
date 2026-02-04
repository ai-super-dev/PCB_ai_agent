"""
Guidelines Page - Professional Design
"""
import customtkinter as ctk
from config import WINDOW_WIDTH, WINDOW_HEIGHT


class GuidelinesPage(ctk.CTkFrame):
    """Page displaying usage guidelines"""
    
    def __init__(self, parent, on_next=None):
        super().__init__(parent, width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        self.parent = parent
        self.on_next = on_next
        self.is_destroyed = False
        
        # Color scheme (matching other pages)
        self.colors = {
            "bg_dark": "#0f172a",
            "bg_card": "#1e293b",
            "border": "#475569",
            "primary": "#3b82f6",
            "primary_hover": "#2563eb",
            "text": "#f8fafc",
            "text_muted": "#94a3b8",
            "text_dim": "#64748b",
            "accent": "#06b6d4"
        }
        
        self.configure(fg_color=self.colors["bg_dark"])
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # === Header ===
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, pady=(50, 30), sticky="n")
        
        title = ctk.CTkLabel(
            header,
            text="Before You Begin",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=self.colors["text"]
        )
        title.pack()
        
        subtitle = ctk.CTkLabel(
            header,
            text="Important guidelines for using EagilinsED",
            font=ctk.CTkFont(size=13),
            text_color=self.colors["text_muted"]
        )
        subtitle.pack(pady=(8, 0))
        
        # === Guidelines Card ===
        card = ctk.CTkFrame(
            self,
            fg_color=self.colors["bg_card"],
            corner_radius=12,
            border_width=1,
            border_color=self.colors["border"]
        )
        card.grid(row=1, column=0, padx=40, pady=10, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        
        # Scrollable content
        scroll = ctk.CTkScrollableFrame(
            card,
            fg_color="transparent",
            scrollbar_button_color=self.colors["bg_card"],
            scrollbar_button_hover_color=self.colors["border"]
        )
        scroll.pack(fill="both", expand=True, padx=20, pady=20)
        scroll.grid_columnconfigure(0, weight=1)
        
        guidelines = [
            ("Altium Designer", "Ensure Altium Designer is running before connecting"),
            ("Save Your Work", "Keep backups - the assistant can modify your design"),
            ("Review Changes", "Always review modifications before applying"),
            ("API Credits", "OpenAI API credits are required for analysis"),
            ("MCP Server", "The MCP server must be running for integration"),
            ("Clear Queries", "Use specific, clear queries for best results"),
            ("Verify Results", "Check placements and routing after modifications")
        ]
        
        for i, (title, desc) in enumerate(guidelines):
            item = ctk.CTkFrame(scroll, fg_color="transparent")
            item.grid(row=i, column=0, sticky="w", pady=8)
            
            # Number
            num = ctk.CTkLabel(
                item,
                text=f"{i+1}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=self.colors["accent"],
                width=24
            )
            num.grid(row=0, column=0, padx=(0, 12))
            
            # Title
            ttl = ctk.CTkLabel(
                item,
                text=title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=self.colors["text"]
            )
            ttl.grid(row=0, column=1, sticky="w")
            
            # Description
            dsc = ctk.CTkLabel(
                item,
                text=desc,
                font=ctk.CTkFont(size=12),
                text_color=self.colors["text_dim"]
            )
            dsc.grid(row=1, column=1, sticky="w", pady=(2, 0))
        
        # === Continue Button ===
        btn = ctk.CTkButton(
            self,
            text="Continue →",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            width=160,
            corner_radius=8,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            command=self.go_next
        )
        btn.grid(row=2, column=0, pady=(20, 40))
    
    def go_next(self):
        """Navigate to next page"""
        if self.on_next:
            self.on_next()
    
    def destroy(self):
        """Override destroy to mark as destroyed"""
        self.is_destroyed = True
        super().destroy()
