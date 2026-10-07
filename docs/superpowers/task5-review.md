# Task 5 集成复审

审查范围：`10d9c20..3ff4d0b`，包含 main 的 DRAM 示例改动。

Verdict：APPROVE WITH NON-BLOCKING COMMENTS。无未解决 BLOCK。

BLOCK-001 已在 `3ff4d0b` 修复：Exposure 默认空资产绑定不再触发读取；仅 Asset
模式、非空 ID、正整数 revision 读取已有资产。两项测试先失败，修复后通过。

## 边界合规

| 边界 | 结论 |
|---|---|
| 固定架构与职责 | PASS |
| 旧 Recipe 与参数兼容 | PASS |
| 语言切换与工作状态 | PASS |
| canonical 单位 | PASS |
| Etch 能力与执行 | PASS |
| Mask revision 与原子恢复 | PASS |
| Layout 与可选依赖 | WARN：NB-002 |
| Workbench、viewer 与导入 | WARN：NB-001 |

## 非阻断意见与回归风险

1. NB-001：MaskControl 预览 URL 未包含资产 ID/revision，同名资产保存后小预览
   可能保持旧图片。后续加入版本并在绑定变化时清除 previewFailed。
2. NB-002：工作台文件选择包含 `.gdsii`，后端支持 `.json/.gds/.oas`；后续统一列表。

以上不阻断实际资产保存、绑定、工艺执行及三维结构更新。未发现 canonical 漂移、
参数静默忽略、失败半提交或 viewer 卸载问题。先处理 NB-001，再处理 NB-002。

最终验证数字记录在 ROADMAP_PROCESS_CAD.md；仅在最终全量通过后合并并推 backup/main。

## 非阻断项跟进（2026-10-07）

NB-001 已在 `6bb3c1c` 修复：预览 URL 包含资产 ID 和 revision，图片按 URL
重新挂载；步骤、掩膜名或绑定改变时清除失败状态，以允许重试。
NB-002 已在 `770dd4e` 修复：文件选择器统一为 `.json,.gds,.oas`，不扩展后端契约。

两项新增测试均确认修复前失败、修复后通过。前端全量 383 项通过，typecheck、build
退出 0；AGENTS 五模块基准回归 186 项通过；grid=128 五个 demo 及 py_compile 通过。
本次仅修改前端，不重复引用 Task 5 的 Python 全量结果作为本次全量验证。
独立复审结论为 APPROVE，无新增 BLOCK/NB，八项边界均 PASS；复审者独立运行
前端针对测试 61 项，以及精确 revision 预览、旧图片执行两项后端测试，均通过。
剩余验证限制：未实测真实浏览器网络事件时序。
