#!/usr/bin/env python3
"""
Diagnostic script to check if exported PCB data has all required fields
"""
import json
from pathlib import Path

def check_pcb_export():
    """Check exported PCB data for completeness"""
    
    # Find the exported file
    base_path = Path(__file__).parent
    pcb_file = base_path / "PCB_Project" / "altium_pcb_info.json"
    if not pcb_file.exists():
        pcb_file = base_path / "altium_pcb_info.json"
    
    if not pcb_file.exists():
        print(f"[ERROR] PCB export file not found!")
        print(f"   Checked: {base_path / 'PCB_Project' / 'altium_pcb_info.json'}")
        print(f"   Checked: {base_path / 'altium_pcb_info.json'}")
        return
    
    print(f"[OK] Found export file: {pcb_file}")
    
    # Load and check
    try:
        with open(pcb_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except UnicodeDecodeError:
        with open(pcb_file, 'r', encoding='latin-1') as f:
            data = json.load(f)
    
    print(f"\n[SUMMARY] Data Summary:")
    print(f"   Components: {len(data.get('components', []))}")
    print(f"   Pads: {len(data.get('pads', []))}")
    print(f"   Tracks: {len(data.get('tracks', []))}")
    print(f"   Vias: {len(data.get('vias', []))}")
    print(f"   Nets: {len(data.get('nets', []))}")
    print(f"   Polygons: {len(data.get('polygons', []))}")
    
    # Check pads
    print(f"\n[CHECK] Checking Pads ({len(data.get('pads', []))} total):")
    pads = data.get('pads', [])
    if pads:
        sample_pad = pads[0]
        print(f"   Sample pad fields: {list(sample_pad.keys())}")
        
        required_fields = ['net', 'x_mm', 'y_mm', 'layer', 'size_x_mm', 'size_y_mm', 'designator']
        missing_fields = []
        for field in required_fields:
            if field not in sample_pad:
                missing_fields.append(field)
        
        if missing_fields:
            print(f"   [WARNING] Missing fields: {missing_fields}")
        else:
            print(f"   [OK] All required fields present")
        
        # Check field completeness across all pads
        field_stats = {}
        for field in required_fields:
            count = sum(1 for p in pads if p.get(field) and str(p.get(field)).strip())
            field_stats[field] = (count, len(pads))
            if count < len(pads):
                print(f"   [WARNING] {field}: {count}/{len(pads)} pads have this field")
        
        # Check for new fields we added
        new_fields = ['hole_size_mm', 'shape', 'rotation', 'component_designator']
        print(f"\n   New fields check:")
        for field in new_fields:
            count = sum(1 for p in pads if p.get(field) is not None)
            print(f"      {field}: {count}/{len(pads)} pads")
    
    # Check components
    print(f"\n[CHECK] Checking Components ({len(data.get('components', []))} total):")
    components = data.get('components', [])
    if components:
        sample_comp = components[0]
        print(f"   Sample component fields: {list(sample_comp.keys())}")
        
        if 'pads' in sample_comp:
            pad_count = len(sample_comp.get('pads', []))
            if pad_count > 0:
                print(f"   [OK] Component has {pad_count} pads linked")
            else:
                print(f"   [WARNING] Component pads array is empty")
        else:
            print(f"   [WARNING] Component missing 'pads' field")
    
    # Check tracks
    print(f"\n[CHECK] Checking Tracks ({len(data.get('tracks', []))} total):")
    tracks = data.get('tracks', [])
    if tracks:
        sample_track = tracks[0]
        print(f"   Sample track fields: {list(sample_track.keys())}")
        required = ['net', 'layer', 'x1_mm', 'y1_mm', 'x2_mm', 'y2_mm', 'width_mm']
        missing = [f for f in required if f not in sample_track]
        if missing:
            print(f"   [WARNING] Missing fields: {missing}")
        else:
            print(f"   [OK] All required fields present")
    
    # Check vias
    print(f"\n[CHECK] Checking Vias ({len(data.get('vias', []))} total):")
    vias = data.get('vias', [])
    if vias:
        sample_via = vias[0]
        print(f"   Sample via fields: {list(sample_via.keys())}")
        required = ['net', 'x_mm', 'y_mm', 'hole_size_mm', 'diameter_mm', 'low_layer', 'high_layer']
        missing = [f for f in required if f not in sample_via]
        if missing:
            print(f"   [WARNING] Missing fields: {missing}")
        else:
            print(f"   [OK] All required fields present")
    
    # Check polygons
    print(f"\n[CHECK] Checking Polygons ({len(data.get('polygons', []))} total):")
    polygons = data.get('polygons', [])
    if polygons:
        sample_poly = polygons[0]
        print(f"   Sample polygon fields: {list(sample_poly.keys())}")
        if 'vertices' in sample_poly:
            vcount = len(sample_poly.get('vertices', []))
            print(f"   [OK] Polygon has {vcount} vertices")
        else:
            print(f"   [WARNING] Polygon missing 'vertices' field")
    
    # Check for connection data
    print(f"\n[CHECK] Checking Connection Data:")
    print(f"   [INFO] Connection data can be inferred from:")
    print(f"      - Pads have 'net' field: {sum(1 for p in pads if p.get('net'))}/{len(pads)} pads")
    print(f"      - Tracks have 'net' field: {sum(1 for t in tracks if t.get('net'))}/{len(tracks)} tracks")
    print(f"      - Vias have 'net' field: {sum(1 for v in vias if v.get('net'))}/{len(vias)} vias")
    print(f"      - Components have 'pads' array: {sum(1 for c in components if c.get('pads'))}/{len(components)} components")
    
    # Check if explicit connection data exists
    has_explicit_connections = False
    if tracks:
        sample_track = tracks[0]
        if 'connected_pads' in sample_track or 'connected_vias' in sample_track:
            has_explicit_connections = True
            print(f"   [OK] Tracks have explicit connection data")
    
    if pads:
        sample_pad = pads[0]
        if 'connected_tracks' in sample_pad or 'connected_vias' in sample_pad:
            has_explicit_connections = True
            print(f"   [OK] Pads have explicit connection data")
    
    if not has_explicit_connections:
        print(f"   [INFO] No explicit connection data found - connections are inferred from net names")
        print(f"   [INFO] This is sufficient for DRC, but explicit connections would be more accurate")
    
    # Check component-to-component connections
    print(f"\n[CHECK] Component-to-Component Connections:")
    print(f"   [INFO] Component connections can be inferred from:")
    print(f"      - Components share pads on the same net")
    print(f"      - Example: If C1-pad1 (net='VCC') and C2-pad1 (net='VCC'), they are connected")
    
    # Show example of component connections
    if components and pads:
        # Find a net with multiple component pads
        net_to_components = {}
        for pad in pads:
            net = pad.get('net', '').strip()
            comp = pad.get('component_designator', '').strip()
            if net and comp:
                if net not in net_to_components:
                    net_to_components[net] = set()
                net_to_components[net].add(comp)
        
        # Find nets connecting multiple components
        multi_comp_nets = {net: comps for net, comps in net_to_components.items() if len(comps) > 1}
        if multi_comp_nets:
            example_net = list(multi_comp_nets.keys())[0]
            example_comps = list(multi_comp_nets[example_net])[:3]
            print(f"   [EXAMPLE] Net '{example_net}' connects components: {', '.join(example_comps)}")
            print(f"   [INFO] Total nets connecting multiple components: {len(multi_comp_nets)}")

if __name__ == '__main__':
    check_pcb_export()
