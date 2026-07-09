"""
TestGen Web Launcher
Starts the FastAPI server and opens the default browser.
Used as the entry point for both development and the .exe build.
"""

import sys
import os
import webbrowser
import threading
import time


def launch(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True):
    """
    Start the TestGen web server and optionally open a browser.

    Args:
        host: Bind address (default 127.0.0.1 for .exe security)
        port: Port number
        open_browser: Whether to auto-open the default browser
    """
    import uvicorn

    if open_browser:
        # Open browser after a short delay to let server start
        def _open():
            time.sleep(1.0)
            url = f"http://{host}:{port}"
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  TestGen Web Server starting...")
    print(f"  Open your browser at: http://{host}:{port}")
    print(f"  Press Ctrl+C to stop\n")

    uvicorn.run(
        "testgen.web.server:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TestGen Web Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8080, help="Port number")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    launch(host=args.host, port=args.port, open_browser=not args.no_browser)
