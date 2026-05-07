"""
Interactive screen-region picker.

Opens a fullscreen, semi-transparent overlay across all monitors. The user
clicks and drags to define a rectangular region; on release, the chosen
region is returned as (x, y, width, height) in absolute virtual-desktop
coordinates.

Designed for the QRL client to let users target the QRL server's display
window without having to type pixel coordinates.
"""

from typing import Callable, Optional, Tuple

import tkinter as tk
from PIL import Image, ImageTk

Region = Tuple[int, int, int, int]


def pick_region(parent: Optional[tk.Misc] = None) -> Optional[Region]:
    """Show the picker and return the selected region, or None on cancel.

    Press Esc to cancel. Press Enter (or release mouse) to confirm.
    """
    result: dict = {"region": None}

    def _capture_screen() -> Optional[Image.Image]:
        try:
            import mss

            with mss.mss() as sct:
                # Monitor 0 in mss is the union of all monitors (virtual desktop)
                shot = sct.grab(sct.monitors[0])
                return Image.frombytes("RGB", shot.size, shot.rgb)
        except Exception:
            try:
                from PIL import ImageGrab

                return ImageGrab.grab(all_screens=True)
            except Exception:
                return None

    background = _capture_screen()

    win = tk.Toplevel(parent) if parent is not None else tk.Tk()
    win.attributes("-topmost", True)
    win.overrideredirect(True)  # no window decorations
    # Span the virtual desktop. Tk's `winfo_v*` reports primary only on some
    # Windows configs, so we fall back to the captured-image dimensions.
    if background is not None:
        vw, vh = background.size
        # On Windows, the virtual-desktop origin can be negative on multi-monitor.
        # We don't know it from PIL/mss directly; assume (0,0) for primary-only.
        # (User can re-snap region after drag.)
        try:
            import mss

            with mss.mss() as sct:
                m0 = sct.monitors[0]
                vx, vy = m0["left"], m0["top"]
        except Exception:
            vx, vy = 0, 0
    else:
        vw = win.winfo_screenwidth()
        vh = win.winfo_screenheight()
        vx, vy = 0, 0
    win.geometry(f"{vw}x{vh}+{vx}+{vy}")

    canvas = tk.Canvas(win, highlightthickness=0, bg="#000000", cursor="crosshair")
    canvas.pack(fill=tk.BOTH, expand=True)

    photo = None
    if background is not None:
        # Dim the screenshot slightly so the selection is visually distinct.
        dim = Image.eval(background, lambda v: int(v * 0.55))
        photo = ImageTk.PhotoImage(dim)
        canvas.create_image(0, 0, image=photo, anchor="nw")

    # Help banner
    banner = canvas.create_rectangle(0, 0, 0, 0, fill="#1e2530", outline="")
    banner_text_lines = [
        "Drag to select a region — Enter to confirm — Esc to cancel",
        "Tip: select tightly around the QR display for fastest reads",
    ]
    text_id = canvas.create_text(
        vw // 2, 24, text=banner_text_lines[0],
        fill="#e6ecf2", font=("Segoe UI", 12, "bold")
    )
    text_id2 = canvas.create_text(
        vw // 2, 46, text=banner_text_lines[1],
        fill="#9aa6b8", font=("Segoe UI", 10)
    )
    canvas.coords(banner, 0, 0, vw, 64)
    canvas.tag_raise(text_id)
    canvas.tag_raise(text_id2)

    rect_id: Optional[int] = None
    handle_ids: list = []
    dim_ids: list = []  # 4 rectangles dimming the *outside* of the selection
    label_id: Optional[int] = None

    drag_state = {"start": None, "end": None}

    def _redraw_selection(x0: int, y0: int, x1: int, y1: int) -> None:
        nonlocal rect_id, label_id
        # Normalize so width/height are positive
        lx, rx = (min(x0, x1), max(x0, x1))
        ty, by = (min(y0, y1), max(y0, y1))

        # Clear prior dim overlays
        for did in dim_ids:
            canvas.delete(did)
        dim_ids.clear()

        # Dim the four areas outside the selection
        outside = "#000000"
        dim_ids.append(canvas.create_rectangle(0, 0, vw, ty, fill=outside, outline="", stipple="gray50"))
        dim_ids.append(canvas.create_rectangle(0, by, vw, vh, fill=outside, outline="", stipple="gray50"))
        dim_ids.append(canvas.create_rectangle(0, ty, lx, by, fill=outside, outline="", stipple="gray50"))
        dim_ids.append(canvas.create_rectangle(rx, ty, vw, by, fill=outside, outline="", stipple="gray50"))

        # Selection rectangle
        if rect_id is None:
            rect_id = canvas.create_rectangle(lx, ty, rx, by, outline="#4a90e2", width=2)
        else:
            canvas.coords(rect_id, lx, ty, rx, by)
            canvas.itemconfigure(rect_id, outline="#4a90e2")

        # Dimensions label
        w, h = rx - lx, by - ty
        text = f"{w} × {h}"
        if label_id is None:
            label_id = canvas.create_text(
                lx + w // 2, max(ty - 14, 12), text=text,
                fill="#e6ecf2", font=("Segoe UI", 11, "bold")
            )
        else:
            canvas.coords(label_id, lx + w // 2, max(ty - 14, 12))
            canvas.itemconfigure(label_id, text=text)
        canvas.tag_raise(label_id)

        # Re-raise the banner so it stays on top
        canvas.tag_raise(banner)
        canvas.tag_raise(text_id)
        canvas.tag_raise(text_id2)

    def _on_press(event: tk.Event) -> None:
        drag_state["start"] = (event.x, event.y)
        drag_state["end"] = (event.x, event.y)
        _redraw_selection(event.x, event.y, event.x, event.y)

    def _on_drag(event: tk.Event) -> None:
        if drag_state["start"] is None:
            return
        drag_state["end"] = (event.x, event.y)
        x0, y0 = drag_state["start"]
        _redraw_selection(x0, y0, event.x, event.y)

    def _on_release(event: tk.Event) -> None:
        if drag_state["start"] is None:
            return
        drag_state["end"] = (event.x, event.y)
        _confirm()

    def _confirm(_event=None) -> None:
        if drag_state["start"] is None or drag_state["end"] is None:
            _cancel()
            return
        x0, y0 = drag_state["start"]
        x1, y1 = drag_state["end"]
        lx, ty = min(x0, x1) + vx, min(y0, y1) + vy
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w < 8 or h < 8:
            # Too small — treat as cancel so the user doesn't get stuck with junk
            _cancel()
            return
        result["region"] = (lx, ty, w, h)
        _close()

    def _cancel(_event=None) -> None:
        result["region"] = None
        _close()

    def _close() -> None:
        try:
            win.destroy()
        except tk.TclError:
            pass

    canvas.bind("<ButtonPress-1>", _on_press)
    canvas.bind("<B1-Motion>", _on_drag)
    canvas.bind("<ButtonRelease-1>", _on_release)
    win.bind("<Escape>", _cancel)
    win.bind("<Return>", _confirm)
    win.focus_force()

    # Block until the picker closes. Use grab_set so other GUI windows pause.
    try:
        win.grab_set()
    except tk.TclError:
        pass
    win.wait_window()
    return result["region"]


def pick_region_async(parent: tk.Misc, on_pick: Callable[[Optional[Region]], None]) -> None:
    """Async variant — opens the picker and calls on_pick when done.

    Useful when called from the GUI thread; doesn't block the parent's
    event loop while waiting.
    """
    region = pick_region(parent)
    parent.after(0, lambda: on_pick(region))
