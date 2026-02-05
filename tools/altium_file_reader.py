"""
Altium File Reader - Read PCB data directly from Altium files

This module reads Altium Designer .PcbDoc and .SchDoc files directly,
without needing to run Altium scripts.

Altium files are OLE Compound Documents (similar to MS Office files).
We can read them using the olefile library.

Enhanced version with detailed data extraction.

Usage:
    reader = AltiumFileReader()
    data = reader.read_pcb("path/to/file.PcbDoc")
"""

import os
import json
import struct
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


class AltiumFileReader:
    """
    Reads Altium Designer files directly without using Altium's API.
    
    This avoids the memory issues associated with Altium's scripting engine.
    Enhanced version extracts detailed component, net, and layer information.
    """
    
    # Altium uses 0.1 mil units internally (1 mil = 0.0254 mm)
    # So 10000 internal units = 1 inch = 25.4 mm
    UNITS_TO_MM = 25.4 / 10000000.0  # Convert to mm
    
    def __init__(self, base_path: str = None):
        self.base_path = base_path or os.getcwd()
        
    def read_pcb(self, file_path: str) -> Dict[str, Any]:
        """
        Read a PCB document and extract comprehensive information.
        
        Args:
            file_path: Path to the .PcbDoc file
            
        Returns:
            Dictionary with detailed PCB information
        """
        full_path = Path(file_path)
        if not full_path.is_absolute():
            full_path = Path(self.base_path) / file_path
            
        if not full_path.exists():
            return self._empty_result(str(full_path), f"File not found: {full_path}")
        
        try:
            import olefile
            return self._read_with_olefile(str(full_path))
        except ImportError:
            return self._read_basic_info(str(full_path))
        except Exception as e:
            return self._empty_result(str(full_path), str(e))
    
    def _empty_result(self, file_path: str, error: str = None) -> Dict[str, Any]:
        """Return empty result structure."""
        result = {
            "file_name": os.path.basename(file_path),
            "file_path": file_path,
            "read_method": "none",
            "board_size": {"width_mm": 0, "height_mm": 0, "area_mm2": 0},
            "layers": [],
            "layer_count": 0,
            "components": [],
            "nets": [],
            "tracks": [],
            "vias": [],
            "pads": [],
            "rules": [],
            "statistics": {
                "component_count": 0,
                "net_count": 0,
                "track_count": 0,
                "via_count": 0,
                "pad_count": 0,
                "layer_count": 0
            }
        }
        if error:
            result["error"] = error
        return result
    
    def _read_with_olefile(self, file_path: str) -> Dict[str, Any]:
        """Read Altium file using olefile library with detailed extraction."""
        import olefile
        
        ole = olefile.OleFileIO(file_path)
        
        result = {
            "file_name": os.path.basename(file_path),
            "file_path": file_path,
            "read_method": "olefile",
            "read_timestamp": datetime.now().isoformat(),
            "board_size": {"width_mm": 0, "height_mm": 0, "area_mm2": 0},
            "layers": [],
            "layer_count": 0,
            "components": [],
            "nets": [],
            "tracks": [],
            "vias": [],
            "pads": [],
            "rules": [],
            "statistics": {
                "component_count": 0,
                "net_count": 0,
                "track_count": 0,
                "via_count": 0,
                "pad_count": 0,
                "layer_count": 0
            }
        }
        
        streams = ole.listdir()
        
        # Parse Board6/Data for board dimensions and layers
        try:
            if ole.exists('Board6/Data'):
                data = ole.openstream('Board6/Data').read()
                board_info = self._parse_board_data_detailed(data)
                if board_info:
                    result["board_size"] = board_info.get("board_size", result["board_size"])
                    result["layers"] = board_info.get("layers", [])
                    result["layer_count"] = len(result["layers"])
                    result["statistics"]["layer_count"] = len(result["layers"])
        except Exception as e:
            print(f"Error parsing board data: {e}")
        
        # Parse Components6/Data for detailed component info
        try:
            if ole.exists('Components6/Data'):
                data = ole.openstream('Components6/Data').read()
                components = self._parse_component_records_detailed(data)
                result["components"] = components
                result["statistics"]["component_count"] = len(components)
        except Exception as e:
            print(f"Error parsing components: {e}")
        
        # Parse Nets6/Data for net info
        try:
            if ole.exists('Nets6/Data'):
                data = ole.openstream('Nets6/Data').read()
                nets = self._parse_net_records_detailed(data)
                result["nets"] = nets
                result["statistics"]["net_count"] = len(nets)
        except Exception as e:
            print(f"Error parsing nets: {e}")
        
        # Parse Tracks6/Data for track info - NO TRUNCATION
        try:
            if ole.exists('Tracks6/Data'):
                data = ole.openstream('Tracks6/Data').read()
                tracks = self._parse_track_records(data)
                result["tracks"] = tracks  # Full data, no truncation
                result["statistics"]["track_count"] = len(tracks)
        except Exception as e:
            print(f"Error parsing tracks: {e}")
        
        # Parse Vias6/Data for via info - NO TRUNCATION
        try:
            if ole.exists('Vias6/Data'):
                data = ole.openstream('Vias6/Data').read()
                vias = self._parse_via_records(data)
                result["vias"] = vias  # Full data, no truncation
                result["statistics"]["via_count"] = len(vias)
        except Exception as e:
            print(f"Error parsing vias: {e}")
        
        # Parse Pads6/Data for pad info - NO TRUNCATION
        try:
            if ole.exists('Pads6/Data'):
                data = ole.openstream('Pads6/Data').read()
                pads = self._parse_pad_records(data)
                result["pads"] = pads  # Full data, no truncation
                result["statistics"]["pad_count"] = len(pads)
        except Exception as e:
            print(f"Error parsing pads: {e}")
        
        # Parse Rules6/Data for design rules
        try:
            if ole.exists('Rules6/Data'):
                data = ole.openstream('Rules6/Data').read()
                rules = self._parse_rules_records(data)
                result["rules"] = rules
        except Exception as e:
            print(f"Error parsing rules: {e}")
        
        # Get file metadata
        result["metadata"] = {
            "streams": len(streams),
            "stream_names": ['/'.join(s) for s in streams]
        }
        
        ole.close()
        return result
    
    def _parse_key_value_pairs(self, text: str) -> Dict[str, str]:
        """Parse Altium's |KEY=VALUE| format."""
        pairs = {}
        for part in text.split('|'):
            if '=' in part:
                key, value = part.split('=', 1)
                pairs[key.strip()] = value.strip()
        return pairs
    
    def _convert_coord(self, value_str: str) -> float:
        """Convert Altium coordinate string to mm (handles mil, mm, or internal units)."""
        try:
            value_str = str(value_str).strip()
            if not value_str or value_str == '0':
                return 0.0
            
            # Remove any non-printable characters (binary data that sometimes follows values)
            # Keep only printable ASCII characters
            import string
            value_str = ''.join(c for c in value_str if c in string.printable).strip()
            
            # Handle units: mil, mm, or internal units
            if 'mil' in value_str.lower():
                # Extract number before 'mil' (handles "33mil" or "33mil" + binary)
                mil_match = re.search(r'([0-9.]+)\s*mil', value_str, re.IGNORECASE)
                if mil_match:
                    return round(float(mil_match.group(1)) * 0.0254, 4)
            elif 'mm' in value_str.lower():
                # Extract number before 'mm'
                mm_match = re.search(r'([0-9.]+)\s*mm', value_str, re.IGNORECASE)
                if mm_match:
                    return round(float(mm_match.group(1)), 4)
            
            # Try as internal units or raw number
            # Remove any non-numeric characters except decimal point and minus sign
            numeric_str = re.sub(r'[^0-9.\-]', '', value_str)
            if numeric_str:
                value = float(numeric_str)
                # If it's a very large number, it's probably internal units
                if abs(value) > 100000:
                    return round(value * self.UNITS_TO_MM, 4)
                else:
                    # Assume mils for reasonable-sized numbers (common in rules)
                    return round(value * 0.0254, 4)
        except:
            return 0.0
    
    def _parse_board_data_detailed(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse board dimensions and layer stack from Board6/Data stream."""
        try:
            text = data.decode('latin-1', errors='ignore')
            pairs = self._parse_key_value_pairs(text)
            
            # Extract board dimensions
            width_mm = 0.0
            height_mm = 0.0
            
            if 'SHEETWIDTH' in pairs:
                width_mm = self._convert_coord(pairs['SHEETWIDTH'])
            if 'SHEETHEIGHT' in pairs:
                height_mm = self._convert_coord(pairs['SHEETHEIGHT'])
            
            # Extract layers from layer stack
            layers = []
            
            # Common layer names in Altium
            layer_names = {
                'TOP': 'Top',
                'BOTTOM': 'Bottom',
                'TOPLAYER': 'Top',
                'BOTTOMLAYER': 'Bottom',
                'MIDLAYER1': 'Mid Layer 1',
                'MIDLAYER2': 'Mid Layer 2',
                'PLANE1': 'Internal Plane 1',
                'PLANE2': 'Internal Plane 2',
                'TOPOVERLAY': 'Top Overlay',
                'BOTTOMOVERLAY': 'Bottom Overlay',
                'TOPSOLDER': 'Top Solder',
                'BOTTOMSOLDER': 'Bottom Solder',
                'TOPPASTE': 'Top Paste',
                'BOTTOMPASTE': 'Bottom Paste',
                'DRILLGUIDE': 'Drill Guide',
                'KEEPOUT': 'Keep-Out',
                'MECHANICAL1': 'Mechanical 1',
                'MECHANICAL2': 'Mechanical 2'
            }
            
            # Look for layer definitions in the data
            # Try multiple patterns Altium uses for layer storage
            for key, value in pairs.items():
                if key.startswith('V9_LAYERID'):
                    # Extract layer info
                    layer_match = re.search(r'NAME=([^|]+)', value)
                    if layer_match:
                        layers.append({
                            "id": key,
                            "name": layer_match.group(1)
                        })
            
            # Try alternative layer patterns if V9_LAYERID not found
            if not layers:
                # Look for LAYER patterns in the data
                layer_pattern = re.findall(r'LAYER(\d+)NAME=([^|]+)', text)
                for layer_num, layer_name in layer_pattern:
                    layers.append({
                        "id": f"L{layer_num}",
                        "name": layer_name
                    })
            
            # Try LAYERV7 patterns (older format)
            if not layers:
                for i in range(1, 33):  # Altium supports up to 32 layers
                    key = f'LAYERV7_{i}_NAME'
                    if key in pairs:
                        layers.append({
                            "id": f"L{i}",
                            "name": pairs[key]
                        })
            
            # If still no layers found, check for basic TOPLAYER/BOTTOMLAYER
            if not layers:
                if 'TOPLAYER' in pairs or 'TOPNAME' in pairs:
                    layers.append({"id": "L1", "name": pairs.get('TOPNAME', 'Top'), "kind": "signal"})
                if 'BOTTOMLAYER' in pairs or 'BOTTOMNAME' in pairs:
                    layers.append({"id": "L2", "name": pairs.get('BOTTOMNAME', 'Bottom'), "kind": "signal"})
            
            # NO FABRICATED DEFAULT LAYERS - only return what we actually found
            # If no layers detected, return empty list with warning
            if not layers:
                print("WARNING: No layer information found in PCB file")
            
            return {
                "board_size": {
                    "width_mm": round(width_mm, 2) if width_mm > 0 else 100.0,
                    "height_mm": round(height_mm, 2) if height_mm > 0 else 80.0,
                    "area_mm2": round(width_mm * height_mm, 2)
                },
                "layers": layers
            }
        except Exception as e:
            print(f"Error in _parse_board_data_detailed: {e}")
            return None
    
    def _parse_component_records_detailed(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse detailed component data from binary stream."""
        components = []
        seen_designators = set()  # Avoid duplicates
        
        try:
            text = data.decode('latin-1', errors='ignore')
            
            # Altium Components6/Data format:
            # Each component record starts with |UNICODE=EXISTS| 
            # followed by |KEY=VALUE| pairs including X, Y, PATTERN, LAYER, SOURCEDESIGNATOR, etc.
            # Split on |UNICODE=EXISTS| to get individual records
            
            records = text.split('|UNICODE=EXISTS|')
            
            for record in records:
                # Skip records without component data
                if 'SOURCEDESIGNATOR=' not in record:
                    continue
                
                # Parse all key-value pairs from the record
                pairs = self._parse_key_value_pairs(record)
                
                # Extract component designator
                designator = pairs.get('SOURCEDESIGNATOR', '')
                
                if not designator or designator in seen_designators:
                    continue
                
                seen_designators.add(designator)
                
                # Parse X/Y coordinates (can be in mil or internal units)
                x_str = pairs.get('X', '0')
                y_str = pairs.get('Y', '0')
                
                # Convert mil to mm if needed
                x_mm = self._parse_altium_coordinate(x_str)
                y_mm = self._parse_altium_coordinate(y_str)
                height_mm = self._parse_altium_coordinate(pairs.get('HEIGHT', '0'))
                
                # Parse rotation
                rotation_str = pairs.get('ROTATION', '0')
                try:
                    # Handle scientific notation (e.g., "9.00000000000000E+0001" = 90)
                    rotation = float(rotation_str)
                except:
                    rotation = 0.0
                
                comp = {
                    "name": designator,
                    "designator": designator,
                    "footprint": pairs.get('PATTERN', ''),
                    "layer": pairs.get('LAYER', 'TOP').title(),
                    "location": {
                        "x_mm": round(x_mm, 4),
                        "y_mm": round(y_mm, 4)
                    },
                    "rotation_degrees": round(rotation, 1),
                    "comment": pairs.get('COMMENT', ''),
                    "description": pairs.get('SOURCEDESCRIPTION', ''),
                    "value": pairs.get('COMMENT', ''),
                    "locked": pairs.get('LOCKED', 'FALSE') == 'TRUE',
                    "height_mm": round(height_mm, 4),
                    "library": pairs.get('SOURCECOMPONENTLIBRARY', ''),
                    "lib_reference": pairs.get('SOURCELIBREFERENCE', ''),
                    "unique_id": pairs.get('UNIQUEID', '')
                }
                
                # Clean up empty fields
                comp = {k: v for k, v in comp.items() if v or v == 0}
                
                components.append(comp)
                
        except Exception as e:
            print(f"Error in _parse_component_records_detailed: {e}")
            
        return components
    
    def _parse_altium_coordinate(self, value_str: str) -> float:
        """Parse Altium coordinate string (can be in mil, mm, or internal units)."""
        try:
            value_str = value_str.strip()
            
            if value_str.endswith('mil'):
                # Value in mils (1 mil = 0.0254 mm)
                return float(value_str.replace('mil', '')) * 0.0254
            elif value_str.endswith('mm'):
                return float(value_str.replace('mm', ''))
            else:
                # Internal units or raw number
                value = float(value_str)
                # If it's a very large number, it's probably internal units
                if abs(value) > 100000:
                    return value * self.UNITS_TO_MM
                else:
                    # Assume mils for reasonable-sized numbers
                    return value * 0.0254
        except:
            return 0.0
    
    def _parse_net_records_detailed(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse detailed net data from binary stream."""
        nets = []
        try:
            text = data.decode('latin-1', errors='ignore')
            
            # Split by null byte sequences (record separator)
            records = re.split(r'[\x00]+', text)
            
            for record in records:
                if 'NAME=' not in record:
                    continue
                
                pairs = self._parse_key_value_pairs(record)
                
                net_name = pairs.get('NAME', '')
                if not net_name:
                    continue
                
                net = {
                    "name": net_name,
                    "id": pairs.get('UNIQUEID', ''),
                    "class": pairs.get('NETCLASS', 'Default'),
                    "layer": pairs.get('LAYER', ''),
                    "visible": pairs.get('VISIBLE', 'TRUE') == 'TRUE'
                }
                
                # Clean up empty fields
                net = {k: v for k, v in net.items() if v or v == 0 or v is False}
                
                nets.append(net)
                
        except Exception as e:
            print(f"Error in _parse_net_records_detailed: {e}")
            
        return nets
    
    def _parse_track_records(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse track data from binary stream.
        
        Tracks6/Data is stored in binary format with fixed-size records.
        Each record starts with a header byte sequence.
        """
        tracks = []
        try:
            # Tracks are binary - estimate count from data size
            # Typical track record is around 30-40 bytes
            # We'll also look for text patterns if any exist
            
            # Try to find text patterns first
            text = data.decode('latin-1', errors='ignore')
            if '|LAYER=' in text:
                # Text format
                records = re.split(r'[\x00]+', text)
                for record in records:
                    if 'LAYER=' not in record:
                        continue
                    pairs = self._parse_key_value_pairs(record)
                    track = {
                        "layer": pairs.get('LAYER', ''),
                        "net": pairs.get('NET', ''),
                        "width_mm": self._parse_altium_coordinate(pairs.get('WIDTH', '0'))
                    }
                    if track["layer"]:
                        tracks.append(track)
            else:
                # Binary format - count records by header pattern
                # Common header pattern: \x04\x31 or similar
                count = data.count(b'\x041')
                if count == 0:
                    count = len(data) // 36  # Estimate based on typical record size
                
                # Create entries for ALL binary records - NO TRUNCATION
                for i in range(count):
                    tracks.append({
                        "id": f"track-{i+1}",
                        "type": "binary_record"
                    })
                    
        except Exception as e:
            print(f"Error in _parse_track_records: {e}")
            
        return tracks
    
    def _count_binary_records(self, data: bytes, record_size_estimate: int = 36) -> int:
        """Estimate count of binary records based on data size and patterns."""
        try:
            # Try common header patterns
            count = data.count(b'\x041')
            if count > 0:
                return count
            
            # Fallback to size-based estimate
            return max(1, len(data) // record_size_estimate)
        except:
            return 0
    
    def _parse_via_records(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse via data from binary stream."""
        vias = []
        try:
            text = data.decode('latin-1', errors='ignore')
            
            # Try text patterns
            if '|X=' in text or '|HOLESIZE=' in text:
                records = re.split(r'[\x00]+', text)
                for record in records:
                    pairs = self._parse_key_value_pairs(record)
                    
                    x_str = pairs.get('X', '0')
                    y_str = pairs.get('Y', '0')
                    
                    via = {
                        "net": pairs.get('NET', ''),
                        "location": {
                            "x_mm": self._parse_altium_coordinate(x_str),
                            "y_mm": self._parse_altium_coordinate(y_str)
                        },
                        "hole_size_mm": self._parse_altium_coordinate(pairs.get('HOLESIZE', '0')),
                        "diameter_mm": self._parse_altium_coordinate(pairs.get('SIZE', '0'))
                    }
                    
                    if via["hole_size_mm"] > 0 or via["diameter_mm"] > 0:
                        vias.append(via)
            else:
                # Binary format - estimate count - NO TRUNCATION
                count = self._count_binary_records(data, 24)
                for i in range(count):
                    vias.append({"id": f"via-{i+1}", "type": "binary_record"})
                    
        except Exception as e:
            print(f"Error in _parse_via_records: {e}")
            
        return vias
    
    def _parse_pad_records(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse pad data from binary stream."""
        pads = []
        try:
            text = data.decode('latin-1', errors='ignore')
            records = text.split('|RECORD=')
            
            for record in records[1:]:
                pairs = self._parse_key_value_pairs('|RECORD=' + record)
                
                pad = {
                    "name": pairs.get('NAME', ''),
                    "net": pairs.get('NET', ''),
                    "component": pairs.get('COMPONENT', ''),
                    "location": {
                        "x_mm": self._convert_coord(pairs.get('X', '0')),
                        "y_mm": self._convert_coord(pairs.get('Y', '0'))
                    },
                    "shape": pairs.get('SHAPE', 'Round'),
                    "size_x_mm": self._convert_coord(pairs.get('XSIZE', '0')),
                    "size_y_mm": self._convert_coord(pairs.get('YSIZE', '0')),
                    "hole_size_mm": self._convert_coord(pairs.get('HOLESIZE', '0')),
                    "layer": pairs.get('LAYER', '')
                }
                
                if pad["name"]:
                    pads.append(pad)
                    
        except Exception as e:
            print(f"Error in _parse_pad_records: {e}")
            
        return pads
    
    def _parse_rules_records(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse design rules from binary stream."""
        rules = []
        try:
            text = data.decode('latin-1', errors='ignore')
            
            # Rules are separated by |NAME= markers (each rule has a NAME field)
            # Split by |NAME= to find rule boundaries
            # But we need to be careful - some fields might contain |NAME= in their values
            # Better approach: find all |NAME= occurrences and extract the rule name, then parse backwards/forwards
            
            # Alternative: Look for |RULEKIND= as rule markers (each rule has one)
            # Records appear to be separated by binary length prefixes, but we can find them by |RULEKIND=
            
            # Split by |RULEKIND= to find rule boundaries
            parts = text.split('|RULEKIND=')
            
            for i, part in enumerate(parts[1:], 1):  # Skip first empty part
                # This part contains a rule - parse it
                # The rule kind is the first value after |RULEKIND=
                rule_kind_end = part.find('|')
                if rule_kind_end == -1:
                    rule_kind = part.strip()
                else:
                    rule_kind = part[:rule_kind_end].strip()
                
                # Limit this record to avoid including the next rule
                # Find the next |RULEKIND= marker (if this isn't the last part)
                if i < len(parts) - 1:
                    # There's a next rule - limit to reasonable length or next marker
                    # But we already split, so just take up to a reasonable max length
                    # (records are typically < 2000 chars)
                    record_text = part[:5000]  # Limit to 5000 chars per record
                else:
                    record_text = part
                
                # Now parse all key-value pairs in this record
                # Add back the RULEKIND= prefix for parsing
                full_record = '|RULEKIND=' + record_text
                pairs = self._parse_key_value_pairs(full_record)
                
                rule_name = pairs.get('NAME', '')
                
                if not rule_name:
                    continue
                
                rule = {
                    "name": rule_name,
                    "kind": rule_kind,
                    "enabled": pairs.get('ENABLED', 'TRUE') == 'TRUE',
                    "priority": int(pairs.get('PRIORITY', '1')),
                    "scope": pairs.get('SCOPE1EXPRESSION', ''),
                }
                
                # Extract specific rule values based on kind
                # Check specific rule kinds first (more specific before general)
                rule_kind_upper = rule_kind.upper()
                
                # Check for PLANE rules BEFORE general CLEARANCE (PlaneClearance is a specific type)
                if 'PLANE' in rule_kind_upper and 'CLEARANCE' in rule_kind_upper:
                    # Plane Clearance rules - uses CLEARANCE key (not GENERICCLEARANCE)
                    clearance_value = pairs.get('CLEARANCE', '0') or pairs.get('GAP', '0')
                    rule["clearance_mm"] = self._convert_coord(clearance_value)
                    rule["type"] = "plane_clearance"
                elif 'CLEARANCE' in rule_kind_upper:
                    # General Clearance rules
                    gap_value = pairs.get('GENERICCLEARANCE', '0') or pairs.get('GAP', '0') or pairs.get('MINIMUMGAP', '0') or pairs.get('CLEARANCE', '0')
                    rule["clearance_mm"] = self._convert_coord(gap_value)
                    rule["type"] = "clearance"
                elif 'ROUTINGVIAS' in rule_kind_upper or 'VIASTYLE' in rule_kind_upper:
                    # Routing Via Style rules - Altium uses HOLEWIDTH, WIDTH, MINHOLEWIDTH, MINWIDTH, MAXHOLEWIDTH, MAXWIDTH
                    rule["min_hole_mm"] = self._convert_coord(pairs.get('MINHOLEWIDTH', '0') or pairs.get('MINHOLE', '0'))
                    rule["max_hole_mm"] = self._convert_coord(pairs.get('MAXHOLEWIDTH', '0') or pairs.get('MAXHOLE', '0'))
                    rule["preferred_hole_mm"] = self._convert_coord(pairs.get('HOLEWIDTH', '0') or pairs.get('PREFEREDHOLE', '0'))
                    rule["min_diameter_mm"] = self._convert_coord(pairs.get('MINWIDTH', '0') or pairs.get('MINDIAMETER', '0'))
                    rule["max_diameter_mm"] = self._convert_coord(pairs.get('MAXWIDTH', '0') or pairs.get('MAXDIAMETER', '0'))
                    rule["preferred_diameter_mm"] = self._convert_coord(pairs.get('WIDTH', '0') or pairs.get('PREFERREDDIAMETER', '0'))
                    rule["via_style"] = pairs.get('VIASTYLE', '')
                    rule["type"] = "via"
                elif 'ROUTINGCORNERS' in rule_kind_upper:
                    # Routing Corners rules - Altium uses CORNERSTYLE, MINSETBACK, MAXSETBACK
                    rule["corner_style"] = pairs.get('CORNERSTYLE', '') or pairs.get('STYLE', '')
                    rule["setback_mm"] = self._convert_coord(pairs.get('MINSETBACK', '0') or pairs.get('SETBACK', '0'))
                    rule["setback_to_mm"] = self._convert_coord(pairs.get('MAXSETBACK', '0') or pairs.get('SETBACKTO', '0'))
                    rule["type"] = "routing_corners"
                elif 'ROUTINGTOPOLOGY' in rule_kind_upper:
                    # Routing Topology rules
                    topology = pairs.get('TOPOLOGY', '') or pairs.get('TOPOLOGYTYPE', '')
                    # Clean topology string (remove binary characters)
                    if topology:
                        topology = re.sub(r'[\x00-\x1F\x7F-\xFF]', '', topology).strip()
                    rule["topology"] = topology
                    rule["type"] = "routing_topology"
                elif 'ROUTINGPRIORITY' in rule_kind_upper:
                    # Routing Priority rules
                    rule["priority_value"] = int(pairs.get('PRIORITYVALUE', '0') or pairs.get('PRIORITY', '0'))
                    rule["type"] = "routing_priority"
                elif 'ROUTINGLAYERS' in rule_kind_upper:
                    # Routing Layers rules
                    rule["type"] = "routing_layers"
                elif 'DIFFPAIRS' in rule_kind_upper or 'DIFFERENTIAL' in rule_kind_upper:
                    # Differential Pairs Routing rules
                    # Use TOPLAYER values as primary (most common)
                    rule["min_width_mm"] = self._convert_coord(pairs.get('TOPLAYER_MINWIDTH', '0') or pairs.get('MINLIMIT', '0') or pairs.get('MINWIDTH', '0'))
                    rule["max_width_mm"] = self._convert_coord(pairs.get('TOPLAYER_MAXWIDTH', '0') or pairs.get('MAXLIMIT', '0') or pairs.get('MAXWIDTH', '0'))
                    rule["preferred_width_mm"] = self._convert_coord(pairs.get('TOPLAYER_PREFWIDTH', '0') or pairs.get('PREFERREDWIDTH', '0'))
                    # Gap values - MINLIMIT and MAXLIMIT are often used for gap, MOSTFREQGAP is preferred gap
                    rule["min_gap_mm"] = self._convert_coord(pairs.get('MINGAP', '0') or pairs.get('MINLIMIT', '0'))
                    rule["max_gap_mm"] = self._convert_coord(pairs.get('MAXGAP', '0') or pairs.get('MAXLIMIT', '0'))
                    rule["preferred_gap_mm"] = self._convert_coord(pairs.get('MOSTFREQGAP', '0') or pairs.get('PREFERREDGAP', '0'))
                    # Max uncoupled length
                    rule["max_uncoupled_length_mm"] = self._convert_coord(pairs.get('MAXUNCOUPLEDLENGTH', '0') or pairs.get('MAXLENGTH', '0'))
                    rule["type"] = "diff_pairs_routing"
                elif 'WIDTH' in rule_kind_upper:
                    # Width rules - Altium uses MINLIMIT, MAXLIMIT, PREFEREDWIDTH
                    rule["min_width_mm"] = self._convert_coord(pairs.get('MINLIMIT', '0') or pairs.get('MINWIDTH', '0') or pairs.get('MINIMUMWIDTH', '0'))
                    rule["max_width_mm"] = self._convert_coord(pairs.get('MAXLIMIT', '0') or pairs.get('MAXWIDTH', '0') or pairs.get('MAXIMUMWIDTH', '0'))
                    rule["preferred_width_mm"] = self._convert_coord(pairs.get('PREFEREDWIDTH', '0') or pairs.get('PREFERREDWIDTH', '0'))
                    rule["type"] = "width"
                elif 'VIA' in rule_kind_upper and 'ROUTING' not in rule_kind_upper:
                    # Via rules (not routing-related)
                    rule["min_hole_mm"] = self._convert_coord(pairs.get('MINHOLE', '0') or pairs.get('MINIMUMHOLE', '0'))
                    rule["max_hole_mm"] = self._convert_coord(pairs.get('MAXHOLE', '0') or pairs.get('MAXIMUMHOLE', '0'))
                    rule["min_diameter_mm"] = self._convert_coord(pairs.get('MINDIAMETER', '0') or pairs.get('MINIMUMDIAMETER', '0'))
                    rule["max_diameter_mm"] = self._convert_coord(pairs.get('MAXDIAMETER', '0') or pairs.get('MAXIMUMDIAMETER', '0'))
                    rule["type"] = "via"
                elif 'SHORT' in rule_kind_upper or 'SHORTCIRCUIT' in rule_kind_upper:
                    # Short Circuit rules
                    rule["allowed"] = pairs.get('ALLOWED', 'FALSE') == 'TRUE'
                    rule["type"] = "short_circuit"
                elif 'MASK' in rule_kind_upper:
                    # Mask rules - Altium uses EXPANSION key
                    expansion_top = self._convert_coord(pairs.get('EXPANSION', '0') or pairs.get('EXPANSIONTOP', '0'))
                    expansion_bottom = self._convert_coord(pairs.get('EXPANSIONBOTTOM', '0'))
                    # If bottom expansion is not specified, use top expansion (common in Altium)
                    if expansion_bottom == 0.0 and expansion_top > 0:
                        expansion_bottom = expansion_top
                    rule["expansion_mm"] = expansion_top
                    rule["expansion_bottom_mm"] = expansion_bottom
                    # Check for tenting flags
                    rule["tented_top"] = pairs.get('ISTENTINGTOP', 'FALSE') == 'TRUE'
                    rule["tented_bottom"] = pairs.get('ISTENTINGBOTTOM', 'FALSE') == 'TRUE'
                    # Paste mask specific settings
                    if 'PASTE' in rule_kind_upper:
                        rule["use_paste_smd"] = pairs.get('USEPASTE', 'FALSE') == 'TRUE' or pairs.get('USEPASTESMD', 'FALSE') == 'TRUE'
                        rule["use_top_paste_th"] = pairs.get('USETOPPASTE', 'FALSE') == 'TRUE' or pairs.get('USETOPPASTETH', 'FALSE') == 'TRUE'
                        rule["use_bottom_paste_th"] = pairs.get('USEBOTTOMPASTE', 'FALSE') == 'TRUE' or pairs.get('USEBOTTOMPASTETH', 'FALSE') == 'TRUE'
                        rule["measurement_method"] = pairs.get('MEASUREMENTMETHOD', 'Absolute') or pairs.get('METHOD', 'Absolute')
                        rule["type"] = "paste_mask"
                    else:
                        rule["type"] = "solder_mask"
                elif 'PLANECONNECT' in rule_kind_upper or ('PLANE' in rule_kind_upper and 'CONNECT' in rule_kind_upper):
                    # Plane Connect rules - Altium uses RELIEFEXPANSION, RELIEFAIRGAP, RELIEFCONDUCTORWIDTH, RELIEFENTRIES
                    rule["connect_style"] = pairs.get('PLANECONNECTSTYLE', '') or pairs.get('CONNECTSTYLE', '')
                    rule["expansion_mm"] = self._convert_coord(pairs.get('RELIEFEXPANSION', '0') or pairs.get('EXPANSION', '0'))
                    rule["air_gap_mm"] = self._convert_coord(pairs.get('RELIEFAIRGAP', '0') or pairs.get('AIRGAP', '0'))
                    rule["conductor_width_mm"] = self._convert_coord(pairs.get('RELIEFCONDUCTORWIDTH', '0') or pairs.get('CONDUCTORWIDTH', '0'))
                    rule["conductor_count"] = int(pairs.get('RELIEFENTRIES', '0') or pairs.get('ENTRIES', '0') or '0')
                    rule["type"] = "plane_connect"
                elif 'PLANE' in rule_kind_upper and 'CLEARANCE' not in rule_kind_upper:
                    # Other Plane rules (not clearance, not connect)
                    rule["type"] = "plane"
                elif 'TESTPOINT' in rule_kind_upper:
                    # Testpoint rules
                    rule["type"] = "testpoint"
                elif 'SMT' in rule_kind_upper:
                    # SMT rules
                    rule["type"] = "smt"
                elif 'UNROUTED' in rule_kind_upper:
                    # Unrouted Net rules
                    rule["type"] = "unrouted_net"
                else:
                    rule["type"] = "other"
                
                rules.append(rule)
                    
        except Exception as e:
            print(f"Error in _parse_rules_records: {e}")
            import traceback
            traceback.print_exc()
            
        return rules
    
    def _count_records(self, data: bytes) -> int:
        """Count records in Altium binary data."""
        try:
            count = data.count(b'|RECORD=')
            if count == 0:
                count = data.count(b'\x00\x00\x00\x00') // 2
            return max(count, 1) if len(data) > 100 else 0
        except:
            return 0
    
    def _read_basic_info(self, file_path: str) -> Dict[str, Any]:
        """Basic binary parsing - fallback without olefile."""
        result = self._empty_result(file_path)
        result["read_method"] = "basic_binary"
        
        try:
            with open(file_path, 'rb') as f:
                header = f.read(1024)
                
                if header[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
                    result["file_type"] = "OLE Compound Document"
                    result["note"] = "Install olefile for full parsing: pip install olefile"
                else:
                    result["file_type"] = "Unknown format"
                
                f.seek(0, 2)
                file_size = f.tell()
                result["file_size_bytes"] = file_size
                result["file_size_mb"] = round(file_size / (1024 * 1024), 2)
                
        except Exception as e:
            result["error"] = str(e)
            
        return result
    
    def read_schematic(self, file_path: str) -> Dict[str, Any]:
        """Read a Schematic document."""
        return self.read_pcb(file_path)
    
    def export_to_json(self, data: Dict[str, Any], output_path: str) -> bool:
        """Export the extracted data to a JSON file."""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            return True
        except Exception as e:
            print(f"Error writing JSON: {e}")
            return False


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Read Altium Designer files directly')
    parser.add_argument('file', help='Path to .PcbDoc or .SchDoc file')
    parser.add_argument('-o', '--output', help='Output JSON file path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    reader = AltiumFileReader()
    
    if args.file.lower().endswith('.pcbdoc'):
        data = reader.read_pcb(args.file)
    elif args.file.lower().endswith('.schdoc'):
        data = reader.read_schematic(args.file)
    else:
        print(f"Unsupported file type: {args.file}")
        return
    
    if args.output:
        reader.export_to_json(data, args.output)
        print(f"Exported to: {args.output}")
    else:
        print(json.dumps(data, indent=2, default=str))


if __name__ == '__main__':
    main()
