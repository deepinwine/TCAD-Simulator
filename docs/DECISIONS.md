# DECISIONS.md — Architecture Decision Records

Numbered, settled decisions. Agents: read before proposing alternatives.
To change a decision, open a new ADR that supersedes the old one — do not silently deviate.

---

ADR-001 — Python `ProcessModel` stays the geometry/process backend.
Reason: the voxel implementation works, is testable, and is shared by desktop, WebUI,
headless, and Agent paths.
Constraint: do not reconsider before Milestone 5.

ADR-002 — WebUI is the primary Process CAD interface for V1.
Reason: the project already ships a multi-user WebUI + Three.js viewer; a fixed three-pane
shell was delivered on top of it (Milestone 1).
Constraint: no React/Vite/Tauri/Electron migration during V1.

ADR-003 — ViennaPS / external TCAD backends deferred.
Reason: validate workflow and geometry UX on the voxel backend first.
Target: revisit after geometry primitives and viewer mature (post-M3).

ADR-004 — `tcad_simulator.py` remains the single canonical source file.
Reason: one distributable file is the project's release model; the split package is a
generated navigation aid.
Constraint: new logic still needs clear internal boundaries; full modularization is a
separate milestone, not a drive-by refactor.

ADR-005 — Recipe JSON compatibility is additive-only.
Reason: recipes are user data; breaking them breaks trust.
Rule: new optional fields + version migration; load/save round-trip must preserve step
types, order, enabled state, and instance names.

ADR-006 — Desktop GUI is maintained but not the primary CAD surface for V1.
Reason: the WebUI session/worker model fits the CAD shell better; Qt stays compatible.
Constraint: no feature may exist only in one UI's private execution path.

ADR-007 — Viewer interactions are browser-local.
Reason: camera, projection, X/Y/Z clipping, and material visibility must feel instant.
Rule: they must not trigger worker recomputes, `preview/manifest` refetches, or geometry
re-downloads. Only lightweight UI state is persisted.

ADR-008 — Timeline restore is view-only; undo/redo is atomic with metadata.
Reason: reviewing a snapshot must never silently recompute; history must restore model
state together with runtime statuses, step errors, timeline position, and recipe name.
Rule: restoring an invalid snapshot returns a structured error, never an implicit run.
Note: undo/redo intentionally invalidates the incremental step cache (entries can span
recipe edits); the cache rebuilds on the next run.

ADR-009 — UI language is Chinese-first with English technical terms.
Reason: matches the primary users; keeps domain vocabulary unambiguous.

ADR-010 — Push discipline: `backup` remote during development, `origin` only at milestone
merge.
Reason: `origin` (FonaTech) is the public release surface; feature branches are reviewed
before landing there.

ADR-011 — Agent relay: one feature per agent, cross-review on handoff.
Reason: interleaved half-finished features from multiple agents are the main quality risk
in this repo; boundaries matter more than style.
Rule: finish half-done work before starting new work; the incoming agent reviews recent
diffs against this file before continuing.
