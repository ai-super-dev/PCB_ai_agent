🚀 **ARCHITECTURE SPECIFICATION

============================================================

# **AI-Enhanced PCB Platform — Architecture Specification**

# (Internal Engineering Design Document)

# ============================================================

**Version:** initial version

**Status:** Engineering Baseline

**Audience:** Backend, Frontend, Kernel, Plugin, AI/ML, DevOps

**Owner:** Architecture Group

**Document Type:** Internal Technical Specification 

---

# Revision History

| Date       | Version | Notes                |
| ---------- | ------- | -------------------- |
| 2025-12-21 | initial | Engineering baseline |

# ============================================================

# ============================================================

# 0. Document Conventions

# ============================================================

### 0.1 Terminology

* **Canonical** — authoritative source of truth within the cloud IR.
* **Artifact** — versioned object stored in the canonical artifact graph.
* **G-IR** — Geometry Internal Representation.
* **C-IR** — Constraint Internal Representation.
* **PrimitiveOp** — low-level engine operation executed by adapters.
* **Patch** — append-only diff describing artifact transformation.
* **Adapter** — Altium/Cadence/KiCad plugin or service mapping PrimitiveOps to engine APIs.
* **MCP Tool** — deterministic transform operating on artifacts.
* **Session Tool** — stateful MCP tool.
* **Agent** — AI module producing suggestions and reasoning.
* **DRC** — Design Rule Check.
* **HS/SI** — High-speed / Signal Integrity.
* **EMI** — Electromagnetic Interference.

### 0.2 Document Norms

This is not an RFC; text is descriptive, but requirements are unambiguous.

Schemas and pseudocode are normative.

### 0.3 Schema Conventions

Schemas are shown in JSON Schema–like formats for clarity, not strict validation.

---

# ============================================================

# 1. System Overview

# ============================================================

The AI-Enhanced PCB Platform is a **cloud-native, artifact-driven design environment** supporting:

* Collaborative PCB design
* AI-assisted layout and optimization
* Bounded bidirectional integration with Altium, Cadence, KiCad
* Artifact-based version control
* Expandable rule and constraint modeling
* High-speed/SI/EMI analysis
* Future internal kernels (geometry, DRC, routing)

### High-Level Flow

1. Engineers work in Altium/Cadence/KiCad.
2. Adapter syncs board state → Canonical IR (G-IR + C-IR).
3. Canvas renders board, overlays AI & DRC insights.
4. AI agents propose patches (`ai.suggestion.patch`).
5. Users accept patches, which update artifacts.
6. Accepted patches convert → PrimitiveOps → synced back to engines.
7. Future: internal routing/DRC kernels replace engine calls.

---

# ============================================================

# 2. Architecture Principles

# ============================================================

### 2.1 Canonical Artifact Model

The cloud artifact graph is  **the only authoritative design state** .

Traditional EDA engines are  *execution providers* , not authorities.

### 2.2 Bounded Bidirectional Collaboration

Only safe, well-defined edit types are allowed to sync back to engines.

This guarantees:

* Safety
* Predictability
* Version consistency
* Regulatory compliance
* Auditability

### 2.3 Extensibility Through IR Layering

Two-layer model:

* G-IR: pure geometry & topology
* C-IR: constraints, rules, HS/SI/EMI information

This enables:

* Engine-agnostic transformations
* Future internal kernels
* Version-independent schema evolution

### 2.4 Agent Supervisability

AI never modifies canonical IR directly.

Agents only produce suggestions; humans commit changes.

### 2.5 Strict Safety Invariants

The system maintains guaranteed non-modification of:

* Net names
* Padstack definitions
* Stack-up
* Footprint geometry
* Reference designators
* Schematic connectivity

Unless explicitly requested through supported patch types.

---

# ============================================================

# 3. Artifact Graph

# ============================================================

### 3.1 Definition

The artifact graph is a versioned DAG of:

| Artifact Type             | Description                            |
| ------------------------- | -------------------------------------- |
| `pcb.board`             | Full board geometry + net topology     |
| `pcb.schematic`         | Logical connectivity                   |
| `pcb.footprint`         | Per-footprint geometric representation |
| `constraint.ruleSet`    | Design rule definitions                |
| `constraint.hsRules`    | High-speed/SI/EMI constraints          |
| `constraint.violations` | DRC and SI violations                  |
| `ai.suggestion.patch`   | AI proposals                           |
| `eco.changeSet`         | ECO between schematic ↔ PCB           |
| `library.part`          | Symbol + footprint metadata            |
| `ui.viewState`          | Canvas state                           |

### 3.2 Artifact Structure Schema

```json
{
  "id": "uuid",
  "type": "string",
  "version": 5,
  "relations": [
    { "role": "uses", "targetId": "constraint-ruleset-id" },
    { "role": "contains", "targetId": "footprint-123" }
  ],
  "data": {},
  "meta": {
    "sourceEngine": "altium | cadence | internal",
    "createdAt": "ISO8601",
    "updatedAt": "ISO8601",
    "createdBy": "user | agent | engine",
    "tags": ["optional"]
  }
}
```

### 3.3 Versioning

