# ROADMAP_PROCESS_CAD — Milestone Roadmap

One screen of truth for "what now". Detailed acceptance criteria live in
`docs/superpowers/specs/`; task-level plans in `docs/superpowers/plans/`.

## M1 — Process CAD Shell (complete)

Fixed three-pane WebUI workspace (Process Flow / Parameters / 3D Viewer), step
drag-and-drop + rename, five new process primitives (Strip / Fill / Wafer Flip / Bonding /
Thinning), WebGL2 viewer with seven standard views + perspective/orthographic cameras +
X/Y/Z independent clipping, MaterialVisual-driven materials, snapshot timeline with
Previous/Next, atomic undo/redo, structured step errors, three demo recipes
(Basic Trench / Spacer Formation / Bonding + Thinning), reproducible baseline runner
(`tools/run_process_cad_baseline.py`).

Status: feature-complete on branch `zcode/process-cad-shell` (baseline and CAD tests green,
fixed-physical-domain 128³ baseline with structural checks ok, browser acceptance passed). Pending: merge with
`codex/process-cad-shell`, then land on `main` and push `origin`.

## M2 — Parameter Exploration (next)

Parameter sweep / DOE across recipes, structural measurement presets, and run-to-run
result comparison (overlay diffs of geometry/metrology between runs).

Candidate first task: a sweep runner that executes a recipe over a parameter grid
headless and tabulates CD/metrology deltas, reusing the baseline runner's harness.

## M3 — Device-Level Bridge

Device region definition (S/D/G), electrodes, meshing export, and an electrical solving
interface stub. Geometry fidelity improvements needed here (contact surfaces, rounding).

## M4 — Assembly & Calibration

Stricter multi-wafer assembly semantics, calibration data ingestion, and reproducible
experiment packages (recipe + data + results bundled).

## M5+ — External Backends

ViennaPS-style surface-evolution backend behind a `GeometryBackend` abstraction
(ADR-003). Only after the voxel workflow and viewer UX are validated.

## Continuous Engineering

- Incremental extraction of Worker / frontend / model subdomains out of the single file
  (each extraction is its own reviewed milestone; ADR-004).
- Stable CI running the five test modules + compile check + baseline.
- Packaging and license review (PyQt5 GPL implications for binaries).
