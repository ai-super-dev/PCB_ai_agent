# Python DRC Validation Engine Documentation

## Overview

The Python DRC (Design Rule Check) validation engine performs comprehensive design rule checking on PCB designs without requiring Altium Designer. It analyzes PCB geometry data and design rules to detect violations and manufacturing issues.

## Architecture

### Components

1. **PythonDRCEngine** (`runtime/drc/python_drc_engine.py`)
   - Main DRC engine class
   - Performs all rule checks
   - Returns violations and warnings

2. **DRCRule** (Data Class)
   - Represents a design rule with all parameters
   - Supports all rule types

3. **DRCViolation** (Data Class)
   - Represents a detected violation
   - Contains location, severity, and details

### Data Flow

```
PCB File (.PcbDoc)
    ↓
AltiumFileReader (extracts data)
    ↓
PCB Data (tracks, vias, pads, nets, components, rules)
    ↓
PythonDRCEngine.run_drc()
    ↓
Violations & Warnings
    ↓
Formatted Report (Altium-style)
```

## Supported Design Rules

The Python DRC engine supports the following design rule types:

### 1. Clearance Constraint

**Purpose:** Ensures minimum spacing between objects on different nets.

**Parameters:**
- `clearance_mm`: Minimum clearance distance (mm)
- `scope1`: First scope (e.g., "All", polygon name)
- `scope2`: Second scope (e.g., "All")
- `scope1_polygon`: Optional named polygon for scope1

**Checks Performed:**
- Pad-to-pad clearance (different nets)
- Via-to-pad clearance (different nets)
- Edge-to-edge distance calculation

**Example:**
```python
{
    "name": "Clearance Constraint",
    "type": "clearance",
    "clearance_mm": 0.2,
    "scope1": "All",
    "scope2": "All"
}
```

**Altium Format:** `Clearance Constraint (Gap=0.2mm) (All),(All)`

---

### 2. Width Constraint

**Purpose:** Validates track widths are within specified limits.

**Parameters:**
- `min_width_mm`: Minimum track width (mm)
- `max_width_mm`: Maximum track width (mm)
- `preferred_width_mm`: Preferred track width (mm)

**Checks Performed:**
- All tracks checked against min/max width
- Violations reported if width < min or width > max

**Example:**
```python
{
    "name": "Width Constraint",
    "type": "width",
    "min_width_mm": 0.254,
    "max_width_mm": 15.0,
    "preferred_width_mm": 0.838
}
```

**Altium Format:** `Width Constraint (Min=0.254mm) (Max=15mm) (Preferred=0.838mm) (All)`

---

### 3. Via / Hole Size Constraint

**Purpose:** Validates via and pad hole sizes.

**Parameters:**
- `min_hole_mm`: Minimum hole diameter (mm)
- `max_hole_mm`: Maximum hole diameter (mm)

**Checks Performed:**
- Via hole sizes
- Pad hole sizes (through-hole components)
- Violations if hole < min or hole > max

**Example:**
```python
{
    "name": "Hole Size Constraint",
    "type": "hole_size",
    "min_hole_mm": 0.025,
    "max_hole_mm": 5.0
}
```

**Altium Format:** `Hole Size Constraint (Min=0.025mm) (Max=5mm) (All)`

---

### 4. Short-Circuit Constraint

**Purpose:** Detects overlapping objects on different nets.

**Parameters:**
- `allowed`: Whether short circuits are allowed (typically False)

**Checks Performed:**
- Pad-to-pad overlaps (different nets)
- Detects when pad edges overlap

**Example:**
```python
{
    "name": "Short-Circuit Constraint",
    "type": "short_circuit",
    "allowed": False
}
```

**Altium Format:** `Short-Circuit Constraint (Allowed=No) (All),(All)`

---

### 5. Un-Routed Net Constraint

**Purpose:** Identifies nets that have pads but no routing tracks.

**Parameters:**
- `enabled`: Whether to check unrouted nets

**Checks Performed:**
- Nets with 2+ pads but no tracks
- Skips single-pad nets (test points, mounting holes)
- Power/ground nets flagged as errors (others as warnings)

**Logic:**
1. Collect all nets with tracks
2. Collect all nets with pads/vias
3. Count pads per net
4. Flag nets with 2+ pads but no tracks

**Example:**
```python
{
    "name": "Un-Routed Net Constraint",
    "type": "unrouted_net",
    "enabled": True
}
```

