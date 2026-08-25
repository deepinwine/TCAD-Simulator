# Process CAD Shell 实现计划索引

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在不重写 `ProcessModel` 或破坏旧 Recipe JSON 的前提下，交付可运行、可回看、可测试的三栏 Process CAD Shell。

**架构：** 保留现有 WebUI HTTP/Worker、`ProcessStep → ProcessModel` 和按材料 `.geom` 网格管线。实施拆为四个可独立验证的计划，先建立兼容与测试基础，再实现工艺原语、Viewer，最后集成为三栏 CAD Shell。

**技术栈：** Python 3.13、NumPy、SciPy、scikit-image、PyQt5、标准库 `unittest`、原生 HTML/CSS/JavaScript、Three.js r145、Git worktree。

---

## 工作区与远程

- 实施 worktree：`/Users/jiajia/.config/superpowers/worktrees/TCAD-Simulator/codex/process-cad-shell`
- 实施分支：`codex/process-cad-shell`
- 上游远程：`origin` → `FonaTech/TCAD-Simulator`
- 备份远程：`backup` → `deepinwine/TCAD-Simulator`
- 备份规则：每个通过验证的提交执行 `git push backup HEAD:codex/process-cad-shell`
- 禁止在实施过程中向 `origin` 推送；合并到 `backup/main` 留到分支收尾阶段决定。

## 文件结构决策

当前运行时以 `tcad_simulator.py` 为规范源码，拆分目录只是生成物。本里程碑遵循现有模式，不单方面重写打包结构。

将创建以下测试文件，每个文件只承担一个职责：

- `tests/__init__.py`：允许按模块运行标准库测试。
- `tests/test_process_cad_foundation.py`：视觉注册表、Recipe 迁移、步骤实例名、状态失效和失败回滚。
- `tests/test_process_cad_primitives.py`：Strip、Fill、Wafer Flip、Bonding、Thinning 的小网格测试。
- `tests/test_process_cad_demos.py`：三个示例配方的 headless 端到端验收。
- `tests/test_webui_viewer_contract.py`：WebGL 初始化、相机、裁剪和材料 payload 的静态/服务契约。
- `tests/test_webui_cad_shell.py`：三栏 HTML、步骤操作、时间线和 API 的服务级测试。
- `tools/run_process_cad_baseline.py`：在临时目录运行编译、自测、demo 与性能基准，输出 JSON 结果。

规范运行时修改集中在：

- `tcad_simulator.py`：材料视觉、工艺原语与步骤、Recipe 迁移、Worker 状态、WebUI、Viewer 和 demos。
- `README.md`：Process CAD Shell 使用入口、三个 demo 和兼容说明。
- `docs/ARCHITECTURE.md`：CAD Shell 数据流、快照失效和 Viewer 后端选择。
- `docs/WEBUI_RUNTIME.md`：WebGL2、Host Render 降级、三轴裁剪和浏览器验收命令。

## 执行顺序

1. [计划 1：兼容与测试基础](2026-08-25-process-cad-foundation.md)
2. [计划 2：工艺原语与示例配方](2026-08-25-process-cad-primitives.md)
3. [计划 3：WebGL Viewer](2026-08-25-webgl-viewer.md)
4. [计划 4：三栏 CAD Shell 与端到端验收](2026-08-25-cad-shell-integration.md)

每个计划完成后必须满足：对应测试通过、`git diff --check` 通过、提交范围与计划一致，并推送到 `backup/codex/process-cad-shell`。

## 总体验收命令

```bash
cd /Users/jiajia/.config/superpowers/worktrees/TCAD-Simulator/codex/process-cad-shell
TCAD_PYCACHE_DIR=$(mktemp -d /tmp/tcad-cad-pycache.XXXXXX)
PYTHONPYCACHEPREFIX="$TCAD_PYCACHE_DIR" /opt/anaconda3/bin/python3 -m py_compile \
  tcad_simulator.py tools/docsite.py tools/split_tcad.py tools/run_process_cad_baseline.py
/opt/anaconda3/bin/python3 -m unittest -v \
  tests.test_process_cad_foundation \
  tests.test_process_cad_primitives \
  tests.test_process_cad_demos \
  tests.test_webui_viewer_contract \
  tests.test_webui_cad_shell
TCAD_SKIP_QT=1 MPLBACKEND=Agg /opt/anaconda3/bin/python3 \
  tools/run_process_cad_baseline.py --grid 128 --output /tmp/tcad-cad-baseline.json
git diff --check
```

预期：编译退出码 0；所有 `unittest` 显示 `OK`；基准 JSON 的 `ok` 为 `true`；差异检查退出码 0。
