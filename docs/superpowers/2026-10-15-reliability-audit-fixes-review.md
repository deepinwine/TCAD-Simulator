# 七项可靠性修复验收记录

日期：2026-10-15。基准：`main@f33e5c480718a0d58c3b01d377d0942aae290f5c`。
分支：`codex/reliability-audit-fixes`。

状态：七项修复、追加边界补修及事务测试校正均已通过独立 SPEC、QUALITY，
整批最终 Verdict 为 APPROVE。所有者随后选择本地合并；已快进到 main 并复验，
尚未推送 GitHub，未重启用户服务。

## 最终审查结论

独立最终评审范围：`f33e5c4..de739f5382a6c49f8ab990c94c8ea7131f209c66`。
无未关闭 BLOCK，无新增 NB，有序修复清单为空。本文最后一次更新仅记录该
判定，不增加实现变更。

八项边界全部 PASS：固定技术栈与职责、ProcessModel／Recipe 协议、单体权威
实现与最小改动、canonical 单位与 Structure 范围、来源与失败原子性、M2
HTTP／二进制契约、Layout／Accurate 可选依赖、React 选择与 Viewer 生命周期。
最终评审另独立运行事务校正用例，1 PASS／2.987 s，编译及全分支 diff check
通过；先前追加的 Timeline、配方切换、步骤选择三个 BLOCK 均已分别关闭。

## 修复与回归

| 审查项 | 修复行为 | 主要回归 |
| --- | --- | --- |
| 1：删除步骤来源 | 剩余材料仅解绑被删除步骤的 owner，不改变正式 grid；历史恢复仍严格验证身份 | 删除、同材料多来源、保存加载、Undo/Redo、损坏快照拒绝 |
| 2：空配方恢复 | 空 `steps_full` 权威发布，不回退旧步骤；发布后的兼容写回失败报告警告 | 命名／全局／重启恢复、旧格式、非法候选及写回故障 |
| 3：CI | 最小核心依赖包含 SciPy、cryptography；新增相关 suite，保持可选引擎边界 | 干净 venv 复跑实际 workflow、无 gdstk 跳过、能力 fixture |
| 4：掩膜缓存 | Structure Pattern 签名跟踪实际布尔内容、形状及消费的文件内容 | 同路径修改、同内容命中、禁用／嵌入输入、设备／FIFO 读取保护 |
| 5：步骤选择 | 按持久 ID 跟随移动；删除对象后依次采用原索引邻居、首个可见步骤、null | reducer 与真实 Provider，移动后删除、中间删除后操作 C、旧 ID 回退 |
| 6：删除当前配方 | 清恢复指针；无其他合法配方时创建独立默认模型；活跃视频先拒绝当前删除 | 保存、关闭重启、断连重启、其他条目、损坏候选、视频结束后恢复 |
| 7：启动器退出 | finally 关闭 manager；部分启动失败避开未运行服务的阻塞 shutdown | Ctrl+C、异常、定时器失败、真实服务最新编辑保存／重启、未启动线程 |

最终整批审查额外发现的边界也纳入原修复范围：

- `f17dd7d`：Timeline 恢复和回滚同时失败时，保留恢复前 Undo，刷新 revision／
  展示缓存，返回真实失败状态；解除故障后 Undo 逐体素恢复。正常恢复及安全
  回滚不增加历史条目。该补修已通过独立 SPEC、QUALITY。
- `07aca97`：import、history load、autosave load 成功后复用既有缓存失效入口；
  避免将旧 Recipe 的来源快照用于新身份。失败候选保留有效缓存，同配方再次
  运行仍命中缓存。基线已有跨配方旧缓存根因，新严格校验引出的拒绝路径也
  一并修复。该补修已通过独立 SPEC、QUALITY。
- `52956ee`：删除中间选中步骤后保留基线邻居选择，不跳到首步。修正先前
  测试中不符合批准设计的期望，同时增加末尾删除及实际后续操作的强断言。
  该补修已通过独立 SPEC、QUALITY。

补充事务测试校正不修改运行时：原基线就存在的杀进程恢复测试，在 loader
合法规范化后比较 pickle 字节而失败。现在在真实 recover 返回、首次 loader
读取前严格比较原始压缩字节和事务产物清理；加载后仍比较完整步骤字典、
step identity、规范化参数和其余全部持久化 blob（含完整 model_state）。
真实子进程 kill 场景保留，没有 skip，也没有关闭规范化或来源校验。

## 主审独立验证

以下均在隔离工作树和临时会话运行；未使用用户的 `.tcad-studio`、配方目录
或运行中的服务。Python 测试统一设置 `TCAD_SKIP_QT=1 MPLBACKEND=Agg`，
`PYTHONPYCACHEPREFIX` 位于 `/tmp`。

