#!/usr/bin/env python3
"""Generate missing footprints and add them to footprint_libraries.json"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from llm_client import LLMClient
from tools.footprint_generator import FootprintGenerator

def main():
    footprint_file = Path(__file__).parent / "PCB_Project" / "footprint_libraries.json"
    
    if not footprint_file.exists():
        print(f"ERROR: {footprint_file} does not exist")
        return 1
    
    # Load existing file
    with open(footprint_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Check what's missing
    existing_footprints = [f.get('footprint_name', '') for f in data.get('footprints', [])]
    existing_footprint_names = {f.upper() for f in existing_footprints}
    dict_keys = set(data.get('footprint_libraries', {}).keys())
    existing_footprint_names.update({k.upper() for k in dict_keys})
    
    required_footprints = {
        'C0805', 'C1206', 'C1210', 'C1812', 'L0805', 'R0805', 'R1210', 
        'TO-252', 'ESOP8L'
    }
    
    missing_required = []
    for rf in required_footprints:
        rf_upper = rf.upper()
        if rf_upper not in existing_footprint_names:
            if rf == 'TO-252':
                if not any('TO-252' in k.upper() for k in existing_footprint_names):
                    missing_required.append(rf)
            else:
                missing_required.append(rf)
    
    if not missing_required:
        print("All required footprints are present!")
        return 0
    
    print(f"Missing footprints: {missing_required}")
    print("Generating missing footprints...")
    
    # Initialize footprint generator
    try:
        llm = LLMClient()
        gen = FootprintGenerator(llm)
    except Exception as e:
        print(f"ERROR: Could not initialize footprint generator: {e}")
        return 1
    
    # Generate missing footprints
    generated_count = 0
    for missing_fp in missing_required:
        try:
            if missing_fp.startswith('C') or missing_fp.startswith('R') or missing_fp.startswith('L'):
                numeric_part = missing_fp[1:]
                standard_dims = gen._get_standard_dimensions(numeric_part)
                if standard_dims:
                    db_footprint = gen._generate_from_standard_database(numeric_part, f'DUMMY_{missing_fp}', 2)
                    if db_footprint:
                        db_footprint['footprint_name'] = missing_fp
                        db_footprint['component_designators'] = []
                        db_footprint['component_count'] = 0
                        data['footprints'].append(db_footprint)
                        data['footprint_libraries'][missing_fp.upper()] = db_footprint
                        data['footprint_libraries'][missing_fp] = db_footprint
                        print(f"✓ Generated {missing_fp}")
                        generated_count += 1
            elif missing_fp == 'TO-252':
                standard_dims = gen._get_standard_dimensions('TO-252')
                fp_name_to_try = 'TO-252'
                if not standard_dims:
                    standard_dims = gen._get_standard_dimensions('TO-252-1')
                    if standard_dims:
                        fp_name_to_try = 'TO-252-1'
                if standard_dims:
                    db_footprint = gen._generate_from_standard_database(fp_name_to_try, 'DUMMY_TO-252', 3)
                    if db_footprint:
                        db_footprint['footprint_name'] = 'TO-252'
                        db_footprint['component_designators'] = []
                        db_footprint['component_count'] = 0
                        data['footprints'].append(db_footprint)
                        data['footprint_libraries']['TO-252'] = db_footprint
                        data['footprint_libraries']['TO-252'.upper()] = db_footprint
                        print(f"✓ Generated TO-252")
                        generated_count += 1
            elif missing_fp == 'ESOP8L':
                standard_dims = gen._get_standard_dimensions('ESOP8L')
                if standard_dims:
                    db_footprint = gen._generate_from_standard_database('ESOP8L', 'DUMMY_ESOP8L', 8)
                    if db_footprint:
                        db_footprint['footprint_name'] = 'ESOP8L'
                        db_footprint['component_designators'] = []
                        db_footprint['component_count'] = 0
                        data['footprints'].append(db_footprint)
                        data['footprint_libraries']['ESOP8L'] = db_footprint
                        data['footprint_libraries']['ESOP8L'.upper()] = db_footprint
                        print(f"✓ Generated ESOP8L")
                        generated_count += 1
        except Exception as e:
            print(f"ERROR generating {missing_fp}: {e}")
            import traceback
            traceback.print_exc()
    
    if generated_count > 0:
        # Save updated file
        with open(footprint_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Saved {generated_count} new footprints to {footprint_file}")
        print(f"Total footprints in file: {len(data.get('footprints', []))}")
    else:
        print("\nNo footprints were generated")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