* Monotonic version increments per artifact.
* Patches apply `fromVersion → toVersion`.
* Patch logs maintain linear history.

### 3.4 Conflict Model

See §12.

---

# ============================================================

# 4. Internal Representation (G-IR + C-IR)

# ============================================================

# 4.1 Geometry IR (G-IR)

G-IR models geometric and topological aspects of PCB designs.

### 4.1.1 G-IR High-Level Structure

```json
{
  "board": {
    "outline": { "polygon": [[x,y], ...] },
    "layers": [
      { "id": "L1", "name": "Top", "kind": "signal", "index": 1 },
      { "id": "L2", "name": "GND", "kind": "plane", "index": 2 }
    ],
    "stackup": {
      "layers": ["L1", "L2"],
      "thicknessMm": 1.6,
      "dielectrics": [ ... ]
    }
  },
  "nets": [
    { "id": "net-gnd", "name": "GND" },
    { "id": "net-vcc", "name": "VCC" }
  ],
  "tracks": [
    {
      "id": "trk1",
      "netId": "net-gnd",
      "layerId": "L1",
      "segments": [
        { "from": [10,10], "to": [30,10], "widthMm": 0.2 }
      ]
    }
  ],
  "vias": [
    {
      "id": "via1",
      "netId": "net-gnd",
      "position": [30,10],
      "drillMm": 0.3,
      "layers": ["L1","L2"]
    }
  ],
  "footprints": [
    {
      "id": "fp-u1",
      "ref": "U1",
      "position": [20,20],
      "rotationDeg": 90,
      "pads": [
        {
          "id": "pad1",
          "netId": "net-gnd",
          "shape": "rect",
          "sizeMm": [1,1]
        }
      ]
    }
  ]
}
```

---

# 4.2 Constraint IR (C-IR)

C-IR models  **rules** ,  **constraints** ,  **design intent** , including advanced HS/SI features.

### 4.2.1 Basic Rules Schema

```json
{
  "rules": [
    {
      "id": "rule-clearance-1",
      "type": "clearance",
      "scope": { "nets": ["net-gnd","net-vcc"] },
      "params": { "minClearanceMm": 0.15 },
      "extensions": { "engine_specific": {} }
    },
    {
      "id": "rule-width-1",
      "type": "traceWidth",
      "scope": { "netclass": "power" },
      "params": {
        "minWidthMm": 0.25,
        "preferredWidthMm": 0.3
      }
    }
  ],
  "netclasses": [
    {
      "id": "nc-power",
      "name": "Power",
      "nets": ["net-vcc"],
      "defaults": {
        "traceWidthMm": 0.3,
        "clearanceMm": 0.2
      }
    }
  ]
}
```

---

# 4.3 High-Speed / SI Constraint Layer

**This section is NEW in v2.0** and essential for credibility in high-speed workflows.

## 4.3.1 Diff Pair Constraints

```json
{
  "diffPairs": [
    {
      "id": "dp-1",
      "nets": ["net-dp+","net-dp-"],
      "params": {
        "pairGapMm": 0.15,
        "couplingStyle": "edge-coupled",
        "maxSkewPs": 12
      }
    }
  ]
}
```

## 4.3.2 Length Budget / Timing Constraints

```json
{
  "lengthBudgets": [
    {
      "id": "lb-dqs",
      "group": ["net-dqs", "net-dq0", "net-dq1", "..."],
      "params": {
        "targetLengthMm": 30.0,
        "maxDeltaMm": 0.5
      }
    }
  ]
}
```

## 4.3.3 Via Model Constraints

```json
{
  "viaModels": [
    {
      "id": "via-budget-1",
      "netGroup": "ddr3",
      "params": {
        "maxViaCount": 4,
        "penaltyPerViaPs": 2.3
      }
    }
  ]
}
```

## 4.3.4 Return Path Constraints

```json
{
  "returnPathRules": [
    {
      "id": "rp1",
      "scope": { "nets": ["ddr3_*"] },
      "params": {
        "forbidSplitPlaneCrossing": true,
        "minPlaneContinuityMm": 2.0
      }
    }
  ]
}
```

## 4.3.5 Crosstalk Budgets

```json
{
  "crosstalkBudgets": [
    {
      "id": "xtalk-1",
      "victimNet": "net-a",
      "aggressorNets": ["net-b","net-c"],
      "params": {
        "minSpacingMm": 0.25,
        "maxCouplingCoeff": 0.3
      }
    }
  ]
}
```

---

# ============================================================

# 5. Global Invariants & Safety Rails

# ============================================================

This section provides **hard guarantees** to engineers.

The platform will **never automatically modify** the following unless explicitly permitted by patch type and user approval:

### 5.1 Immutable Objects (Global)

* Net names
* Net connectivity (schematic connectivity)
* Reference designators
* Padstack definitions (drill size, shape)
* Stack-up
* Component symbols
* Footprint geometries
* Power/ground plane shapes (unless within region reroute and explicitly approved)
* Library definitions

### 5.2 Immutable Constraint Types

* Complex constraint scoping (rooms, classes, rule hierarchy)
* High-speed constraints (diff pair grouping, timing groups)
* Stack-up-dependent constraints