| 验证 | 实际结果 | 对应代码 |
| --- | --- | --- |
| 最小 venv：实际 CI 编译与 25 模块核心命令 | 535 tests，OK，13 skipped，142.840 s；编译 exit 0 | `07aca97` |
| AGENTS 五模块基线（开发环境） | 207 tests，OK，91.510 s | `52956ee` |
| 无 gdstk：`python -m unittest tests.test_layout_adapter` | 25 tests，OK，19 skipped | `07aca97` |
| `tools/run_process_cad_baseline.py --grid 128 --output /tmp/tcad-fixes-grid128-final.json` | 五个示例全部 `ok:true`，exit 0 | `07aca97` |
| 前端 `npm test -- --run --maxWorkers=1 --no-file-parallelism` | 35 files，627 tests PASS，21.13 s | `52956ee` |
| 前端 `npm run typecheck`、`npm run build` | 均 exit 0，串行执行 | `52956ee` |
| HTTP facade 与掩膜事务／安全／资产／Workbench 五模块 | 47 tests，OK，5.841 s | `5ce6cfb` |
| 配方切换新增 5 项 HTTP | 5 tests，OK，3.317 s | `07aca97` |
| Timeline 四类恢复边界 | 4 tests，OK，2.414 s | `f17dd7d` |
| 启动器生命周期 | 15 tests，OK，4.856 s | `a71128a` |

最小环境为 Python 3.13.5、macOS arm64，依赖仅使用 CI 的
`numpy matplotlib scipy cryptography` 及其传递依赖；已确认无 Qt、gdstk、
ViennaPS、ViennaLS、Numba。实际命令从 `.github/workflows/ci.yml` 的
`Compile check` 与 `Core backend tests` 提取执行，并检查最终退出码。
该核心集合包含 AGENTS 要求的五模块、Structure、来源、编辑 HTTP、Recipe、
facade 与 launcher 回归；不是以本机完整开发依赖替代 CI 配置验证。
前端本机运行时为 Node 26.0.0、npm 11.12.1。

核心命令从实际 CI 提取执行，可在仓库根目录使用相同最小环境复跑：

```bash
TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-main-merge-ci \
  /tmp/tcad-ci-fix-QcpZnp4E.venv/bin/python - <<'PY'
import os
from pathlib import Path
import subprocess
import sys
from tests.test_ci_contract import WORKFLOW, run_script

environment = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'])
workflow = WORKFLOW.read_text(encoding='utf-8')
for name in ('Compile check', 'Core backend tests'):
    subprocess.run(['/bin/bash', '-e', '-o', 'pipefail', '-c', run_script(workflow, name)],
                   env=environment, check=True)
PY
```

上述 `/tmp` venv 是本轮核验环境，不是项目运行依赖。
补充五模块的实际命令为：

```bash
TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-root-mask-final \
  /opt/anaconda3/bin/python3 -m unittest \
  tests.test_process_api_http tests.test_mask_asset_transaction \
  tests.test_mask_asset_security tests.test_mask_assets tests.test_mask_workbench_e2e
```

最终还单独编译 simulator、launcher、tools、Structure、process_api 与本次
修改的测试文件，并检查全分支 `git diff --check f33e5c4`，均 exit 0。

事务校正还由实现者执行 6 种纯内存故障变体：跳过恢复、先读取后恢复、恢复
字节损坏、加载后模型损坏、步骤 identity 损坏、参数损坏。六种均被断言捕获，
未以异常报错代替预期测试失败；该故障注入记录不替代主审的独立 47 项 GREEN。

## 架构与集成边界

保持 React／Python／ProcessModel／Three.js，未新增工艺物理算法、后端协议、
保存端点或执行器。来源仍为显示辅助数据，材料 grid 仍是 canonical。
未合入独立的深度区间刻蚀分支，也未重启用户服务。

所有者选择选项 1 后，main 从 `f33e5c4` 快进至已审查的 `9cf1052`，无冲突；
没有拉取上游 origin，也没有推送任何 remote。全部修复提交已保留于 main，
仅清理已合并的临时工作树及功能分支，其他工作树和用户未跟踪文件不变。
后续推送仍需单独指令，目标为 `deepinwine` 对应的 backup remote，而非上游 origin。

### main 合并后复验

在 `/Users/jiajia/Documents/test/TCAD-Simulator` 执行，代码 HEAD 为 `9cf1052`；
此后仅追加本条集成记录，没有修改运行时实现。

| 验证 | 结果 |
| --- | --- |
| 实际 CI 编译／核心后端 | 编译 exit 0；535 tests，OK，13 skipped，145.677 s |
| HTTP facade 与掩膜补充五模块 | 47 tests，OK，5.500 s |
| 前端串行全量 | 35 files，627 tests PASS，19.35 s |
| typecheck／build | 均 exit 0 |
| grid128 基准 | 五个示例全部通过，输出 `/tmp/tcad-main-merged-grid128.json` |

## 已知限制

- 未运行远端 Linux CI、Python 3.12、Node 22 或 Windows 真机验证；本机
  最小环境通过不等于这些平台已经实测。
- 存在既有 `worker_crash.log`／`live.log` ResourceWarning、Numba fork 提示、
  jsdom navigation／canvas 提示及 Vite 大于 500 kB 的构建警告。
- worker shutdown 仍有既有 RPC 超时及强制终止限制，不保证强杀或超时后的保存。
- 文件签名防止设备／FIFO 阻塞读取，但文件签名与随后执行之间的外部文件改写
  竞态未扩展为新的文件锁协议；Windows 的实际竞态未验证。
- 来源事务需要备份内存；没有以本次测试宣称消除所有内存不足风险。
- 本报告仅说明列明范围的修复与回归，不宣称仓库不存在其他 bug。
