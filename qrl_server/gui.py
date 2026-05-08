#!/usr/bin/env python3
"""
QRL Server GUI

Workflow-first layout: pick a file, choose throughput mode, hit Start. The
flashing QR display opens in its own window optimised for tight capture from
the QRL Client.
"""

import collections
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import List, Optional

from PIL import Image, ImageTk

from qrl_client.monitors import MonitorInfo, list_monitors, monitor_at_point, primary_monitor

from .config import ConfigManager, ServerConfig
from .encoder import QRLEncoder
from .parallel_encoder import ParallelQREncoder
from .qr_generator import QRGenerator
from .ui_theme import (
    ACCENT,
    BG,
    BG_ELEVATED,
    BG_INPUT,
    BORDER,
    FG,
    FG_MUTED,
    apply_theme,
    card,
    section_heading,
    set_status,
    status_pill,
)

# Speed presets — (label, seconds per QR)
SPEED_PRESETS = [
    ("Slow (2 fps)", 0.5),
    ("Balanced (10 fps)", 0.1),
    ("Fast (20 fps)", 0.05),
    ("Max (30 fps)", 0.033),
]

# Error-correction level chips — label + EC letter.
EC_LEVELS = [
    ("L", "L"),
    ("M", "M"),
    ("Q", "Q"),
    ("H", "H"),
]

# Maximum entries in the lazy QR cache. Each cached QR image is small (mode-1
# bitmap, ~5-30 KB), but for very large files the cache could otherwise grow
# unboundedly — 100 MB / 1140 B/QR is ~88,000 chunks worth of images.
# The display only needs the next few frames to be hot at any moment, so
# evicting old entries is safe.
QR_CACHE_MAX = 4096


class _LRUDict:
    """Simple LRU dict — popping from the front on overflow keeps memory
    bounded while letting the display loop iterate sequentially without
    ever missing a cached frame.

    Composition (rather than OrderedDict subclassing) avoids subtle issues
    where dict-method-overrides in a C-backed subclass aren't always called
    by the parent's internal methods."""

    def __init__(self, max_size: int):
        self._d: "collections.OrderedDict" = collections.OrderedDict()
        self._max = max_size

    def __contains__(self, key) -> bool:
        return key in self._d

    def __getitem__(self, key):
        value = self._d[key]
        self._d.move_to_end(key)  # mark recently used
        return value

    def __setitem__(self, key, value) -> None:
        if key in self._d:
            self._d.move_to_end(key)
        self._d[key] = value
        while len(self._d) > self._max:
            self._d.popitem(last=False)

    def __len__(self) -> int:
        return len(self._d)

    def __iter__(self):
        return iter(self._d)

    def keys(self):
        return self._d.keys()

    def values(self):
        return self._d.values()


# Pixel-density presets — (label, pixels per QR module).
# Higher density = sharper QRs (more pixels per black/white cell), bigger
# native render, slower to generate, more bytes in PDF/video exports.
# For live screen-display this also gives the client more pixels per module
# to lock onto, which helps when capture is at a lower resolution than
# the QR display.
DENSITY_PRESETS = [
    ("Normal (10 px/module)", 10),
    ("Sharp (16 px/module)", 16),
    ("Ultra (24 px/module)", 24),
]


