# EagilinsED

AI-powered PCB design co-pilot that generates layouts from schematics automatically.

## Quick Start

### Using COM Automation (Recommended - Altium 20-24)

```powershell
# Terminal 1: Start COM server (requires Altium Designer 20-24 running)
.\venv\Scripts\Activate.ps1
python mcp_server_com_based.py

# Terminal 2: Start app
.\venv\Scripts\Activate.ps1
python main.py
```

### Using File-Based Method (Fallback - Any Altium Version)

```powershell
# Terminal 1: Start file-based server
.\venv\Scripts\Activate.ps1
python mcp_server_file_based.py

# Altium: Run export_all.pas script to export data
# Terminal 2: Start app
.\venv\Scripts\Activate.ps1
python main.py
```

## Features

- **Analyze** - Identify functional blocks in schematic
- **Strategy** - Generate placement recommendations  
- **Review** - Find design issues and suggest fixes
- **Generate Layout** - Create PCB layout automatically

## Usage

1. Connect to MCP server
2. Export schematic data from Altium
3. Ask: `"Generate layout for this design"`
4. Run generated script in Altium

## Example Commands

```
"Analyze this schematic"
"Generate placement strategy"
"Review this design for issues"
"Generate layout"
```

## Requirements

- Python 3.11+
- Altium Designer 20-24 (for COM automation) or any version (for file-based)
- OpenAI API key
- pywin32 (for COM automation): `pip install pywin32`

## Setup

```powershell
pip install -r requirements.txt
```

Create `.env`:
```
OPENAI_API_KEY=your-key
```

## Documentation

See `SCRIPT_GUIDE.md` for detailed script structure and usage instructions.

