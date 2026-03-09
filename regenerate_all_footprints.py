"""
Regenerate ALL footprints from scratch with proper format
"""
import sys
sys.path.insert(0, '.')

from tools.footprint_generator import FootprintGenerator
from llm_client import LLMClient
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load schematic
with open('PCB_Project/schematic_info.json', 'r', encoding='utf-8') as f:
    schematic_data = json.load(f)

components = schematic_data.get('components', [])
logger.info(f"Loaded {len(components)} components from schematic")

# Initialize LLM client and generator
llm_client = LLMClient()
generator = FootprintGenerator(llm_client)

# Generate footprints
logger.info("Generating footprint libraries...")
result = generator.generate_footprints_batch(components)

# Extract footprint libraries
footprint_libraries = result.get('_footprint_libraries', {})

# Create proper format
output = {
    "footprints": [],
    "footprint_libraries": {}
}

# Add to both structures
for footprint_key, footprint_spec in footprint_libraries.items():
    output["footprints"].append(footprint_spec)
    
    # Also add to footprint_libraries dict
    footprint_name = footprint_spec.get('footprint_name', footprint_key)
    library_key = footprint_name.upper().replace('(', '').replace(')', '').replace(' ', '').replace('.', 'X').replace('*', 'X')
    output["footprint_libraries"][library_key] = footprint_spec

# Save
with open('PCB_Project/footprint_libraries.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

logger.info(f"\nGenerated {len(output['footprints'])} footprints")
logger.info("Footprint libraries saved to PCB_Project/footprint_libraries.json")
