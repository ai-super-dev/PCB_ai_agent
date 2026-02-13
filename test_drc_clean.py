"""Test DRC engine without any debug code or hard-coding"""
import json
from runtime.drc.python_drc_engine import PythonDRCEngine
from tools.altium_file_reader import AltiumFileReader

# Load data from Altium export (has polygon geometry)
with open('PCB_Project/altium_pcb_info.json', 'r', encoding='latin-1') as f:
    export_data = json.load(f)

# Load rules from file reader (has actual rule values)
reader = AltiumFileReader()
file_data = reader.read_pcb('PCB_Project/Y904A23-GF-DYPCB-V1.0.PcbDoc')
file_rules = file_data.get('rules', [])

# Create lookup for file rules
file_rules_lookup = {r.get('name', '').upper(): r for r in file_rules}

# Merge rule values from file reader into export rules
export_rules = export_data.get('rules', [])
for rule in export_rules:
    rule_name = rule.get('name', '').upper()
    if rule_name in file_rules_lookup:
        file_rule = file_rules_lookup[rule_name]
        # Merge clearance values
        if rule.get('clearance_mm', 0) == 0.0 and file_rule.get('clearance_mm', 0) > 0:
            rule['clearance_mm'] = file_rule['clearance_mm']
        # Merge per-object-type clearances
        if file_rule.get('track_to_poly_clearance_mm', 0) > 0:
            rule['track_to_poly_clearance_mm'] = file_rule['track_to_poly_clearance_mm']
        if file_rule.get('pad_to_poly_clearance_mm', 0) > 0:
            rule['pad_to_poly_clearance_mm'] = file_rule['pad_to_poly_clearance_mm']
        if file_rule.get('via_to_poly_clearance_mm', 0) > 0:
            rule['via_to_poly_clearance_mm'] = file_rule['via_to_poly_clearance_mm']
        # Merge type
        if file_rule.get('type') and file_rule.get('type') != 'other':
            rule['type'] = file_rule['type']

print(f"Loaded {len(export_rules)} rules")
print(f"Loaded {len(export_data.get('polygons', []))} polygons")

# Check clearance rule
clearance_rule = next((r for r in export_rules if r.get('name') == 'Clearance'), None)
if clearance_rule:
    print(f"\nClearance rule (after merge):")
    print(f"  clearance_mm: {clearance_rule.get('clearance_mm')}mm")
    print(f"  track_to_poly_clearance_mm: {clearance_rule.get('track_to_poly_clearance_mm')}mm")
    print(f"  scope_first: {clearance_rule.get('scope_first')}")
    print(f"  scope_second: {clearance_rule.get('scope_second')}")

# Run DRC
pcb_data = {
    "tracks": export_data.get('tracks', []),
    "vias": export_data.get('vias', []),
    "pads": export_data.get('pads', []),
    "nets": export_data.get('nets', []),
    "components": export_data.get('components', []),
    "polygons": export_data.get('polygons', [])
}

engine = PythonDRCEngine()
result = engine.run_drc(pcb_data, export_rules)

print(f"\nDRC Results:")
print(f"  Violations: {result['summary']['rule_violations']}")
print(f"  Warnings: {result['summary']['warnings']}")

# Show clearance violations only
clearance_violations = [v for v in result.get('violations', []) if 'clearance' in v.get('rule_type', '').lower()]
print(f"\nClearance Violations: {len(clearance_violations)}")

for i, v in enumerate(clearance_violations[:10]):  # Show first 10
    print(f"  {i+1}. {v.get('message')}")