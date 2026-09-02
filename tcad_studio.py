# -*- coding: utf-8 -*-
"""TCAD Studio 桌面启动器：无头服务器 + 系统浏览器（M12，ADR-022）。

用法：python tcad_studio.py [--port 8765]
"""
import argparse
import socket
import threading
import time
import webbrowser
from pathlib import Path


def find_free_port(start: int = 8765) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port in range")


def main() -> int:
    parser = argparse.ArgumentParser(description="TCAD Studio")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    import os
    os.environ["TCAD_SKIP_QT"] = "1"
    os.environ["MPLBACKEND"] = "Agg"

    from tcad_simulator import WebUIServerManager

    port = find_free_port(args.port)
    storage = Path.home() / ".tcad-studio"
    storage.mkdir(parents=True, exist_ok=True)

    manager = WebUIServerManager(
        storage_root=str(storage),
        host="127.0.0.1",
        port=port,
    )
    manager.start()
    url = f"http://127.0.0.1:{port}/studio/"
    print(f"TCAD Studio 已启动：{url}")
    print("按 Ctrl+C 退出。")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n正在关闭…")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
