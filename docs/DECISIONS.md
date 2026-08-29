# DECISIONS.md — Architecture Decision Records

Numbered, settled decisions. Agents: read before proposing alternatives.
To change a decision, add a new ADR that supersedes the old one — never deviate silently.

---

ADR-001 — Python `ProcessModel` stays the geometry/process backend (Fast Mode).
Reason: the voxel implementation works, is testable, and is shared by desktop, WebUI,
headless, and Agent paths.
Constraint: do not replace before equivalent regression coverage exists; wrapped as
`VoxelBackend` at M7 with behavior unchanged.

ADR-002 — ~~WebUI is the primary Process CAD interface for V1; no React migration.~~
**SUPERSEDED by ADR-012** (owner decision, 2026-08-29): the long-term frontend is
React + TypeScript + Vite, introduced as a parallel frontend from M2. The spirit of this
ADR survives as a migration rule: the legacy WebUI remains functional and is only
deprecated after React parity (M5).

ADR-003 — ViennaPS / external TCAD backends deferred behind an adapter.
Reason: validate workflow and geometry UX on the voxel backend first.
Path (per ADR-014): experiments/ sandbox at M8 → `ViennaPSBackend` at M9.

ADR-004 — `tcad_simulator.py` remains the single canonical source until an explicit
migration milestone.
Reason: one distributable file is the current release model; the split package is a
generated navigation aid.
Constraint: no mass extraction for aesthetics; new modules only for real boundaries.

ADR-005 — Recipe JSON compatibility is additive-only.
Reason: recipes are user data; breaking them breaks trust.
Rule: new optional fields + version migration; load/save round-trip preserves step types,
order, enabled state, and instance names.

ADR-006 — Desktop GUI is maintained but not the primary CAD surface.
Reason: the WebUI session/worker model fits the CAD shell better; Qt stays compatible.
Constraint: no feature may exist in only one UI's private execution path.

ADR-007 — Viewer interactions are browser-local.
Reason: camera, projection, clipping, and material visibility must feel instant.
Rule: they must not trigger worker recomputes, `preview/manifest` refetches, or geometry
re-downloads; only lightweight UI state is persisted.

ADR-008 — Timeline restore is view-only; undo/redo is atomic with metadata.
Reason: reviewing a snapshot must never silently recompute; history restores model state
together with runtime statuses, step errors, timeline position, and recipe name.
Rule: restoring an invalid snapshot returns a structured error, never an implicit run.
Note: undo/redo intentionally invalidates the incremental step cache; it rebuilds on the
next run.

ADR-009 — UI language is Chinese-first with English technical terms.

ADR-010 — Push discipline: `backup` remote during development; `origin` (public) only at
approved milestone merges.

ADR-011 — Agent relay: one feature per agent, cross-review on handoff.
Reason: interleaved half-finished features are the main quality risk; boundaries matter
more than style. (Roles formalized in ADR-017.)

ADR-012 — Target frontend is React + TypeScript + Vite, built as a **parallel** frontend
under `frontend/` starting at M2 (supersedes ADR-002).
Reason: owner decision; a component frontend better serves the Process CAD UI long term.
Constraints: legacy WebUI is not deleted; React consumes stable APIs; deprecation only
after parity + regression green (M5).

ADR-013 — Python API layer target: FastAPI + Pydantic, reached by strangler migration.
Reason: typed schemas and async APIs suit the React frontend and job orchestration.
Constraints: first build a compatibility facade over the existing worker/session runtime;
standardize endpoints incrementally; API delegates to existing layers and never becomes a
source of process physics; large geometry uses binary/streaming representations.

ADR-014 — Accurate engine = C++20 ViennaPS + ViennaLS + VTK via official bindings or
pybind11 (extends ADR-003).
Reason: mature scientific libraries beat hand-rolled engines; heavy compute belongs in
compiled code.
Constraints: prototype only under `experiments/viennaps` (M8) before `ViennaPSBackend`
(M9); the app runs without ViennaPS; no per-step forced ViennaPS implementations; no
hidden repeated voxel↔level-set lossy conversions.

ADR-015 — VTK is the canonical geometry/scientific data interchange.
Reason: bridges voxel and level-set backends to the viewer with one representation.
Rule: VTP/VTU for surfaces/volumes; HDF5 or Zarr for large arrays; STL is export-only.

ADR-016 — KLayout is an optional layout engine behind `LayoutAdapter` (M6).
Reason: GDS/OASIS hierarchy, booleans, ROI extraction beyond gdstk.
Constraints: gdstk support stays; lithography receives normalized mask geometry, never
KLayout objects; KLayout never becomes a process engine.

ADR-017 — Agent roles: GLM implements, Codex reviews.
Reason: mutual review beats single-agent drift; the reviewer must not compete with the
implementer.
Rule: reviews produce a verdict + findings + repair list; fixes go back to the
implementer; `main` receives only approved merges. Owner arbitrates architecture; agent
counter-proposals are recorded as "Future Architecture Suggestion", not implemented.

ADR-018 — One concern per change.
Reason: mixed diffs (migration + physics + UI + dependency) are unreviewable and risky.
Rule: if a task forces two concerns, split the commits or the milestone.
