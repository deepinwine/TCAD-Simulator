# M6 LayoutAdapter 设计说明

- 日期：2026-09-01
- 状态：已批准开工（所有者指令「合并 并继续」）
- 目标里程碑：M6 — KLayout LayoutAdapter
- 基线提交：`0d31acd`（backup/main，M5 已合并）

## 1. 背景与目标

光刻步骤当前只接受位图掩膜（PNG/NPY/自动生成）。M6 建立 `layout/` 包：以
**LayoutAdapter** 抽象统一 GDS/OASIS 版图进出——层级展平、布尔运算、ROI 裁剪、
以及**归一化掩膜几何 → 光刻栅格**的桥接（ADR-016）。gdstk 为必备引擎
（环境已装 1.0.1）；KLayout 为可选后端（未装时能力探测回退 gdstk）。

## 2. 约束（ADR-016 + 宪法）

- 光刻只消费**归一化掩膜几何**（nm 坐标多边形 + layer/datatype + bounds），
  绝不接触 gdstk/KLayout 对象——引擎类型不越过 `layout/adapter.py` 边界。
- KLayout 永不成为工艺引擎；缺失时全部能力由 gdstk 承接（或显式报不支持）。
- 不改动 `tcad_simulator.py` 的既有 GDS 函数（M7+ 再统一收编）；`layout/` 是并行新层。
- 单位约定：内部一律 nm；GDS 写出按 unit=1µm/precision=1nm（与既有导出一致）。

## 3. 关键设计

```text
layout/
├── __init__.py     # 公共导出
├── geometry.py     # 归一化类型（纯数据 + 纯函数：ROI 裁剪、bounds、图层过滤）
└── adapter.py      # LayoutAdapter：read/write/boolean/rasterize（引擎边界）
```

- `MaskPolygon(points_nm, layer, datatype)`；`LayoutGeometry(polygons, bounds_nm)`。
- `read(path)`：GDS/OASIS → 展平层级 → 按 (layer, datatype) 合并为归一化多边形。
- `write(geo, path)`：归一化 → GDS（单 cell 多边形直出）。
- `boolean(a, b, op)`：and/or/not/sub/xor（gdstk 布尔；KLayout 后端同语义）。
- `rasterize(geo, shape, bounds)`：even-odd 扫描线填充 → numpy 布尔栅格
  （光刻桥接：与 ExposureStep 的 custom mask 栅格语义对齐）。
- `LayoutAdapter.probe()` 返回可用后端与能力清单；默认构造用 gdstk。

## 4. 验证策略

- 纯函数（ROI 裁剪、栅格化）直接单测；适配器测试走 write→read 回环。
- 布尔运算用简单几何断言面积/包围盒。
- KLayout 后端测试在缺依赖时 skipUnless，语义与 gdstk 对等。

## 5. 任务划分

见 `docs/superpowers/plans/2026-09-01-m6-layout.md`。
