# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for TCAD Studio (M12) — headless, no Qt.
# Build: pyinstaller tcad_studio.spec

import os

block_cipher = None

a = Analysis(
    ["tcad_studio.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # React 前端构建产物（需先 npm run build）
        ("frontend/dist", "frontend/dist"),
    ],
    hiddenimports=[
        "tcad_simulator",
        "process_api",
        "process_backend",
        "geometry_scene",
        "layout",
        "numpy",
        "matplotlib.backends.backend_agg",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 排除 Qt/GUI（无头路线）
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "tkinter",
        "matplotlib.backends.backend_qt5agg",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TCAD Studio",
    debug=False,
    strip=False,
    upx=True,
    console=True,  # 保留控制台以显示日志
    icon=None,     # TODO: 添加 .icns/.ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="TCAD Studio",
)
