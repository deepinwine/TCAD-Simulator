# Geometry Bridge 语义约定（M13）

本文档定义 FAST（Voxel）与 ACCURATE（ViennaPS）后端之间几何交接的统一语义。
**所有 conversion 代码必须遵守本约定；修改需同步更新本文。**

## 1. Canonical Internal Unit

```text
nm（纳米）
```

- GeometryScene 内部坐标一律 nm。
- VoxelBackend 的 `voxel_size_nm` 已为 nm；`material_surfaces()` 输出 **µm**（历史约定）——在 bridge 边界乘 1000 转为 nm。
- ViennaPSBackend 的 Domain 坐标为 **µm**（`ps.Length.setUnit("um")`）——在 bridge 边界乘 1000 转为 nm。

## 2. Coordinate System

两个后端一致：

```text
+X = wafer flat direction（横向）
+Y = wafer perpendicular（横向）
+Z = process up（生长/沉积方向为正，刻蚀向下为负）
```

- Voxel `model.grid[ix, iy, iz]`：iz 增大 → z 增大（+Z up）。
- ViennaPS substrate 表面在 z=0、体在 z<0、mask/deposit 在 z>0（+Z up）。
- Three.js Viewer：camera.up = (0,0,1)，与 +Z up 一致。

**无需坐标翻转。** 若未来某引擎不一致，必须在 adapter 边界修正，不得依赖 viewer 补偿。

## 3. Material Identity

统一使用 `tcad_simulator.MaterialDatabase` 的 **整数 material ID**（0=Void, 1=Silicon, 2=SiO2, 3=SiN, 4=Photoresist, …）作为 canonical key。

| 引擎 | 表示 | 转换 |
|---|---|---|
| Voxel | `grid[ix,iy,iz] = mat_id` | 直接使用 |
| ViennaPS | `ps.Material.Si` 等枚举 | 在 ViennaPSBackend 内维护 `ps.Material ↔ mat_id` 映射表 |
| GeometryScene | `MaterialMesh.mat_id` | 直接使用 MaterialDatabase ID |

ViennaPS 映射表（代码内维护，禁止运行时猜测）：

```python
VIENNAPS_TO_MAT_ID = {
    ps.Material.Si: 1,       # Silicon
    ps.Material.SiO2: 2,     # Silicon Dioxide
    ps.Material.Si3N4: 3,    # Silicon Nitride
    ps.Material.PolySi: 5,   # Polysilicon
    ps.Material.Mask: 4,     # → Photoresist（近似）
    ps.Material.Air: 0,      # → Void
}
```

## 4. Representation Summary

| | VoxelBackend | ViennaPSBackend | GeometryScene |
|---|---|---|---|
| 核心 | `uint16 grid[ix,iy,iz]` | level-set `Domain` | `MaterialMesh(mat_id, triangles)` |
| 单位 | nm（voxel_size_nm） | µm（Domain 坐标） | **nm（canonical）** |
| +Z | up | up | up |
| 材料 | mat_id (MaterialDatabase) | ps.Material 枚举 | mat_id (MaterialDatabase) |
| 表面 | `get_material_surfaces()` → µm 三角 | `getSurfaceMesh()` → µm 顶点 | nm 三角 |
| 快照 | `snapshot_state()` bytes | `Domain.deepCopy()` | dataclass（不可变） |

## 5. Conversion Paths

### A. Voxel → GeometryScene
已有（`material_surfaces` → `GeometryScene.from_surfaces`）。补强：bridge 边界 **µm→nm ×1000**。

### B. ViennaPS → GeometryScene
已有（backend `material_surfaces`）。补强：同上 **µm→nm**。

### C. GeometryScene → Voxel（voxelization）
**新增**。将三角网格体素化为 `material_id grid`：
- 输入：GeometryScene（nm）+ 目标 grid shape + voxel_size_nm
- 算法：per-material even-odd 扫描线填充（复用 `layout/adapter.py` 的栅格化思路，扩展到 3D）
- 要求：closed manifold surface；不满足则报错（不 silent corrupt）
- 材料 precedence：后到的 mesh 覆盖先到的（模拟 stacked deposition 顺序）

### D. GeometryScene → ViennaPS（level-set）
**新增**。将多材料表面转换为 ViennaPS `Domain`（layered level-set stack）：
- 第一版支持：substrate + stacked conformal layers + trench/hole（从上到下逐层 `MakeTrench.MaterialLayer`）
- 不支持的 topology：`bridge.can_convert_to_viennaps()` 返回明确原因

## 6. HybridBackend Canonical Scene

重构后，`HybridBackend` 在每步执行后维护一个 canonical `GeometryScene`（nm）：

```text
step → route → backend.execute_step
                 ↓
       backend.material_surfaces (µm)
                 ↓ ×1000
       canonical GeometryScene (nm)
                 ↓ (if switching backend)
       bridge convert → new backend state
```

**不维护两个互相漂移的隐藏 state。** 每步完成后 canonical scene 是唯一真相。
