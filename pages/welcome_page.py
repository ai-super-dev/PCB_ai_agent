"""
Welcome Page - Professional Interface
Main entry point for EagilinsED
"""
import customtkinter as ctk
import tkinter
from mcp_client import AltiumMCPClient
from config import WINDOW_WIDTH, WINDOW_HEIGHT
import threading
from pathlib import Path


class WelcomePage(ctk.CTkFrame):
    """Professional welcome page with modern design"""
    
    def __init__(self, parent, on_connect_success=None):
        super().__init__(parent, width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        self.parent = parent
        self.on_connect_success = on_connect_success
        self.mcp_client = AltiumMCPClient()
        self.loading_active = False
        self.is_destroyed = False  # Track if widget is destroyed
        self.spinner_dots = 0
        
        # Color scheme
        self.colors = {
            "bg_dark": "#0f172a",
            "bg_card": "#1e293b",
            "border": "#334155",
            "primary": "#3b82f6",
            "primary_hover": "#2563eb",
            "success": "#10b981",
            "error": "#ef4444",
            "text": "#f8fafc",
            "text_muted": "#94a3b8",
            "text_dim": "#64748b",
            "accent": "#06b6d4"
        }
        
        self.configure(fg_color=self.colors["bg_dark"])
        self.setup_ui()
    
    def setup_ui(self):
        """Setup professional UI"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # === Header Section ===
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, pady=(50, 0), sticky="n")
        header.grid_columnconfigure(0, weight=1)
        
        # Brand name with accent
        brand_frame = ctk.CTkFrame(header, fg_color="transparent")
        brand_frame.grid(row=0, column=0)
        
        # Main title
        title = ctk.CTkLabel(
            brand_frame,
            text="EagilinsED",
            font=ctk.CTkFont(family="Segoe UI", size=52, weight="bold"),
            text_color=self.colors["text"]
        )
        title.grid(row=0, column=0)
        
        # Subtitle with accent line
        subtitle_frame = ctk.CTkFrame(header, fg_color="transparent")
        subtitle_frame.grid(row=1, column=0, pady=(8, 0))
        
        # Left line
        left_line = ctk.CTkFrame(subtitle_frame, width=40, height=2, fg_color=self.colors["accent"])
        left_line.grid(row=0, column=0, padx=(0, 12))
        
        subtitle = ctk.CTkLabel(
            subtitle_frame,
            text="Intelligent PCB Design Co-Pilot",
            font=ctk.CTkFont(size=14, weight="normal"),
            text_color=self.colors["text_muted"]
        )
        subtitle.grid(row=0, column=1)
        
        # Right line
        right_line = ctk.CTkFrame(subtitle_frame, width=40, height=2, fg_color=self.colors["accent"])
        right_line.grid(row=0, column=2, padx=(12, 0))
        
        # === Main Content Card ===
        main_card = ctk.CTkFrame(
            self,
            fg_color=self.colors["bg_card"],
            corner_radius=20,
            border_width=1,
            border_color=self.colors["border"]
        )
        main_card.grid(row=1, column=0, pady=40, padx=50, sticky="n")
        main_card.grid_columnconfigure(0, weight=1)
        
        # Logo
        logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            try:
                from PIL import Image as PILImage
                pil_image = PILImage.open(logo_path)
                
                if pil_image.mode == 'RGBA':
                    pass
                elif pil_image.mode == 'P' and 'transparency' in pil_image.info:
                    pil_image = pil_image.convert('RGBA')
                elif pil_image.mode not in ('RGB', 'RGBA', 'L'):
                    pil_image = pil_image.convert('RGB')
                
                # Resize
                img_w, img_h = pil_image.size
                max_w, max_h = 280, 200
                ratio = min(max_w / img_w, max_h / img_h)
                new_size = (int(img_w * ratio), int(img_h * ratio))
                pil_image = pil_image.resize(new_size, resample=PILImage.Resampling.LANCZOS)
                
                logo_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=new_size)
                logo_label = ctk.CTkLabel(main_card, image=logo_image, text="")
                logo_label.grid(row=0, column=0, pady=(30, 20))
            except Exception:
                pass
        
        # Feature highlights
        features_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        features_frame.grid(row=1, column=0, pady=(10, 20), padx=30)
        
        features = [
            ("Analyze", "Functional block detection"),
            ("Generate", "Autonomous layout creation"),
            ("Review", "Design issue identification")
        ]
        
        for i, (title, desc) in enumerate(features):
            feature_item = ctk.CTkFrame(features_frame, fg_color="transparent")
            feature_item.grid(row=0, column=i, padx=15)
            
            # Dot indicator
            dot = ctk.CTkLabel(
                feature_item,
                text="●",
                font=ctk.CTkFont(size=10),
                text_color=self.colors["accent"]
            )
            dot.grid(row=0, column=0, padx=(0, 6))
            
            feature_text = ctk.CTkLabel(
                feature_item,
                text=title,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=self.colors["text"]
            )
            feature_text.grid(row=0, column=1)
        
        # Divider
        divider = ctk.CTkFrame(main_card, height=1, fg_color=self.colors["border"])
        divider.grid(row=2, column=0, sticky="ew", padx=30, pady=15)
        
        # Status area
        self.status_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        self.status_frame.grid(row=3, column=0, pady=(5, 15))
        
        self.status_icon = ctk.CTkLabel(
            self.status_frame,
            text="○",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_dim"]
        )
        self.status_icon.grid(row=0, column=0, padx=(0, 8))
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Ready to connect",
            font=ctk.CTkFont(size=13),
            text_color=self.colors["text_dim"]
        )
        self.status_label.grid(row=0, column=1)
        
        # Connect button
        self.connect_button = ctk.CTkButton(
            main_card,
            text="Connect to Server",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=48,
            width=220,
            corner_radius=10,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_hover"],
            command=self.connect_to_altium
        )
        self.connect_button.grid(row=4, column=0, pady=(5, 25))
        
        # Loading spinner (hidden)
        self.spinner_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        self.spinner_label = ctk.CTkLabel(
            self.spinner_frame,
            text="●  ○  ○",
            font=ctk.CTkFont(size=24),
            text_color=self.colors["primary"]
        )
        self.spinner_label.grid(row=0, column=0)
        
        # Error label
        self.error_label = ctk.CTkLabel(
            main_card,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["error"],
            wraplength=300
        )
        self.error_label.grid(row=5, column=0, pady=(0, 20))
        
        # === Footer ===
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, pady=(0, 30), sticky="s")
        
        footer_text = ctk.CTkLabel(
            footer,
            text="Python File Reader - NO Altium Scripts Needed!",
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_dim"]
        )
        footer_text.grid(row=0, column=0)
        
        # Version
        version_label = ctk.CTkLabel(
            footer,
            text="v1.0",
            font=ctk.CTkFont(size=10),
            text_color=self.colors["text_dim"]
        )
        version_label.grid(row=1, column=0, pady=(5, 0))
    
    def _animate_spinner(self):
        """Animate loading spinner"""
        if not self.loading_active or self.is_destroyed:
            return
        
        try:
            # Check if widget still exists
            if not hasattr(self, 'winfo_exists') or not self.winfo_exists():
                self.is_destroyed = True
                return
            
            states = ["●  ○  ○", "○  ●  ○", "○  ○  ●"]
            self.spinner_dots = (self.spinner_dots + 1) % len(states)
            self.spinner_label.configure(text=states[self.spinner_dots])
            
            if self.loading_active and not self.is_destroyed:
                if hasattr(self, 'winfo_exists') and self.winfo_exists():
                    self.after(350, self._animate_spinner)
        except (AttributeError, RuntimeError, tkinter.TclError):
            # Widget is destroyed or invalid
            self.is_destroyed = True
            self.loading_active = False
            pass
    
    def _start_loading(self):
        """Start loading state"""
        self.loading_active = True
        self.connect_button.grid_remove()
        self.spinner_frame.grid(row=4, column=0, pady=(5, 25))
        self.spinner_dots = 0
        self._animate_spinner()
    
    def _stop_loading(self):
        """Stop loading state"""
        self.loading_active = False
        self.spinner_frame.grid_remove()
        self.connect_button.grid()
    
    def connect_to_altium(self):
        """Connect to MCP server"""
        self.connect_button.configure(state="disabled")
        self.error_label.configure(text="")
        self.status_icon.configure(text="◌", text_color=self.colors["primary"])
        self.status_label.configure(text="Connecting...", text_color=self.colors["text_muted"])
        
        self._start_loading()
        self.update()
        
        def connect_thread():
            try:
                success, message = self.mcp_client.connect_simple()
                if not self.is_destroyed and hasattr(self, 'winfo_exists') and self.winfo_exists():
                    try:
                        self.after(0, self._on_connect_complete, success, message)
                    except (AttributeError, RuntimeError, tkinter.TclError):
                        self.is_destroyed = True
            except Exception as e:
                if not self.is_destroyed and hasattr(self, 'winfo_exists') and self.winfo_exists():
                    try:
                        self.after(0, self._on_connect_complete, False, str(e))
                    except (AttributeError, RuntimeError, tkinter.TclError):
                        self.is_destroyed = True
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def _on_connect_complete(self, success: bool, message: str):
        """Handle connection result"""
        self._stop_loading()
        
        if success:
            self.status_icon.configure(text="●", text_color=self.colors["success"])
            self.status_label.configure(text="Connected", text_color=self.colors["success"])
            if not self.is_destroyed and hasattr(self, 'winfo_exists') and self.winfo_exists():
                try:
                    self.after(500, lambda: self.on_connect_success(self.mcp_client) if self.on_connect_success and not self.is_destroyed and hasattr(self, 'winfo_exists') and self.winfo_exists() else None)
                except (AttributeError, RuntimeError, tkinter.TclError):
                    self.is_destroyed = True
        else:
            self.status_icon.configure(text="●", text_color=self.colors["error"])
            self.status_label.configure(text="Connection failed", text_color=self.colors["error"])
            self.error_label.configure(text=message)
            self.connect_button.configure(state="normal")
    
    def get_mcp_client(self):
        """Get MCP client instance"""
        return self.mcp_client
    
    def destroy(self):
        """Override destroy to mark as destroyed"""
        self.is_destroyed = True
        self.loading_active = False  # Stop spinner
        super().destroy()