class _GridPicker(ttk.Frame):
    """Excel-style grid size picker.

    Hover to preview cols×rows, click to commit. Below the canvas: a status
    label and an Auto-fit checkbox that overrides the manual selection by
    sizing the grid to the screen at display time.

    Calls `on_change(cols, rows, auto)` whenever the user commits a change.
    """

    CELL = 14       # cell side length in px
    GAP = 2         # gap between cells in px
    MAX_COLS = 8
    MAX_ROWS = 8

    def __init__(self, parent, on_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_change = on_change
        self._cols = 1
        self._rows = 1
        self._auto = False

        canvas_w = self.MAX_COLS * (self.CELL + self.GAP) - self.GAP
        canvas_h = self.MAX_ROWS * (self.CELL + self.GAP) - self.GAP

        # Top row: canvas + status label side-by-side.
        top = ttk.Frame(self, style="Card.TFrame")
        top.pack(fill=tk.X)

        self._canvas = tk.Canvas(
            top, width=canvas_w, height=canvas_h,
            bg=BG_ELEVATED, highlightthickness=0, cursor="hand2",
        )
        self._canvas.pack(side=tk.LEFT)

        self._cell_ids = {}  # (col, row) -> canvas rect id
        for r in range(self.MAX_ROWS):
            for c in range(self.MAX_COLS):
                x0 = c * (self.CELL + self.GAP)
                y0 = r * (self.CELL + self.GAP)
                rid = self._canvas.create_rectangle(
                    x0, y0, x0 + self.CELL, y0 + self.CELL,
                    fill=BG_INPUT, outline=BORDER, width=1,
                )
                self._cell_ids[(c, r)] = rid

        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<Button-1>", self._on_click)

        # Status label to the right of the grid.
        right = ttk.Frame(top, style="Card.TFrame")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        self._status_var = tk.StringVar()
        ttk.Label(
            right, textvariable=self._status_var, style="Card.TLabel",
        ).pack(anchor="w", pady=(canvas_h // 2 - 12, 0))

        self._auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            right, text="Auto-fit screen", variable=self._auto_var,
            command=self._on_auto_toggle,
        ).pack(anchor="w", pady=(6, 0))

        self._refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_grid(self, cols: int, rows: int, auto: bool = False) -> None:
        """Programmatic set — does NOT fire on_change."""
        self._cols = max(1, min(int(cols), self.MAX_COLS))
        self._rows = max(1, min(int(rows), self.MAX_ROWS))
        self._auto = bool(auto)
        self._auto_var.set(self._auto)
        self._refresh()

    def get_grid(self) -> tuple:
        return (self._cols, self._rows, self._auto)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _on_motion(self, event) -> None:
        if self._auto:
            return
        c, r = self._xy_to_cell(event.x, event.y)
        self._paint(c + 1, r + 1, hover=True)

    def _on_leave(self, _event) -> None:
        self._refresh()

    def _on_click(self, event) -> None:
        if self._auto:
            return
        c, r = self._xy_to_cell(event.x, event.y)
        self._cols, self._rows = c + 1, r + 1
        self._refresh()
        if self._on_change:
            self._on_change(self._cols, self._rows, self._auto)

    def _on_auto_toggle(self) -> None:
        self._auto = bool(self._auto_var.get())
        self._refresh()
        if self._on_change:
            self._on_change(self._cols, self._rows, self._auto)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _xy_to_cell(self, x: int, y: int) -> tuple:
        c = x // (self.CELL + self.GAP)
        r = y // (self.CELL + self.GAP)
        c = max(0, min(int(c), self.MAX_COLS - 1))
        r = max(0, min(int(r), self.MAX_ROWS - 1))
        return c, r

    def _refresh(self) -> None:
        """Redraw using the committed selection (no hover)."""
        self._paint(self._cols, self._rows, hover=False)

    def _paint(self, cols: int, rows: int, hover: bool) -> None:
        for (c, r), rid in self._cell_ids.items():
            in_sel = c < cols and r < rows
            if self._auto:
                # Dim everything when auto is on; nothing is selectable.
                self._canvas.itemconfig(rid, fill=BG_INPUT, outline=BORDER)
            elif in_sel:
                self._canvas.itemconfig(rid, fill=ACCENT, outline=ACCENT)
            else:
                self._canvas.itemconfig(rid, fill=BG_INPUT, outline=BORDER)
        if self._auto:
            self._status_var.set("Auto-fit (sized at display time)")
        else:
            streams = cols * rows
            prefix = "Hover: " if hover else ""
            self._status_var.set(
                f"{prefix}{cols}×{rows} grid · "
                f"{streams} stream{'s' if streams != 1 else ''}"
            )


def auto_grid_for_screen(screen_w: int, screen_h: int,
                         qr_target_px: int = 240, spacing: int = 8) -> tuple:
    """How many QRs fit on a screen of (w, h) at the given per-QR pixel target?

    Returns (cols, rows). Reserves a small margin for window chrome / taskbar.
    """
    margin = 24
    usable_w = max(screen_w - margin, qr_target_px)
    usable_h = max(screen_h - margin, qr_target_px)
    cols = max(1, (usable_w + spacing) // (qr_target_px + spacing))
    rows = max(1, (usable_h + spacing) // (qr_target_px + spacing))
    return int(cols), int(rows)


class _ScrollableFrame(ttk.Frame):
    """Vertically scrollable container. Pack content into `.inner`.

    Mousewheel scrolling fires when the cursor is within this frame's bounds,
    so it coexists safely with other scrollable widgets elsewhere in the app.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg=BG)
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self.inner = ttk.Frame(self._canvas)
        self._win_id = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel, add=True)

    def _on_frame_configure(self, _event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._win_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        try:
            rx = self.winfo_rootx()
            ry = self.winfo_rooty()
            if rx <= event.x_root <= rx + self.winfo_width() and \
               ry <= event.y_root <= ry + self.winfo_height():
                self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass


class QRLServerGUI:
    """Modern QRL server GUI."""

    def __init__(self, master: Optional[tk.Misc] = None, parent: Optional[tk.Misc] = None):
        # Three modes:
        #   parent: embedded into a frame (e.g. a notebook tab in the combined GUI)
        #   master: Toplevel under another Tk root (used by tests)
        #   neither: standalone — owns its Tk root
        if parent is not None:
            self.root = ttk.Frame(parent)
            self.root.pack(fill=tk.BOTH, expand=True)
            self._window = parent.winfo_toplevel()
            self._embedded = True
            self._dnd_available = False
        elif master is None:
            try:
                from tkinterdnd2 import TkinterDnD

                self.root = TkinterDnD.Tk()
                self._dnd_available = True
            except Exception:
                self.root = tk.Tk()
                self._dnd_available = False
            self._window = self.root
            self._embedded = False
        else:
            self.root = tk.Toplevel(master)
            self._dnd_available = False
            self._window = self.root
            self._embedded = False

        if not self._embedded:
            self._window.title("QRL Server — QR Stream Encoder")
            self._window.geometry("1100x780")
            self._window.minsize(960, 680)

        self.fonts = apply_theme(self._window)

        # Application state
        self.config = ServerConfig()
        self.encoder: Optional[QRLEncoder] = None
        self.parallel_encoder: Optional[ParallelQREncoder] = None
        self.current_file: Optional[str] = None
        self.qr_images: List[Image.Image] = []
        self.encoding_thread: Optional[threading.Thread] = None
        self.is_encoding = False
        self.is_displaying = False
        self.use_parallel_encoding = False
        self.total_chunks = 0

        # Grid/mode state — _grid_cols/_grid_rows are the *effective* values
        # used by the display loop. For auto-fit they're computed at display
        # start; otherwise they mirror config.qr_grid_cols/rows.
        # _grid_cols/_grid_rows are the actual layout used by display loop.
        # For "auto" mode, these are computed at display start from the
        # server-window's current monitor dimensions.
        self._grid_cols = 1
        self._grid_rows = 1

        # Display state
        self.current_qr_index = 0
        self.display_cycle = 0
        self.qr_window: Optional[tk.Toplevel] = None
        self.qr_display_label: Optional[tk.Label] = None
        self.qr_photo: Optional[ImageTk.PhotoImage] = None
        # Cached pre-generated QR sets for parallel mode
        self._cached_qr_sets: Optional[List[List[Image.Image]]] = None
        self._manifest_qr_image: Optional[Image.Image] = None

        self._build_ui()
        self._bind_events()
        self._load_default_config()
        self._update_button_states()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Header
        header = ttk.Frame(self.root, padding=(20, 16, 20, 12))
        header.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(header, text="QRL Server", style="H1.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="Encode any file into a sequence of flashing QR codes.",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(12, 0), pady=(8, 0))
        self.status_label = status_pill(header)
        self.status_label.pack(side=tk.RIGHT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # Body — two columns
        body = ttk.Frame(self.root, padding=(20, 16))
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=2, uniform="cols")
        body.columnconfigure(1, weight=3, uniform="cols")
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_workflow_panel(left)

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_status_panel(right)

        self._build_status_bar()

    def _build_workflow_panel(self, parent: ttk.Frame) -> None:
        # === Primary actions — pinned at the bottom, always visible ===
        # Pack BEFORE the scroll area: tkinter's BOTTOM allocator takes space
        # from the bottom first, leaving the rest for the expanding scroll frame.
        action_card = card(parent)
        action_card.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        actions = ttk.Frame(action_card, style="Card.TFrame")
        actions.pack(fill=tk.X)

        ttk.Label(
            action_card,
            text=(
                "⚙ Prepare  compresses your file, splits it into chunks, and validates settings.\n"
                "▶ Start display  opens the QR window — point the client at it to receive the file."
            ),
            style="CardMuted.TLabel",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(8, 0))

        self.encode_btn = ttk.Button(actions, text="⚙  Prepare", command=self._encode_file)
        self.encode_btn.pack(side=tk.LEFT)

        self.display_btn = ttk.Button(
            actions,
            text="▶  Start display",
            style="Primary.TButton",
            command=self._start_display,
            state=tk.DISABLED,
        )
        self.display_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.stop_btn = ttk.Button(
            actions,
            text="■  Stop",
            style="Danger.TButton",
            command=self._stop_display,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.export_video_btn = ttk.Button(
            actions, text="Export video…", command=self._export_video, state=tk.DISABLED,
        )
        self.export_video_btn.pack(side=tk.RIGHT)
        self.export_pdf_btn = ttk.Button(
            actions, text="Export PDF…", command=self._export_pdf, state=tk.DISABLED,
        )
        self.export_pdf_btn.pack(side=tk.RIGHT, padx=(0, 6))

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        # === Scrollable configuration sections (1–5) ===
        scroll = _ScrollableFrame(parent)
        scroll.pack(fill=tk.BOTH, expand=True)
        sections = scroll.inner

        # === 1. File or folder ===
        file_card = card(sections)
        file_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(file_card, "1. File or folder to send", on_card=True).pack(anchor="w")
        ttk.Label(
            file_card,
            text="A folder is sent as a tar archive and auto-extracted on the client.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        file_row = ttk.Frame(file_card, style="Card.TFrame")
        file_row.pack(fill=tk.X)
        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_row, textvariable=self.file_path_var)
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        ttk.Button(file_row, text="File…", command=self._browse_file).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(file_row, text="Folder…", command=self._browse_folder).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        hint = "Drag a file or folder here, or use the buttons." if self._dnd_available else ""
        self.file_info_var = tk.StringVar(value=hint)
        ttk.Label(file_card, textvariable=self.file_info_var, style="CardMuted.TLabel").pack(
            anchor="w", pady=(8, 0)
        )

        if self._dnd_available:
            self._wire_drag_and_drop(file_card)
            self._wire_drag_and_drop(self.file_entry)

        # === 2. Speed ===
        speed_card = card(sections)
        speed_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(speed_card, "2. Display speed", on_card=True).pack(anchor="w")
        ttk.Label(
            speed_card,
            text=(
                "How long each QR code is shown before switching to the next one.\n"
                "Faster = more data per second, but the client's camera must be able to keep up.\n"
                "If the client reports missed frames, slow down."
            ),
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        speed_chips = ttk.Frame(speed_card, style="Card.TFrame")
        speed_chips.pack(fill=tk.X)
        self.speed_buttons: List[ttk.Button] = []
        for label, duration in SPEED_PRESETS:
            btn = ttk.Button(
                speed_chips,
                text=label,
                style="Chip.TButton",
                command=lambda d=duration: self._set_speed_preset(d),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self.speed_buttons.append(btn)

        # === 3. Quality / chunk size ===
        quality_card = card(sections)
        quality_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(quality_card, "3. QR quality", on_card=True).pack(anchor="w")
        ttk.Label(
            quality_card,
            text=(
                "Controls how much data fits in each QR code and how well it survives screen glare.\n"
                "Trade-off: more robustness = fewer bytes per QR = more QR codes = slower transfer."
            ),
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        # QR version picker
        version_row = ttk.Frame(quality_card, style="Card.TFrame")
        version_row.pack(fill=tk.X)
        ttk.Label(version_row, text="QR version:", style="CardMuted.TLabel").pack(side=tk.LEFT)
        version_values = ["Auto (fit data)"] + [str(v) for v in range(1, 41)]
        self.version_combo = ttk.Combobox(
            version_row, values=version_values, state="readonly", width=16,
        )
        self.version_combo.set("Auto (fit data)")
        self.version_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.version_combo.bind("<<ComboboxSelected>>", self._on_version_changed)
        self.version_cap_var = tk.StringVar()
        ttk.Label(
            version_row, textvariable=self.version_cap_var, style="CardMuted.TLabel",
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            quality_card,
            text=(
                "Version = the size/density of the QR grid (v1 = 21×21 modules, v40 = 177×177).\n"
                "Auto lets the library pick the smallest version that fits your chunk size — leave\n"
                "this on Auto unless you have a specific reason to pin it."
            ),
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # Error-correction level
        ec_chips = ttk.Frame(quality_card, style="Card.TFrame")
        ec_chips.pack(fill=tk.X, pady=(10, 0))
        self.ec_buttons: List[ttk.Button] = []
        for label, ec in EC_LEVELS:
            btn = ttk.Button(
                ec_chips,
                text=label,
                style="Chip.TButton",
                command=lambda e=ec: self._set_ec_level(e),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self.ec_buttons.append(btn)
        ttk.Label(
            quality_card,
            text="L = 7%  ·  M = 15%  ·  Q = 25%  ·  H = 30% damage/glare recovery",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # Bytes / QR slider — ceiling set by EC level + version
        chunk_row = ttk.Frame(quality_card, style="Card.TFrame")
        chunk_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(chunk_row, text="Bytes / QR:", style="CardMuted.TLabel").pack(side=tk.LEFT)
        self.chunk_size_var = tk.IntVar(value=self.config.chunk_size)
        self.chunk_slider = ttk.Scale(
            chunk_row,
            from_=50,
            to=self.config.chunk_size,
            orient=tk.HORIZONTAL,
            variable=self.chunk_size_var,
            command=self._on_chunk_slider,
        )
        self.chunk_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        self.chunk_label_var = tk.StringVar()
        ttk.Label(chunk_row, textvariable=self.chunk_label_var, style="Card.TLabel", width=8).pack(
            side=tk.LEFT
        )
        ttk.Label(
            quality_card,
            text=(
                "How many raw data bytes go into each QR code (header overhead excluded).\n"
                "More bytes = fewer QRs total but each is denser and slightly harder to scan.\n"
                "Less bytes = more QRs but each decodes more reliably. Max is set by version + EC level."
            ),
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # === 4. Pixel density ===
        density_card = card(sections)
        density_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(density_card, "4. QR pixel density", on_card=True).pack(anchor="w")
        ttk.Label(
            density_card,
            text=(
                "Screen pixels per QR module (each module is one of the tiny black/white squares).\n"
                "Higher = the generated image is physically larger and sharper.\n"
                "For live display the window scales the image to fit, so this mainly affects\n"
                "exported PDF/video quality. Leave on Normal (10 px) for everyday use."
            ),
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        density_chips = ttk.Frame(density_card, style="Card.TFrame")
        density_chips.pack(fill=tk.X)
        self.density_buttons: List[ttk.Button] = []
        for label, box_size in DENSITY_PRESETS:
            btn = ttk.Button(
                density_chips,
                text=label,
                style="Chip.TButton",
                command=lambda b=box_size: self._set_density_preset(b),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self.density_buttons.append(btn)

        # === 5. Throughput mode (single vs grid) ===
        mode_card = card(sections)
        mode_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(mode_card, "5. Throughput mode", on_card=True).pack(anchor="w")
        ttk.Label(
            mode_card,
            text=(
                "Show multiple independent QR streams side-by-side. Each stream carries a different\n"
                "portion of the file in parallel — the client reads all streams simultaneously and\n"
                "merges them. A 2×2 grid gives ~4× the data throughput of a single QR.\n"
                "The client must be able to see the entire grid clearly."
            ),
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        self.grid_picker = _GridPicker(
            mode_card, on_change=self._on_grid_changed, style="Card.TFrame"
        )
        self.grid_picker.pack(fill=tk.X)

    def _build_status_panel(self, parent: ttk.Frame) -> None:
        # Summary card
        summary_card = card(parent)
        summary_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(summary_card, "Current settings", on_card=True).pack(anchor="w")
        self.summary_var = tk.StringVar(value="No file selected.")
        ttk.Label(
            summary_card, textvariable=self.summary_var, style="Card.TLabel"
        ).pack(anchor="w", pady=(8, 0))

        # Progress card
        progress_card = card(parent)
        progress_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(progress_card, "Encoding & display progress", on_card=True).pack(anchor="w")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            progress_card, variable=self.progress_var, maximum=100
        )
        self.progress_bar.pack(fill=tk.X, pady=(8, 4))

        self.progress_label_var = tk.StringVar(value="Ready.")
        ttk.Label(
            progress_card, textvariable=self.progress_label_var, style="Card.TLabel"
        ).pack(anchor="w")

        # Stats grid
        stats = ttk.Frame(progress_card, style="Card.TFrame")
        stats.pack(fill=tk.X, pady=(10, 0))
        for col in range(4):
            stats.columnconfigure(col, weight=1, uniform="stats")

        def stat(parent, label, var):
            cell = ttk.Frame(parent, style="Card.TFrame")
            ttk.Label(cell, text=label, style="CardMuted.TLabel").pack(anchor="w")
            ttk.Label(cell, textvariable=var, style="Card.TLabel").pack(anchor="w")
            return cell

        self.chunks_stat_var = tk.StringVar(value="–")
        self.bytes_per_qr_var = tk.StringVar(value="–")
        self.throughput_var = tk.StringVar(value="–")
        self.cycle_stat_var = tk.StringVar(value="–")

        stat(stats, "Chunks", self.chunks_stat_var).grid(row=0, column=0, sticky="w")
        stat(stats, "Bytes / QR", self.bytes_per_qr_var).grid(row=0, column=1, sticky="w")
        stat(stats, "Throughput", self.throughput_var).grid(row=0, column=2, sticky="w")
        stat(stats, "Cycle", self.cycle_stat_var).grid(row=0, column=3, sticky="w")

        # Logs
        logs_card = card(parent)
        logs_card.pack(fill=tk.BOTH, expand=True)
        head_row = ttk.Frame(logs_card, style="Card.TFrame")
        head_row.pack(fill=tk.X)
        section_heading(head_row, "Activity log", on_card=True).pack(side=tk.LEFT)
        ttk.Button(head_row, text="Clear", command=self._clear_log).pack(side=tk.RIGHT)
        self.log_text = scrolledtext.ScrolledText(
            logs_card,
            height=14,
            state=tk.DISABLED,
            bg=BG_INPUT,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            borderwidth=0,
            font=self.fonts["mono"],
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    def _build_status_bar(self) -> None:
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(side=tk.BOTTOM, fill=tk.X)
        bar = ttk.Frame(self.root, padding=(20, 6))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_var, style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            bar,
            text="QRL  ·  Esc closes the QR display window",
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

    def _bind_events(self) -> None:
        if not self._embedded:
            self._window.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ------------------------------------------------------------------
    # Config / preset plumbing
    # ------------------------------------------------------------------
    def _load_default_config(self) -> None:
        try:
            self.config = ConfigManager.load_config()
        except Exception as e:
            self._log(f"Using default config: {e}")
        self._set_speed_preset(self.config.duration, refresh_only=True)
        # Sync version combo before quality preset so _sync_chunk_slider_max
        # uses the correct version when computing the slider ceiling.
        if hasattr(self, "version_combo"):
            v = self.config.qr_version
            self.version_combo.set(str(v) if v is not None else "Auto (fit data)")
        self._set_ec_level(self.config.error_correction, refresh_only=True)
        self._set_density_preset(self.config.qr_box_size, refresh_only=True)
        self._apply_grid(
            self.config.qr_grid_cols,
            self.config.qr_grid_rows,
            auto=self.config.qr_grid_auto,
            refresh_only=True,
        )
        self._refresh_summary()

    def _set_speed_preset(self, duration: float, refresh_only: bool = False) -> None:
        if not refresh_only:
            self.config.duration = duration
            if duration < 0.05:
                self._log(f"Tip: {1/duration:.0f} FPS is aggressive — make sure the client matches.")
        for btn, (_, value) in zip(self.speed_buttons, SPEED_PRESETS):
            style = (
                "ChipActive.TButton"
                if abs(value - self.config.duration) < 1e-3
                else "Chip.TButton"
            )
            btn.configure(style=style)
        self._refresh_summary()

    def _set_ec_level(self, ec: str, refresh_only: bool = False) -> None:
        if not refresh_only:
            self.config.error_correction = ec
        for btn, (_, level) in zip(self.ec_buttons, EC_LEVELS):
            btn.configure(style="ChipActive.TButton" if level == self.config.error_correction else "Chip.TButton")
        if hasattr(self, "chunk_slider"):
            self._sync_chunk_slider_max()
            self.chunk_size_var.set(self.config.chunk_size)
        self._refresh_summary()

    def _on_version_changed(self, _event=None) -> None:
        val = self.version_combo.get()
        self.config.qr_version = None if val == "Auto (fit data)" else int(val)
        self._sync_chunk_slider_max()
        self._refresh_summary()

    def _on_chunk_slider(self, _value) -> None:
        self.config.chunk_size = int(self.chunk_size_var.get())
        self._sync_chunk_slider_max()
        self._refresh_summary()

    def _sync_chunk_slider_max(self) -> None:
        """Update slider ceiling and capacity label to reflect EC level + QR version.

        Ceiling = total QR capacity minus HEADER_SIZE (9 bytes), giving the
        maximum user-visible payload that fits alongside the chunk header.
        """
        if not hasattr(self, "chunk_slider"):
            return
        from .chunk import HEADER_SIZE
        from .qr_generator import QRGenerator
        if self.config.qr_version is not None:
            total = QRGenerator.get_version_chunk_capacity(
                self.config.qr_version, self.config.error_correction
            )
            cap = max(0, total - HEADER_SIZE)
            self.version_cap_var.set(f"max {cap} B at v{self.config.qr_version}")
        else:
            total = QRGenerator.get_max_chunk_size(self.config.error_correction)
            cap = max(0, total - HEADER_SIZE)
            auto_v = self._compute_auto_version(self.config.chunk_size + HEADER_SIZE)
            self.version_cap_var.set(f"max {cap} B  ·  auto → v{auto_v}")
        cap = max(cap, 50)
        self.chunk_slider.configure(to=cap)
        if self.config.chunk_size > cap:
            self.config.chunk_size = cap
            self.chunk_size_var.set(cap)
        self.chunk_label_var.set(f"{self.config.chunk_size} B")

    def _compute_auto_version(self, needed_bytes: int) -> int:
        """Smallest QR version (1-40) that can hold needed_bytes at current EC level."""
        for v in range(1, 41):
            if QRGenerator.get_version_chunk_capacity(v, self.config.error_correction) >= needed_bytes:
                return v
        return 40

    def _set_density_preset(self, box_size: int, refresh_only: bool = False) -> None:
        """Pixels per QR module. Affects native render size and on-screen sharpness."""
        if not refresh_only:
            self.config.qr_box_size = box_size
        for btn, (_, value) in zip(self.density_buttons, DENSITY_PRESETS):
            style = "ChipActive.TButton" if value == self.config.qr_box_size else "Chip.TButton"
            btn.configure(style=style)
        self._refresh_summary()

    # Target per-QR pixel size for the Auto-fit-screen mode. Independent of
    # config.qr_physical_size (which is the MAX size for non-auto modes).
    # 400 px is a good practical default — small enough that a 1080p screen
    # still fits a 5x2 grid (10 streams = ~10× single-stream throughput) but
    # large enough that mss/pyzbar reliably reads each code from the client
    # capture. Going much smaller (e.g. 200) packs more QRs but they become
    # too small to scan, especially after capture downsampling.
    AUTO_QR_TARGET_PX = 400

    def _on_grid_changed(self, cols: int, rows: int, auto: bool) -> None:
        """Callback fired by the GridPicker when the user clicks a cell or
        toggles auto-fit."""
        self._apply_grid(cols, rows, auto=auto)

    def _apply_grid(self, cols: int, rows: int, auto: bool, *,
                    refresh_only: bool = False) -> None:
        """Update the effective grid layout used by the display loop and
        persist it to ServerConfig.

        - cols/rows are clamped to [1, 32].
        - When auto=True, the user's cols/rows are remembered (so unchecking
          auto restores them) but the *effective* grid is recomputed from the
          monitor under the server window. It's recomputed again at display
          start in case the window moved.
        - refresh_only=True skips the config write and just resyncs derived
          state and the picker UI from current config (used during config load).
        """
        if not refresh_only:
            self.config.qr_grid_cols = max(1, min(int(cols), 32))
            self.config.qr_grid_rows = max(1, min(int(rows), 32))
            self.config.qr_grid_auto = bool(auto)

        if self.config.qr_grid_auto:
            ec, er = self._auto_grid_for_current_monitor()
            self._grid_cols, self._grid_rows = ec, er
            if not refresh_only:
                self._log(
                    f"Auto-fit: {ec}×{er} = {ec*er} streams "
                    f"(monitor {self._last_auto_monitor_label})"
                )
        else:
            self._grid_cols = self.config.qr_grid_cols
            self._grid_rows = self.config.qr_grid_rows

        self._mode_streams = self._grid_cols * self._grid_rows
        self.use_parallel_encoding = self._mode_streams > 1

        # Resync the picker UI to the saved config (the user's manual
        # selection persists through auto toggling).
        picker = getattr(self, "grid_picker", None)
        if picker is not None:
            picker.set_grid(
                self.config.qr_grid_cols,
                self.config.qr_grid_rows,
                auto=self.config.qr_grid_auto,
            )
        self._refresh_summary()

    def _auto_grid_for_current_monitor(self) -> tuple:
        """Find the monitor under the server window and compute (cols, rows).
        Always uses AUTO_QR_TARGET_PX, NOT config.qr_physical_size."""
        try:
            self._window.update_idletasks()
            cx = self._window.winfo_x() + self._window.winfo_width() // 2
            cy = self._window.winfo_y() + self._window.winfo_height() // 2
            mon = monitor_at_point(cx, cy) or primary_monitor()
            if mon is None:
                self._last_auto_monitor_label = "unknown"
                return 1, 1
            self._last_auto_monitor_label = (
                f"{mon.name.split('  ·  ')[0]} {mon.width}×{mon.height}"
            )
            return auto_grid_for_screen(
                mon.width, mon.height, qr_target_px=self.AUTO_QR_TARGET_PX
            )
        except Exception as e:
            self._last_auto_monitor_label = f"error ({e})"
            return 1, 1

    def _refresh_summary(self) -> None:
        if not self.current_file:
            self.summary_var.set("Pick a file or folder to begin.")
            return
        size = getattr(self, "_current_size_bytes", 0)
        size_mb = size / (1024 * 1024)
        streams = getattr(self, "_mode_streams", 1)
        bytes_per_sec = (self.config.chunk_size * streams) / max(self.config.duration, 1e-6)
        layout = (
            f"{self._grid_cols}×{self._grid_rows} grid"
            if streams > 1
            else "single QR"
        )
        self.summary_var.set(
            f"{Path(self.current_file).name}  ·  {size_mb:.2f} MB  ·  "
            f"{self.config.chunk_size} B/QR @ {1/self.config.duration:.0f} FPS × {layout}  →  "
            f"~{bytes_per_sec/1024:.1f} KB/s"
        )

    # ------------------------------------------------------------------
    # File picker
    # ------------------------------------------------------------------
    def _wire_drag_and_drop(self, widget: tk.Widget) -> None:
        """Register a widget to accept dropped files."""
        try:
            from tkinterdnd2 import DND_FILES
        except Exception:
            return

        def _on_drop(event):
            # event.data is a Tk-quoted list of paths; pick the first
            data = event.data.strip()
            if data.startswith("{") and data.endswith("}"):
                # Path with spaces is wrapped in {}
                data = data[1:-1]
            else:
                # Multiple paths separated by spaces — take first
                data = data.split()[0] if data else ""
            data = data.strip().strip('"')
            if not data:
                return
            self._set_current_file(data)

        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", _on_drop)

    def _set_current_file(self, path: str) -> None:
        """Common handler for file/folder selection from any source (browse or DND)."""
        p = Path(path)
        if not p.exists():
            messagebox.showerror("Not found", path)
            return
        self.file_path_var.set(str(p))
        self.current_file = str(p)
        if p.is_dir():
            file_count, total_size = self._summarize_directory(p)
            self._current_size_bytes = total_size
            self.file_info_var.set(
                f"📁 folder  ·  {file_count:,} files  ·  "
                f"{total_size:,} bytes  ·  {total_size/1024/1024:.2f} MB "
                f"(packed as tar archive)"
            )
        else:
            size = p.stat().st_size
            self._current_size_bytes = size
            self.file_info_var.set(
                f"📄 file  ·  {size:,} bytes  ·  {size/1024/1024:.2f} MB"
            )
        self._refresh_summary()
        self._update_button_states()

    @staticmethod
    def _summarize_directory(root: Path) -> tuple:
        """Walk a directory and return (file_count, total_bytes)."""
        count = 0
        total = 0
        try:
            for sub in root.rglob("*"):
                if sub.is_file():
                    count += 1
                    try:
                        total += sub.stat().st_size
                    except OSError:
                        pass
        except (PermissionError, OSError):
            pass
        return count, total

    def _browse_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select file to encode",
            filetypes=[
                ("All files", "*.*"),
                ("Text files", "*.txt *.md"),
                ("Image files", "*.jpg *.jpeg *.png *.bmp"),
                ("PDF / docs", "*.pdf *.doc *.docx"),
            ],
        )
        if filename:
            self._set_current_file(filename)

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder to encode (sent as tar)")
        if folder:
            self._set_current_file(folder)

    # ------------------------------------------------------------------
    # Encode workflow
    # ------------------------------------------------------------------
    def _encode_file(self) -> None:
        if not self.current_file or not Path(self.current_file).exists():
            messagebox.showerror("No file", "Please pick a valid file first.")
            return
        if self.is_encoding:
            return
        try:
            self.config.validate()
        except ValueError as e:
            messagebox.showerror("Configuration error", str(e))
            return

        self.is_encoding = True
        set_status(self.status_label, "running", "Encoding")
        self._update_status("Encoding…")
        self._update_button_states()
        self.encoding_thread = threading.Thread(target=self._encode_worker, daemon=True)
        self.encoding_thread.start()

    def _encode_worker(self) -> None:
        """Encoding pipeline. QR images are NOT pre-generated — they're
        rendered on-the-fly during display (with a lazy cache so repeat
        cycles are fast). This makes "Prepare" finish in milliseconds instead
        of waiting for thousands of QRs to be encoded upfront."""
        try:
            src_path = Path(self.current_file)
            is_dir = src_path.is_dir()
            file_size = getattr(self, "_current_size_bytes", 0) or src_path.stat().st_size
            kind = "folder" if is_dir else "file"
            self._log_main(
                f"▸ Encoding {kind}: {src_path.name}  ({file_size:,} bytes / {file_size/1024/1024:.2f} MB)"
            )
            if file_size == 0:
                raise ValueError(f"{kind.title()} is empty")
            if file_size > self.config.max_file_size:
                raise ValueError(
                    f"{kind.title()} ({file_size/1024/1024:.1f} MB) exceeds max ({self.config.max_file_size/1024/1024:.1f} MB)"
                )
            if is_dir:
                self._log_main("  ↳ Packing as tar archive (auto-extracted on the client)")

            if self.config.qr_grid_auto:
                cols, rows = self._auto_grid_for_current_monitor()
                self._grid_cols, self._grid_rows = cols, rows
                self._mode_streams = cols * rows
                self.use_parallel_encoding = self._mode_streams > 1
                self._log_main(f"▸ Auto-grid: {cols}×{rows} = {cols*rows} parallel streams")

            # Reset caches — bounded LRU so very large files (tens of
            # thousands of chunks) don't blow memory.
            self._qr_cache = _LRUDict(QR_CACHE_MAX)
            self._qr_set_cache = _LRUDict(QR_CACHE_MAX)
            self._manifest_qr_image = None

            if self.use_parallel_encoding:
                streams = self._mode_streams
                self._log_main(
                    f"▸ Splitting across {streams} parallel streams "
                    f"(chunk size {self.config.chunk_size} B)…"
                )
                self.parallel_encoder = ParallelQREncoder(
                    self.current_file,
                    num_streams=streams,
                    chunk_size=self.config.chunk_size,
                    error_correction=self.config.error_correction,
                    box_size=self.config.qr_box_size,
                    border=self.config.qr_border,
                    qr_version=self.config.qr_version,
                )
                self.parallel_encoder.prepare_parallel_streams()
                self.total_chunks = self.parallel_encoder.get_total_chunks()
                stats = self.parallel_encoder.calculate_theoretical_throughput(
                    self.config.duration
                )
                total_qrs = self.total_chunks * streams
                if self.parallel_encoder._compressed:
                    ratio = self.parallel_encoder._original_size / max(len(self.parallel_encoder._data), 1)
                    self._log_main(
                        f"  Compressed {self.parallel_encoder._original_size:,} → "
                        f"{len(self.parallel_encoder._data):,} bytes ({ratio:.1f}× speedup over the wire)"
                    )
                else:
                    self._log_main("  Skipping compression (data doesn't shrink — already compressed)")
                self._log_main(
                    f"  {self.total_chunks:,} chunks/stream  ·  "
                    f"{total_qrs:,} QR images total  ·  "
                    f"~{stats.get('kilobytes_per_second', 0):.1f} KB/s theoretical"
                )
            else:
                self._log_main(f"▸ Splitting file (chunk size {self.config.chunk_size} B)…")
                self.encoder = QRLEncoder(
                    self.current_file,
                    chunk_size=self.config.chunk_size,
                    qr_version=self.config.qr_version,
                    error_correction=self.config.error_correction,
                    box_size=self.config.qr_box_size,
                    border=self.config.qr_border,
                )
                self.total_chunks = self.encoder.prepare_chunks()
                if self.encoder._compressed:
                    ratio = self.encoder._original_size / max(len(self.encoder._data), 1)
                    self._log_main(
                        f"  Compressed {self.encoder._original_size:,} → "
                        f"{len(self.encoder._data):,} bytes ({ratio:.1f}× speedup over the wire)"
                    )
                else:
                    self._log_main("  Skipping compression (data doesn't shrink — already compressed)")
                self._log_main(f"  {self.total_chunks:,} chunks ready")

            self._log_main("▸ Ready to display — QRs generate in background while you watch")
            # Kick off non-blocking background prefetch so the display loop
            # can read pre-rendered frames from the cache instead of generating
            # them inline (which would stall display when grids are large).
            self._start_background_prefetch()
            self.root.after(0, self._encoding_complete)
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._encoding_error(err))
        finally:
            self.is_encoding = False
            self.root.after(0, self._update_button_states)

    def _start_background_prefetch(self) -> None:
        """Background QR prefetch.

        For files that fit in the LRU cache (small/medium): runs to completion
        and leaves every QR cached. Display reads from cache after the first
        moment and runs at full FPS.

        For files larger than the cache: stays AHEAD of the display position
        by a fixed window (LOOKAHEAD entries). Old entries are evicted as
        new ones come in. Display still benefits — every frame is a cache
        hit at the moment it's needed."""
        self._prefetch_gen = getattr(self, "_prefetch_gen", 0) + 1
        gen = self._prefetch_gen

        # How far ahead of the display index to stay. Smaller = less wasted
        # work if user stops early; larger = more cushion when generation
        # is slower than display rate.
        LOOKAHEAD = 256

        def _root_alive() -> bool:
            try:
                return bool(self.root.winfo_exists())
            except (tk.TclError, RuntimeError, AttributeError):
                return False

        def _display_position() -> int:
            return self.current_qr_index if self.is_displaying else 0

        def worker():
            try:
                t0 = time.time()
                if self.use_parallel_encoding and self.parallel_encoder is not None:
                    total = self.total_chunks
                    streams = self._mode_streams
                    bounded = total > QR_CACHE_MAX
                    last_decile = -1
                    for i in range(total):
                        if gen != self._prefetch_gen or not _root_alive():
                            return
                        # Stay within LOOKAHEAD of the display position when
                        # the file exceeds the cache — otherwise the LRU
                        # would just evict our work before display sees it.
                        while bounded and (i - _display_position()) > LOOKAHEAD:
                            if gen != self._prefetch_gen or not _root_alive():
                                return
                            time.sleep(0.05)
                        if i not in self._qr_set_cache:
                            self._qr_set_cache[i] = self.parallel_encoder.generate_qr_set(i)
                        decile = (i + 1) * 10 // max(total, 1)
                        if decile > last_decile and decile < 10:
                            last_decile = decile
                            self._log_main(
                                f"  …generated {decile*10}% ({i+1}/{total} sets, {streams * (i+1):,} QRs)"
                            )
                    elapsed = time.time() - t0
                    msg = "Cache full" if not bounded else "All QRs generated"
                    self._log_main(f"  ✓ {msg}: {total * streams:,} QRs in {elapsed:.1f}s")
                elif self.encoder is not None:
                    total = self.total_chunks
                    bounded = total > QR_CACHE_MAX
                    last_decile = -1
                    for i in range(total):
                        if gen != self._prefetch_gen or not _root_alive():
                            return
                        while bounded and (i - _display_position()) > LOOKAHEAD:
                            if gen != self._prefetch_gen or not _root_alive():
                                return
                            time.sleep(0.05)
                        if i not in self._qr_cache:
                            self._qr_cache[i] = self.encoder.generate_qr_for_chunk(i)
                        decile = (i + 1) * 10 // max(total, 1)
                        if decile > last_decile and decile < 10:
                            last_decile = decile
                            self._log_main(f"  …generated {decile*10}% ({i+1}/{total} QRs)")
                    elapsed = time.time() - t0
                    msg = "Cache full" if not bounded else "All QRs generated"
                    self._log_main(f"  ✓ {msg}: {total:,} QRs in {elapsed:.1f}s")
            except Exception as e:
                self._log_main(f"  ✗ Background generation error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _cpu_count() -> int:
        import os
        return os.cpu_count() or 4

    def _log_main(self, msg: str) -> None:
        """Log to the activity panel from any thread (marshals to main thread).

        Silently no-ops if the root has been destroyed — important for
        background threads that may outlive the GUI (e.g. prefetch workers
        that finish after the user closes the window or a test tears down)."""
        try:
            self.root.after(0, lambda: self._log(msg))
        except (tk.TclError, RuntimeError):
            pass

    def _set_progress_label(self, text: str) -> None:
        try:
            self.root.after(0, lambda: self.progress_label_var.set(text))
        except (tk.TclError, RuntimeError):
            pass

    def _on_prefetch_progress(self, done: int, total: int, start_time: float) -> None:
        """Called from worker thread as QRs finish. Throttled to avoid log spam."""
        now = time.time()
        # Update progress label every ~0.25s
        last = getattr(self, "_last_progress_at", 0)
        if now - last > 0.25 or done == total:
            self._last_progress_at = now
            elapsed = now - start_time
            rate = done / max(elapsed, 1e-3)
            self._set_progress_label(
                f"Generating QR images: {done:,} / {total:,}  ·  {rate:.0f} QR/s"
            )
        # Log only at decile boundaries to avoid spamming the activity log
        last_decile = getattr(self, "_last_logged_decile", -1)
        decile = (done * 10) // max(total, 1)
        if decile > last_decile and decile < 10:
            self._last_logged_decile = decile
            self._log_main(f"  …{decile*10}%  ({done:,} / {total:,} QRs)")
        if done == total:
            self._last_logged_decile = -1  # reset for next encode

    def _encoding_complete(self) -> None:
        self.progress_var.set(100)
        self.progress_label_var.set(f"Ready to send {self.total_chunks:,} QR codes.")
        set_status(self.status_label, "ok", "Ready")
        self._update_status("Ready to display")
        self.chunks_stat_var.set(f"{self.total_chunks:,}")
        self.bytes_per_qr_var.set(f"{self.config.chunk_size}")
        bps = (self.config.chunk_size * getattr(self, "_mode_streams", 1)) / max(self.config.duration, 1e-6)
        self.throughput_var.set(f"{bps/1024:.1f} KB/s")

    def _encoding_error(self, msg: str) -> None:
        self.progress_label_var.set(f"Error: {msg}")
        set_status(self.status_label, "error", "Error")
        self._update_status("Encoding failed")
        self._log(f"✗ {msg}")
        messagebox.showerror("Encoding error", msg)

    # ------------------------------------------------------------------
    # Display workflow
    # ------------------------------------------------------------------
    def _start_display(self) -> None:
        if self.total_chunks == 0:
            messagebox.showerror("Nothing to display", "Prepare a file first.")
            return
        if self.is_displaying:
            return
        self.is_displaying = True
        set_status(self.status_label, "running", "Displaying")
        self._update_status("Displaying QR sequence…")
        self._log("Opening QR display window…")
        self._update_button_states()
        self.current_qr_index = 0
        self.display_cycle = 0
        self._showed_manifest_this_cycle = False
        try:
            self._create_qr_display_window()
        except Exception as e:
            self._log(f"✗ Failed to open display window: {e}")
            self.is_displaying = False
            set_status(self.status_label, "error", "Display error")
            self._update_button_states()
            messagebox.showerror("Display window failed", str(e))
            return
        # Schedule the first frame after the window is fully drawn
        self.root.after(150, self._show_next_qr)

    def _stop_display(self) -> None:
        self.is_displaying = False
        try:
            if self.qr_window is not None and self.qr_window.winfo_exists():
                self.qr_window.destroy()
        except (AttributeError, tk.TclError):
            pass
        self.qr_window = None
        set_status(self.status_label, "idle", "Idle")
        self._update_status("Display stopped")
        self._update_button_states()

    def _create_qr_display_window(self) -> None:
        self.qr_window = tk.Toplevel(self._window)
        self.qr_window.title("QRL Display  ·  F11: fullscreen  ·  Esc: exit/close")
        self.qr_window.configure(bg="white")

        # Find the monitor that the SERVER window is currently on, so the
        # QR display opens on the same screen the user is looking at.
        self._window.update_idletasks()
        cx = self._window.winfo_x() + self._window.winfo_width() // 2
        cy = self._window.winfo_y() + self._window.winfo_height() // 2
        target = monitor_at_point(cx, cy) or primary_monitor()

        if self.config.fullscreen and target is not None:
            # Position on target monitor at full size, then enable -fullscreen
            # below. Doing both in one go can leave fullscreen on the original
            # monitor because the geometry move is async.
            self.qr_window.geometry(
                f"{target.width}x{target.height}{target.x:+d}{target.y:+d}"
            )
            self._log(f"QR display fullscreen on {target.name} ({target.width}x{target.height})")
        else:
            # Windowed: pick a sensible square and center on the target monitor.
            win_w = win_h = 800
            if target is not None:
                off_x = target.x + max((target.width - win_w) // 2, 0)
                off_y = target.y + max((target.height - win_h) // 2, 0)
                self.qr_window.geometry(f"{win_w}x{win_h}{off_x:+d}{off_y:+d}")
                self._log(f"QR display windowed on {target.name} ({win_w}x{win_h})")
            else:
                self.qr_window.geometry(f"{win_w}x{win_h}")

        self.qr_display_label = tk.Label(
            self.qr_window, bg="white", text="Loading…", font=self.fonts["body"]
        )
        self.qr_display_label.pack(expand=True, fill=tk.BOTH)

        def _close():
            self.is_displaying = False
            try:
                if self.qr_window is not None and self.qr_window.winfo_exists():
                    self.qr_window.destroy()
            except tk.TclError:
                pass
            self.qr_window = None
            self._update_button_states()
            set_status(self.status_label, "idle", "Idle")

        def _toggle_fullscreen(_e=None):
            if self.qr_window is None:
                return
            self.qr_window.attributes(
                "-fullscreen", not self.qr_window.attributes("-fullscreen")
            )

        def _escape(_e=None):
            # Exit fullscreen first if currently fullscreen; otherwise close.
            if self.qr_window is None:
                return
            if self.qr_window.attributes("-fullscreen"):
                self.qr_window.attributes("-fullscreen", False)
            else:
                _close()

        self.qr_window.protocol("WM_DELETE_WINDOW", _close)
        self.qr_window.bind("<Escape>", _escape)
        self.qr_window.bind("<F11>", _toggle_fullscreen)

        # Force the window to materialize on the target monitor BEFORE
        # optionally going fullscreen — otherwise -fullscreen captures
        # whichever monitor the window happened to be created on.
        self.qr_window.deiconify()
        self.qr_window.lift()
        self.qr_window.focus_force()
        self.qr_window.update_idletasks()
        self.qr_window.update()

        if self.config.fullscreen:
            self.qr_window.attributes("-topmost", True)
            self.qr_window.attributes("-fullscreen", True)
            self.qr_window.update_idletasks()
            # Drop topmost after a moment so it doesn't stay above everything forever
            self.qr_window.after(500, lambda: self.qr_window.attributes("-topmost", False)
                                 if self.qr_window else None)

    def _show_next_qr(self) -> None:
        if not self.is_displaying or not self.qr_window:
            return
        try:
            # At the start of each cycle, show the manifest QR once so a
            # late-joining client can pick up the filename. Generated lazily.
            if not self._showed_manifest_this_cycle:
                self._showed_manifest_this_cycle = True
                if self._manifest_qr_image is None:
                    self._manifest_qr_image = self._lazy_manifest()
                if self._manifest_qr_image is not None:
                    self._render_single(self._manifest_qr_image)
                    self.qr_window.title("QRL Display  ·  manifest")
                    if self.is_displaying:
                        self.root.after(
                            max(int(self.config.duration * 1000), 1), self._show_next_qr
                        )
                    return

            if self.use_parallel_encoding and self.parallel_encoder:
                qr_images = self._lazy_qr_set(self.current_qr_index)
                cols, rows = self._grid_cols, self._grid_rows
                self.current_qr_index += 1
            else:
                cols, rows = self._grid_cols, self._grid_rows
                cells = cols * rows
                qr_images = []
                for i in range(cells):
                    chunk_idx = (self.current_qr_index + i) % self.total_chunks
                    qr_images.append(self._lazy_qr_image(chunk_idx))
                self.current_qr_index += cells

            combined = self._compose_grid(qr_images, cols, rows)
            self._render_single(combined)

            # Progress + window title
            pct = (self.current_qr_index / max(self.total_chunks, 1)) * 100
            self.progress_var.set(min(pct, 100))
            self.progress_label_var.set(
                f"QR {min(self.current_qr_index, self.total_chunks):,}/{self.total_chunks:,}"
                + (f" — cycle {self.display_cycle + 1}" if self.display_cycle else "")
            )
            self.cycle_stat_var.set(f"{self.display_cycle + 1}")
            self.qr_window.title(
                f"QRL Display  ·  {min(self.current_qr_index, self.total_chunks):,}/{self.total_chunks:,}"
            )

            if self.current_qr_index >= self.total_chunks:
                self.current_qr_index = 0
                self.display_cycle += 1
                self._showed_manifest_this_cycle = False  # show manifest again next cycle
                if not self.config.repeat:
                    self.is_displaying = False
                    self._update_status("Display complete")
                    set_status(self.status_label, "ok", "Complete")
                    self._update_button_states()
                    if self.qr_window:
                        self.qr_window.destroy()
                        self.qr_window = None
                    return

            if self.is_displaying:
                self.root.after(max(int(self.config.duration * 1000), 1), self._show_next_qr)
        except Exception as e:
            self._log(f"Display error: {e}")
            self.is_displaying = False
            self._update_button_states()
            set_status(self.status_label, "error", "Display error")

    # ------------------------------------------------------------------
    # Lazy QR generation — generate on first access, cache with LRU bound
    # ------------------------------------------------------------------
    def _lazy_qr_image(self, chunk_idx: int) -> Image.Image:
        cache = getattr(self, "_qr_cache", None)
        if cache is None:
            self._qr_cache = cache = _LRUDict(QR_CACHE_MAX)
        if chunk_idx not in cache:
            cache[chunk_idx] = self.encoder.generate_qr_for_chunk(chunk_idx)
        return cache[chunk_idx]

    def _lazy_qr_set(self, set_idx: int) -> List[Image.Image]:
        cache = getattr(self, "_qr_set_cache", None)
        if cache is None:
            self._qr_set_cache = cache = _LRUDict(QR_CACHE_MAX)
        if set_idx not in cache:
            cache[set_idx] = self.parallel_encoder.generate_qr_set(set_idx)
        return cache[set_idx]

    def _lazy_manifest(self) -> Optional[Image.Image]:
        if self.use_parallel_encoding and self.parallel_encoder is not None:
            return self.parallel_encoder.generate_manifest_qr()
        if self.encoder is not None:
            return self.encoder.generate_manifest_qr(num_streams=1)
        return None

    def _render_single(self, image: Image.Image) -> None:
        """Render a single PIL image, fit to the display window."""
        win_w = max(self.qr_window.winfo_width(), 200)
        win_h = max(self.qr_window.winfo_height(), 200)
        iw, ih = image.size
        # Fit-to-window in both directions (scale up or down). NEAREST keeps
        # module boundaries sharp on upscale; BICUBIC smooths the rare downscale.
        scale = min(win_w / iw, win_h / ih) if iw and ih else 1.0
        if abs(scale - 1.0) > 0.01:
            new_w = max(int(iw * scale), 1)
            new_h = max(int(ih * scale), 1)
            resample = Image.Resampling.NEAREST if scale > 1.0 else Image.Resampling.BICUBIC
            image = image.resize((new_w, new_h), resample)
        self.qr_photo = ImageTk.PhotoImage(image)
        self.qr_display_label.configure(image=self.qr_photo, text="")
        self.qr_display_label.image = self.qr_photo

    def _compose_grid(
        self,
        qr_images: List[Image.Image],
        cols: int,
        rows: int,
        target_w: Optional[int] = None,
        target_h: Optional[int] = None,
    ) -> Image.Image:
        """Compose `qr_images` into a `cols × rows` grid.

        Uses the display window dimensions when available (live display); when
        called from an offscreen context (export), pass target_w/target_h —
        defaults sized for a comfortable export."""
        if not qr_images:
            raise ValueError("No QR images")
        spacing = 8
        if target_w is None or target_h is None:
            if self.qr_window is not None:
                target_w = max(self.qr_window.winfo_width(), 200) - 16
                target_h = max(self.qr_window.winfo_height(), 200) - 16
            else:
                # Offscreen / export default: 1920×1080 canvas
                target_w = 1920
                target_h = 1080
        per_w = max((target_w - spacing * (cols - 1)) // cols, 64)
        per_h = max((target_h - spacing * (rows - 1)) // rows, 64)
        per_qr = min(per_w, per_h)  # square cells

        # Resize at INTEGER multiples of native QR size: a naïve NEAREST resize
        # from e.g. 370 → 400 makes some modules 11px wide and others 10px,
        # which confuses pyzbar. Snapping to a clean multiple keeps every
        # module identical. Some pixel area may go unused (white margin) but
        # that strictly helps scanning reliability.
        resized = [self._resize_to_clean_multiple(img, per_qr) for img in qr_images]
        while len(resized) < cols * rows:
            resized.append(Image.new("RGB", (per_qr, per_qr), "white"))

        total_w = per_qr * cols + spacing * (cols - 1)
        total_h = per_qr * rows + spacing * (rows - 1)
        canvas = Image.new("RGB", (total_w, total_h), "white")
        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c
                qr = resized[idx]
                cell_x = c * (per_qr + spacing)
                cell_y = r * (per_qr + spacing)
                # Centre the QR in its cell so any leftover slack becomes
                # extra white margin (more quiet zone is good).
                ox = cell_x + (per_qr - qr.size[0]) // 2
                oy = cell_y + (per_qr - qr.size[1]) // 2
                canvas.paste(qr, (ox, oy))
        return canvas

    def _resize_to_clean_multiple(
        self, qr_img: Image.Image, target_px: int, box_size: Optional[int] = None
    ) -> Image.Image:
        """Resize a QR image so every module is the same size in the output.

        The image was rendered at `box_size` pixels per module. The QR has
        `module_count = native // box_size` modules per side (including the
        quiet zone border). To preserve uniform modules in the output we must
        snap target_px to a multiple of `module_count`."""
        native = qr_img.size[0]  # QR images are square
        if native == 0:
            return qr_img
        if box_size is None:
            box_size = self.config.qr_box_size if self.config else QRGenerator.DEFAULT_BOX_SIZE
        module_count = max(1, native // max(box_size, 1))

        # Pick the largest integer pixels-per-module that fits target_px
        per_module = target_px // module_count
        new_size = per_module * module_count

        # Cell smaller than module_count — must non-integer resize to fit at all.
        if new_size <= 0 or new_size > target_px:
            return qr_img.resize((target_px, target_px), Image.Resampling.BILINEAR)

        # Integer-multiple snap would waste >15% of the cell (typical for a
        # 4x4 grid in a small window). BILINEAR at full target_px is ~2-3x
        # faster than BICUBIC and decoded fine by pyzbar after screen capture.
        if new_size < target_px * 0.85:
            return qr_img.resize((target_px, target_px), Image.Resampling.BILINEAR)

        if new_size == native:
            return qr_img
        return qr_img.resize((new_size, new_size), Image.Resampling.NEAREST)

    # ------------------------------------------------------------------
    # Exports — PDF (paginated) and MP4 video
    # ------------------------------------------------------------------
    def _frames_for_export(self):
        """Yield the sequence of composed display frames as PIL Images.
        Includes the manifest as the first frame, then one frame per chunk
        index with the same grid layout the live display would use."""
        # Manifest first
        manifest = self._lazy_manifest()
        if manifest is not None:
            yield manifest

        cols, rows = self._grid_cols, self._grid_rows
        if self.use_parallel_encoding and self.parallel_encoder:
            for set_idx in range(self.total_chunks):
                imgs = self.parallel_encoder.generate_qr_set(set_idx)
                yield self._compose_grid(imgs, cols, rows)
        else:
            cells = cols * rows
            i = 0
            while i < self.total_chunks:
                batch = []
                for j in range(cells):
                    idx = (i + j) % self.total_chunks
                    batch.append(self.encoder.generate_qr_for_chunk(idx))
                yield self._compose_grid(batch, cols, rows)
                i += cells

    def _export_pdf(self) -> None:
        if self.total_chunks == 0:
            messagebox.showerror("Nothing to export", "Prepare a file first.")
            return
        out = filedialog.asksaveasfilename(
            title="Export QR sequence as PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"{Path(self.current_file).stem}_qr.pdf" if self.current_file else "qr.pdf",
        )
        if not out:
            return
        threading.Thread(target=self._export_pdf_worker, args=(out,), daemon=True).start()

    def _export_pdf_worker(self, out_path: str) -> None:
        try:
            self._log_main(f"▸ Exporting PDF → {out_path}")
            t0 = time.time()
            frames = list(self._frames_for_export())
            if not frames:
                raise ValueError("No frames to export")
            # PIL writes multipage PDFs natively. Convert to RGB to be safe.
            rgb_frames = [f.convert("RGB") for f in frames]
            rgb_frames[0].save(
                out_path,
                save_all=True,
                append_images=rgb_frames[1:],
                resolution=150.0,
            )
            elapsed = time.time() - t0
            self._log_main(f"  ✓ Wrote {len(frames)} pages in {elapsed:.2f}s")
            self.root.after(
                0, lambda: messagebox.showinfo("PDF saved", f"{len(frames)} pages → {out_path}")
            )
        except Exception as e:
            self._log_main(f"  ✗ PDF export failed: {e}")
            self.root.after(0, lambda err=str(e): messagebox.showerror("PDF export failed", err))

    def _export_video(self) -> None:
        if self.total_chunks == 0:
            messagebox.showerror("Nothing to export", "Prepare a file first.")
            return
        out = filedialog.asksaveasfilename(
            title="Export QR sequence as video",
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4")],
            initialfile=f"{Path(self.current_file).stem}_qr.mp4" if self.current_file else "qr.mp4",
        )
        if not out:
            return
        threading.Thread(target=self._export_video_worker, args=(out,), daemon=True).start()

    def _export_video_worker(self, out_path: str) -> None:
        try:
            import cv2
            import numpy as np

            fps = max(round(1.0 / max(self.config.duration, 1e-3)), 1)
            self._log_main(f"▸ Exporting video at {fps} FPS → {out_path}")
            t0 = time.time()

            frames = list(self._frames_for_export())
            if not frames:
                raise ValueError("No frames to export")

            # Pad all frames to the size of the largest one (manifest may be
            # smaller than a parallel-grid composed frame).
            max_w = max(f.width for f in frames)
            max_h = max(f.height for f in frames)

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(out_path, fourcc, fps, (max_w, max_h))
            if not writer.isOpened():
                raise RuntimeError("OpenCV could not open video writer (codec missing?)")

            for i, frame in enumerate(frames):
                rgb = frame.convert("RGB")
                if rgb.size != (max_w, max_h):
                    canvas = Image.new("RGB", (max_w, max_h), "white")
                    canvas.paste(rgb, ((max_w - rgb.width) // 2, (max_h - rgb.height) // 2))
                    rgb = canvas
                bgr = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
                writer.write(bgr)
                if (i + 1) % max(1, len(frames) // 10) == 0:
                    self._log_main(f"  …{(i+1)*100//len(frames)}% ({i+1}/{len(frames)})")

            writer.release()
            elapsed = time.time() - t0
            self._log_main(f"  ✓ {len(frames)} frames @ {fps} FPS in {elapsed:.2f}s")
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Video saved", f"{len(frames)} frames @ {fps} FPS → {out_path}"
                ),
            )
        except Exception as e:
            self._log_main(f"  ✗ Video export failed: {e}")
            self.root.after(0, lambda err=str(e): messagebox.showerror("Video export failed", err))

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _update_button_states(self) -> None:
        if self.is_encoding:
            self.encode_btn.configure(state=tk.DISABLED)
            self.display_btn.configure(state=tk.DISABLED)
            self.export_pdf_btn.configure(state=tk.DISABLED)
            self.export_video_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.DISABLED)
            return
        has_file = bool(self.current_file)
        has_chunks = self.total_chunks > 0
        self.encode_btn.configure(state=tk.NORMAL if has_file else tk.DISABLED)
        self.display_btn.configure(
            state=tk.NORMAL if has_chunks and not self.is_displaying else tk.DISABLED
        )
        self.export_pdf_btn.configure(state=tk.NORMAL if has_chunks else tk.DISABLED)
        self.export_video_btn.configure(state=tk.NORMAL if has_chunks else tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL if self.is_displaying else tk.DISABLED)

    def _update_status(self, text: str) -> None:
        self.status_var.set(text)

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def shutdown(self) -> None:
        """Stop background work without destroying the window. Used by the
        combined GUI when the user closes the parent window."""
        if self.is_encoding:
            self.is_encoding = False
        self._stop_display()
        # Invalidate any in-flight prefetch generation
        self._prefetch_gen = getattr(self, "_prefetch_gen", 0) + 1

    def _on_closing(self) -> None:
        if self.is_encoding:
            if not messagebox.askyesno("Quit", "Encoding in progress. Quit anyway?"):
                return
        self._stop_display()
        if self._embedded:
            return
        try:
            self._window.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        if self._embedded:
            return
        try:
            self._window.mainloop()
        except KeyboardInterrupt:
            self._on_closing()


def main() -> None:
    try:
        app = QRLServerGUI()
        app.run()
    except Exception as e:
        print(f"Error starting QRL Server GUI: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
