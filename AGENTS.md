# AGENTS.md — Project Constitution for Coding Agents

Read this file completely before writing any code in this repository.
It applies to every agent (Codex, GLM, Claude Code, Gemini CLI, Cursor, …) and every human contributor.

## Project Mission

Lightweight Semiconductor Process CAD — a process-engineer-facing virtual fabrication
workbench: Process Flow + Step Parameters + Interactive 3D Structure + Process Timeline.
Target users: process engineers, device R&D, patent engineers, process education.

## Source Of Truth

- `tcad_simulator.py` (~100k lines, single file) is the canonical implementation.
- `tcad_simulator_split/` is a generated developer view, never edit it.
- Plans/specs live in `docs/superpowers/`; architecture docs in `docs/`.
- Tests live in `tests/`; they are the behavioral contract — never delete or weaken one.

## Architecture Contract (must keep)

```text
Recipe / UI  (PyQt5 desktop | WebUI | Headless | Agent)
    ↓
PROCESS_STEP_FACTORIES
    ↓
ProcessStep.execute(model)      ← the only step protocol, shared by all interfaces
    ↓
ProcessModel                    ← the only voxel/process truth (grid, fields, snapshots)
    ↓
Geometry / caches / per-material .geom meshes
    ↓
Viewer / metrology / export
```

Rules:

1. All process physics and voxel mutation live in `ProcessModel` (or model helpers).
   `ProcessStep` subclasses only validate parameters and call the model.
2. UI (Qt or browser JS) collects parameters and displays results. UI never mutates the
   voxel grid and never re-implements process logic in JavaScript.
3. Never create a parallel execution path (e.g. `GeometryService`/`VoxelEngine` next to
   `ProcessModel`). One feature must not end up split across old and new systems.
4. Browser-local interactions (camera, projection, clipping planes, material visibility)
   must not trigger worker recomputes or geometry refetches.
5. Recipe JSON evolves additively: new optional fields + version migration only.
   Old recipes must always load, run, and round-trip.

## DO NOT

- Rewrite or re-architect working code because you would have designed it differently.
- Replace the tech stack (React/Vue/Electron/Tauri/Rust, heavy TCAD backends) — see DECISIONS.md.
- Duplicate process logic (no second deposition/etch implementation for a second UI).
- Put process physics in JS or Qt widgets.
- Break recipe compatibility or remove/weaken tests.
- Reformat, rename, or move large code regions unrelated to your task (minimal coherent diff).
- Push to `origin` (FonaTech) during milestone development; push to `backup` only.
- Commit runtime data (`TCAD_Web_Data/`, selftest outputs, split artifacts) — see `.gitignore`.

## Current Priority (V1)

Process CAD UI → 3D Viewer fidelity → Timeline review → geometry fidelity →
advanced process steps → ViennaPS later (see `docs/ROADMAP_PROCESS_CAD.md`).

## Working Discipline

- TDD: write the failing test first, implement, keep all tests green. Never lower assertions.
- Baseline before/after: the full suite is
  `python3 -m unittest tests.test_process_cad_foundation tests.test_process_cad_primitives tests.test_process_cad_demos tests.test_webui_viewer_contract tests.test_webui_cad_shell`
  (run with `TCAD_SKIP_QT=1 MPLBACKEND=Agg`; keep `PYTHONPYCACHEPREFIX` out of the worktree).
- Compile check: `python3 -m py_compile tcad_simulator.py tools/*.py`.
- Performance baseline: `tools/run_process_cad_baseline.py --grid 128 --output <json>` must exit 0.
- Commits: small, typed, Chinese scope — `feat(域): 描述` / `fix(域): …` / `test(域): …` / `docs(域): …`.
  Every diff must be justifiable by its feature.
- Each milestone works in its own worktree + branch under
  `~/.config/superpowers/worktrees/TCAD-Simulator/<owner>/<branch>`; verified commits are pushed
  to `backup`. Do not work directly on `main`.
- Plan documents quote line numbers that drift; locate code by content, not by line number.
- UI copy is Chinese-first with English technical terms (Deposition, Etch, CMP, WebGL2 …).

## Multi-Agent Relay Protocol

1. One feature is completed end-to-end by ONE agent (tests → implementation → docs → commit).
2. If another agent left a feature half-done, finishing it is the first task.
   Do not start three new things next to a half-finished one.
3. Different naming/style between agents is acceptable; broken architecture boundaries are not.
   Control the boundary (UI → ProcessStep → ProcessModel), not the variable names.
4. On handoff, the incoming agent first performs a review pass: read recent commits and diffs,
   check them against this file, `docs/ROADMAP_PROCESS_CAD.md`, and `docs/DECISIONS.md`,
   fix violations, then continue the next task.
5. Suggested first message to an agent resuming after another agent's work:

   > Another agent has continued development. First run a handoff audit:
   > `git log`, `git diff`, test baseline. Review the recent changes against
   > AGENTS.md / docs/DECISIONS.md / docs/ROADMAP_PROCESS_CAD.md for architecture
   > violations before writing new code. Report findings, then continue the next task.

## Key Documents

- `docs/ROADMAP_PROCESS_CAD.md` — milestones and current status.
- `docs/DECISIONS.md` — numbered decisions (ADRs). Do not relitigate them casually.
- `docs/ARCHITECTURE.md`, `docs/WEBUI_RUNTIME.md`, `docs/ALGORITHMS.md` — how things work.
- `docs/superpowers/specs/` — milestone design docs (acceptance criteria).
- `docs/superpowers/plans/` — task-level implementation plans (checkboxes are not maintained;
  real progress is the git history).
