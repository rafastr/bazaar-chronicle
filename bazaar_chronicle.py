import threading
import time
import webbrowser

from main import run_tracker_watch_mode
from web.app import run_web_app

APP_URL = "http://127.0.0.1:5000"


def _open_browser() -> None:
    try:
        webbrowser.open(APP_URL)
    except Exception:
        pass


def _start_tracker_thread() -> threading.Thread:
    t = threading.Thread(
        target=run_tracker_watch_mode,
        kwargs={
            "pretty": False,
            "screenshots_enabled": True,
        },
        daemon=True,
    )
    t.start()
    return t


if __name__ == "__main__":
    _start_tracker_thread()
    threading.Timer(1.5, _open_browser).start()
    run_web_app()
