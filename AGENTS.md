# AGENTS.md — TCAD Studio Project Constitution

Every agent (GLM, Codex, Claude Code, Gemini CLI, Cursor, …) and every contributor reads
this file completely before writing any code. The long-term technology stack below is
FIXED unless the repository owner explicitly changes it.

Project: evolving `deepinwine/TCAD-Simulator` (from the FonaTech prototype) into
**TCAD Studio** — a maintainable semiconductor virtual fabrication / Process CAD platform.

## 1. Target Technology Stack (fixed)

| Layer | Technology | Notes |
| --- | --- | --- |
| Frontend | React + TypeScript + Vite | Process Flow editor, parameter forms, material tree, timeline, job state, metrology UI |
| 3D Viewer | Three.js | Rendering only — orbit/pan/zoom, persp/ortho, X/Y/Z clipping, visibility, selection, measurement |
| Application layer | Python — 3.10+ compatible today; 3.12+ target for the new API/application modules (M4+, see ARCHITECTURE_TARGET) | Recipe, ProcessStep, project/session state, backend routing, jobs, materials, metrology, AI recipes, serialization, API, snapshots |
| Fast geometry | existing voxel `ProcessModel` | Preserved as Fast Mode backend until equivalent regression coverage exists |
| Accurate engine | C++20 + ViennaPS + ViennaLS + VTK (+ OpenMP) | Integrated via official Python bindings / pybind11 |
| Geometry interchange | VTK (VTP/VTU; HDF5/Zarr for large arrays) | STL is export-only, never canonical |
| Layout / mask | gdstk (kept) + future KLayout `LayoutAdapter` | KLayout is a layout engine, never a process engine |

## 2. Architectural Direction

```text
React / Three.js
    | HTTP / WebSocket
    v
Python Application Layer
    v
Recipe / ProcessStep
    v
Backend Router  ──────────────┐
    |                         |
    v                         v
Voxel Backend (FAST)    ViennaPS Backend (ACCURATE)
    |                         |
    └───────────┬─────────────┘
                v
        Geometry / VTK
                v
            Three.js

GDS / OASIS -> gdstk / KLayout -> Mask Geometry -> Process Recipe / Backend
```

## 3. Existing Compatibility Boundary (must keep working)

```text
Recipe -> PROCESS_STEP_FACTORIES -> ProcessStep.execute(model) -> ProcessModel
```

This protocol currently serves desktop UI, WebUI, headless simulation, recipe
serialization, Agent-generated recipes, and selftests. Do NOT break it casually;
during migration, compatibility adapters are preferred over rewrites.

## 4. Current Source Of Truth

- `tcad_simulator.py` remains the canonical implementation until an explicit migration
  milestone changes that. Do NOT mass-extract the monolith for aesthetics.
- New modules may be created when they establish a real architectural boundary.
- The React frontend lives in `frontend/` as a **parallel client**; the legacy WebUI
  stays functional until React passes feature parity (see roadmap M5).

## 5. Boundaries

- **Frontend**: operates on application/API state; sends process requests
  (`{"type":"deposit","material":"SiO2","thickness_nm":100}`); never computes geometry,
  never mutates voxel arrays, never duplicates process algorithms in JS.
- **Three.js**: renders returned geometry. Does not deposit, etch, CMP, or own physics.
- **Python**: the application brain — recipe, steps, jobs, snapshots, materials, state,
  routing, persistence, metrology orchestration, LLM workflows. Python is not required
  to implement all heavy simulation; that belongs in compiled libraries.
- **C++**: use mature scientific libraries (ViennaPS/ViennaLS/VTK) via adapters. Do not
  hand-roll a C++ TCAD engine; do not rewrite ViennaPS or VTK functionality in Python.
- **KLayout**: behind `LayoutAdapter`; lithography receives normalized mask geometry,
  never KLayout objects; gdstk support is not removed.
- **ViennaPS**: optional backend behind an adapter; the app must run without it;
  unsupported steps get explicit capability/fallback behavior; no hidden repeated
  voxel↔level-set lossy conversions; never wired directly into every ProcessStep.

## 6. Fast vs Accurate Modes (guidance)

- FAST / voxel: ideal blanket deposition, ideal CMP, fill, wafer flip, bonding, thinning.
- ACCURATE / ViennaPS: HAR plasma etch, wet undercut, ALD conformality, directional flux
  deposition, selective etching, redeposition — wherever voxel geometry is insufficient.

