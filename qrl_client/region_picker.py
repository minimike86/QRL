"""
Interactive screen-region picker.

Opens a fullscreen, semi-transparent overlay on every monitor. The user
clicks and drags to define a rectangular region on any monitor; on release
the chosen region is returned as (x, y, width, height) in mss virtual-desktop
coordinates (physical pixels, can be negative on left/above-primary monitors).

Using per-monitor Toplevel windows instead of one spanning window avoids two
Windows-specific pitfalls:
  1. A wide window created on the primary monitor may be clipped by the window
     manager to that monitor's bounds even with overrideredirect=True.
  2. Negative geometry coordinates (secondary monitor left of primary) are
     mis-parsed by Tk's geometry parser (treats "-X" as "X from right edge").
"""

from typing import Callable, Optional, Tuple
import sys
import tkinter as tk
from PIL import Image, ImageTk

Region = Tuple[int, int, int, int]


def _dpi_scale() -> float:
    """Best-effort: physical-pixels-per-logical-pixel on Windows.

    mss returns physical pixels; Tk event coordinates are logical pixels.
    Multiplying logical coords by this factor gives physical coords.
    Returns 1.0 on non-Windows or when the query fails.
    """
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        # Per-system DPI (blended average across monitors)
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return dpi / 96.0  # 96 DPI is 100% scaling baseline
    except Exception:
        return 1.0


def _grab_monitor(mon: dict) -> Optional[Image.Image]:
    """Capture a single monitor as a PIL RGB image."""
    try:
        import mss
        with mss.mss() as sct:
            raw = sct.grab(mon)
            return Image.frombytes("RGB", raw.size, raw.rgb)
    except Exception:
        try:
            from PIL import ImageGrab
            x, y, w, h = mon["left"], mon["top"], mon["width"], mon["height"]
            return ImageGrab.grab(bbox=(x, y, x + w, y + h))
        except Exception:
            return None


