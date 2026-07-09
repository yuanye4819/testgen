"""
TestGen Desktop GUI
Native desktop window with embedded WebView — no browser, no CMD window.
"""

import sys
import os
import threading
import time


def find_free_port(start=19900):
    """Find an available port starting from `start`."""
    import socket
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start


def start_server(port: int):
    """Start uvicorn in a background daemon thread."""
    import uvicorn

    # Suppress uvicorn logs — GUI mode has no terminal
    config = uvicorn.Config(
        "testgen.web.server:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        log_config=None,  # disable dictConfig which crashes without tty
    )
    server = uvicorn.Server(config)

    def run():
        server.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    # Wait until the server is actually running
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("Server failed to start")


def main():
    port = find_free_port()

    # Start backend server
    start_server(port)

    # Open native desktop window with embedded WebView
    import webview

    url = f"http://127.0.0.1:{port}"
    webview.create_window(
        title="TestGen - AI 测试用例生成器",
        url=url,
        width=1200,
        height=800,
        min_size=(900, 600),
        resizable=True,
        fullscreen=False,
        text_select=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