## 7. DO NOT

- Rewrite the project from scratch; replace `ProcessModel` before regression coverage exists.
- Implement semiconductor process physics in React/JavaScript/Three.js.
- Replace the existing recipe format without migration support.
- Remove gdstk when introducing KLayout; embed ViennaPS throughout ProcessStep classes;
  force every ProcessStep to have a ViennaPS implementation.
- Mix architecture migration + physics changes + UI redesign in the same commit.
- Repository-wide formatting during feature work; unrelated refactors in a feature diff.
- Create alternative abstractions when equivalent ones already exist.
- Introduce CUDA as a mandatory dependency.
- Claim foundry-calibrated physical accuracy without validation data.
- Delete or weaken tests. Push to `origin` during milestone development (`backup` only).
- Commit runtime data (`TCAD_Web_Data/`, selftest outputs, split artifacts).

## 8. Working Discipline

- One milestone at a time; one feature per agent, end-to-end (test → code → docs → commit).
- If another agent left a feature half-done, finish it first — do not start new work beside it.
- TDD: failing test → implementation → all green. Never lower assertions.
- Baseline suite (run with `TCAD_SKIP_QT=1 MPLBACKEND=Agg`, `PYTHONPYCACHEPREFIX` outside
  the worktree): `python3 -m unittest tests.test_process_cad_foundation
  tests.test_process_cad_primitives tests.test_process_cad_demos
  tests.test_webui_viewer_contract tests.test_webui_cad_shell`
- Compile: `python3 -m py_compile tcad_simulator.py tools/*.py`.
- Performance: `tools/run_process_cad_baseline.py --grid 128 --output <json>` must exit 0.
- Commits: small, typed, Chinese scope — `feat(域): 描述` / `fix(域): …` / `test(域): …` /
  `docs(域): …`. Every diff must be justifiable by its feature.
- Branches: feature branches per milestone (`feature/m1-process-cad`, `feature/react-shell`,
  …). `main` receives only reviewed, approved merges. Worktrees live under
  `~/.config/superpowers/worktrees/TCAD-Simulator/<owner>/<branch>`.
- Plan documents quote line numbers that drift — locate code by content.
- UI copy is Chinese-first with English technical terms.
- If you see a better architecture: write it under "Proposed Future Improvement";
  do not implement it unless the approved milestone requires it.

## 9. Agent Roles & Review Loop

- **GLM is the primary implementation engineer.** Implements approved milestones; does not
  redesign architecture on personal preference.
- **Codex is the architecture and code reviewer.** Reviews diffs (not just final files)
  against this file, `docs/ARCHITECTURE_TARGET.md`, `docs/ROADMAP_PROCESS_CAD.md`,
  `docs/DECISIONS.md`, and tests. Does NOT replace implementations with its own version;
  outputs a review with verdict `APPROVE` / `APPROVE WITH NON-BLOCKING COMMENTS` /
  `REQUEST CHANGES`, blocking findings (BLOCK-001…), non-blocking (NB-001…), boundary
  compliance marks (PASS/WARN/FAIL), regression assessment, and an ordered repair list.
  Re-review after fixes covers only the blocking areas and new diff.
- Loop: GLM implements → commit → Codex review → (fix → re-review) → merge → next milestone.

### Definition of Done (per milestone)

implementation + feature tests + regression tests green + minimal coherent diff +
documented architecture decisions + Codex review + blocking findings resolved + final pass.

### Handoff report (GLM → Codex, per milestone)

Goal / Changed Files / Architecture Decisions / Existing APIs Reused / Tests Added /
Tests Executed (exact commands + results) / Known Limitations / Risks / Diff Summary /
Reviewer Checklist.

## 10. Key Documents

- `docs/ARCHITECTURE_TARGET.md` — target architecture and migration strategy.
- `docs/ROADMAP_PROCESS_CAD.md` — milestones M0–M12 and current status.
- `docs/DECISIONS.md` — numbered ADRs; do not relitigate casually; supersede via new ADR.
- `docs/ARCHITECTURE.md`, `docs/WEBUI_RUNTIME.md`, `docs/ALGORITHMS.md` — current system.
- `docs/superpowers/specs|plans/` — milestone designs and task plans (checkboxes unmaintained;
  git history is the progress record).
