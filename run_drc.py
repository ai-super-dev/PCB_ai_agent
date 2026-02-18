"""
Complete DRC workflow script
Automatically fixes clearance values and runs DRC
"""
import json
import subprocess
import sys
from runtime.drc.python_drc_engine import PythonDRCEngine

print("=" * 80)
print("PYTHON DRC ENGINE - COMPLETE WORKFLOW")
print("=" * 80)

# Step 1: Check if JSON file exists
json_path = 'PCB_Project/altium_pcb_info.json'
try:
    with open(json_path, 'r', encoding='utf-8', errors='ignore') as f:
        pcb_data = json.load(f)
    print(f"\n[OK] Loaded PCB data from {json_path}")
except FileNotFoundError:
    print(f"\n[ERROR] {json_path} not found!")
    print("  Please export PCB data from Altium first:")
    print("  1. Open PCB in Altium Designer")
    print("  2. Run: DXP → Run Script → command_server.pas → GetPCBInfo")
    sys.exit(1)

# Step 2: Check and fix clearance values
rules = pcb_data.get('rules', [])
clearance_rule = None
for rule in rules:
    if rule.get('name') == 'Clearance':
        clearance_rule = rule
        break

if clearance_rule:
    current_clearance = clearance_rule.get('clearance_mm', 0)
    print(f"\nClearance rule value in JSON: {current_clearance}mm")
    
    if current_clearance == 0.0:
        print("  [WARNING] Clearance is 0.0mm")
        print("  -> This is expected - Altium's scripting API cannot read the Gap property")
        print("  -> The actual clearance value in Altium is likely 0.2mm (check your DRC rules)")
        print("  -> Running fix_clearance_values.py to set it to 0.2mm...")
        
        # Run the fix script
        result = subprocess.run(['python', 'fix_clearance_values.py'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("  [OK] Clearance values fixed to 0.2mm")
            # Reload the data
            with open(json_path, 'r', encoding='utf-8', errors='ignore') as f:
                pcb_data = json.load(f)
        else:
            print("  [ERROR] Failed to fix clearance values")
            print(result.stderr)
    else:
        print(f"  [OK] Clearance value is set: {current_clearance}mm")
else:
    print("\n[WARNING] 'Clearance' rule not found in PCB data")

# Step 3: Run DRC
print("\n" + "=" * 80)
print("RUNNING DRC...")
print("=" * 80)

engine = PythonDRCEngine()
result = engine.run_drc(pcb_data, pcb_data.get('rules', []))

# Step 4: Display results
print(f"\n{'=' * 80}")
print("DRC RESULTS")
print("=" * 80)

print(f"\nTotal violations: {result['summary']['rule_violations']}")
print(f"Total warnings: {result['summary']['warnings']}")
print(f"Status: {'PASSED' if result['summary']['passed'] else 'FAILED'}")

if result['violations_by_type']:
    print(f"\nViolations by type:")
    for vtype, count in sorted(result['violations_by_type'].items()):
        print(f"  {vtype}: {count}")

if result['violations']:
    print(f"\nDetailed violations:")
    for i, v in enumerate(result['violations'][:20]):  # Show first 20
        print(f"\n{i+1}. {v['rule_name']}")
        print(f"   {v['message'][:120]}...")
        if 'actual_value' in v and 'required_value' in v:
            print(f"   Actual: {v['actual_value']}mm, Required: {v['required_value']}mm")
    
    if len(result['violations']) > 20:
        print(f"\n... and {len(result['violations']) - 20} more violation(s).")

print("\n" + "=" * 80)
print("WORKFLOW COMPLETE")
print("=" * 80)
print("\nTo update with new PCB changes:")
print("1. Export from Altium: DXP → Run Script → command_server.pas → GetPCBInfo")
print("2. Run this script again: python run_drc.py")
