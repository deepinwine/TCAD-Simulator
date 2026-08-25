# Process CAD 工艺原语实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 新增独立的 Strip、Fill、Wafer Flip、Bonding 和 Thinning 工艺步骤，并提供 Basic Trench、Spacer Formation、Bonding + Thinning 三个可运行 demo。

**架构：** 每个新步骤继承 `ProcessStep`，只做参数声明、校验和调用；体素变换位于 `ProcessModel`。所有空间共址的 3D 物理场通过统一 helper 变换，避免 Wafer Flip 后材料与掺杂/缺陷错位。

**技术栈：** Python 3.13、NumPy、SciPy `ndimage`、标准库 `unittest`、现有 ProcessStep 工厂与 demo recipe API。

---

### 任务 1：建立工艺原语测试夹具

**文件：**
- 创建：`tests/test_process_cad_primitives.py`

- [ ] **步骤 1：创建小网格模型 helper**

```python
import unittest

import numpy as np

import tcad_simulator as tcad


def make_model(shape=(10, 10, 16)):
    db = tcad.MaterialDatabase()
    model = tcad.ProcessModel(db, grid_shape=shape, voxel_size_nm=10.0)
    model.grid.fill(0)
    model._rebuild_height_map()
    return db, model
```

- [ ] **步骤 2：验证空测试模块可加载**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives`

预期：退出码 0，输出 `Ran 0 tests` 和 `OK`。

- [ ] **步骤 3：Commit**

```bash
git add tests/test_process_cad_primitives.py
git commit -m "test(工艺原语): 建立小网格测试夹具"
git push backup HEAD:codex/process-cad-shell
```

### 任务 2：实现 Strip

**文件：**
- 修改：`tcad_simulator.py:13980-14610`
- 修改：`tcad_simulator.py:19018-19100`
- 测试：`tests/test_process_cad_primitives.py`

- [ ] **步骤 1：编写全局与暴露连通 Strip 失败测试**

```python
class StripTests(unittest.TestCase):
    def test_global_strip_removes_only_selected_material(self):
        db, model = make_model()
        oxide = db.id("Silicon Dioxide")
        resist = db.id("Photoresist")
        model.grid[:, :, :4] = oxide
        model.grid[2:8, 2:8, 4:6] = resist
        removed = model.strip_materials(["Photoresist"], exposed_only=False)
        self.assertEqual(removed, 6 * 6 * 2)
        self.assertFalse(np.any(model.grid == resist))
        self.assertTrue(np.any(model.grid == oxide))

    def test_exposed_strip_keeps_sealed_pocket(self):
        db, model = make_model()
        oxide = db.id("Silicon Dioxide")
        resist = db.id("Photoresist")
        model.grid[1:9, 1:9, 1:9] = oxide
        model.grid[3:5, 3:5, 3:5] = resist
        model.grid[6:8, 6:8, 8:10] = resist
        model.strip_materials(["Photoresist"], exposed_only=True, direction="top")
        self.assertTrue(np.any(model.grid[3:5, 3:5, 3:5] == resist))
        self.assertFalse(np.any(model.grid[6:8, 6:8, 8:10] == resist))
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.StripTests`

预期：FAIL，`strip_materials` 尚未定义。

- [ ] **步骤 3：实现模型操作**

```python
def strip_materials(self, materials: Sequence[Any], exposed_only: bool = False, direction: str = "top") -> int:
    ids = {int(self.material_db.id(value)) for value in materials}
    target = np.isin(self.grid, np.fromiter(ids, dtype=np.uint16))
    if bool(exposed_only):
        void = self.grid == 0
        seed = np.zeros_like(void, dtype=bool)
        seed[:, :, -1 if str(direction).lower() == "top" else 0] = True
        reachable_void = ndimage.binary_propagation(seed, mask=void)
        exposed = ndimage.binary_dilation(reachable_void) & target
        removable = ndimage.binary_propagation(exposed, mask=target)
    else:
        removable = target
    removed = int(np.count_nonzero(removable))
    self.grid[removable] = np.uint16(0)
    self._rebuild_height_map()
    self._refresh_open_mask()
    self._invalidate_mesh_cache()
    return removed
