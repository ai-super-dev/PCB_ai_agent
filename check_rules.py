"""Quick script to check rules in altium_pcb_info.json"""
import json
from pathlib import Path

file_path = Path("altium_pcb_info.json")
if file_path.exists():
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
            rules = data.get('rules', [])
            print(f"✅ File exists: {file_path}")
            print(f"✅ Total rules found: {len(rules)}")
            if rules:
                print(f"\nFirst 5 rule names:")
                for i, rule in enumerate(rules[:5], 1):
                    print(f"  {i}. {rule.get('name', 'Unnamed')} - Type: {rule.get('type', 'unknown')} - Enabled: {rule.get('enabled', False)}")
            else:
                print("❌ Rules array is empty!")
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"❌ File not found: {file_path}")
