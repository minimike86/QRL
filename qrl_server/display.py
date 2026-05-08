"""
QRL Display Handler

Standalone flashing-QR-code window. Used by the CLI / non-GUI workflow.
The Tk GUI uses its own embedded display logic; this class is for headless
or scripted use (and for unit-testable display-loop logic).
"""

import threading
import time
from typing import Callable, List, Optional

from PIL import Image


class DisplayHandler:
    """Displays a sequence of QR images in a Tk window, advancing on a timer."""

    def __init__(
        self,
        qr_images: List[Image.Image],
        duration: float = 0.1,
        repeat: bool = True,
        window_title: str = "QRL",
        on_frame: Optional[Callable[[int], None]] = None,
    ):
        self.qr_images = qr_images
        self.duration = duration
        self.repeat = repeat
        self.window_title = window_title
        self._on_frame = on_frame

        self._running = False
        self._index = 0
        self._cycle = 0
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Open the Tk window and begin cycling. Returns immediately."""
        if self._running:
            return
        if not self.qr_images:
            raise ValueError("No QR images to display")

        self._running = True
        self._thread = threading.Thread(target=self._tk_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def set_duration(self, duration: float) -> None:
        self.duration = duration

    def is_running(self) -> bool:
        return self._running

    def current_index(self) -> int:
        return self._index

    def cycle_count(self) -> int:
        return self._cycle

    # ------------------------------------------------------------------
    # Headless tick — pure logic, used by tests and by the embedded GUI display.
    # ------------------------------------------------------------------
    def tick(self) -> Optional[Image.Image]:
        """Advance one frame. Returns the image to show, or None when finished."""
        if not self._running:
            return None
        if self._index >= len(self.qr_images):
            self._index = 0
            self._cycle += 1
            if not self.repeat:
                self._running = False
                return None

        image = self.qr_images[self._index]
        if self._on_frame is not None:
            self._on_frame(self._index)
        self._index += 1
        return image

    # ------------------------------------------------------------------
    # Tk-driven display loop
    # ------------------------------------------------------------------
    def _tk_loop(self) -> None:
        # Imported here so the rest of the module is import-safe in headless tests.
        import tkinter as tk
        from PIL import ImageTk

        root = tk.Tk()
        root.title(self.window_title)
        root.configure(bg="white")

        first = self.qr_images[0]
        root.geometry(f"{first.size[0] + 40}x{first.size[1] + 40}")

        photo = ImageTk.PhotoImage(first)
        label = tk.Label(root, image=photo, bg="white")
        label.image = photo
        label.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

        def _close():
            self._running = False
            try:
                root.destroy()
            except tk.TclError:
                pass

        root.protocol("WM_DELETE_WINDOW", _close)
        root.bind("<Escape>", lambda _e: _close())

        def _advance():
            if not self._running:
                _close()
                return
            image = self.tick()
            if image is None:
                _close()
                return
            new_photo = ImageTk.PhotoImage(image)
            label.configure(image=new_photo)
            label.image = new_photo
            root.after(max(int(self.duration * 1000), 1), _advance)

        # Start the rotation after the first frame is drawn.
        root.after(max(int(self.duration * 1000), 1), _advance)
        try:
            root.mainloop()
        except Exception:
            pass
        finally:
            self._running = False


def play_sequence(
    qr_images: List[Image.Image],
    duration: float = 0.1,
    repeat: bool = True,
    window_title: str = "QRL",
) -> None:
    """Convenience: open the window and block until the user closes it."""
    handler = DisplayHandler(qr_images, duration=duration, repeat=repeat, window_title=window_title)
    handler.start()
    while handler.is_running():
        time.sleep(0.05)