```

- [ ] **步骤 4：增加 `StripStep` 与工厂项**

`StripStep.parameter_specs()` 定义 `materials`（分号分隔）、`exposed_only` 和 `direction`；`execute()` 将材料字符串拆为非空列表并拒绝 `Void`。

- [ ] **步骤 5：运行测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.StripTests
git add tcad_simulator.py tests/test_process_cad_primitives.py
git commit -m "feat(工艺): 添加独立 Strip 步骤"
git push backup HEAD:codex/process-cad-shell
```

预期：2 个 Strip 测试 PASS。

### 任务 3：实现 Fill

**文件：**
- 修改：`tcad_simulator.py:11611-11710`
- 修改：`tcad_simulator.py:19018-19110`
- 测试：`tests/test_process_cad_primitives.py`

- [ ] **步骤 1：编写连通 void Fill 测试**

```python
class FillTests(unittest.TestCase):
    def test_fill_open_trench_without_filling_sealed_void(self):
        db, model = make_model((12, 12, 18))
        silicon = db.id("Silicon")
        copper = db.id("Copper")
        model.grid[:, :, :10] = silicon
        model.grid[2:5, 2:5, 5:10] = 0
        model.grid[8:10, 8:10, 3:5] = 0
        filled = model.fill_voids("Copper", max_depth_nm=60.0, direction="top", include_sealed=False)
        self.assertGreater(filled, 0)
        self.assertTrue(np.any(model.grid[2:5, 2:5, :] == copper))
        self.assertFalse(np.any(model.grid[8:10, 8:10, 3:5] == copper))
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.FillTests`

预期：FAIL，`fill_voids` 尚未定义。

- [ ] **步骤 3：实现几何 Fill**

```python
def fill_voids(self, material: Any, max_depth_nm: float, direction: str = "top", include_sealed: bool = False) -> int:
    material_id = np.uint16(self.material_db.id(material))
    depth_voxels = max(1, int(math.ceil(float(max_depth_nm) / float(self.voxel_size_nm))))
    void = self.grid == 0
    occupied_z = np.flatnonzero(np.any(self.grid != 0, axis=(0, 1)))
    if occupied_z.size == 0:
        return 0
    seed = np.zeros_like(void, dtype=bool)
    top = str(direction).lower() == "top"
    seed[:, :, -1 if top else 0] = True
    reachable = void if bool(include_sealed) else ndimage.binary_propagation(seed, mask=void)
    z = np.arange(self.grid.shape[2])[None, None, :]
    surface = int(occupied_z[-1] if top else occupied_z[0])
    if top:
        cavity_region = z <= surface
        depth_mask = z >= max(0, surface - depth_voxels + 1)
    else:
        cavity_region = z >= surface
        depth_mask = z <= min(self.grid.shape[2] - 1, surface + depth_voxels - 1)
    fill_mask = reachable & cavity_region & depth_mask
    count = int(np.count_nonzero(fill_mask))
    self.grid[fill_mask] = material_id
    self._rebuild_height_map()
    self._refresh_open_mask()
    self._invalidate_mesh_cache()
    return count
```

- [ ] **步骤 4：增加 `FillStep` 与参数验证**

参数为 `material`、`max_depth_nm`、`direction`、`include_sealed`；深度必须大于 0，材料不能是 `Void`。

- [ ] **步骤 5：运行测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.FillTests
git add tcad_simulator.py tests/test_process_cad_primitives.py
git commit -m "feat(工艺): 添加连通空隙 Fill 步骤"
git push backup HEAD:codex/process-cad-shell
```

### 任务 4：实现 Wafer Flip 与 3D 物理场同步

**文件：**
- 修改：`tcad_simulator.py:7381-8554`
- 修改：`tcad_simulator.py:19018-19120`
- 测试：`tests/test_process_cad_primitives.py`

- [ ] **步骤 1：编写材料与物理场同步测试**

```python
class WaferFlipTests(unittest.TestCase):
    def test_flip_reverses_grid_and_spatial_fields(self):
        _db, model = make_model((4, 4, 6))
        model.grid[:, :, 1] = 2
        model.grid[:, :, 4] = 3
        model.doping = np.zeros(model.grid.shape, dtype=np.float32)
        model.doping[:, :, 1] = 7.0
        before_grid = model.grid.copy()
        before_doping = model.doping.copy()
        model.flip_wafer()
        np.testing.assert_array_equal(model.grid, np.flip(before_grid, axis=2))
        np.testing.assert_array_equal(model.doping, np.flip(before_doping, axis=2))
        self.assertEqual(model.active_side, "bottom")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.WaferFlipTests`

预期：FAIL，`flip_wafer` 或 `active_side` 尚未定义。

- [ ] **步骤 3：建立空间字段白名单**

```python
def _spatial_volume_field_names(self) -> Tuple[str, ...]:
    return (
        "doping", "active_dopants", "interstitials", "vacancies",
        "cluster_interstitial", "cluster_bic", "damage_concentration",
        "temperature", "defects_interstitial", "defects_vacancy",
    )
