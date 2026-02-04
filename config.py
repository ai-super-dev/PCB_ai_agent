"""
Configuration file for EagilinsED
"""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Recommended models (2025-2026):
# - gpt-4o: Best for PCB analysis (fast, capable)
# - gpt-4o-mini: Cheaper alternative
# - o1-mini: For complex reasoning tasks
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# MCP Configuration
# Default port 8765 for new Python-based MCP server
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8765")
MCP_TIMEOUT = int(os.getenv("MCP_TIMEOUT", "30"))

# UI Configuration
WINDOW_WIDTH = 450  # Mobile phone width (larger)
WINDOW_HEIGHT = 850  # Mobile phone height (larger)
WINDOW_TITLE = "EagilinsED - PCB Design Assistant"

# Altium Designer Connection
ALTIUM_CONNECTION_TIMEOUT = 10