def _position_window(win: tk.Toplevel, x: int, y: int, w: int, h: int) -> None:
    """Position a Toplevel at (x, y) in screen coordinates.

    Tk's geometry string treats negative offsets as "from the opposite edge",
    so we use the Win32 SetWindowPos API on Windows for reliable absolute
    positioning at negative coordinates (e.g. a monitor left of the primary).
    On other platforms we use standard Tk geometry.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            win.update_idletasks()
            hwnd = win.winfo_id()
            # SWP_NOZORDER=0x0004 | SWP_NOACTIVATE=0x0010
            ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004 | 0x0010)
            return
        except Exception:
            pass
    # Fallback: standard Tk geometry (works for positive coords on non-Windows)
    win.geometry(f"{w}x{h}+{x}+{y}")


def pick_region(parent: Optional[tk.Misc] = None) -> Optional[Region]:
    """Show the picker and return the selected region, or None on cancel.

    Displays one fullscreen overlay per monitor. Press Esc or click without
    dragging to cancel. Release the mouse button to confirm a selection.
    """
    try:
        import mss
        with mss.mss() as sct:
            # Physical monitors (1-based; 0 is the virtual-desktop union).
            monitors = [dict(m) for m in sct.monitors[1:]]
    except Exception:
        monitors = []

    if not monitors:
        # Fallback: treat the whole Tk screen as one monitor.
        root_ref = parent if parent is not None else None
        try:
            tmp = tk.Tk() if root_ref is None else None
            ref = tmp or root_ref
            sw = ref.winfo_screenwidth()
            sh = ref.winfo_screenheight()
            if tmp:
                tmp.destroy()
        except Exception:
            sw, sh = 1920, 1080
        monitors = [{"left": 0, "top": 0, "width": sw, "height": sh}]

    scale = _dpi_scale()

    result: dict = {"region": None, "done": False}
    windows: list = []

    def _finish(region: Optional[Region]) -> None:
        if result["done"]:
            return
        result["done"] = True
        result["region"] = region
        for w in windows:
            try:
                w.destroy()
            except tk.TclError:
                pass

    def _make_overlay(mon: dict) -> None:
        """Create one fullscreen overlay for a single monitor."""
        mx, my = mon["left"], mon["top"]
        mw, mh = mon["width"], mon["height"]

        screenshot = _grab_monitor(mon)

        win = tk.Toplevel(parent) if parent is not None else tk.Tk()
        win.attributes("-topmost", True)
        win.overrideredirect(True)

        # Size to logical pixels (Tk coords); position via SetWindowPos/geometry
        # so negative coords work on Windows (secondary monitor left of primary).
        lw = max(1, int(round(mw / scale)))
        lh = max(1, int(round(mh / scale)))
        win.geometry(f"{lw}x{lh}")
        win.update_idletasks()
        _position_window(win, mx, my, lw, lh)
        win.update_idletasks()

        canvas = tk.Canvas(win, highlightthickness=0, bg="#000000", cursor="crosshair")
        canvas.pack(fill=tk.BOTH, expand=True)

        if screenshot is not None:
            dim = Image.eval(screenshot, lambda v: int(v * 0.55))
            # Scale screenshot down to logical pixel canvas size
            if dim.size != (lw, lh):
                dim = dim.resize((lw, lh), Image.Resampling.BILINEAR)
            photo = ImageTk.PhotoImage(dim)
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas._bg_photo = photo  # prevent GC

        # Instruction banner
        banner = canvas.create_rectangle(0, 0, lw, 52, fill="#1e2530", outline="")
        t1 = canvas.create_text(lw // 2, 18,
            text="Drag to select region — Esc: cancel",
            fill="#e6ecf2", font=("Segoe UI", 11, "bold"))
        t2 = canvas.create_text(lw // 2, 38,
            text="Select tightly around the QR display for fastest reads",
            fill="#9aa6b8", font=("Segoe UI", 9))

        rect_id = [None]
        dim_ids = []
        label_id = [None]
        drag = {"start": None}

        def _redraw(x0, y0, x1, y1):
            lx, rx = min(x0, x1), max(x0, x1)
            ty, by = min(y0, y1), max(y0, y1)
            for did in dim_ids:
                canvas.delete(did)
            dim_ids.clear()
            half = "#000000"
            dim_ids.append(canvas.create_rectangle(0, 0, lw, ty,  fill=half, outline="", stipple="gray50"))
            dim_ids.append(canvas.create_rectangle(0, by, lw, lh,  fill=half, outline="", stipple="gray50"))
            dim_ids.append(canvas.create_rectangle(0, ty, lx, by,  fill=half, outline="", stipple="gray50"))
            dim_ids.append(canvas.create_rectangle(rx, ty, lw, by, fill=half, outline="", stipple="gray50"))
            if rect_id[0] is None:
                rect_id[0] = canvas.create_rectangle(lx, ty, rx, by, outline="#4a90e2", width=2)
            else:
                canvas.coords(rect_id[0], lx, ty, rx, by)
            w_px, h_px = int((rx - lx) * scale), int((by - ty) * scale)
            txt = f"{w_px} x {h_px}"
            if label_id[0] is None:
                label_id[0] = canvas.create_text(
                    lx + (rx - lx) // 2, max(ty - 14, 12),
                    text=txt, fill="#e6ecf2", font=("Segoe UI", 10, "bold"))
            else:
                canvas.coords(label_id[0], lx + (rx - lx) // 2, max(ty - 14, 12))
                canvas.itemconfigure(label_id[0], text=txt)
            canvas.tag_raise(label_id[0])
            canvas.tag_raise(banner)
            canvas.tag_raise(t1)
            canvas.tag_raise(t2)

        def _press(ev):
            drag["start"] = (ev.x, ev.y)

        def _motion(ev):
            if drag["start"] is None:
                return
            _redraw(*drag["start"], ev.x, ev.y)

        def _release(ev):
            if drag["start"] is None:
                return
            x0, y0 = drag["start"]
            x1, y1 = ev.x, ev.y
            pw, ph = abs(x1 - x0), abs(y1 - y0)
            if pw < 8 or ph < 8:
                _finish(None)
                return
            # Convert from logical Tk canvas coords → physical virtual-desktop coords.
            lx_log = min(x0, x1)
            ty_log = min(y0, y1)
            lx_phys = mx + int(round(lx_log * scale))
            ty_phys = my + int(round(ty_log * scale))
            w_phys = int(round(pw * scale))
            h_phys = int(round(ph * scale))
            _finish((lx_phys, ty_phys, w_phys, h_phys))

        canvas.bind("<ButtonPress-1>", _press)
        canvas.bind("<B1-Motion>", _motion)
        canvas.bind("<ButtonRelease-1>", _release)
        win.bind("<Escape>", lambda _e: _finish(None))
        windows.append(win)

    for mon in monitors:
        _make_overlay(mon)

    # Focus the first overlay so Esc works immediately
    if windows:
        windows[0].focus_force()

    # Block until any overlay closes (all others are destroyed in _finish)
    if windows:
        windows[0].wait_window(windows[0])
    # Wait for any remaining overlays (in case the first was closed externally)
    for w in windows[1:]:
        try:
            w.wait_window(w)
        except Exception:
            pass

    return result["region"]


def pick_region_async(parent: tk.Misc, on_pick: Callable[[Optional[Region]], None]) -> None:
    """Async variant — opens the picker and calls on_pick when done."""
    region = pick_region(parent)
    parent.after(0, lambda: on_pick(region))
