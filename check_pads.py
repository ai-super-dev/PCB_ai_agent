import json

# Load PCB data
with open('PCB_Project/altium_pcb_info.json', encoding='latin-1') as f:
    data = json.load(f)

# Find C154 pads
c154_pads = [p for p in data.get('pads', []) if 'C154' in p.get('designator', '')]
print(f'Found {len(c154_pads)} C154 pads:')
for p in c154_pads:
    print(f"  {p.get('designator')}: net={p.get('net')}, x={p.get('x_mm')}, y={p.get('y_mm')}")

# Find all pads with -12V net
minus12v_pads = [p for p in data.get('pads', []) if p.get('net') == '-12V']
print(f'\nFound {len(minus12v_pads)} pads on -12V net:')
for p in minus12v_pads:
    print(f"  {p.get('designator')}: x={p.get('x_mm')}, y={p.get('y_mm')}")

# Check if there are any nets with similar names
similar_nets = [n for n in data.get('nets', []) if '12' in n.get('name', '')]
print(f'\nNets containing "12": {[n.get("name") for n in similar_nets]}')