### 5.3 Allowed Auto-Modifications (When Requested)

* Track segment movement
* Via placement/deletion
* Component movement
* Region reroute
* Netclass width / clearance adjustments

### 5.4 Patch Validation

All AI-generated patches MUST:

1. Pass schema validation
2. Respect safety invariants
3. Reference existing nets only
4. Preserve topology
5. Pass preliminary DRC check (local kernel)

Pseudocode:

```python
def validate_patch(patch, gir, cir):
    assert patch.artifactId in artifact_graph

    for op in patch.ops:
        assert op.type in PATCH_MATRIX.allowedOps

        assert not modifies_forbidden_fields(op)

        if op.netId:
            assert op.netId in gir.nets

    return True
```

---

# ============================================================

# 6. Patch Model & Capability Matrix

# ============================================================

# 6.1 Patch Schema

```json
{
  "artifactId": "uuid",
  "fromVersion": 3,
  "toVersion": 4,
  "ops": [
    {
      "op": "replace",
      "path": "/tracks/0/segments/0/to",
      "value": [32.0,10.0]
    }
  ],
  "meta": {
    "author": "user-123",
    "source": "canvas | agent | engineSync",
    "explain": "AI: improved clearance and reduced skew"
  }
}
```

---

# 6.2 MVP Patch Types (6 months)

| Category   | Patch Type           |
| ---------- | -------------------- |
| Geometry   | MoveComponent        |
| Geometry   | MoveTrackSegment     |
| Geometry   | AddTrackSegment      |
| Geometry   | DeleteTrackSegment   |
| Geometry   | AddVia / DeleteVia   |
| Routing    | RegionReroute        |
| Constraint | UpdateNetclassWidth  |
| Constraint | UpdateClearanceParam |

---

# 6.3 Phase 2 Patch Types

### High-Speed & SI Patch Types

* AdjustDiffPairSpacing
* TuneDiffPairLength
* FixReturnPath
* ImproveCrosstalkSpacing
* ReduceViaCountOnCriticalPath
* InsertStitchingVias
* RerouteToAvoidPlaneSplit

Schemas:

```json
{
  "op": "TuneDiffPairLength",
  "payload": {
    "pairId": "dp-1",
    "targetLengthMm": 30.0
  }
}
```

---

# 6.4 Out-of-Scope Patch Types (v1–v2)

* Padstack editing
* Net renaming
* Stack-up changes
* Schematic ECO changes

---

# 6.5 Agent Trajectory & CRUD (Normative)

The system MUST record the full agent lifecycle as artifacts in the canonical
graph. CRUD operations apply to artifacts and patches, not to scripts or
adapter outputs. Scripts are generated only as execution artifacts from patches.

### 6.5.1 Required Artifact Types

```json
{
  "type": "ai.intent",
  "data": { "action": "generate_layout", "scope": "schematic", "parameters": {} }
}
```

```json
{
  "type": "ai.suggestion.patch",
  "data": { "patch": { ... }, "explain": { ... } }
}
```

```json
{
  "type": "execution.run",
  "data": { "adapter": "altium", "patchId": "patch-123", "method": "script" }
}
```

```json
{
  "type": "execution.result",
  "data": { "runId": "run-456", "status": "success", "details": {} }
}
```

```json
{
  "type": "user.override",
  "data": { "targetPatchId": "patch-123", "reason": "moved connector closer to edge" }
}
```

### 6.5.2 CRUD Rules

* Create/Update/Delete operations target artifacts and patches only.
* Adapter outputs (e.g., scripts) are non-authoritative, ephemeral products.
* All user refinements modify artifacts or patch proposals, then re-emit patches.

### 6.5.3 Execution Flow (Required)

```
Heuristic → Patch → User Refine → Patch → Execute (script) → Result
```

Execution is the final step; design reasoning must remain inside agent logic
and artifact updates, not inside scripts or adapters.

---

# ============================================================

# 7. Transform Runtime (MCP Tools)

# ============================================================

### 7.1 Tool Types

* **Stateless Tools:**
  * `drc.run`
  * `fab.export`
  * `analyze.congestion`
* **Session Tools:**
  * `routing.session.start/apply/getState/end`
  * `hs.session.skewOptimization`
  * `si.session.crosstalkCheck`

### 7.2 Stateless Tool Contract

```json
{
  "tool": "drc.run",
  "inputArtifacts": ["pcb-board-1","constraint-ruleset-1"],
  "params": { "scope": "region", "regionBBox": [x1,y1,x2,y2] }
}
```

Response:

```json
{
  "updatedPatches": [...],
  "newArtifacts": [
    {
      "type": "constraint.violations",
      "data": { ... }
    }
  ]
}
```

---

# 7.3 Session Tool Contract

### Start

```json
{ "tool": "routing.session.start", "params": { "regionBBox": [...] } }
```

### Apply

```json
{ "tool": "routing.session.applyPatch", "sessionId": "sess123", "patch": {...} }
```

### Get State

```json
{ "tool": "routing.session.getState", "sessionId": "sess123" }
```

---

# ============================================================

# 8. Engine Adapter Architecture

# ============================================================

### 8.1 Adapter Responsibilities

