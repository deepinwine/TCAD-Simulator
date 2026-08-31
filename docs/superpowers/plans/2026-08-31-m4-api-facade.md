# M4 Python API Facade 实现计划

- 日期：2026-08-31
- 分支：`codex/m4-api-facade`（基线 `31ce391`）
- 设计说明：`docs/superpowers/specs/2026-08-31-m4-api-facade-design.md`
- 纪律：TDD 先行；每任务一个提交；全套验证（vitest + tsc + build + Python 183 基线
  + Golden 五流程）通过后才提交；仅推送 `backup`。

## 任务 1：schema 层 + Facade 核心（load/init/run_step/run_all）

**文件：**

- 创建：process_api/__init__.py、schemas.py、errors.py、facade.py
- 创建：tests/test_process_api_facade.py

**步骤：**

1. 红灯：形状测试——`InitView`/`StepView`/`RunView`/`ModelSummaryView`/`MaterialView`
   序列化键名与冻结契约逐字段一致（camelCase）。
2. 红灯：facade 行为测试——load_demo → init（全 ready、factories 非空、materials
   含 Silicon）；run_all（Basic Trench @ grid 48）全部 done、revision 递增；run_step
   后续步骤 dirty；未装载时调用抛 ProcessCadError。
3. 红灯：parity 测试——facade run_all 与直接 runtime 驱动在相同网格下
   occupied_voxels、材料名集合完全一致。
4. 实现 schemas（dataclasses + `to_json` camelCase 映射）、errors、facade。
5. 全套验证；提交 `feat(M4): 建立 Python API Facade 核心与类型化 schema`。

## 任务 2：set_step 参数编辑与 dirty 级联

**步骤：**

1. 红灯：合法参数 → SetStepView（step 更新 + statuses 级联 dirty + warnings）；
   非法参数（越界/未知键）→ ProcessCadError（parameter_path、不改变模型）。
2. 实现并验证；提交 `feat(M4): Facade 参数编辑与状态级联`。

## 任务 3：Timeline 与快照恢复

**步骤：**

1. 红灯：run_to；get_timeline（item.state/runtimeStatus/snapshotValid/current）；
   restore_timeline 恢复模型与状态；无效快照抛错。
2. 实现并验证；提交 `feat(M4): Facade 时间线与快照`。

## 任务 4：Geometry manifest 与 STL

**步骤：**

1. 红灯：preview_manifest 返回 typed meshes（materialId/name/triangleCount/
   boundingBox/visual）；revision 语义与模型一致；material_stl 输出非空字节且以
   `solid` 头开始。
2. 实现并验证；提交 `feat(M4): Facade 几何清单与 STL`。

## 任务 5：FastAPI /api/v2 适配层（视依赖可用性）

**步骤：**

1. 若 FastAPI 可安装：可选依赖 + 默认关闭的 `/api/v2` 只读端点（init/manifest），
   形状复用 facade 序列化；依赖不可用则改为记录 ADR 由所有者决定引入时机。
2. 提交 `feat(M4): FastAPI v2 适配层`（或 `docs(M4): 记录适配层依赖决策`）。

## 任务 6：文档与里程碑收口

- README（process_api 用法示例）、ARCHITECTURE_TARGET（M4 交付）、ROADMAP、spec；
  全量回归；生产冒烟；提交 `docs(M4): 记录 API Facade 交付`；推送 backup，
  等待所有者合并。