**Altium Format:** `Un-Routed Net Constraint ((All))`

**Note:** This check does NOT consider polygon pours or power planes, as that data is not available in the extracted PCB data.

---

### 6. Hole To Hole Clearance

**Purpose:** Ensures minimum spacing between drill holes.

**Parameters:**
- `gap_mm`: Minimum clearance between hole edges (mm)

**Checks Performed:**
- Via-to-via hole clearance
- Edge-to-edge distance between holes

**Example:**
```python
{
    "name": "Hole To Hole Clearance",
    "type": "hole_to_hole_clearance",
    "gap_mm": 0.254
}
```

**Altium Format:** `Hole To Hole Clearance (Gap=0.254mm) (All).(All)`

---

### 7. Minimum Solder Mask Sliver

**Purpose:** Detects gaps in solder mask that are too small.

**Parameters:**
- `gap_mm`: Minimum solder mask gap (mm)

**Checks Performed:**
- Pad-to-pad spacing for potential slivers
- Simplified check (full implementation requires solder mask geometry)

**Example:**
```python
{
    "name": "Minimum Solder Mask Sliver",
    "type": "solder_mask_sliver",
    "gap_mm": 0.06
}
```

**Altium Format:** `Minimum Solder Mask Sliver (Gap=0.06mm) (All),(All)`

---

### 8. Silk To Solder Mask

**Purpose:** Checks clearance between silk screen and solder mask.

**Parameters:**
- `clearance_mm`: Minimum clearance (mm)

**Status:** Currently disabled - requires actual silk screen geometry data which is not available in extracted PCB data.

**Note:** Altium only checks this when clearance > 0. With 0mm clearance, overlap is allowed.

**Example:**
```python
{
    "name": "Silk To Solder Mask",
    "type": "silk_to_solder_mask",
    "clearance_mm": 0.0
}
```

**Altium Format:** `Silk To Solder Mask (Clearance=0mm) (IsPad). (All)`

---

### 9. Silk to Silk

**Purpose:** Checks clearance between silk screen elements.

**Parameters:**
- `clearance_mm`: Minimum clearance between silk screen elements (mm)

**Status:** Currently disabled - requires actual silk screen geometry data which is not available in extracted PCB data.

**Note:** Altium only checks this when clearance > 0. With 0mm clearance, overlap is allowed.

**Example:**
```python
{
    "name": "Silk to Silk",
    "type": "silk_to_silk",
    "clearance_mm": 0.0
}
```

**Altium Format:** `Silk to Silk (Clearance=0mm) (All),(All).`

---

### 10. Height Constraint

**Purpose:** Validates component heights are within limits.

**Parameters:**
- `min_height_mm`: Minimum component height (mm)
- `max_height_mm`: Maximum component height (mm)
- `preferred_height_mm`: Preferred component height (mm)

**Checks Performed:**
- Component height from PCB data
- Violations if height < min or height > max

**Example:**
```python
{
    "name": "Height Constraint",
    "type": "height",
    "min_height_mm": 0.0,
    "max_height_mm": 25.4,
    "preferred_height_mm": 12.7
}
```

**Altium Format:** `Height Constraint (Min=0mm) (Max=25.4mm) (Preferred=12.7mm) (All).`

---

### 11. Modified Polygon

**Purpose:** Checks for modified or shelved polygons.

**Parameters:**
- `allow_modified`: Whether modified polygons are allowed
- `allow_shelved`: Whether shelved polygons are allowed

**Checks Performed:**
- Detects polygons marked as modified
- Detects polygons marked as shelved

**Example:**
```python
{
    "name": "Modified Polygon",
    "type": "modified_polygon",
    "allow_modified": False,
    "allow_shelved": False
}
```

**Altium Format:** `Modified Polygon (Allow modified: No), (Allow shelved: No)`

---

### 12. Net Antennae

**Purpose:** Detects stub traces (net antennae).

**Parameters:**
- `tolerance_mm`: Tolerance for antenna detection (mm)

**Status:** Placeholder - full implementation requires complete net topology analysis.

**Example:**
```python
{
    "name": "Net Antennae",
    "type": "net_antennae",
    "tolerance_mm": 0.0
}
```

**Altium Format:** `Net Antennae (Tolerance=0mm) (All)`

---

### 13. Power Plane Connect Rule

**Purpose:** Defines how components connect to power planes.