* Serialize engine DB → G-IR + C-IR
* Apply PrimitiveOps atomically
* Run DRC
* Run router
* Report engine health

### 8.2 PrimitiveOps Schema

```json
{
  "op": "MoveComponent",
  "payload": {
    "ref": "U1",
    "newPositionMm": [20,20],
    "newRotationDeg": 90
  }
}
```

Supported ops mirror Patch Matrix.

---

# 8.3 Adapter IDL

```text
GetBoardState(): BoardState
ApplyPrimitiveOps(ops[]): ApplyResult
RunDRC(scope): DrcResult
RunRouter(scope): RouteResult
Ping(): HealthStatus
```

BoardState:

```json
{
  "geometry": { ... G-IR ... },
  "constraints": { ... C-IR ... },
  "meta": { "engine": "altium", "version": "24.1" }
}
```

---

# 8.5 Pseudocode: Patch → PrimitiveOps

```python
def patch_to_ops(patch, gir, cir):
    ops = []
    for change in patch.ops:
        if change.op == "replace" and path_is_track_segment(change.path):
            ops.append({
                "op": "MoveTrackSegment",
                "payload": {
                    "segmentId": segment_id_from_path(change.path),
                    "newSegments": compute_segments(change)
                }
            })
        # ... handle via/region reroute/etc ...
    return ops
```

---

# ============================================================

# **9. AI Agent Architecture** 

# ============================================================

This section defines the architecture, lifecycle, safety model, and operational semantics of all AI agents in the platform.

Agents are responsible for producing **explainable, safe, bounded patch proposals** that assist designers while respecting constraints, governance, and global invariants.

Agents **never** directly modify canonical artifacts; they produce *suggestions* in the form of `ai.suggestion.patch` artifacts.

Only humans (or authorized automation under explicit approval) can commit patches.

---

# 9.1 Agent Types

The platform implements multiple specialized agents with different responsibilities:

| Agent                        | Responsibility                                         |
| ---------------------------- | ------------------------------------------------------ |
| **Conversation Agent** | Intent extraction, task delegation, NLP interface      |
| **Reviewer Agent**     | DRC reasoning, violation clustering, rule explanations |
| **Routing Agent**      | Local optimization of routing, region reroutes         |
| **Placement Agent**    | Component clustering, minor placement adjustments      |
| **HS/SI Agent**        | Skew, diff-pair quality, return path, via optimization |
| **Crosstalk Agent**    | Parallel-run detection and spacing proposals           |
| **DFM Agent**          | Manufacturability hints, solder/thermal concerns       |
| **ECO Agent**          | Schematic ↔ layout consistency checks                 |
| **Governance Agent**   | Enforces user roles, permissions, protected regions    |

Agents operate independently but coordinate through the **Orchestrator Layer** (§9.2).

---

# 9.2 Agent Orchestration Model

The platform uses an **Orchestrator Agent** to coordinate all others:

### 9.2.1 Responsibilities

* Interpret user intent (`ai.intent` artifacts)
* Identify which domain agents should engage
* Manage conflicts among agent outputs
* Govern permission checks
* Enforce global invariants
* Present a unified set of `ai.suggestion.patch` proposals

### 9.2.2 Orchestration Flow

```
User Message
   ↓
Conversation Agent (intent extraction)
   ↓
Orchestrator Agent
   ↓        ↘
Routing Agent  Reviewer Agent  HS/SI Agent ...
   ↓             ↓                 ↓
candidate patches + explanations
   ↓
Orchestrator: validate + merge + filter
   ↓
Output ai.suggestion.patch artifacts
```

### 9.2.3 Patch Arbitration Rules

1. High-Speed/SI constraints override routing convenience.
2. Governance rules override all agent proposals.
3. Reviewer Agent may veto patches creating new violations.
4. Only one patch per artifact region may be active unless explicitly merged.

---

# 9.3 Intent Interpretation

The Conversation Agent converts natural language instructions into structured intents.

### 9.3.1 Intent Schema

```json
{
  "type": "ai.intent",
  "data": {
    "action": "optimize_region | fix_drc | tune_skew | reroute_nets | analyze_si",
    "scope": "region | nets | whole_board",
    "regionBBox": [x1, y1, x2, y2],
    "nets": ["DDR3_DQS*", "GND"],
    "parameters": {
      "maxViaCount": 4,
      "targetClearanceMm": 0.18
    }
  }
}
```

### 9.3.2 Intent Resolution Algorithm (Pseudocode)

```python
def interpret_intent(user_msg):
    intent = parse_language(user_msg)
    intent = normalize_scope(intent)
    intent = link_board_context(intent)
    return intent
```

---

# 9.4 Tool-Calling Semantics

Agents do **not** access engines directly.

They must call MCP Tools:

* `drc.run`
* `routing.session.*`
* `hs.check_return_path`
* `si.estimate_crosstalk`
* `eco.compute_changeSet`
* etc.

### 9.4.1 Tool-Calling Contract

1. Agents generate input parameters exclusively from artifact graph state.
2. MCP tools return:
   * new artifacts
   * patches
   * structured analysis reports
3. Agents validate results before producing suggestions.

### 9.4.2 Example Call

