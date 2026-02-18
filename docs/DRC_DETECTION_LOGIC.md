# Python DRC Engine - Violation Detection Logic

This document explains how each type of DRC violation is detected by the Python DRC engine.

---

## 1. Clearance Violations

**Rule Type:** `clearance`

**Purpose:** Ensures minimum spacing between copper objects on different nets.

### Detection Algorithm:

#### **Track-to-Pad Clearance**
1. **Filter tracks:** Only check tracks on signal/copper layers (skip overlay, mechanical, solder mask)
2. **Filter pads:** Skip pads on same net as track (no clearance needed)
3. **Layer compatibility:** Only check if track and pad can connect (same layer or Multi Layer pad)
4. **Distance calculation:**
   - Calculate distance from pad center to track line segment
   - `clearance = distance_to_line - track_radius - pad_radius`
   - If `clearance < min_clearance` → violation
5. **Special handling:**
   - Skip fanout tracks (tracks connecting to component pads) from same component
   - Skip components that have specific clearance rules (e.g., BGA, SOIC) when checking general rules

#### **Track-to-Track Clearance**
1. **Filter:** Only tracks on signal layers, different nets, same layer
2. **Distance calculation:**
   - Calculate minimum distance between two line segments
   - Account for track widths (half-width on each side)
   - `clearance = min_distance - track1_radius - track2_radius`
   - If `clearance < min_clearance` → violation

#### **Track-to-Via Clearance**
1. **Filter:** Track and via on different nets, compatible layers
2. **Distance calculation:**
   - Calculate distance from track line segment to via center
   - `clearance = distance_to_line - track_radius - via_radius`
   - If `clearance < min_clearance` → violation

#### **Via-to-Pad Clearance**
1. **Filter:** Via and pad on different nets, compatible layers
2. **Distance calculation:**
   - Calculate center-to-center distance
   - `clearance = center_distance - via_radius - pad_radius`
   - If `clearance < min_clearance` → violation

#### **Via-to-Via Clearance**
1. **Filter:** Vias on different nets, compatible layers
2. **Distance calculation:**
   - Calculate center-to-center distance
   - `clearance = center_distance - via1_radius - via2_radius`
   - If `clearance < min_clearance` → violation

#### **Pad-to-Pad Clearance**
1. **Filter:** Pads on different nets, same layer (or Multi Layer pads)
2. **Distance calculation:**
   - Calculate center-to-center distance
   - `clearance = center_distance - pad1_radius - pad2_radius`
   - If `clearance < min_clearance` → violation
3. **Special handling:** Only checked under `ComponentClearance` rule (not general clearance rules)

#### **Scope Filtering (InNamedPolygon)**
- If rule scope is `InNamedPolygon('Name')`, only check objects within that polygon
- Extract polygon name from scope expression
- Filter pads/tracks/vias to only those inside the specified polygon(s)
- This enables rules like `KZBZHUANYONG` and `LBBZHUANYONG`

#### **Disabled Checks:**
- **Track-to-Polygon/Copper:** Disabled because exported copper regions are bounding boxes, not actual poured copper with relief cutouts
- **Pad-to-Polygon/Copper:** Disabled for same reason (would produce false positives)

---

## 2. Short-Circuit Violations

**Rule Type:** `short_circuit`

**Purpose:** Detects overlapping copper objects on different nets (actual copper overlap, not just proximity).

### Detection Algorithm:

#### **Pad-to-Pad Short-Circuit**
1. **Filter:** Pads on different nets, same layer (or Multi Layer pads)
2. **Overlap detection:**
   - Calculate bounding boxes for both pads
   - Check if bounding boxes overlap:
     - X overlap: `pad1_right > pad2_left AND pad2_right > pad1_left`
     - Y overlap: `pad1_top > pad2_bottom AND pad2_top > pad1_bottom`
   - If both X and Y overlap → short-circuit violation
3. **Critical:** Only flags actual geometric overlap, not just close proximity

#### **Via-to-Pad Short-Circuit**
1. **Filter:** Via and pad on different nets, compatible layers
2. **Overlap detection:**
   - Calculate center-to-center distance
   - If `distance < via_radius + pad_radius` → short-circuit violation

#### **Via-to-Via Short-Circuit**
1. **Filter:** Vias on different nets, compatible layers
2. **Overlap detection:**
   - Calculate center-to-center distance
   - If `distance < via1_radius + via2_radius` → short-circuit violation

#### **Disabled Checks:**
- **Pad-to-Polygon Short-Circuit:** Disabled because exported copper regions are bounding boxes, not actual poured copper with relief cutouts

---

## 3. Width Violations

**Rule Type:** `width`

**Purpose:** Ensures track widths are within specified min/max range.

### Detection Algorithm:

1. **Filter tracks:** Only check tracks on signal/copper layers
2. **Validate width data:**
   - Skip if no width data available
   - Check for binary parsing errors: if >10% of tracks have widths > max_width, data is unreliable → skip check
