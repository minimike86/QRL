"""
QRL Capture Handler

Continuously captures screen regions in a background thread using mss
(fast, no per-frame Python copy). Frames are buffered as numpy BGR arrays
for direct pyzbar / OpenCV consumption.
"""

import threading
import time
from collections import deque
from typing import Deque, List, Optional, Tuple

import numpy as np


class CaptureHandler:
    """Captures screen regions in a background thread."""

    def __init__(
        self,
        monitor: int = 0,
        region: Optional[Tuple[int, int, int, int]] = None,
        interval: float = 0.05,
        buffer_size: int = 120,
    ):
        self.monitor = monitor
        self.region = region
        self.interval = interval
        self.buffer_size = buffer_size

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frames: Deque[np.ndarray] = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
        self._frames_captured = 0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def is_running(self) -> bool:
        return self._running

    def get_frames(self) -> List[np.ndarray]:
        """Return and clear all buffered frames."""
        with self._lock:
            frames = list(self._frames)
            self._frames.clear()
        return frames

    def push_frame(self, frame: np.ndarray) -> None:
        """Inject a frame directly. Used by tests and by integration loops."""
        with self._lock:
            self._frames.append(frame)
            self._frames_captured += 1

    def set_region(self, region: Tuple[int, int, int, int]) -> None:
        self.region = region

    def get_frames_captured(self) -> int:
        return self._frames_captured

    def _monitor_def(self, sct) -> dict:
        if self.region is not None:
            x, y, w, h = self.region
            # mss accepts negative left/top (multi-monitor virtual desktop on Windows)
            return {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        # `monitor` here is the 1-based mss index (1 = primary). 0 is also accepted
        # as a legacy "primary" alias.
        idx = self.monitor if self.monitor >= 1 else 1
        if idx >= len(sct.monitors):
            idx = 1
        return sct.monitors[idx]

    def _capture_loop(self) -> None:
        try:
            import mss
        except ImportError:
            self._fallback_capture_loop()
            return

        with mss.mss() as sct:
            mon = self._monitor_def(sct)
            while self._running:
                start = time.perf_counter()
                try:
                    raw = sct.grab(mon)
                    # mss returns BGRA; drop alpha for OpenCV/pyzbar
                    arr = np.asarray(raw)[:, :, :3].copy()
                    self.push_frame(arr)
                except Exception:
                    pass
                elapsed = time.perf_counter() - start
                wait = self.interval - elapsed
                if wait > 0:
                    time.sleep(wait)

    def _fallback_capture_loop(self) -> None:
        from PIL import ImageGrab

        while self._running:
            start = time.perf_counter()
            try:
                bbox = None
                if self.region is not None:
                    x, y, w, h = self.region
                    bbox = (x, y, x + w, y + h)
                img = ImageGrab.grab(bbox=bbox)
                arr = np.array(img)
                if arr.ndim == 3 and arr.shape[2] == 3:
                    arr = arr[:, :, ::-1].copy()  # RGB → BGR
                self.push_frame(arr)
            except Exception:
                pass
            elapsed = time.perf_counter() - start
            wait = self.interval - elapsed
            if wait > 0:
                time.sleep(wait)