```json
{
  "tool": "drc.run",
  "inputArtifacts": ["pcb-board-1", "constraint-ruleset-1"],
  "params": { "scope": "region", "regionBBox": [10,10,60,40] }
}
```

---

# 9.5 Patch Generation Pipeline

This is the formal pipeline all agents must follow.

```
Intent → Fetch IR → Run Tools → Analyze → Generate Patches → Validate → Explain → Emit Suggestion
```

---

## 9.5.1 Formal Pipeline Steps

### Step 1 — Gather Inputs

* `pcb.board`
* `constraint.ruleSet`
* `constraint.hsRules`
* Violations
* ECO diffs (optional)
* Role constraints

### Step 2 — Run MCP Tools

Agents call stateless or session tools as required.

### Step 3 — Generate Candidate Patches

* Move segments
* Add vias
* Adjust pair spacing
* Tune diff-pair lengths
* Improve return path
* Reduce crosstalk risk

### Step 4 — Validate Against C-IR

Validation includes:

1. Clearance compliance
2. Width compliance
3. HS/SI compliance (skew, coupling, return paths)
4. Global safety invariants

### Step 5 — Filter Conflicts

Remove candidates that:

* Touch protected regions
* Modify protected nets
* Conflict with other agent proposals

### Step 6 — Produce `ai.suggestion.patch`

Includes explainability metadata.

---

# 9.6 Explainability Architecture

Every AI suggestion MUST include structured reasoning.

### 9.6.1 Explainability Schema

```json
{
  "reason": "Improve spacing and reduce skew",
  "triggeredBy": ["viol-12", "viol-15"],
  "metricsBefore": {
    "skewPs": 18,
    "minClearanceMm": 0.12
  },
  "metricsAfter": {
    "skewPs": 9,
    "minClearanceMm": 0.19
  },
  "tradeoffs": [
    "Length increased by 1.2mm to maintain coupling"
  ]
}
```

### 9.6.2 Explanation Requirements

Explanations must:

* Reference relevant violations
* Quantify benefits
* Quantify tradeoffs
* Avoid vague NLP phrasing
* Provide engineer-level clarity

---

# 9.7 Safety, Invariants & Governance Enforcement

Agents must enforce the safety boundaries defined in Sections 5 and 11.

### 9.7.1 Prohibited Operations

Agents may not:

* Change net names
* Modify footprints
* Alter stack-up
* Change pin mappings
* Add/remove components
* Modify schematic connectivity

### 9.7.2 Patch Governance

Agents must:

* Call the Governance Agent to authorize patch scopes
* Label patches with required approval roles

### 9.7.3 Protected Region Logic

If intent touches a protected region:

1. Agent produces  **no patch** , but produces a warning:
   ```
   "This region is protected. Senior approval is required."
   ```
2. Orchestrator forwards approval request.

---

# 9.8 Error Handling & Fallback Behavior

Agents must gracefully handle:

### 9.8.1 Tool Failures

If MCP tools fail:

* Fallback to partial analysis
* Emit reason-only suggestions (no patches)
* Log diagnostics

### 9.8.2 No Valid Routing Solution

If tool returns “no route”:

* Suggest constraint updates
* Suggest component movement
* Suggest region enlargement

### 9.8.3 Conflicting Constraints

If constraints conflict:

* Create `constraint.violation.conflict` artifact
* Produce high-level explanation

---

# 9.9 Session-Based Agent Behavior

### 9.9.1 Session Lifecycle

Agents may create routing/HS/SI sessions:

```
session.start → session.applyPatch* → session.getState → session.end
```

Agents must track:

* sessionId
* affected region
* lock tokens
* intermediate states

### 9.9.2 Best Practices

* Keep sessions short (avoid locking regions too long)
* Stop session when incremental improvement stalls
* Summaries must be returned with:
  * metrics improved
  * # of ops
  * # of violations resolved

---

# 9.10 Agent Performance Expectations

### 9.10.1 Time Budget

| Operation                                      | Budget   |
| ---------------------------------------------- | -------- |
| Intent parsing                                 | < 300 ms |
| Tool selection                                 | < 150 ms |
| Patch generation                               | < 1 s    |
| Explanation synthesis                          | < 500 ms |
| Full agent cycle (excluding DRC/routing tools) | < 2 s    |

### 9.10.2 Rate Limits

* Max 10 tool calls per agent per request
* Max 3 active sessions per region
* Max 50 patches per batch

---

# 9.11 Multi-Agent Interaction Semantics

### 9.11.1 Conflict Resolution

Rules:

1. HS/SI Agent can veto Routing Agent
2. DFM Agent can veto changes that violate manufacturability
3. Reviewer Agent can veto anything that increases DRC count
4. Governance Agent can veto anything that violates permissions

### 9.11.2 Patch Prioritization

Order of precedence:

1. Safety
2. Integrity (SI / EMI / timing)
3. DRC
4. DFM
5. Routing convenience

---

# 9.12 Complete Example: Agent-Generated Patch Flow

### Scenario

User:

> “Fix the DQS timing in the DDR3 region and improve return paths.”

### End-to-end pipeline

