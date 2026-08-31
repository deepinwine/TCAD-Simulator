# M3 Viewer 完善设计说明

- 日期：2026-08-31
- 状态：已实现（M3 交付于 `codex/m3-viewer`，详见 `docs/ROADMAP_PROCESS_CAD.md`）
- 目标里程碑：M3 — Three.js Viewer (React)
- 基线提交：`8b2d4c0`（backup/main，M2 已合并）

## 1. 背景与目标

M2 交付了最小真实网格查看器：manifest/STL 按修订加载、ISO/六视图、旋转/平移/缩放、
按需渲染、相机操作零 API 请求。M3 在不扩大后端契约的前提下补齐工程师日常工作所需
的查看能力：

1. 透视/正交投影切换（CAD 检视常需正交视图）。
2. X/Y/Z 独立裁剪平面（查看内部结构）。
3. 材料级显示控制（可见性/透明度，数据来自 manifest 的 `visual` 字段）。
4. 选择与测量（点选网格显示信息；两点距离测量）。
5. run/all 长 POST 静默期连接中断的状态对账（M2 验收发现的 Known Limitation）。

## 2. 约束

- **冻结契约不动**：M3 全部为浏览器本地能力，不新增/修改任何后端端点。
- 相机、裁剪、材料显示、测量均不产生 `/api` 请求（沿用 M2 的零请求验证法）。
- 所有几何参数（包围盒）来自已加载网格本身，不额外请求。
- 旧 WebUI 不动（ADR-012）。

## 3. 关键设计

### 3.1 投影切换

- `fitCamera.ts` 新增 `calculateOrthographicFit(bounds, viewAspect)`：以包围球半径
  推导 frustum 半宽/高（宽高比取容器 aspect，保持与透视 fit 相同的目标/方向语义），
  near/far 给充足余量（near = -4×radius，far = 8×radius 量级）。
- `viewerRuntime` 维护 `perspective` 与 `orthographic` 两个 camera；切换时保留当前
  方向与 target，正交 zoom 由等效视尺寸推导，OrbitControls 换绑后 `change` 仍驱动
  同一 `scheduleRender`。
- UI：查看器工具栏新增「透视/正交」切换按钮（aria-pressed 表状态）。

### 3.2 裁剪平面

- 状态：每轴 `{enabled, position}`，position 以包围盒 min/max 归一化（UI 滑杆 0..1）。
- 实现：`renderer.localClippingEnabled = true`；所有材质挂 `clippingPlanes`（启用轴
  的 `THREE.Plane`，法向沿轴负向，位置由归一化值映射回世界坐标）。
- UI：三轴滑杆 + 启用开关，置于查看器工具栏可折叠区。

### 3.3 材料显示控制

- 数据源：meshLoader 已返回 manifest 的 `visual`（visible/opacity 等）。
- 状态存 React（`Record<matId, {visible, opacity}>`），变更仅作用于对应 mesh 的
  `material.opacity/transparent/visible`，不回写后端。
- UI：Viewer 内材料列表面板（名称 + 可见性开关 + 透明度滑杆）。

### 3.4 选择与测量

- 点击（无拖拽位移阈值内）→ `Raycaster` 求交 → 高亮命中 mesh（emissive 提亮）并
  显示材料名/三角数信息条。
- 测量模式：两次点击取表面点，画线 + 距离标签（HTML overlay，世界坐标投影）。
- 全部本地，无 API。

### 3.5 run/all 网络失败对账

- `run/failed` 且 `error.code === 'network_error'` 时，错误条提供「重新同步」动作：
  依次重拉 `timeline/get` + `preview/manifest`，以服务端权威状态覆盖本地（服务端可能
  已完成运行——M2 验收实测此场景）。

## 4. 任务划分

见 `docs/superpowers/plans/2026-08-31-m3-viewer.md`。每任务独立提交、TDD、全量回归。
