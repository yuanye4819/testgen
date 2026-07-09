"""
TestGen Desktop Launcher
Starts backend server and opens default browser — full browser experience.
"""

import sys
import os
import threading
import time
import webbrowser


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

    config = uvicorn.Config(
        "testgen.web.server:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        log_config=None,
    )
    server = uvicorn.Server(config)

    def run():
        server.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()

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
    start_server(port)

    url = f"http://127.0.0.1:{port}"
    print(f"TestGen running at {url}")
    webbrowser.open(url)

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")


if __name__ == "__main__":
    main()