**Parameters:**
- `connect_style`: Connection style (e.g., "Relief Connect")
- `expansion_mm`: Relief expansion (mm)
- `conductor_width_mm`: Conductor width (mm)
- `air_gap_mm`: Air gap (mm)
- `conductor_count`: Number of conductors (entries)

**Status:** Rule definition supported, but validation logic not yet implemented.

**Example:**
```python
{
    "name": "Power Plane Connect Rule",
    "type": "plane_connect",
    "connect_style": "Relief Connect",
    "expansion_mm": 0.508,
    "conductor_width_mm": 0.254,
    "air_gap_mm": 0.254,
    "conductor_count": 4
}
```

**Altium Format:** `Power Plane Connect Rule (Relief Connect) (Expansion=0.508mm) (Conductor Width=0.254mm) (Air Gap=0.254mm) (Entries=4) (All)`

---

## Validation Logic Details

### Clearance Checking

**Algorithm:**
1. For each pad, calculate its effective radius (size_x/2 or size_y/2, whichever is larger)
2. For each other pad on a different net:
   - Calculate center-to-center distance
   - Calculate edge-to-edge clearance: `distance - radius1 - radius2`
   - If clearance < minimum: report violation
3. Repeat for via-to-pad pairs

**Mathematical Formula:**
```
clearance = sqrt((x2 - x1)² + (y2 - y1)²) - radius1 - radius2
```

**Edge Cases Handled:**
- Same net pads (skipped)
- Zero coordinates (skipped)
- Missing location data (handled gracefully)

---

### Width Checking

**Algorithm:**
1. Iterate through all tracks
2. For each track:
   - Get track width
   - Compare with min_width_mm and max_width_mm
   - Report violation if outside range

**Edge Cases:**
- Tracks with width = 0 (skipped)
- Missing width data (skipped)

---

### Unrouted Net Detection

**Algorithm:**
1. Collect all nets that have tracks → `nets_with_tracks`
2. Collect all nets that have pads/vias → `nets_with_pads`
3. Count pads per net → `pad_count_per_net`
4. For each net in PCB:
   - Skip if net has tracks (it's routed)
   - Skip if single pad (test point, mounting hole)
   - Skip if no pads/vias (orphaned net definition)
   - Flag if 2+ pads but no tracks

**Why This Logic:**
- Altium doesn't flag single-pad nets (they're typically test points)
- Polygon pours and power planes aren't detectable from track data alone
- Only multi-pad nets without routing are considered violations

---

### Short-Circuit Detection

**Algorithm:**
1. For each pad pair on different nets:
   - Calculate center-to-center distance
   - Calculate combined radius (radius1 + radius2)
   - If distance < combined_radius: pads overlap → short circuit

**Mathematical Formula:**
```
overlap = (radius1 + radius2) - sqrt((x2 - x1)² + (y2 - y1)²)
if overlap > 0: short circuit detected
```

---

## Limitations

### Data Availability

The Python DRC engine works with data extracted from Altium PCB files. Some limitations:

1. **No Polygon/Pour Data**
   - Cannot detect connections via copper pours
   - Unrouted net check may flag nets connected via polygons
   - Power/ground plane connections not detectable

2. **No Silk Screen Geometry**
   - Silk-to-silk checks disabled (no geometry data)
   - Silk-to-solder-mask checks disabled

3. **No Complete Net Topology**
   - Net antennae detection not fully implemented
   - Cannot detect all connectivity paths

4. **Binary Track Data**
   - Some track records are in binary format
   - Net associations may not be fully reliable

### Rule Coverage

**Fully Implemented:**
- ✅ Clearance constraints
- ✅ Width constraints
- ✅ Via/hole size constraints
- ✅ Short-circuit detection
- ✅ Unrouted net detection (with limitations)
- ✅ Hole-to-hole clearance
- ✅ Solder mask sliver (simplified)
- ✅ Height constraints
- ✅ Modified polygon detection

**Partially Implemented:**
- ⚠️ Solder mask sliver (simplified check)
- ⚠️ Net antennae (placeholder)

**Not Implemented:**
- ❌ Silk-to-silk (no geometry data)
- ❌ Silk-to-solder-mask (no geometry data)
- ❌ Power plane connect validation
- ❌ Differential pair routing
- ❌ Routing topology
- ❌ Via style constraints
- ❌ Routing corners
- ❌ Routing layers
- ❌ Routing priority

---

## Rule Format