```

`dopant_species_fields` 和 `_resist_state` 中 3D 数组单独遍历；2D `open_mask`、`resist_exposure` 与 `last_intensity` 不沿 Z 翻转。

- [ ] **步骤 4：实现 `flip_wafer`**

```python
def flip_wafer(self) -> None:
    self.grid = np.flip(self.grid, axis=2).copy()
    for name in self._spatial_volume_field_names():
        value = getattr(self, name, None)
        if isinstance(value, np.ndarray) and value.shape == self.grid.shape:
            setattr(self, name, np.flip(value, axis=2).copy())
    for key, value in list(getattr(self, "dopant_species_fields", {}).items()):
        if isinstance(value, np.ndarray) and value.shape == self.grid.shape:
            self.dopant_species_fields[key] = np.flip(value, axis=2).copy()
    self.active_side = "bottom" if getattr(self, "active_side", "top") == "top" else "top"
    self._rebuild_height_map()
    self._refresh_open_mask()
    self._invalidate_mesh_cache()
```

在 `snapshot_state` / `restore_state` 增加可选 `active_side`，默认 `top`。

- [ ] **步骤 5：增加 `WaferFlipStep`、运行测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.WaferFlipTests
git add tcad_simulator.py tests/test_process_cad_primitives.py
git commit -m "feat(工艺): 添加物理场同步 Wafer Flip"
git push backup HEAD:codex/process-cad-shell
```

### 任务 5：实现 Bonding

**文件：**
- 修改：`tcad_simulator.py:7381-8554`
- 修改：`tcad_simulator.py:19018-19130`
- 测试：`tests/test_process_cad_primitives.py`

- [ ] **步骤 1：编写键合层与 handle wafer 测试**

```python
class BondingTests(unittest.TestCase):
    def test_bonding_adds_interface_and_handle_on_active_side(self):
        db, model = make_model((6, 6, 20))
        silicon = db.id("Silicon")
        oxide = db.id("Silicon Dioxide")
        model.grid[:, :, :4] = silicon
        result = model.bond_wafer(
            handle_material="Silicon",
            handle_thickness_nm=40.0,
            bonding_material="Silicon Dioxide",
            bonding_layer_nm=10.0,
        )
        self.assertEqual(result["bond_voxels"], 1)
        self.assertEqual(result["handle_voxels"], 4)
        self.assertTrue(np.any(model.grid == oxide))
        self.assertGreater(np.count_nonzero(model.grid == silicon), 6 * 6 * 4)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.BondingTests`

预期：FAIL，`bond_wafer` 尚未定义。

- [ ] **步骤 3：实现单模型堆叠键合**

`bond_wafer()` 将 nm 转换为至少一个 voxel，检查剩余 Z 空间，在 `active_side` 的外露边界依次放置键合层和 handle wafer。若空间不足，抛出包含所需/可用 voxel 数的 `ValueError`；不得覆盖现有非 Void 体素。

核心写入采用完整切片而不是逐体素循环：

```python
self.grid[:, :, bond_slice] = np.where(
    self.grid[:, :, bond_slice] == 0,
    bond_id,
    self.grid[:, :, bond_slice],
)
self.grid[:, :, handle_slice] = np.where(
    self.grid[:, :, handle_slice] == 0,
    handle_id,
    self.grid[:, :, handle_slice],
)
```

- [ ] **步骤 4：增加 `BondingStep` 与参数**