1. Conversation Agent → `ai.intent`
2. Orchestrator selects Routing Agent + HS/SI Agent
3. HS/SI Tool run:
   * `hs.check_return_path`
   * `hs.compute_skew`
4. Routing Agent:
   * Creates candidate segment modifications
   * Proposes via reductions
5. HS/SI Agent:
   * Rejects patches that violate skew budgets
   * Inserts `TuneDiffPairLength` patches
   * Adds stitching vias
6. Validated + merged patches → `ai.suggestion.patch`

### Example Output

```json
{
  "type": "ai.suggestion.patch",
  "artifactId": "pcb-board-1",
  "data": {
    "patch": { ...patchOps... },
    "explain": {
      "reason": "Improve DQS timing and ensure continuous return path",
      "triggeredBy": ["skew-viol-3", "rp-viol-1"],
      "metricsBefore": { "skewPs": 18, "rpContinuityScore": 0.62 },
      "metricsAfter": { "skewPs": 9, "rpContinuityScore": 0.94 },
      "tradeoffs": ["Trace length increased by 1.4mm"]
    }
  }
}
```

Engineers see both the **patch** and the **engineering logic** behind it.

---

# **10. Schematic / Library / ECO Integration**

# ============================================================

This section defines how  **logical design** ,  **library metadata** , and **ECO processes** are integrated into the canonical artifact system.

It expands on the artifact types introduced earlier.

---

## **10.1 Schematic Representation (`pcb.schematic`)**

The schematic is modeled as a structured artifact representing:

* Logical nets
* Symbols
* Pin mappings
* Hierarchical sheets
* Connectivity graph
* Variant information
* Electrical intent descriptors (future)

### **10.1.1 Schema**

```json
{
  "type": "pcb.schematic",
  "version": 3,
  "data": {
    "symbols": [
      {
        "id": "sym-u1",
        "ref": "U1",
        "libraryId": "lib-part-u1",
        "pins": [
          { "pinNumber": "1", "netName": "GND" },
          { "pinNumber": "2", "netName": "VCC" }
        ]
      }
    ],
    "nets": [
      { "name": "GND", "members": ["sym-u1.pin1", "sym-c1.pin2"] }
    ],
    "hierarchy": [
      {
        "sheetId": "top",
        "children": ["ddr3-block", "power-block"]
      }
    ]
  }
}
```

---

## **10.2 Library Model (`library.part`)**

### Purpose

To ensure consistent:

* Symbol ↔ footprint mapping
* Electrical properties
* Package parameters
* Lifecycle metadata

### **10.2.1 Schema**

```json
{
  "type": "library.part",
  "data": {
    "partNumber": "TPS7A4501",
    "footprintId": "fp-u1",
    "package": "SOT-223",
    "pins": [
      { "symbolPin": "1", "footprintPad": "PAD1" }
    ],
    "attributes": {
      "supplier": "TI",
      "variants": ["DNI", "HighTemp"]
    }
  }
}
```

---

## **10.3 ECO Flows (`eco.changeSet`)**

### Purpose

Track differences between schematic ↔ layout and propose user-visible update steps.

### **10.3.1 When generated**

* After schematic update
* After PCB update
* After component swaps
* After symbol/footprint updates
* During variant changes

### **10.3.2 Schema**

```json
{
  "type": "eco.changeSet",
  "data": {
    "changes": [
      {
        "type": "pinSwap",
        "symbolRef": "U1",
        "from": "pin3",
        "to": "pin4",
        "reason": "Updated schematic mapping"
      },
      {
        "type": "footprintUpdate",
        "ref": "U1",
        "oldFp": "SOT-23",
        "newFp": "SOT-223"
      }
    ]
  }
}
```

### **10.3.3 Agent Responsibilities**

Agents may:

* Detect inconsistencies
* Generate `eco.changeSet` artifacts
* Recommend order of application
* Identify impact on layout

Agents must NOT automatically apply ECO patches.

---

## **10.4 Schematic/Layout Cross-Integrity Rules**

These rules must be enforced by validation tools:

| Rule                    | Description                                      |
| ----------------------- | ------------------------------------------------ |
| Pin-mapping correctness | footprint pad ↔ symbol pin alignment            |
| Net mismatch            | a net present in schematic but missing in layout |
| Dangling nets           | layout-only nets not present in schematic        |
| “DNI” enforcement     | pads tied to DNI parts flagged on layout         |
| Variant support         | optional parts must not break routing rules      |

---

# ============================================================

# **11. Roles / Permissions / Governance**

# ============================================================

This section defines multi-user collaboration, authority controls, and access rights.

---

## **11.1 Role Types**

| Role                      | Permissions                                         |
| ------------------------- | --------------------------------------------------- |
| **Viewer**          | View artifacts, inspect patches                     |
| **Junior Designer** | Propose patches (user edits), accept AI suggestions |
| **Senior Designer** | Commit patches, approve region locks                |
| **Lead / Owner**    | Modify protected regions, high-speed nets           |
| **Administrator**   | Manage permissions, tenant settings                 |

---

## **11.2 Region Ownership**

`pcb.board` contains optional metadata:

```json
{
  "regions": [
    {
      "id": "hs-zone-1",
      "ownerRole": "Lead",
      "nets": ["ddr3_*"],
      "locked": false
    }
  ]
}
```

* Only designated roles may modify protected regions.
* AI may only **propose** patches for protected regions unless overridden.

---

## **11.3 Protected Nets**

Critical nets may be designated:

```json
{
  "protectedNets": [
    { "net": "DDR3_DQS*", "role": "Lead" }
  ]
}
```

Only matching roles can commit patches touching them.

---

## **11.4 Patch Approval Workflow**

1. AI produces `ai.suggestion.patch`
2. Junior Designer selects “approve” → becomes `pending.patch`
3. Senior Designer must “commit” → becomes a real patch
4. Adapter receives PrimitiveOps and applies

This prevents junior mistakes or AI misfires.

---

## **11.5 Region Locking Workflow**

State machine:

```
Unlocked → (session.start) → Locked.by.session
Locked.by.session → (session.end) → Unlocked
```

Rules:

* Only one active session per region.
* Locks may be preempted by Lead-level roles.
* AI sessions require Senior or Lead approval.

---

# ============================================================

# **12. Latency & Interactivity SLOs**

# ============================================================

Real-time responsiveness is essential for productivity.

This section defines  **target SLOs** , not hard guarantees.

---

## **12.1 UI Responsiveness**

| Operation                     | Target Latency | Notes                          |
| ----------------------------- | -------------- | ------------------------------ |
| Canvas overlay updates        | < 100 ms       | Pure client (WebGL/WebGPU)     |
| Hit testing                   | < 50 ms        | KiCanvas / local spatial index |
| Selecting/dragging components | < 60 ms        | Client-side rendering only     |

---

## **12.2 Backend Interactions**

| Operation                    | Target       | Notes                        |
| ---------------------------- | ------------ | ---------------------------- |
| Region DRC (internal kernel) | < 2 s        | up to ~5k objects            |
| AI suggestion generation     | < 5 s        | per region                   |
| Engine DRC                   | asynchronous | engine-dependent             |
| Engine reroute (region)      | < 10 s       | typical Altium/Cadence range |

---

## **12.3 Compute Tiers**

The runtime is divided into three latency tiers:

### **Tier 1 – Local (Wasm Kernel)**

* Fast hit tests
* Preliminary DRC
* Constraint sanity checks

### **Tier 2 – Fast Cloud Kernel (Rust/Wasm microservices)**

* Region DRC
* Region routing heuristics
* HS/SI estimation

### **Tier 3 – Engine Calls (slow)**

* Altium/Cadence DRC
* Engine-based routing
* Used for signoff or validation

---

# ============================================================

# **13. Deployment & Compatibility Model**

# ============================================================

This section defines runtime deployment, connector integration, and engine compatibility.

---

## **13.1 Local Engine Adapters**

Adapters must support:

* Windows (Altium / Cadence)
* CLI-based KiCad (Windows/Linux/Mac)

Adapters communicate with backend via:

* Secure WebSocket
* Secure HTTP/HTTPS
* Optional local-tunnel proxy for firewall compliance

---

## **13.2 Update Strategy**

* Adapters autoupdate only within safe version ranges
* Breaking engine API changes detected via contract tests
* Version pinning possible for enterprise environments

---

## **13.3 Engine Compatibility Table**

| Tool    | Versions Supported | Notes                                    |
| ------- | ------------------ | ---------------------------------------- |
| Altium  | 20.xx–24.xx       | COM automation tested via CI             |
| Allegro | 17.4+              | SKILL API verified via CI contract tests |
| KiCad   | 6.x–8.x           | CLI and file parsing                     |

---

## **13.4 On-Prem / Air-Gapped Support**

An enterprise may deploy:

* Artifact Store
* Transform Runtime
* Agent Runner
* Internal Wasm kernels

Internally with:

* Plugin → local server only
* No cloud dependency

---

## **13.5 Offline Modes**

When backend unreachable:

* Canvas loads last-synced artifacts
* AI disabled or limited to cached models
* Patches cached locally until reconnection
* Engine adapter continues local operation without sync

---

# ============================================================

# **14. Advanced AI Value (Cross-Project Intelligence)**

# ============================================================

This section captures product differentiation beyond “AI routing helper.”

---

## **14.1 Pattern Learning Across Designs**

Agents may compare:

* multiple boards
* multiple revisions
* entire product families

Using historical artifact graph data.

### Example tools:

* `pattern.find_repeated_violations`
* `history.analyze_respins`
* `compare.board_family`
* `rule.derive_optimal_params`

---

## **14.2 Organization-Wide Constraint Drift Detection**

Analyze:

* rule differences across teams
* divergence from “golden” designs
* common pain points

Output:

* recommended C-IR adjustments
* organization-level constraint standards

---

## **14.3 Example: Learned Return Path Rule**

AI learns that:

* 70% of EMI failures in a certain org relate to diff pairs crossing plane splits
* DRC does not catch this in their legacy flow

AI proposes:

```json
{
  "type": "constraint.returnPathRule",
  "data": {
    "forbidSplitPlaneCrossing": true,
    "appliesTo": ["DDR*", "PCIE*"]
  }
}
```

