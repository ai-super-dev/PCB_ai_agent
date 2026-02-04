"""
EagilinsED - Agent-Driven PCB Design Assistant
Main Application Entry Point
"""
import customtkinter as ctk
import logging
import sys
from pages.welcome_page import WelcomePage
from pages.agent_page import AgentPage
from config import WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_TITLE
from mcp_client import AltiumMCPClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("EagilinsED")


class EagilinsEDApp(ctk.CTk):
    """Main application class"""
    
    def __init__(self):
        super().__init__()
        
        # Configure window
        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)
        
        # Set appearance mode and color theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Store MCP client and project mode
        self.mcp_client = None
        self.project_mode = None  # "existing" or "new"
        self.project_name = None  # Store project name for new projects
        
        # Show welcome page
        self.show_welcome_page()
    
    def _safe_destroy_widgets(self):
        """Safely destroy all child widgets"""
        widgets = list(self.winfo_children())
        
        # First, mark all widgets as destroyed to prevent new callbacks
        for widget in widgets:
            try:
                if hasattr(widget, 'is_destroyed'):
                    widget.is_destroyed = True
                # Stop any animations or active processes
                if hasattr(widget, 'loading_active'):
                    widget.loading_active = False
                if hasattr(widget, '_stop_loading'):
                    try:
                        widget._stop_loading()
                    except:
                        pass
            except:
                pass
        
        # Process pending events to let callbacks complete
        try:
            self.update_idletasks()
        except:
            pass
        
        # Now destroy widgets with proper exception handling
        for widget in widgets:
            try:
                if hasattr(widget, 'winfo_exists') and widget.winfo_exists():
                    widget.destroy()
            except Exception:
                # Widget may already be destroyed or in invalid state
                # This is safe to ignore
                pass
    
    def show_welcome_page(self):
        """Show welcome and connection page"""
        # Clear existing widgets safely
        self._safe_destroy_widgets()
        
        welcome_page = WelcomePage(
            self,
            on_connect_success=self.on_connect_success
        )
        welcome_page.pack(fill="both", expand=True)
    
    def on_connect_success(self, mcp_client: AltiumMCPClient):
        """Callback when connection is successful"""
        logger.info("MCP connection established successfully")
        self.mcp_client = mcp_client
        # Go directly to agent page - all configuration via natural language
        self.show_agent_page()
    
    def show_agent_page(self):
        """Show main agent page"""
        # Clear existing widgets safely
        self._safe_destroy_widgets()
        
        if self.mcp_client:
            agent_page = AgentPage(
                self, 
                self.mcp_client, 
                on_back=self.show_welcome_page
            )
            agent_page.pack(fill="both", expand=True)
        else:
            # Fallback: show welcome page if no client
            self.show_welcome_page()


def main():
    """Main entry point"""
    logger.info("=" * 50)
    logger.info("EagilinsED - PCB Design Assistant")
    logger.info("=" * 50)
    logger.info("Starting application...")
    
    try:
        app = EagilinsEDApp()
        logger.info("Application window created successfully")
        app.mainloop()
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise


if __name__ == "__main__":
    main()

