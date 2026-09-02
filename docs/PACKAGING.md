# M12：桌面打包方案

## 许可分析（ADR-022 前置）

| 方案 | 许可影响 | 可行性 |
|---|---|---|
| PyQt5 + PyInstaller | PyQt5 为 GPL v3；与 MIT 冲突 | ❌ 需改许可或买商业许可 |
| **无头 Python + React** | MIT 兼容；零 GPL 依赖 | ✅ **推荐** |
| PySide6 | LGPL（可动态链接） | ⚠️ 但我们不需要 Qt GUI |

**结论**：本项目已具备无 Qt 路径（`TCAD_SKIP_QT=1` + `WebUIServerManager` + React 前端 `/studio/`），桌面打包走 **无头服务器 + 系统浏览器** 路线，完全规避 Qt 许可。

## 方案

```text
tcad-studio（PyInstaller 单文件）
  ├── Python 无头服务器（tcad_simulator + process_api + layout + geometry_scene）
  ├── React 前端（frontend/dist/ 静态文件）
  └── 启动脚本：起服务器 → 打开浏览器
```

## 构建

```bash
# 1. 构建前端
cd frontend && npm ci && npm run build && cd ..

# 2. 打包
pyinstaller tcad_studio.spec
```

产物：`dist/TCAD Studio.app`（macOS）或 `dist/TCADStudio.exe`（Windows）。

## ADR-022 记录见 DECISIONS.md
