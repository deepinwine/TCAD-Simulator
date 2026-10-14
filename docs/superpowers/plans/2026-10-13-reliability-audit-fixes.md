# 七项可靠性修复实现计划

> 面向 AI 工作者：使用 subagent-driven-development，严格按 BLOCK 编号顺序执行。
> 每项先写失败测试，再最小实现、小提交、规格审查和质量审查。

**目标：** 关闭当前版本七项已复现可靠性问题。
**架构：** 复用现有来源、Recipe、HTTP、headless cache、React reducer 与 launcher。
**技术栈：** Python／NumPy／SciPy、React／TypeScript、现有 unittest 与 Vitest。

## 公共执行约定

工作树：`~/.config/superpowers/worktrees/TCAD-Simulator/codex/reliability-audit-fixes`。
Python 使用 `/opt/anaconda3/bin/python3`，环境为
`TCAD_SKIP_QT=1 MPLBACKEND=Agg PYTHONPYCACHEPREFIX=/tmp/tcad-reliability-fixes`。
HTTP fixture 可复用 `tests.test_structure_editor_http.StructureEditorHTTPTests` 的
临时 manager 与 `_request`；仅测试临时会话，不能连接用户运行中的服务。
不降低旧断言、不删除测试。进展以 Git 与审查结果为准。

## Task 1 / BLOCK-001：删除已构建步骤的来源

文件：`structure_cad/display_provenance.py`、`tcad_simulator.py`、
`tests/test_structure_display_provenance.py`、`tests/test_structure_display_http.py`。

- [ ] HTTP 失败测试：导入 Wafer(20 nm) 与 Deposit(SiO2,10 nm)，run/all，删除
  index 1，保存，new，load；断言加载成功且体素保持，未删 owner 不变。
  回归最小核心断言：

```python
loaded = self.request('POST', '/api/recipe/load', {'id': saved_id})
self.assertTrue(loaded['ok'], loaded)
```

- [ ] 来源测试覆盖 unknown 0、同材料多个 owner、旧无来源与身份碰撞仍拒绝；
  加入删除后保存及相关 undo／timeline 恢复后再次保存加载。
- [ ] 运行上述两模块，确认新测试因 source-bound mapping 失败。
- [ ] 最小实现来源解绑／降级，保留正式 grid、材料场及已登记其他 owner；
  检查失败原子性，不在 loader 中无条件放宽 identity 校验。
- [ ] 最终审查故障回归：timeline 恢复非法来源、随后 rollback restore 也失败时，
  返回 `rolled_back:false` 和 rollback error；保留本次恢复前 Undo，递增 revision、
  失效展示缓存，故障解除后 Undo 逐体素恢复原 grid／来源。回滚成功则仍保持
  revision／历史不变，不新增时间线执行或回放。
- [ ] 重跑来源、显示 HTTP、Structure editor；编译与 diff check。
- [ ] `fix(来源绑定): 修复删除步骤后的配方保存加载`，两阶段审查后 Task 2。

## Task 2 / BLOCK-002：空配方整体加载

文件：`tcad_simulator.py`、`tests/test_webui_cad_shell.py`。

- [ ] 保存真实空配方，再进入非空配方；history_load 返回空列表：

```python
self.assertTrue(response['ok'], response)
self.assertEqual(response['result']['recipe'], [])
```

- [ ] 验证全局 autosave、同目录 worker 重启、旧文件缺字段及非法候选拒绝。
- [ ] 运行 `CadShellWorkerHistoryTests`，确认空列表与旧步骤不一致的 RED。
- [ ] 用字段存在性选择 steps_full／steps，整体发布空 rebuilt，保持 detached
  校验和失败时当前 ID 不变；不重构其他恢复逻辑。
- [ ] 重跑整个 webui_cad_shell、Structure editor 与 Task 1 回归。
- [ ] `fix(配方恢复): 正确保留空步骤列表`，两阶段审查后 Task 3。

## Task 3 / BLOCK-003：CI 依赖闭环

文件：`.github/workflows/ci.yml`、新增 `tests/test_ci_contract.py`、
`tests/test_recipe_planner.py`、`tests/test_m18_hybrid_truth.py`。

- [ ] 静态回归检查实际 pip install 步骤含 scipy／cryptography、核心 suite 包含本轮测试与
  Structure／显示／编辑模块；修改前断言失败，不匹配注释中的文字。
- [ ] 最小 CI 配置修复，不强制安装 gdstk、ViennaPS、Qt，不吞测试失败。
- [ ] 临时 venv 安装 CI 同一依赖集，运行代表性 facade/schema 与 Structure
  测试；记录 Python 版本及退出码，不能只用开发环境确认。
- [ ] 完整干净核心套件已暴露 Library／Admin 配置强制依赖 cryptography，
  `init` 返回缺包错误。补齐这个既有核心依赖后重跑实际 CI 命令，不修改
  加密代码，不强制安装整套开发依赖。
- [ ] 干净环境已暴露 `ValidatorTests.test_mode_recommendations` 对真实 ViennaPS
  安装的隐式依赖。保留全部已有推荐断言，以显式能力 fixture 测试推荐分支，
  并追加 backend 不可用时空推荐的测试；不为了 CI 强制安装可选求解器。
- [ ] `FastAccurateFastTests.test_continuous_flow` 同样隐式依赖引擎可用性：
  只在该测试的刻蚀路由请求阶段显式声明 Accurate 可用，保留原 Accurate／
  fallback 与 canonical 断言；另测引擎不可用时真实 Fast 路由，不改运行时代码。
- [ ] 回归 no-gdstk 路径及 diff check。
- [ ] `fix(CI): 补齐结构模块依赖与回归覆盖`，两阶段审查后 Task 4。