This is  **new engineering insight** , not a DRC check.

---

# ============================================================

# **15. High-Speed / SI Scenario Examples (Killer Scenarios)**

# ============================================================

These scenarios demonstrate why the platform is uniquely valuable.

---

## **15.1 DDR3 DQS Return Path Issue**

Symptoms:

* DRC passes
* Timing looks okay
* Board fails EMI testing

Agent detects:

* DQS diff-pair crosses a narrow void in GND plane
* Results in poor return path and radiated emissions

### AI Suggestion:

`ai.suggestion.patch` for:

* rerouting pair slightly
* adding stitching vias
* ensuring uninterrupted return path

### Why legacy tools failed:

* Altium/Cadence DRC does not evaluate return-path continuity unless rules are manually set.

---

## **15.2 Crosstalk on Adjacent DDR3 Byte Lanes**

Agent identifies:

* High coupling due to long parallelism
* Violations of learned crosstalk budgets

AI proposes:

* Increase spacing in critical region
* Adjust routing topology to reduce parallel lengths
* Reassign track order where safe

---

## **15.3 Via Count Penalty in High-Speed Path**

Agent detects:

* Excessive vias in address/control lines
* Predicted timing violation relative to flight-time model

AI Suggests:

* Route flattening
* Local guide paths
* Reducing via count from 7 → 3

---

# ============================================================

# **16. Roadmap**

# ============================================================

## **16.1 MVP Phase**

* Two-layer IR (G-IR + basic C-IR)
* Canvas with overlay
* Adapter sync (G-IR + C-IR)
* MVP Patch Matrix
* Stateless DRC tools
* Reviewer + Routing Agents
* Basic C-IR rules (width, clearance)

---

## **16.2 Phase 2**

* HS/SI C-IR expansion
* Length budgets, diff pairs
* Crosstalk and via models
* Role-based governance
* On-prem enterprise support
* Rust/Wasm region-kernel for DRC
* Region-based SI analysis tools
* Advanced agent explainability

---

## **16.3 Phase 3**

* Full internal DRC kernel
* Internal routing kernel
* SI/EMI analysis kernels
* Fully agent-driven reroute sessions
* Enterprise rule recommender
* Multi-board/system-level optimization
* Autonomous constraint refinement

---

# ============================================================

# **17. Glossary**

# ============================================================

* **Artifact** — Versioned canonical object
* **Patch** — Diff transforming artifact state
* **G-IR** — Geometry IR
* **C-IR** — Constraint IR
* **PrimitiveOp** — Engine-side atomic operation
* **MCP Tool** — Transform service
* **Session Tool** — Stateful MCP tool
* **Adapter** — Engine integration service
* **HS/SI** — High-Speed / Signal Integrity
* **EMI** — Electromagnetic Interference
* **ECO** — Engineering Change Order

---

# ============================================================

# **Appendix A — Full PrimitiveOps Catalog**

# ============================================================

```json
[
  { "op": "MoveComponent" },
  { "op": "MoveTrackSegment" },
  { "op": "AddTrackSegment" },
  { "op": "DeleteTrackSegment" },
  { "op": "AddVia" },
  { "op": "DeleteVia" },
  { "op": "RegionReroute" },
  { "op": "UpdateNetclassWidth" },
  { "op": "UpdateClearanceParam" },

  // HS/SI Ops (Phase 2)
  { "op": "TuneDiffPairLength" },
  { "op": "AdjustDiffPairSpacing" },
  { "op": "FixReturnPath" },
  { "op": "InsertStitchingVias" },
  { "op": "ReduceViaCountOnCriticalPath" },
  { "op": "ImproveCrosstalkSpacing" }
]
```

---

# ============================================================

# **Appendix B — AI Explainability Schema**

# ============================================================

```json
{
  "type": "ai.suggestion.patch",
  "data": {
    "patch": { ... },
    "explain": {
      "reason": "Improve clearance and reduce skew",
      "triggeredBy": ["viol-54", "rule-clearance-1"],
      "metricsBefore": {
        "clearanceMm": 0.12,
        "skewPs": 14
      },
      "metricsAfter": {
        "clearanceMm": 0.18,
        "skewPs": 9
      },
      "tradeoffs": [
        "Length increased by 1.2mm to reduce via count"
      ]
    }
  }
}
```

---

# ============================================================

# **Appendix C — Patch Application Pseudocode**

# ============================================================

```python
def apply_patch(artifact, patch):
    assert patch.fromVersion == artifact.version

    newData = deepcopy(artifact.data)

    for op in patch.ops:
        newData = apply_json_pointer_op(newData, op)

    artifact.data = newData
    artifact.version += 1
    return artifact
```

---

# ============================================================

# **Appendix D — Killer Scenario Workflow (DDR3 Return Path)**

# ============================================================

Pseudocode for HS/SI agent:

```python
def analyze_return_path(board, constraints):
    for dp in constraints.diffPairs:
        path = extract_diffpair_path(board, dp)
        rp_ok, metrics = check_return_path_continuity(path, board)
        if not rp_ok:
            patch = propose_stitch_vias(path, constraints)
            return create_suggestion(patch, metrics)
```

---