参数为 `handle_material`、`handle_thickness_nm`、`bonding_material`、`bonding_layer_nm`；两个厚度分别验证为大于 0 和大于等于 0。

- [ ] **步骤 5：运行测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.BondingTests
git add tcad_simulator.py tests/test_process_cad_primitives.py
git commit -m "feat(工艺): 添加单模型 Wafer Bonding"
git push backup HEAD:codex/process-cad-shell
```

### 任务 6：实现 Thinning

**文件：**
- 修改：`tcad_simulator.py:13984-14323`
- 修改：`tcad_simulator.py:19018-19140`
- 测试：`tests/test_process_cad_primitives.py`

- [ ] **步骤 1：编写 active-side-aware 减薄测试**

```python
class ThinningTests(unittest.TestCase):
    def test_thinning_uses_backside_after_flip(self):
        db, model = make_model((5, 5, 16))
        silicon = db.id("Silicon")
        model.grid[:, :, :10] = silicon
        model.flip_wafer()
        removed = model.thin_wafer(target_thickness_nm=50.0, material="Silicon")
        self.assertEqual(removed, 5 * 5 * 5)
        silicon_z = np.flatnonzero(np.any(model.grid == silicon, axis=(0, 1)))
        self.assertEqual(len(silicon_z), 5)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.ThinningTests`

预期：FAIL，`thin_wafer` 尚未定义。

- [ ] **步骤 3：实现减薄**

`thin_wafer()` 根据 `active_side` 推导 backside，从该端只移除目标材料，直到目标材料的投影厚度等于 `ceil(target_thickness_nm / voxel_size_nm)`；目标厚度大于当前厚度时返回 0，小于等于 0 时抛出 `ValueError`。

- [ ] **步骤 4：增加 `ThinningStep`、运行测试并 Commit**

```bash
/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives.ThinningTests
git add tcad_simulator.py tests/test_process_cad_primitives.py
git commit -m "feat(工艺): 添加背面感知 Wafer Thinning"
git push backup HEAD:codex/process-cad-shell
```

### 任务 7：增加三个示例配方与 headless 验收

**文件：**
- 修改：`tcad_simulator.py:60123-60550`
- 修改：`tcad_simulator.py:88380-88680`
- 创建：`tests/test_process_cad_demos.py`

- [ ] **步骤 1：编写 demo 注册测试**

```python
import unittest

import tcad_simulator as tcad


class ProcessCadDemoTests(unittest.TestCase):
    def test_required_demo_names_exist(self):
        demos = tcad._webui_demo_recipes(tcad.MaterialDatabase())
        self.assertTrue({"Basic Trench", "Spacer Formation", "Bonding + Thinning"}.issubset(demos))

    def test_each_demo_uses_known_factories(self):
        demos = tcad._webui_demo_recipes(tcad.MaterialDatabase())
        for name in ("Basic Trench", "Spacer Formation", "Bonding + Thinning"):
            for step in demos[name]["steps"]:
                self.assertIn(step["name"], tcad.PROCESS_STEP_FACTORIES)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_demos`

预期：FAIL，缺少 `_webui_demo_recipes` 或三个名称。

- [ ] **步骤 3：把 demo 定义集中到纯函数**

`_webui_demo_recipes(material_db)` 返回名称到 `{description, steps}` 的字典。三条序列严格采用设计文档第 10 节，并使用小于 128³ 时仍能产生可见体素的厚度参数。

- [ ] **步骤 4：增加 headless 运行断言**

为每个 demo 构造 `ProcessModel(grid_shape=(64,64,96), voxel_size_nm=10.0)`，依序执行启用步骤；断言无异常、至少两种非 Void 材料、最终包围盒非空。Bonding demo 额外断言 `active_side` 和目标剩余厚度。

- [ ] **步骤 5：运行原语与 demo 测试**

运行：`/opt/anaconda3/bin/python3 -m unittest -v tests.test_process_cad_primitives tests.test_process_cad_demos`

预期：所有测试 PASS。

- [ ] **步骤 6：验证并 Commit**

```bash
git diff --check
git add tcad_simulator.py tests/test_process_cad_demos.py
git commit -m "feat(示例): 添加三套 Process CAD 工艺配方"
git push backup HEAD:codex/process-cad-shell
```
