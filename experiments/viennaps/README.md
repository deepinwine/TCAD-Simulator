# ViennaPS Sandbox (M8, ADR-014)

本目录是 ViennaPS 精确引擎的**沙盒**：原型与独立验证只发生在这里，
不接入 `process_backend` 注册表（那是 M9 ViennaPSBackend 的事），
更不影响现有 VoxelBackend 与任何生产路径。

## 内容

- `probe.py` — 能力探测（python 绑定 / cmake / C++ 工具链 / 注册表视角），
  支持 `--json` 机读输出。
- `trench_reference.py` — 参考实验：掩膜开口的 SF6O2 干法刻蚀沟槽
  （0.64µm 视场 / 8nm 网格 / 30s 工艺时间），输出 VTK 表面网格与 JSON 摘要；
  引擎缺失时以安装指引退出（码 3）。
- `README.md` — 本文件。

## 本机安装记录（macOS/arm64，已验证 2026-09-01）

PyPI 上的 `ViennaLS 5.8.5` 与 `ViennaPS 4.6.2` wheel 存在跨模块 pybind11
ABI 不匹配（导入即 SIGSEGV）。成功路径为**源码构建**（需要
`brew install libomp`）：

```bash
git clone --depth 1 https://github.com/ViennaTools/ViennaLS.git /tmp/ViennaLS
git clone --depth 1 https://github.com/ViennaTools/ViennaPS.git /tmp/ViennaPS
/opt/anaconda3/bin/python3 -m pip install "pybind11>=3.0,<3.1" -i https://pypi.org/simple
PYB=$(/opt/anaconda3/bin/python3 -m pybind11 --cmakedir)

cmake -S /tmp/ViennaLS -B /tmp/vls-build -DCMAKE_BUILD_TYPE=Release \
  -DVIENNALS_BUILD_PYTHON=ON -Dpybind11_DIR=$PYB \
  -DOpenMP_ROOT=/opt/homebrew/opt/libomp \
  -DPython_EXECUTABLE=/opt/anaconda3/bin/python3 -DPython_ROOT_DIR=/opt/anaconda3 \
  -DPython_FIND_STRATEGY=LOCATION
cmake --build /tmp/vls-build -j8 && cmake --install /tmp/vls-build --prefix /tmp/vls-install
# 用 build 里的 cpython-313 _core.so 替换 site-packages/viennals/ 内同名文件

cmake -S /tmp/ViennaPS -B /tmp/vps-build -DCMAKE_BUILD_TYPE=Release \
  -DVIENNAPS_BUILD_PYTHON=ON -Dpybind11_DIR=$PYB \
  -DOpenMP_ROOT=/opt/homebrew/opt/libomp \
  -DPython_EXECUTABLE=/opt/anaconda3/bin/python3 -DPython_ROOT_DIR=/opt/anaconda3 \
  -DPython_FIND_STRATEGY=LOCATION -DCMAKE_PREFIX_PATH=/tmp/vls-install
cmake --build /tmp/vps-build -j8
# 同样替换 site-packages/viennaps/_core.so；若 dyld 报 libembree4.dylib，
# 用 install_name_tool 指向 wheel 自带的 viennaps/.dylibs/libembree4.dylib
```

验证结果：`trench_reference.py` 以 viennaps 4.7.0（源码 HEAD）完整执行
SF6O2 刻蚀（时间步进日志 + 862KB VTK 网格输出，exit 0）；
`tests/test_viennaps_sandbox.py` 全绿。

## 下一步（M9）

1. 把参考实验的几何/工艺参数与 VoxelBackend 的 Basic Trench 做定量对照
   （沟槽深度/宽度标定）；
2. 在 `process_backend` 注册 `ViennaPSBackend`（`precision='geometry'`）并
   引入能力模型与显式回退。