3. **Width validation:**
   - For each track with valid width:
     - If `width < min_width` → violation
     - If `width > max_width` → violation
   - **Note:** Preferred width is NOT checked (it's just a preference, not a constraint)

---

## 4. Unrouted Net Violations

**Rule Type:** `unrouted_net`

**Purpose:** Detects nets that have pads but no complete routing path between them.

### Detection Algorithm:

#### **MODE 1: Connection-Based (Preferred)**
Uses Altium's `eConnectionObject` data (ratsnest lines).

1. **Connection objects:**
   - Connection objects = ratsnest lines = pad pairs that SHOULD be connected but have NO copper path
   - Altium removes connection objects when routing is complete (tracks, vias, planes all counted)
   - Remaining connection objects = unrouted connections

2. **Processing:**
   - Group connections by net name
   - For each net with connections:
     - **Check plane layer assignment:** If net is assigned to internal plane layer → skip (all pads connected via plane)
     - **Report violation:** If net has connection objects and is not on a plane → unrouted net violation

3. **Key insight:** Trust Altium's connection objects. If they exist, the net is unrouted (unless on a plane).

#### **MODE 2: Fallback (If connections not exported)**
Builds connectivity graph using Union-Find algorithm.

1. **Build connectivity graph:**
   - Create nodes for all pads, vias, track endpoints
   - Connect nodes that are physically connected:
     - Pads on same component and same net (component internal connection)
     - Pads to vias (if layers compatible)
     - Track endpoints to pads/vias (if within tolerance)
     - Track endpoints to other track endpoints (T-junctions, overlaps)
     - Track endpoints to polygon pours (if within polygon)
     - Vias to vias (if overlapping)

2. **Check connectivity:**
   - For each net:
     - Get all pads for that net
     - Check if all pads are in the same connected component (using Union-Find)
     - If pads are in different components → unrouted net violation

3. **Tolerance:**
   - `CONNECTION_TOLERANCE = 1.0mm` (accounts for coordinate rounding)
   - Pad connection: circular distance check with 0.8mm tolerance
   - Track-to-track: accounts for track width and T-junctions

#### **Special Cases:**
- **Single-pad nets:** Skipped (test points, mounting holes)
- **Plane layer nets:** Skipped (all pads automatically connected via plane)
- **Empty connections list:** If `connections = []` (exported but empty), all nets are fully routed → return 0 violations

---

## 5. Net Antennae Violations

**Rule Type:** `net_antennae`

**Purpose:** Detects tracks with floating (unconnected) endpoints (dead-end stubs).

### Detection Algorithm:

1. **Filter nets:**
   - Only check nets that have unrouted connections (from ratsnest data)
   - If all nets are fully routed (`connections = []`), no antennae possible → return 0 violations

2. **Collect connection data:**
   - Pads: (x, y, half_radius) - uses `max(size_x, size_y)/2` for rotation-safe radius
   - Vias: (x, y, radius)
   - Polygon pours: (net, layer, vertices) - for connectivity check
   - Fills: (x1, y1, x2, y2, net, layer) - copper rectangles
   - Arcs: endpoints with half-width

3. **Check each track endpoint:**
   - For each track on a net with unrouted connections:
     - Check both endpoints (start and end)
     - For each endpoint:
       - **Connection tolerance:** `CONN_TOL = track_half_width` (adaptive, not hard-coded)
       - Check if endpoint connects to:
         - Pad: `distance <= pad_radius + CONN_TOL`
         - Via: `distance <= via_radius + CONN_TOL`
         - Another track endpoint (T-junction): `distance <= track1_half_width + track2_half_width + CONN_TOL`
         - Track body (overlap): Check if endpoint is within another track's body (considering width)
         - Polygon pour: Check if endpoint is within polygon on same net
         - Fill: Check if endpoint is within fill rectangle on same net
         - Arc endpoint: Check if endpoint connects to arc endpoint
     - If BOTH endpoints are connected → track is OK
     - If ONE endpoint is unconnected → Net Antennae violation

4. **Key features:**
   - Only checks tracks on nets with incomplete routing
   - Uses adaptive tolerance based on track width
   - Accounts for T-junctions and track overlaps
   - Considers polygon pours, fills, and arcs

---

## 6. Hole Size Violations

**Rule Type:** `hole_size` or `via`

**Purpose:** Ensures via and pad hole sizes are within specified min/max range.

### Detection Algorithm:

1. **Check vias:**
   - For each via:
     - Get hole size from `hole_size_mm`
     - If `hole_size < min_hole` → violation
     - If `hole_size > max_hole` → violation

2. **Check pads:**
   - For each pad:
     - Get hole size from `hole_size_mm` (for through-hole pads)
     - If `hole_size < min_hole` → violation
     - If `hole_size > max_hole` → violation

---

## 7. Hole-to-Hole Clearance Violations

**Rule Type:** `hole_to_hole_clearance`

**Purpose:** Ensures minimum spacing between drill holes.

### Detection Algorithm:

1. **Check via-to-via:**
   - Calculate center-to-center distance between vias
   - `clearance = center_distance - via1_hole_radius - via2_hole_radius`
   - If `clearance < min_clearance` → violation

2. **Check pad-to-pad:**
   - Calculate center-to-center distance between pads
   - `clearance = center_distance - pad1_hole_radius - pad2_hole_radius`
   - If `clearance < min_clearance` → violation

3. **Check via-to-pad:**
   - Calculate center-to-center distance
   - `clearance = center_distance - via_hole_radius - pad_hole_radius`
   - If `clearance < min_clearance` → violation

---

## 8. Solder Mask Sliver Violations

**Rule Type:** `solder_mask_sliver`

**Purpose:** Detects narrow gaps in solder mask between pads/vias.

### Detection Algorithm:

1. **Check pad-to-pad:**
   - Calculate center-to-center distance
   - Calculate combined solder mask radius (pad radius + mask expansion)
   - `gap = center_distance - combined_mask_radius`
   - If `0 < gap < min_sliver` → violation (narrow gap detected)

2. **Check via-to-via:**
   - Similar calculation using via solder mask radius

3. **Check via-to-pad:**
   - Similar calculation

---

## 9. Silk-to-Solder Mask Clearance Violations

**Rule Type:** `silk_to_solder_mask`

**Purpose:** Ensures silk screen text doesn't overlap solder mask openings.

### Detection Algorithm:

1. **For each component:**
   - Get component bounding box (from silk screen)
   - Get all pads/vias for that component
   - Calculate solder mask openings (pad/via positions with mask expansion)
   - Check if silk screen overlaps solder mask openings
   - If overlap detected → violation

---

## 10. Silk-to-Silk Clearance Violations

**Rule Type:** `silk_to_silk`

**Purpose:** Ensures minimum spacing between silk screen text on different components.

### Detection Algorithm:

1. **For each component pair:**
   - Get bounding boxes for both components' silk screen
   - Calculate minimum distance between bounding boxes
   - If `distance < min_clearance` → violation

---

## Key Design Principles

### 1. **Layer Filtering**
- Only check objects on signal/copper layers
- Skip overlay, mechanical, solder mask, keep-out layers
- Check layer compatibility for multi-layer objects (vias, Multi Layer pads)

### 2. **Net Filtering**
- Only check objects on different nets (for clearance/short-circuit)
- Same-net objects don't need clearance (they're connected)

