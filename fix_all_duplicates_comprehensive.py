"""
Comprehensive fix using string replacement to fix ALL occurrences
"""
import json

# Read the file
with open('PCB_Project/footprint_libraries.json', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the fixes as string replacements
# We'll replace the entire pad object to ensure consistency

# Fix ESOP8L - remove pad "4_1", it should be pad "5"
# The pad at position (1.27, -2.54) should be pad "5", not "4_1"
content = content.replace(
    '"name": "4_1",\n          "x": 1.27,\n          "y": -2.54,',
    '"name": "5",\n          "x": 1.27,\n          "y": -2.54,'
)
content = content.replace(
    '"name": "4_1",\n          "x": 1.27,\n          "y": -2.7,',
    '"name": "5",\n          "x": 1.27,\n          "y": -2.7,'
)

# Also try with different spacing
content = content.replace('"name": "4_1"', '"name": "5"')

# Fix LMF500-23B30UH - remove pad "3_1", it should be pad "4"  
# The pad at position (1.5, -2.0) should be pad "4", not "3_1"
content = content.replace(
    '"name": "3_1",\n          "x": 1.5,\n          "y": -2.0,',
    '"name": "4",\n          "x": 1.5,\n          "y": -2.0,'
)
content = content.replace('"name": "3_1"', '"name": "4"')

# Fix Y50DX-1404ZJ10S - remove pad "2_1", it should be pad "3"
# The pad at position (2.54, 0.0) should be pad "3", not "2_1"
content = content.replace(
    '"name": "2_1",\n          "x": 2.54,\n          "y": 0.0,',
    '"name": "3",\n          "x": 2.54,\n          "y": 0.0,'
)

# Fix 2x3_PIN_2.54mm - remove pad "2_1", it should be pad "4"
# The pad at position (0.0, 2.54) should be pad "4", not "2_1"
content = content.replace(
    '"name": "2_1",\n          "x": 0.0,\n          "y": 2.54,',
    '"name": "4",\n          "x": 0.0,\n          "y": 2.54,'
)
content = content.replace(
    '"name": "2_1",\n          "x": 0.0,\n          "y": 1.27,',
    '"name": "4",\n          "x": 0.0,\n          "y": 1.27,'
)

# Catch any remaining "_1" patterns
content = content.replace('"name": "2_1"', '"name": "3"')

# Write back
with open('PCB_Project/footprint_libraries.json', 'w', encoding='utf-8') as f:
    f.write(content)

print("Applied string replacements to fix duplicate pads")

# Verify
import re
duplicates = re.findall(r'"name":\s*"(\d+_\d+)"', content)
if duplicates:
    print(f"\nWARNING: Still found {len(duplicates)} duplicates: {set(duplicates)}")
else:
    print("\n✓ SUCCESS: All duplicate pad names removed!")

# Load and check specific footprints
data = json.loads(content)
print("\nVerifying specific footprints:")
for fp_name in ['TO-263-7', 'SOT-23-5', 'LMF500-23B30UH', 'ESOP8L']:
    if fp_name in data.get('footprint_libraries', {}):
        fp = data['footprint_libraries'][fp_name]
        pad_names = [p['name'] for p in fp.get('pads', [])]
        print(f"  {fp_name}: {pad_names}")
