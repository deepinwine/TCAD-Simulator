# Current Technical Debt

Last updated: 2026-09-03 (M25 start)

## ISSUE-001 — FAST→ACCURATE bridge not true geometry import
**Status**: 🔴 OPEN — M25 target
**Impact**: HybridBackend `_bridge_to_accurate()` only validates; doesn't construct ViennaPS Domain from canonical GeometryScene.
**Plan**: Implement `load_geometry_scene()` in ViennaPSBackend using `MakeTrench.MaterialLayer` stacked approach.

## ISSUE-002 — height_map Z-axis rebuild direction
**Status**: 🔴 OPEN — M25 fix
**Impact**: `HybridBackend._rebuild_voxel_derived()` may reverse wrong axis (`mask[::-1]` on axis=0 instead of axis=2).
**Plan**: Write regression test with known grid; verify height_map matches expected top-Z.

## ISSUE-003 — Material mapping silent approximation
**Status**: 🔴 OPEN — M25 fix
**Impact**: `material_mapping.py` uses `getattr(ps.Material, "TiN", ps.Material.Si)` — silently maps TiN→Si, W→Si, HfO2→SiO2.
**Plan**: Only exact mappings; unsupported materials raise `unsupported_material`.

## ISSUE-004 — Multi-material surface fallback may relabel as Silicon
**Status**: 🔴 OPEN
**Impact**: When per-level-set extraction fails, `material_surfaces()` falls back to whole-domain surface labeled Silicon.
**Plan**: Only allow Silicon fallback for single-material domains; multi-material domains raise or skip.

## ISSUE-005 — Geometry validation duplication
**Status**: 🟡 PARTIAL
**Impact**: `can_convert_to_viennaps()` and `scene_to_viennaps_layers()` have inconsistent checks.
**Plan**: Unify into `validate_scene_for_viennaps()`.

## ISSUE-006 — Metrology units mixed nm/µm
**Status**: 🟡 PARTIAL
**Impact**: `MetrologyEngine.etch_depth()` receives backend raw surfaces (µm) but ROI is nm.
**Plan**: Metrology input should be GeometryScene (nm); adapter converts µm→nm at boundary.

## ISSUE-007 — Etch depth not feature-aware (patterned trench)
**Status**: 🔴 OPEN
**Impact**: Current `etch_depth()` uses blanket surface descent, not trench ROI.
**Plan**: M28 CrossSectionEngine.

## ISSUE-008 — Process tests assert "runs" not "correct geometry"
**Status**: 🔴 OPEN
**Impact**: ALD/Directional/Selective tests only check message and non-empty surfaces.
**Plan**: M28-M30 add geometry metric assertions.

## ISSUE-009 — Scene→Voxel 41.5s @ 128³
**Status**: 🔴 OPEN — M27 target
**Impact**: Python even-odd voxelizer is performance hotspot.
**Plan**: VTK C++ pipeline or numpy vectorization.

## ISSUE-010 — Benchmark uses random triangle soup
**Status**: 🟡 PARTIAL
**Plan**: Add analytic box, Basic Trench, HAR trench benchmarks.

## ISSUE-011 — CI workflow exists but not verified on GitHub Actions
**Status**: 🟡 UNKNOWN
**Plan**: Push to backup and check Actions tab.

## ISSUE-012 — ROADMAP status drift
**Status**: 🟡 PARTIAL
**Plan**: Update after each milestone.