### 3. **Tolerance Handling**
- Use adaptive tolerances based on object geometry (track width, pad size)
- Account for coordinate rounding and floating-point precision
- `CONNECTION_TOLERANCE = 1.0mm` for connectivity checks
- `CONN_TOL = track_half_width` for Net Antennae (adaptive)

### 4. **Scope Support**
- Support `InNamedPolygon('Name')` scope for clearance rules
- Filter objects to only those within specified polygon(s)
- Support component-type scopes (IsBGA, IsSOIC) via component type data

### 5. **Priority Handling**
- Rules with higher priority take precedence
- General (All),(All) rules skip components that have specific rules
- Prevents false positives from rule conflicts

### 6. **Data Validation**
- Skip checks if required data is missing or unreliable
- Validate width data before checking width violations
- Check for binary parsing errors

### 7. **Connectivity Algorithm**
- Use Union-Find (Disjoint Set Union) for efficient connectivity checking
- Accounts for tracks, vias, pads, polygon pours, fills, arcs
- Handles T-junctions, overlaps, and multi-layer connections

---

## Limitations

1. **Polygon/Copper Geometry:**
   - Exported copper regions are bounding boxes, not actual poured copper with relief cutouts
   - Pad-to-polygon and track-to-polygon checks are disabled to avoid false positives
   - Would need actual poured copper geometry with cutouts for accurate checks

2. **Complex Scopes:**
   - Some scope expressions are not fully supported (e.g., `InComponent`, `InNetClass`)
   - `InNamedPolygon` is supported for clearance rules

3. **Routing Topology:**
   - Routing topology rules are parsed but not fully validated
   - Would require complex graph analysis

4. **Differential Pairs:**
   - Differential pair rules are parsed but validation is limited
   - Would require coupling length analysis

---

## Summary

The Python DRC engine uses:
- **Geometric calculations** for clearance and short-circuit detection
- **Union-Find algorithm** for connectivity analysis (unrouted nets)
- **Adaptive tolerances** based on object geometry
- **Altium's connection objects** (ratsnest) for accurate unrouted net detection
- **Layer and net filtering** to match Altium's behavior
- **Scope support** for polygon-based and component-type rules

The engine is designed to match Altium's DRC behavior as closely as possible, using the same data sources (Altium export) and similar algorithms.
