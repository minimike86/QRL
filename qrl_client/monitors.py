"""
Monitor discovery for the QRL client.

Returns a list of monitors with friendly labels suitable for a dropdown.
On Windows, also tries to surface the OS device name (e.g. "DELL U2723QE")
via the win32 GetMonitorInfo API; falls back to "Display N" otherwise.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MonitorInfo:
    index: int                # 1-based mss index (matches mss.monitors[index])
    name: str                 # friendly label, e.g. "Primary  ·  1920×1080"
    x: int                    # virtual-desktop x (can be negative)
    y: int                    # virtual-desktop y (can be negative)
    width: int
    height: int
    is_primary: bool

    @property
    def bounds(self) -> tuple:
        return (self.x, self.y, self.width, self.height)


def list_monitors() -> List[MonitorInfo]:
    """Enumerate physical monitors. Always returns at least one entry."""
    try:
        import mss
    except ImportError:
        # Fallback: Tk reports the primary monitor only.
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.destroy()
        return [MonitorInfo(1, f"Primary  ·  {w}×{h}", 0, 0, w, h, True)]

    # mss.MSS is the modern entry point; mss.mss is the deprecated alias.
    MSS = getattr(mss, "MSS", mss.mss)
    with MSS() as sct:
        # mss.monitors[0] is the union of all monitors; physical monitors start at 1.
        physical = sct.monitors[1:]
        if not physical:
            return [MonitorInfo(1, "Primary", 0, 0, 0, 0, True)]

    # Try to get Windows device names so users see "DELL U2723" etc.
    device_names = _windows_monitor_names()

    monitors: List[MonitorInfo] = []
    for i, mon in enumerate(physical, start=1):
        x, y = mon["left"], mon["top"]
        w, h = mon["width"], mon["height"]
        is_primary = (x == 0 and y == 0)

        device = device_names[i - 1] if i - 1 < len(device_names) else None
        position = _position_label(x, y, is_primary)

        if device:
            label = f"{device}  ·  {w}×{h}{position}"
        elif is_primary:
            label = f"Primary  ·  {w}×{h}"
        else:
            label = f"Display {i}  ·  {w}×{h}{position}"

        monitors.append(MonitorInfo(i, label, x, y, w, h, is_primary))
    return monitors


def find_by_index(index: int) -> Optional[MonitorInfo]:
    """Look up a monitor by its 1-based mss index. Returns None if not found."""
    for m in list_monitors():
        if m.index == index:
            return m
    return None


def monitor_at_point(x: int, y: int) -> Optional[MonitorInfo]:
    """Return the monitor whose bounds contain the given virtual-desktop point."""
    for m in list_monitors():
        if m.x <= x < m.x + m.width and m.y <= y < m.y + m.height:
            return m
    return None


def primary_monitor() -> Optional[MonitorInfo]:
    """Return the primary (origin 0,0) monitor."""
    for m in list_monitors():
        if m.is_primary:
            return m
    monitors = list_monitors()
    return monitors[0] if monitors else None


# --- internals ------------------------------------------------------------
def _position_label(x: int, y: int, is_primary: bool) -> str:
    if is_primary:
        return ""
    if x < 0 and y == 0:
        return "  ·  left of primary"
    if x > 0 and y == 0:
        return "  ·  right of primary"
    if y < 0 and x == 0:
        return "  ·  above primary"
    if y > 0 and x == 0:
        return "  ·  below primary"
    return f"  ·  at ({x}, {y})"


def _windows_monitor_names() -> List[str]:
    """Best-effort: enumerate Windows monitor friendly names. Returns empty
    list on any failure or non-Windows platform."""
    try:
        import sys

        if sys.platform != "win32":
            return []
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HMONITOR,
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            wintypes.LPARAM,
        )

        names: List[str] = []

        def _callback(hMonitor, hdcMonitor, lprcMonitor, lParam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hMonitor, ctypes.byref(info)):
                # szDevice is like "\\.\DISPLAY1" — friendlier than nothing.
                # We'll prettify by stripping the prefix.
                raw = info.szDevice
                if raw.startswith("\\\\.\\"):
                    raw = raw[4:]
                names.append(raw)
            return True

        user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_callback), 0)
        return names
    except Exception:
        return []
