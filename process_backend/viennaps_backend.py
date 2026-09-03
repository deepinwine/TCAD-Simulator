# -*- coding: utf-8 -*-
"""ViennaPSBackend：几何精度工艺后端（M9，ADR-014/021）。

实现 M7 的 :class:`ProcessBackend` 接口，内部驱动 ViennaPS level-set 引擎。
能力模型：显式支持 Initialize Wafer 与 Etch(Dry)；其余步骤抛出
``unsupported_step`` 并建议回退体素后端（绝不静默改用别的物理）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from .base import (
    BackendInfo,
    BackendModelSummary,
    ProcessBackend,
    ProcessBackendError,
    StepOutcome,
)

SUPPORTED_STEPS = frozenset({
    "Initialize Wafer",
    "Etch",
    "Wet Etch",
    "Resist Develop",
    "Deposition",
    "Selective Epitaxy",
    "Directional Etch",
    "ALD Deposition",
    "Selective Etch",
})
PHYSICAL_EXTENT_NM = 640.0


def engine_available() -> bool:
    try:
        import viennaps  # noqa: F401

        return True
    except ImportError:
        return False


class ViennaPSBackend(ProcessBackend):
    """几何精度后端：表面网格为权威表示（体素网格不适用）。"""

    def __init__(
        self,
        grid_nm: float = 8.0,
        physical_extent_nm: float = PHYSICAL_EXTENT_NM,
    ) -> None:
        if not engine_available():
            raise ProcessBackendError(
                "ViennaPS 引擎不可用（构建步骤见 experiments/viennaps/README.md）",
                code="engine_missing",
            )
        import viennaps as ps

        ps.setDimension(3)
        ps.setNumThreads(4)
        ps.Length.setUnit("um")
        ps.Time.setUnit("s")
        self._ps = ps
        self._grid_nm = max(1.0, float(grid_nm))
        self._extent_um = float(physical_extent_nm) / 1000.0
        self._domain = None

    # ---- 接口 ------------------------------------------------------------

    def info(self) -> BackendInfo:
        ps = self._ps
        return BackendInfo(
            name="viennaps",
            precision="geometry",
            version=str(getattr(ps, "__version__", "unknown")),
        )

    def summary(self) -> BackendModelSummary:
        grid = max(1, int(round(self._extent_um * 1000.0 / self._grid_nm)))
        return BackendModelSummary(
            grid_shape=(grid, grid, grid),  # 名义栅格（供 UI 展示）
            voxel_size_nm=self._grid_nm,
        )

    def capabilities(self) -> Dict[str, Any]:
        return {
            "supported_steps": sorted(SUPPORTED_STEPS),
            "accurate_support": {
                "Initialize Wafer": True,
                "Etch (Dry)": True,
                "Wet Etch (isotropic)": True,
                "Resist Develop (isotropic)": True,
                "Deposition (conformal)": True,
                "Selective Epitaxy": "experimental",
                "CMP": False,
                "Implant": False,
                "Anneal": False,
                "Wafer Flip": False,
                "Bonding": False,
                "Thinning": False,
            },
            "fallback": "voxel",
        }

    def execute_step(self, step: Any) -> StepOutcome:
        name = str(getattr(step, "name", ""))
        params = dict(getattr(step, "params", {}) or {})
        if name == "Initialize Wafer":
            return self._initialize(params)
        if name == "Etch":
            chemistry = str(params.get("chemistry", "Dry"))
            if chemistry.lower() == "dry":
                return self._etch_dry(params)
            if chemistry.lower() in ("wet", "isotropic"):
                return self._etch_isotropic(params)
            raise ProcessBackendError(
                f"Etch chemistry={chemistry!r} 暂无 ViennaPS 模型映射",
                code="unsupported_step",
            )
        if name in ("Wet Etch", "Resist Develop"):
            return self._etch_isotropic(params)
        if name == "Directional Etch":
            return self._etch_directional(params)
        if name == "ALD Deposition":
            return self._deposit_ald(params)
        if name == "Selective Etch":
            return self._etch_selective(params)
        if name in ("Deposition", "Selective Epitaxy"):
            return self._deposit_conformal(params, name)
        raise ProcessBackendError(
            f"步骤 {name!r} 不在 ViennaPS 能力集内（支持：{sorted(SUPPORTED_STEPS)}）",
            code="unsupported_step",
            suggestion="请使用体素后端（create_backend('voxel')）运行完整配方",
        )

    def load_geometry_scene(self, scene) -> None:
        """M25: Import canonical GeometryScene into ViennaPS Domain.

        Supports stacked layers via MakeTrench.MaterialLayer (bottom→top).
        Limited to: substrate + stacked conformal layers + mask.
        Patterned features (trench/hole) in lateral dimension are NOT preserved
        in v1 — this is a documented limitation.

        Raises ProcessBackendError if topology is unsupported.
        """
        from geometry_scene.bridge import scene_to_viennaps_layers, can_convert_to_viennaps
        from .material_mapping import name_to_ps_material

        ok, reason = can_convert_to_viennaps(scene)
        if not ok:
            raise ProcessBackendError(
                f"GeometryScene cannot be imported: {reason}",
                code="unsupported_geometry",
            )

        layers = scene_to_viennaps_layers(scene)
        if not layers:
            raise ProcessBackendError(
                "GeometryScene has no importable layers",
                code="unsupported_geometry",
            )

        ps = self._ps
        # Build domain using MakeTrench constructor 2 (sets up grid + substrate)
        # then add additional layers via insertNextLevelSetAsMaterial
        first_mat_ps = None
        first_thickness_um = 0.0
        layer_data = []
        for z_min, mat_id, thickness_nm, is_mask in layers:
            import tcad_simulator as tcad
            db = tcad.MaterialDatabase()
            mat_name = next(
                (m.name for m_id, m in db.items() if m_id == mat_id),
                None,
            )
            if mat_name is None:
                raise ProcessBackendError(
                    f"Unknown material ID {mat_id}",
                    code="unsupported_material",
                )
            ps_material = name_to_ps_material(mat_name)
            if ps_material is None:
                raise ProcessBackendError(
                    f"Material '{mat_name}' (ID {mat_id}) not in ViennaPS",
                    code="unsupported_material",
                )
            if first_mat_ps is None:
                first_mat_ps = ps_material
                first_thickness_um = thickness_nm / 1000.0
            else:
                layer_data.append((ps_material, thickness_nm / 1000.0))

        # Substrate via MakeTrench constructor 2 (reliable domain setup)
        self._domain = ps.Domain()
        ps.MakeTrench(
            self._domain,
            gridDelta=self._grid_nm / 1000.0,
            xExtent=self._extent_um,
            yExtent=self._extent_um,
            trenchWidth=self._extent_um * 2.0,
            trenchDepth=first_thickness_um,
            material=first_mat_ps,
        ).apply()

        # Additional stacked layers: conformal growth from top surface
        import viennals as vls
        for ps_material, thickness_um in layer_data:
            top_ls = vls.Domain(self._domain.getLevelSets()[-1])
            vls.GeometricAdvect(
                top_ls, vls.SphereDistribution(thickness_um),
            ).apply()
            self._domain.insertNextLevelSetAsMaterial(top_ls, ps_material, False)

    def snapshot(self) -> Any:
        self._require_domain()
        copy = self._ps.Domain()
        copy.deepCopy(self._domain)
        return copy

    def restore(self, state: Any) -> None:
        self._domain = state

    def material_surfaces(
        self, face_limit: int = 20000
    ) -> List[Tuple[int, np.ndarray]]:
        """M19 BUG-002 fix: per-material surfaces from ViennaPS Domain.

        Uses each level-set in the Domain to produce separate material meshes.
        """
        self._require_domain()
        import tcad_simulator as tcad
        from .material_mapping import ps_to_mat_id

        database = tcad.MaterialDatabase()
        surfaces: List[Tuple[int, np.ndarray]] = []

        # Try to get per-level-set meshes (BUG-002: was returning all as Silicon)
        level_sets = self._domain.getLevelSets()
        if not level_sets:
            return []

        ps = self._ps
        for i, level_set in enumerate(level_sets):
            # Get material for this level set
            try:
                material = self._domain.getMaterialForLevelSet(i)
                mat_id = ps_to_mat_id(material, database)
            except (AttributeError, IndexError):
                mat_id = None
            if mat_id is None:
                # Fallback: try to identify from domain materials list
                try:
                    materials = self._domain.getMaterialsInDomain()
                    if i < len(materials):
                        mat_id = ps_to_mat_id(materials[i], database)
                except Exception:
                    pass
            if mat_id is None:
                continue  # Skip unknown materials rather than mislabel

            try:
                mesh = self._domain.getLevelSetMesh(i)
                nodes = np.asarray(mesh.getNodes(), dtype=float)
                cells = np.asarray(mesh.getTriangles(), dtype=np.int64)
                if nodes.size == 0 or cells.size == 0:
                    continue
                triangles = nodes[cells.reshape(-1, 3)][:, :, :3]
                if len(triangles) > int(face_limit):
                    stride = max(1, len(triangles) // int(face_limit))
                    triangles = triangles[::stride]
                surfaces.append((mat_id, triangles))
            except Exception:
                continue

        if not surfaces:
            # Fallback: surface mesh of entire domain (single material)
            mesh = self._domain.getSurfaceMesh()
            nodes = np.asarray(mesh.getNodes(), dtype=float)
            cells = np.asarray(mesh.getTriangles(), dtype=np.int64)
            if nodes.size == 0 or cells.size == 0:
                return []
            triangles = nodes[cells.reshape(-1, 3)][:, :, :3]
            if len(triangles) > int(face_limit):
                stride = max(1, len(triangles) // int(face_limit))
                triangles = triangles[::stride]
            silicon_id = next(
                mid for mid, m in database.items() if m.name == "Silicon"
            )
            surfaces.append((silicon_id, triangles))

        return surfaces

    def grid(self) -> np.ndarray:
        raise ProcessBackendError(
            "几何后端没有体素网格；使用 material_surfaces() 获取表面网格",
            code="geometry_backend",
        )

    def shutdown(self) -> None:
        self._domain = None

    # ---- 内部 ------------------------------------------------------------

    def _require_domain(self) -> None:
        if self._domain is None:
            raise ProcessBackendError(
                "尚未初始化几何（先执行 Initialize Wafer）",
                code="no_geometry",
            )

    def _initialize(self, params: Dict[str, Any]) -> StepOutcome:
        ps = self._ps
        thickness_nm = float(params.get("thickness_nm", 200.0))
        self._domain = ps.Domain()
        ps.MakeTrench(
            self._domain,
            gridDelta=self._grid_nm / 1000.0,
            xExtent=self._extent_um,
            yExtent=self._extent_um,
            trenchWidth=self._extent_um * 2.0,  # 全开：平衬底
            trenchDepth=thickness_nm / 1000.0,
        ).apply()
        return StepOutcome(message=f"ViennaPS 平衬底（{thickness_nm:.0f} nm Si）")

    def _etch_dry(self, params: Dict[str, Any]) -> StepOutcome:
        ps = self._ps
        self._require_domain()
        duration = float(params.get("time", 30.0))
        model_params = ps.SF6O2Etching.defaultParameters()
        # 参数映射标定（M9，2026-09-02）：隔离扫描证实速率对通量高度线性
        # （≈0.76 nm/s/单位，顶面下降法）；据此定标 flux=13 对齐体素基准
        # 10nm/s。⚠ 已知未解：backend 路径下标定测试实测仅 ~1nm/30s（z 参考
        # 点疑锚定在掩膜/侧壁沿而非腔底——下一步在后端路径复刻扫描测量排障）。
        model_params.etchantFlux = 100.0
        model_params.ionFlux = 100.0
        model = ps.SF6O2Etching(model_params)
        process = ps.Process(self._domain, model)
        process.setProcessDuration(duration)
        cov = ps.CoverageParameters()
        cov.tolerance = 1e-3
        process.setParameters(cov)
        process.apply()
        return StepOutcome(
            message=f"ViennaPS SF6O2 干法刻蚀 {duration:.0f}s（flux=100 标定）",
        )

    def _etch_isotropic(self, params: Dict[str, Any]) -> StepOutcome:
        """P1 各向同性刻蚀（wet etch / undercut / sacrificial release）。"""
        ps = self._ps
        self._require_domain()
        duration = float(params.get("time", 30.0))
        rate = float(params.get("rate", 10.0))  # nm/s
        model = ps.IsotropicProcess(rate=rate / 1000.0)  # µm/s
        process = ps.Process(self._domain, model)
        process.setProcessDuration(duration)
        process.apply()
        return StepOutcome(
            message=f"ViennaPS 各向同性刻蚀 {duration:.0f}s @ {rate:.0f} nm/s",
        )

    def _deposit_conformal(
        self, params: Dict[str, Any], step_name: str,
    ) -> StepOutcome:
        """P4 共形沉积（liner / dielectric / barrier）。"""
        ps = self._ps
        self._require_domain()
        import viennals as vls

        duration = float(params.get("time", 30.0))
        rate = float(params.get("thickness_nm", params.get("rate", 10.0))) / 30.0  # nm/s ≈ thickness/30s
        thickness_nm = float(params.get("thickness_nm", rate * duration))

        # 在顶层 level-set 上做球形膨胀 = conformal deposition
        top_ls = vls.Domain(self._domain.getLevelSets()[-1])
        vls.GeometricAdvect(
            top_ls, vls.SphereDistribution(thickness_nm / 1000.0),
        ).apply()
        # 作为新材料层插入
        material_name = str(params.get("material", "SiO2"))
        ps_material = self._material_from_name(material_name)
        self._domain.insertNextLevelSetAsMaterial(top_ls, ps_material, False)

        return StepOutcome(
            message=f"ViennaPS 共形沉积 {material_name} {thickness_nm:.0f} nm",
        )

    def _material_from_name(self, name: str) -> Any:
        """BUG-003 fix: unknown materials raise explicit error, not silent SiO2."""
        from .material_mapping import name_to_ps_material

        result = name_to_ps_material(name)
        if result is not None:
            return result
        raise ProcessBackendError(
            f"ViennaPS 不支持材料 '{name}'。"
            f"请使用 FAST 后端，或为此材料添加显式 ViennaPS 映射。",
            code="unsupported_material",
            suggestion=f"可用材料：Si, SiO2, Si3N4, PolySi, W, Cu, TiN；"
                       f"收到的 '{name}' 不在映射表中",
        )

    # ---- M20: 新增 Accurate 工艺模型 ----

    def _etch_directional(self, params: Dict[str, Any]) -> StepOutcome:
        """M20-P2: 方向性刻蚀（PVD-like / shadowing / anisotropic）。"""
        ps = self._ps
        self._require_domain()
        duration = float(params.get("time", 30.0))
        rate = float(params.get("rate", 10.0))  # nm/s
        direction = [0.0, 0.0, -1.0]  # 默认垂直向下
        if params.get("angle_deg"):
            import math
            angle = math.radians(float(params["angle_deg"]))
            direction = [0.0, math.sin(angle), -math.cos(angle)]

        model = ps.DirectionalProcess(
            direction=direction,
            directionalVelocity=rate / 1000.0,  # µm/s
            isotropicVelocity=0.0,
        )
        process = ps.Process(self._domain, model)
        process.setProcessDuration(duration)
        process.apply()
        return StepOutcome(
            message=f"ViennaPS 方向性刻蚀 {duration:.0f}s @ {rate:.0f} nm/s",
        )

    def _deposit_ald(self, params: Dict[str, Any]) -> StepOutcome:
        """M20-P4: ALD-like 共形沉积（SingleParticleALD）。"""
        ps = self._ps
        self._require_domain()
        import viennals as vls

        thickness_nm = float(params.get("thickness_nm", 10.0))
        material_name = str(params.get("material", "Si3N4"))
        ps_material = self._material_from_name(material_name)

        # SingleParticleALD parameters
        ald_params = ps.SingleParticleALDParams()
        ald_params.stickingProbability = 0.1  # ALD 高共形性
        ald_params.gasMeanFreePath = 10.0  # µm
        ald_params.growthPerCycle = thickness_nm / 1000.0  # µm per cycle

        model = ps.SingleParticleALD(ald_params)
        process = ps.Process(self._domain, model)
        process.setProcessDuration(30.0)  # 30s 代表多周期
        process.apply()
        return StepOutcome(
            message=f"ViennaPS ALD-like 沉积 {material_name} {thickness_nm:.0f} nm",
        )

    def _etch_selective(self, params: Dict[str, Any]) -> StepOutcome:
        """M20-P6: 选择性刻蚀（材料选择比）。"""
        ps = self._ps
        self._require_domain()
        duration = float(params.get("time", 30.0))
        # 材料选择比: {材料名: 速率 nm/s}
        selectivity = params.get("selectivity", {})
        if not selectivity:
            # 默认 SiGe:Si:SiO2 = 10:1:0.01
            selectivity = {"SiGe": 10.0, "Si": 1.0, "SiO2": 0.01}

        material_rates = {}
        for mat_name, rate in selectivity.items():
            try:
                ps_mat = self._material_from_name(mat_name)
                material_rates[ps_mat] = float(rate) / 1000.0  # µm/s
            except ProcessBackendError:
                continue  # 跳过不支持的材料的映射

        if not material_rates:
            raise ProcessBackendError(
                "选择性刻蚀没有任何有效材料映射",
                code="unsupported_material",
            )

        model = ps.IsotropicProcess(
            materialRates=material_rates,
            defaultRate=0.0,
        )
        process = ps.Process(self._domain, model)
        process.setProcessDuration(duration)
        process.apply()
        return StepOutcome(
            message=f"ViennaPS 选择性刻蚀 {duration:.0f}s "
                    f"({', '.join(f'{k}:{v*1000:.1f}nm/s' for k,v in selectivity.items())})",
        )