### Input Format

Rules are provided as a list of dictionaries:

```python
rules = [
    {
        "name": "Clearance Constraint",
        "type": "clearance",  # or "kind": "Clearance"
        "clearance_mm": 0.2,
        "scope1": "All",
        "scope2": "All",
        "enabled": True,
        "priority": 1
    },
    # ... more rules
]
```

### Rule Type Normalization

The engine normalizes rule types from Altium's format:

- `"Clearance"` → `"clearance"`
- `"Width"` → `"width"`
- `"RoutingViaStyle"` → `"via"`
- `"ShortCircuit"` → `"short_circuit"`
- `"UnRoutedNet"` → `"unrouted_net"`
- etc.

---

## Usage Example

```python
from runtime.drc.python_drc_engine import PythonDRCEngine

# Prepare PCB data
pcb_data = {
    "tracks": [...],  # List of track dicts
    "vias": [...],    # List of via dicts
    "pads": [...],    # List of pad dicts
    "nets": [...],    # List of net dicts
    "components": [...],  # List of component dicts
    "polygons": [...]     # List of polygon dicts
}

# Prepare rules
rules = [
    {
        "name": "Clearance Constraint",
        "type": "clearance",
        "clearance_mm": 0.2,
        "enabled": True
    },
    # ... more rules
]

# Run DRC
engine = PythonDRCEngine()
result = engine.run_drc(pcb_data, rules)

# Access results
summary = result["summary"]
violations = result["violations"]
warnings = result["warnings"]
```

---

## Output Format

### Summary

```python
{
    "warnings": 0,
    "rule_violations": 0,
    "total": 0,
    "passed": True
}
```

### Violations

```python
[
    {
        "rule_name": "Clearance Constraint",
        "type": "clearance",
        "severity": "error",
        "message": "Clearance violation: 0.15mm < 0.2mm between pads",
        "location": {"x_mm": 10.5, "y_mm": 20.3},
        "actual_value": 0.15,
        "required_value": 0.2,
        "objects": ["pad1", "pad2"],
        "net_name": None,
        "component_name": None
    }
]
```

---

## Comparison with Altium DRC

### Similarities

- ✅ Same rule types and parameters
- ✅ Same violation detection logic (where implemented)
- ✅ Same report format
- ✅ Same severity levels (error/warning)

### Differences

- ⚠️ Cannot detect polygon/pour connections
- ⚠️ Cannot check silk screen geometry
- ⚠️ Some advanced rules not implemented
- ⚠️ May have false positives for unrouted nets (due to polygon connections)

### Accuracy

For rules that are fully implemented:
- **Clearance:** High accuracy (geometric calculation)
- **Width:** High accuracy (direct measurement)
- **Hole Size:** High accuracy (direct measurement)
- **Short-Circuit:** High accuracy (geometric overlap)
- **Unrouted Net:** Medium accuracy (may miss polygon connections)
- **Height:** High accuracy (if component height data available)

---

## Future Enhancements

### Planned Improvements

1. **Polygon/Pour Detection**
   - Extract polygon data from PCB
   - Consider polygon connections in unrouted net check
   - Detect power/ground plane connections

2. **Silk Screen Support**
   - Extract silk screen geometry
   - Enable silk-to-silk checks
   - Enable silk-to-solder-mask checks

3. **Advanced Rules**
   - Differential pair routing
   - Routing topology validation
   - Via style constraints
   - Routing corners

4. **Performance Optimization**
   - Spatial indexing for faster clearance checks
   - Parallel processing for large boards

---

## Troubleshooting

### Common Issues

**Issue:** Too many false violations
- **Solution:** Check if rules are correctly extracted from PCB
- **Solution:** Verify rule parameters match Altium settings

**Issue:** Missing violations
- **Solution:** Ensure all PCB data is extracted (not truncated)
- **Solution:** Check if rule is enabled

**Issue:** Unrouted net false positives
- **Solution:** This is expected - polygon connections not detectable
- **Solution:** Manually verify nets connected via polygons

---

## References

- Altium Designer Design Rules Documentation
- IPC Standards for PCB Design
- Python DRC Engine Source: `runtime/drc/python_drc_engine.py`
- PCB Data Reader: `tools/altium_file_reader.py`

---

## Version History

- **v1.0** (Current)
  - Initial implementation
  - Core rule types supported
  - Basic geometric checks

---

*Last Updated: 2026-02-10*