## Task 4 / BLOCK-004：Structure Pattern 缓存失效

文件：`tcad_simulator.py`、`tests/test_recipe_reliability.py`。

- [ ] `(4,4,8)`、voxel=5 的 Wafer20／Custom Pattern／Etch10 配方：同 ctx
  左半改右半，与新 ctx 逐体素比较；旧代码应有 32 个错误体素。

```python
np.testing.assert_array_equal(cached_grid, fresh_grid)
```

- [ ] 覆盖同路径掩膜文件更新、掩膜形状变化与不变输入继续命中缓存。
- [ ] 运行 RecipeReliabilityTests 观察 RED，再扩展既有曝光签名输入到
  Structure Pattern，不创建独立执行器。
- [ ] 重跑 recipe_reliability、Structure、headless/demo 回归和 diff check。
- [ ] `fix(无界面缓存): 跟踪结构光刻掩膜变化`，两阶段审查后 Task 5。

## Task 5 / BLOCK-005：移动选中对象

文件：`frontend/src/state/appReducer.ts`、`AppStateContext.test.tsx`、
`appReducer.test.ts`；仅实际需要时修改 `AppStateContext.tsx`。

- [ ] 挂载真实 AppStateProvider：初始化、A、B，选中 A 下移，再删除；断言
  请求作用于 A 的新 index，旧代码实际删 B；上移和连续移动也保持身份。
- [ ] reducer 测试：

```typescript
expect(next.recipe.find(s => s.index === next.selectedStepIndex)?.stepId)
  .toBe(selected.stepId);
```

- [ ] 验证对象被删除与旧服务无 stepId 的选择回退，保留 initialization gate。
- [ ] 最小按 identity 选择，不修改工艺 geometry、单位或 Viewer 生命周期。
- [ ] 串行 Vitest、typecheck 与 build，不能增加测试 timeout 掩盖失败。
- [ ] `fix(步骤选择): 移动后跟随持久化身份`，两阶段审查后 Task 6。

## Task 6 / BLOCK-006：删除当前配方不复活

文件：`tcad_simulator.py`、`tests/test_webui_cad_shell.py`。

- [ ] 真实临时 worker 删除唯一当前配方：旧 ID 不再绑定；后续 save、正常
  shutdown 重启与连接断开后重启均不含旧 ID 或旧自定义步骤。
- [ ] 验证删除非当前条目保持当前 grid/recipe；当前删除且还有其他条目时切换。
- [ ] 视频会话活跃时，在恢复指针及历史文件变更前拒绝删除当前配方；验证
  拒绝后的 `video_end`／shutdown 恢复合法，结束后正常删除仍成功，非当前
  条目仍可删除。不得自动取消视频或移除严格来源校验。
- [ ] 先观察 RED，再修解除绑定及全局 autosave/session 指针；无其他条目时
  使用既有全新 Untitled 默认初始化，不把被删配方重新保存。
- [ ] 重跑 history 类、全部 webui_cad_shell 与 Task 1/2 保存加载回归。
- [ ] `fix(配方删除): 清理当前绑定与恢复指针`，两阶段审查后 Task 7。

## Task 7 / BLOCK-007：启动器退出保存

文件：`tcad_studio.py`、`tests/test_tcad_studio_launcher.py`；为部分启动失败的
安全清理，最小修改 `tcad_simulator.py` 中的 `WebUIServerManager`，不改 Admin manager。

- [ ] 以隔离 fake manager 验证 Ctrl+C、运行时异常均调用 stop 一次：

```python
manager.stop.assert_called_once_with()
```

- [ ] 实际临时 worker shutdown 保存最近编辑，再同目录重启核对值；不使用
  用户 `.tcad-studio`。保持 Ctrl+C 返回 0，异常传播，浏览器设置不变。
- [ ] 最小 finally 清理，不新增保存端点或线程模型。
- [ ] 真实 manager 已创建 HTTPServer、Thread.start 抛 RuntimeError／KeyboardInterrupt
  时，清理不能等待尚未运行的 serve_forever；保持关闭资源、会话清理、异常
  传播和 Ctrl+C 返回 0。先失败再通过，测试有确定性释放措施，不能永久挂起。
- [ ] launcher 与 history 回归、编译、diff check。
- [ ] `fix(启动器): 退出时关闭服务并刷新保存`，两阶段审查。

## 补充回归校正（七项修复闭环后）

文件：`tests/test_mask_asset_transaction.py`，仅测试变更。

- [ ] 保留杀进程场景，将严格原始字节断言移到真实 recover 返回后、首次
  loader 读取前；断言恢复 hook 被执行及其先于加载，事务产物已清理。
- [ ] 加载后仍核对原配方、step identity、规范化参数、完整 model_state；
  不因兼容性规范化合法写回而要求 pickle 字节一直不变。
- [ ] 原基线已确认此测试失败；先验证错误断言位置，再专项 GREEN、独立
  规格与质量审查，重跑全部掩膜补充套件。

## 最终验收与交接

- [ ] `/opt/anaconda3/bin/python3 -m unittest` 运行全部本轮测试、Structure /
  来源／编辑／Recipe／facade 回归及 AGENTS 五模块基线。
- [ ] 编译 `tcad_simulator.py tools/*.py structure_cad/*.py process_api/*.py`。
- [ ] `tools/run_process_cad_baseline.py --grid 128 --output /tmp/tcad-fixes-grid128.json`。
- [ ] 前端 `npm test -- --run --maxWorkers=1 --no-file-parallelism`、
  `npm run typecheck`、`npm run build`。
- [ ] 全部 diff 独立最终审查，关闭 BLOCK；记录真实验证与限制。
- [ ] 交接已提交分支，不自动合并／推送 main，不重启用户服务。
