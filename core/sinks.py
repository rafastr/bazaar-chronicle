from __future__ import annotations

import json
import os
import threading
import time
from typing import List, Optional, Set


from .events import Event
from core.config import settings


def _notify_screenshot_taken() -> None:
    def _worker() -> None:
        try:
            from win11toast import toast

            toast(
                "Bazaar Chronicle",
                "Final board captured. You can continue now.",
                duration="short",
            )
        except Exception as e:
            print(json.dumps(
                {"type": "NotificationError", "error": repr(e)},
                ensure_ascii=False
            ))

    threading.Thread(target=_worker, daemon=True).start()


class Sink:
    def handle(self, ev: Event) -> List[Event]:
        return []


class StdoutSink(Sink):
    def __init__(self, pretty: bool = False) -> None:
        self.pretty = pretty

    def handle(self, ev: Event) -> List[Event]:
        d = ev.to_dict()
        if self.pretty:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(d, ensure_ascii=False))
        return []


class ScreenshotSink(Sink):
    WINDOW_TITLE = "The Bazaar"

    def __init__(
        self,
        enabled: bool,
        out_dir: str,
        monitor_index: int = 1,
        delay_seconds: float = 2.7,
        cooldown_seconds: float = 5.0,
        trigger_event_types: Optional[Set[str]] = None,
    ) -> None:
        self.enabled = enabled
        self.out_dir = out_dir
        self.monitor_index = monitor_index
        self.delay_seconds = delay_seconds
        self.cooldown_seconds = cooldown_seconds
        self.trigger_event_types = trigger_event_types or set()

        self._last_shot_ts: float = 0.0

        if self.enabled:
            os.makedirs(self.out_dir, exist_ok=True)

    def handle(self, ev: Event) -> List[Event]:
        if not self.enabled:
            return []

        if ev.type not in self.trigger_event_types:
            return []

        now = time.time()
        if now - self._last_shot_ts < self.cooldown_seconds:
            return []

        self._last_shot_ts = now
        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

        path = self._take_screenshot(prefix=ev.type)
        if not path:
            return []

        return [Event(type="ScreenshotSaved", raw=ev.raw, screenshot_path=path)]

    def _find_bazaar_client_rect(self) -> Optional[dict]:
        try:
            import win32gui
        except Exception as e:
            print(json.dumps(
                {
                    "type": "WindowCaptureInfo",
                    "message": "pywin32 not available; falling back to monitor capture",
                    "error": repr(e),
                },
                ensure_ascii=False,
            ))
            return None

        matches: list[int] = []

        def _enum_cb(hwnd, _extra) -> None:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return

                title = win32gui.GetWindowText(hwnd) or ""
                if self.WINDOW_TITLE.lower() in title.lower():
                    matches.append(hwnd)
            except Exception:
                return

        try:
            win32gui.EnumWindows(_enum_cb, None)
        except Exception as e:
            print(json.dumps(
                {"type": "WindowCaptureError", "stage": "EnumWindows", "error": repr(e)},
                ensure_ascii=False,
            ))
            return None

        if not matches:
            print(json.dumps(
                {
                    "type": "WindowCaptureInfo",
                    "message": f'Window "{self.WINDOW_TITLE}" not found; falling back to monitor capture',
                },
                ensure_ascii=False,
            ))
            return None

        hwnd = matches[0]

        try:
            if win32gui.IsIconic(hwnd):
                print(json.dumps(
                    {
                        "type": "WindowCaptureInfo",
                        "message": f'Window "{self.WINDOW_TITLE}" is minimized; falling back to monitor capture',
                    },
                    ensure_ascii=False,
                ))
                return None

            client_rect = win32gui.GetClientRect(hwnd)
            left_top = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
            right_bottom = win32gui.ClientToScreen(hwnd, (client_rect[2], client_rect[3]))

            left, top = left_top
            right, bottom = right_bottom
            width = right - left
            height = bottom - top

            if width < 200 or height < 200:
                print(json.dumps(
                    {
                        "type": "WindowCaptureInfo",
                        "message": "Game client rect too small; falling back to monitor capture",
                        "rect": {
                            "left": left,
                            "top": top,
                            "width": width,
                            "height": height,
                        },
                    },
                    ensure_ascii=False,
                ))
                return None

            rect = {
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }

            print(json.dumps(
                {
                    "type": "WindowCaptureInfo",
                    "message": f'Using client area of "{self.WINDOW_TITLE}"',
                    "rect": rect,
                },
                ensure_ascii=False,
            ))
            return rect

        except Exception as e:
            print(json.dumps(
                {"type": "WindowCaptureError", "stage": "GetClientRect", "error": repr(e)},
                ensure_ascii=False,
            ))
            return None

    def _get_fallback_monitor_rect(self, sct) -> dict:
        monitors = sct.monitors
        idx = self.monitor_index

        if idx < 1 or idx >= len(monitors):
            idx = 1

        monitor = monitors[idx]

        print(json.dumps(
            {
                "type": "MonitorCaptureInfo",
                "requested_monitor_index": self.monitor_index,
                "used_monitor_index": idx,
                "monitor_count": len(monitors) - 1,
                "rect": {
                    "left": monitor["left"],
                    "top": monitor["top"],
                    "width": monitor["width"],
                    "height": monitor["height"],
                },
            },
            ensure_ascii=False,
        ))

        return monitor

    def _take_screenshot(self, prefix: str = "shot") -> Optional[str]:
        try:
            from mss import mss
            from PIL import Image
        except Exception as e:
            print(json.dumps(
                {"type": "ScreenshotError", "error": repr(e), "hint": "Install mss and pillow"},
                ensure_ascii=False
            ))
            return None

        with mss() as sct:
            region = self._find_bazaar_client_rect()
            if region is None:
                region = self._get_fallback_monitor_rect(sct)

            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.rgb)

            ts = int(time.time())
            filename = f"{prefix}_{ts}.png"
            path = os.path.join(self.out_dir, filename)
            img.save(path)

            print(json.dumps(
                {
                    "type": "ScreenshotSaved",
                    "path": path,
                    "size": {"width": img.width, "height": img.height},
                },
                ensure_ascii=False,
            ))

            _notify_screenshot_taken()
            return path
