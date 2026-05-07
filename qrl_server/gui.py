#!/usr/bin/env python3
"""
QRL Server GUI

Workflow-first layout: pick a file, choose throughput mode, hit Start. The
flashing QR display opens in its own window optimised for tight capture from
the QRL Client.
"""

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

# Robustness presets — (label, error correction level, suggested chunk size)
QUALITY_PRESETS = [
    ("Maximum throughput", "L", 2670),
    ("Balanced", "Q", 1490),
    ("Robust", "H", 1140),
]

# Parallel mode presets — value is either an int num_streams or "auto".
# "auto" computes a fill-the-screen grid at display time.
MODE_PRESETS = [
    ("Single stream", 1),
    ("2×2 grid (4×)", 4),
    ("3×3 grid (9×)", 9),
    ("4×4 grid (16×)", 16),
    ("Auto-fit screen", "auto"),
]


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


class QRLServerGUI:
    """Modern QRL server GUI."""

    def __init__(self, master: Optional[tk.Misc] = None):
        # Tests share a single Tk root via a Toplevel; production creates its own.
        # When standalone, prefer TkinterDnD.Tk so file drag-and-drop works.
        if master is None:
            try:
                from tkinterdnd2 import TkinterDnD

                self.root = TkinterDnD.Tk()
                self._dnd_available = True
            except Exception:
                self.root = tk.Tk()
                self._dnd_available = False
        else:
            self.root = tk.Toplevel(master)
            self._dnd_available = False
        self.root.title("QRL Server — QR Stream Encoder")
        self.root.geometry("1100x780")
        self.root.minsize(960, 680)

        self.fonts = apply_theme(self.root)

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

        # Grid/mode state
        # _mode_value is one of: int (num_streams), "auto"
        self._mode_value = 1
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
        # === 1. File ===
        file_card = card(parent)
        file_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(file_card, "1. File to send", on_card=True).pack(anchor="w")
        ttk.Label(
            file_card,
            text="Pick any binary or text file.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        file_row = ttk.Frame(file_card, style="Card.TFrame")
        file_row.pack(fill=tk.X)
        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_row, textvariable=self.file_path_var)
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        ttk.Button(file_row, text="Browse…", command=self._browse_file).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        # Drag-and-drop hint + wire up DND on the file entry if available
        hint = "Drag a file here or use Browse." if self._dnd_available else ""
        self.file_info_var = tk.StringVar(value=hint)
        ttk.Label(file_card, textvariable=self.file_info_var, style="CardMuted.TLabel").pack(
            anchor="w", pady=(8, 0)
        )

        if self._dnd_available:
            self._wire_drag_and_drop(file_card)
            self._wire_drag_and_drop(self.file_entry)

        # === 2. Speed ===
        speed_card = card(parent)
        speed_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(speed_card, "2. Display speed", on_card=True).pack(anchor="w")
        ttk.Label(
            speed_card,
            text="Faster sends more data per second; the client must keep up.",
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
        quality_card = card(parent)
        quality_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(quality_card, "3. QR quality", on_card=True).pack(anchor="w")
        ttk.Label(
            quality_card,
            text="Higher robustness recovers from screen glare; lower fits more bytes per QR.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        quality_chips = ttk.Frame(quality_card, style="Card.TFrame")
        quality_chips.pack(fill=tk.X)
        self.quality_buttons: List[ttk.Button] = []
        for label, ec, chunk in QUALITY_PRESETS:
            btn = ttk.Button(
                quality_chips,
                text=label,
                style="Chip.TButton",
                command=lambda e=ec, c=chunk: self._set_quality_preset(e, c),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self.quality_buttons.append(btn)

        # === 4. Throughput mode (single vs grid) ===
        mode_card = card(parent)
        mode_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(mode_card, "4. Throughput mode", on_card=True).pack(anchor="w")
        ttk.Label(
            mode_card,
            text="Display multiple QRs at once for parallel decoding.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        mode_chips = ttk.Frame(mode_card, style="Card.TFrame")
        mode_chips.pack(fill=tk.X)
        self.mode_buttons: List[ttk.Button] = []
        for label, streams in MODE_PRESETS:
            btn = ttk.Button(
                mode_chips,
                text=label,
                style="Chip.TButton",
                command=lambda s=streams: self._set_mode_preset(s),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self.mode_buttons.append(btn)

        # === Primary actions ===
        action_card = card(parent)
        action_card.pack(fill=tk.X, pady=(0, 12))
        actions = ttk.Frame(action_card, style="Card.TFrame")
        actions.pack(fill=tk.X)

        self.encode_btn = ttk.Button(
            actions, text="⚙  Prepare", command=self._encode_file
        )
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

        self.save_qr_btn = ttk.Button(
            actions,
            text="Save QR images…",
            command=self._save_qr_images,
            state=tk.DISABLED,
        )
        self.save_qr_btn.pack(side=tk.RIGHT)

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
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ------------------------------------------------------------------
    # Config / preset plumbing
    # ------------------------------------------------------------------
    def _load_default_config(self) -> None:
        try:
            self.config = ConfigManager.load_config()
        except Exception as e:
            self._log(f"Using default config: {e}")
        self._set_speed_preset(self.config.duration, refresh_only=True)
        self._set_quality_preset(self.config.error_correction, self.config.chunk_size, refresh_only=True)
        self._set_mode_preset(1, refresh_only=True)
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

    def _set_quality_preset(self, ec: str, chunk_size: int, refresh_only: bool = False) -> None:
        if not refresh_only:
            self.config.error_correction = ec
            self.config.chunk_size = chunk_size
        for btn, (_, level, _) in zip(self.quality_buttons, QUALITY_PRESETS):
            style = "ChipActive.TButton" if level == self.config.error_correction else "Chip.TButton"
            btn.configure(style=style)
        self._refresh_summary()

    def _set_mode_preset(self, mode_value, refresh_only: bool = False) -> None:
        """mode_value is either an int (explicit num_streams) or "auto"."""
        if not refresh_only:
            self._mode_value = mode_value
            if mode_value == "auto":
                # Compute now using the server window's current monitor; will
                # be recomputed at display start in case the window moved.
                cols, rows = self._auto_grid_for_current_monitor()
                self._grid_cols, self._grid_rows = cols, rows
                self.use_parallel_encoding = (cols * rows) > 1
                self._mode_streams = cols * rows
            else:
                num = int(mode_value)
                self.use_parallel_encoding = num > 1
                self._mode_streams = num
                if num == 1:
                    self._grid_cols = self._grid_rows = 1
                else:
                    side = int(num ** 0.5)
                    if side * side == num:
                        self._grid_cols = self._grid_rows = side
                    else:
                        # Non-perfect-square explicit value — pack as a row
                        self._grid_cols, self._grid_rows = num, 1
            self.config.qr_grid_size = max(self._grid_cols, self._grid_rows)
        for btn, (_, value) in zip(self.mode_buttons, MODE_PRESETS):
            style = "ChipActive.TButton" if value == self._mode_value else "Chip.TButton"
            btn.configure(style=style)
        self._refresh_summary()

    def _auto_grid_for_current_monitor(self) -> tuple:
        """Find the monitor under the server window and compute (cols, rows)."""
        try:
            self.root.update_idletasks()
            cx = self.root.winfo_x() + self.root.winfo_width() // 2
            cy = self.root.winfo_y() + self.root.winfo_height() // 2
            mon = monitor_at_point(cx, cy) or primary_monitor()
            if mon is None:
                return 1, 1
            return auto_grid_for_screen(
                mon.width, mon.height, qr_target_px=self.config.qr_physical_size
            )
        except Exception:
            return 1, 1

    def _refresh_summary(self) -> None:
        if not self.current_file:
            self.summary_var.set("Pick a file to begin.")
            return
        size = Path(self.current_file).stat().st_size if Path(self.current_file).exists() else 0
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
        """Common handler for file selection from any source (browse or DND)."""
        p = Path(path)
        if not p.exists():
            messagebox.showerror("File not found", path)
            return
        self.file_path_var.set(str(p))
        self.current_file = str(p)
        size = p.stat().st_size
        self.file_info_var.set(f"{size:,} bytes  ·  {size/1024/1024:.2f} MB")
        self._refresh_summary()
        self._update_button_states()

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
        try:
            self._log(f"Encoding {self.current_file}")
            file_size = Path(self.current_file).stat().st_size
            if file_size == 0:
                raise ValueError("File is empty")
            if file_size > self.config.max_file_size:
                raise ValueError(
                    f"File ({file_size/1024/1024:.1f} MB) exceeds max ({self.config.max_file_size/1024/1024:.1f} MB)"
                )

            # If "auto" mode, recompute grid in case the user moved the window
            # since they picked the preset.
            if self._mode_value == "auto":
                cols, rows = self._auto_grid_for_current_monitor()
                self._grid_cols, self._grid_rows = cols, rows
                self._mode_streams = cols * rows
                self.use_parallel_encoding = self._mode_streams > 1
                self._log(f"Auto grid for current monitor: {cols}×{rows} = {cols*rows} streams")

            self._cached_qr_sets = None
            self._manifest_qr_image = None

            if self.use_parallel_encoding:
                streams = self._mode_streams
                self.parallel_encoder = ParallelQREncoder(
                    self.current_file,
                    num_streams=streams,
                    chunk_size=self.config.chunk_size,
                    error_correction=self.config.error_correction,
                )
                self.parallel_encoder.prepare_parallel_streams()
                self.total_chunks = self.parallel_encoder.get_total_chunks()
                stats = self.parallel_encoder.calculate_theoretical_throughput(self.config.duration)
                self._log(
                    f"Parallel: {streams} streams × {self.total_chunks} sets  "
                    f"→ {stats.get('kilobytes_per_second', 0):.1f} KB/s theoretical"
                )
                # Pre-generate every set once, in parallel
                self.root.after(0, lambda: self.progress_label_var.set(
                    f"Pre-generating {self.total_chunks * streams} QRs across CPU cores…"
                ))
                t0 = time.time()
                self._cached_qr_sets = self.parallel_encoder.prefetch_all_qr_sets()
                self._manifest_qr_image = self.parallel_encoder.generate_manifest_qr()
                elapsed = time.time() - t0
                self._log(
                    f"Pre-generated {self.total_chunks * streams} QRs in {elapsed:.2f}s "
                    f"({(self.total_chunks * streams)/max(elapsed, 1e-3):.0f} QR/s)"
                )
            else:
                self.encoder = QRLEncoder(
                    self.current_file,
                    chunk_size=self.config.chunk_size,
                    error_correction=self.config.error_correction,
                )
                self.total_chunks = self.encoder.prepare_chunks()
                if (
                    getattr(self.config, "prefetch_qr_images", True)
                    and file_size <= getattr(self.config, "prefetch_max_bytes", 5 * 1024 * 1024)
                ):
                    self.root.after(0, lambda: self.progress_label_var.set(
                        f"Pre-generating {self.total_chunks} QRs across CPU cores…"
                    ))
                    t0 = time.time()
                    self.encoder.prefetch_qr_images()
                    self._manifest_qr_image = self.encoder.generate_manifest_qr(num_streams=1)
                    elapsed = time.time() - t0
                    self._log(
                        f"Pre-generated {self.total_chunks} QRs in {elapsed:.2f}s "
                        f"({self.total_chunks/max(elapsed, 1e-3):.0f} QR/s)"
                    )
            self.root.after(0, self._encoding_complete)
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._encoding_error(err))
        finally:
            self.is_encoding = False
            self.root.after(0, self._update_button_states)

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
        self.qr_window = tk.Toplevel(self.root)
        self.qr_window.title("QRL Display")
        self.qr_window.configure(bg="white")

        # Find the monitor that the SERVER window is currently on, so the
        # QR display opens on the same screen the user is looking at.
        self.root.update_idletasks()
        cx = self.root.winfo_x() + self.root.winfo_width() // 2
        cy = self.root.winfo_y() + self.root.winfo_height() // 2
        target = monitor_at_point(cx, cy) or primary_monitor()

        if target is not None:
            # Two-step approach: position WITHOUT fullscreen first so Tk
            # actually moves the window to the target monitor, then turn on
            # fullscreen. Doing both in one go can leave fullscreen on the
            # original monitor because the geometry move is async.
            self.qr_window.geometry(
                f"{target.width}x{target.height}{target.x:+d}{target.y:+d}"
            )
            self._log(f"QR display targeting {target.name} ({target.width}x{target.height} at {target.x:+d},{target.y:+d})")
        else:
            self.qr_window.geometry("800x600")

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

        self.qr_window.protocol("WM_DELETE_WINDOW", _close)
        self.qr_window.bind("<Escape>", lambda _e: _close())
        self.qr_window.bind("<F11>", lambda _e: self.qr_window.attributes(
            "-fullscreen", not self.qr_window.attributes("-fullscreen")
        ))

        # Force the window to materialize on the target monitor BEFORE going
        # fullscreen. Without this, -fullscreen captures whichever monitor the
        # window happened to be created on (usually the primary).
        self.qr_window.deiconify()
        self.qr_window.lift()
        self.qr_window.focus_force()
        self.qr_window.update_idletasks()
        self.qr_window.update()

        # Now go fullscreen on the (now-correctly-positioned) monitor.
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
            # late-joining client can pick up the filename.
            if (
                not self._showed_manifest_this_cycle
                and self._manifest_qr_image is not None
            ):
                self._showed_manifest_this_cycle = True
                self._render_single(self._manifest_qr_image)
                self.qr_window.title("QRL Display  ·  manifest")
                if self.is_displaying:
                    self.root.after(
                        max(int(self.config.duration * 1000), 1), self._show_next_qr
                    )
                return

            if self.use_parallel_encoding and self.parallel_encoder:
                if self._cached_qr_sets is not None:
                    qr_images = self._cached_qr_sets[self.current_qr_index]
                else:
                    qr_images = self.parallel_encoder.generate_qr_set(self.current_qr_index)
                cols, rows = self._grid_cols, self._grid_rows
                self.current_qr_index += 1
            else:
                cols, rows = self._grid_cols, self._grid_rows
                cells = cols * rows
                qr_images = []
                cached = self.encoder.get_qr_images() if self.encoder else None
                for i in range(cells):
                    chunk_idx = (self.current_qr_index + i) % self.total_chunks
                    qr_images.append(
                        cached[chunk_idx] if cached else self.encoder.generate_qr_for_chunk(chunk_idx)
                    )
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

    def _render_single(self, image: Image.Image) -> None:
        """Render a single PIL image, fit to the display window."""
        win_w = max(self.qr_window.winfo_width(), 200)
        win_h = max(self.qr_window.winfo_height(), 200)
        # Scale image to fit while preserving aspect ratio
        iw, ih = image.size
        scale = min(win_w / iw, win_h / ih, 1.0) if iw and ih else 1.0
        if scale < 1.0:
            image = image.resize((int(iw * scale), int(ih * scale)), Image.Resampling.NEAREST)
        self.qr_photo = ImageTk.PhotoImage(image)
        self.qr_display_label.configure(image=self.qr_photo, text="")
        self.qr_display_label.image = self.qr_photo

    def _compose_grid(self, qr_images: List[Image.Image], cols: int, rows: int) -> Image.Image:
        """Compose `qr_images` into a `cols × rows` grid sized to the display window."""
        if not qr_images:
            raise ValueError("No QR images")
        spacing = 8
        win_w = max(self.qr_window.winfo_width(), 200) - 16
        win_h = max(self.qr_window.winfo_height(), 200) - 16
        per_w = max((win_w - spacing * (cols - 1)) // cols, 64)
        per_h = max((win_h - spacing * (rows - 1)) // rows, 64)
        per_qr = min(per_w, per_h)  # keep QRs square

        resized = [img.resize((per_qr, per_qr), Image.Resampling.NEAREST) for img in qr_images]
        # Pad with white if fewer QRs than grid cells
        while len(resized) < cols * rows:
            resized.append(Image.new("RGB", (per_qr, per_qr), "white"))

        total_w = per_qr * cols + spacing * (cols - 1)
        total_h = per_qr * rows + spacing * (rows - 1)
        canvas = Image.new("RGB", (total_w, total_h), "white")
        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c
                canvas.paste(resized[idx], (c * (per_qr + spacing), r * (per_qr + spacing)))
        return canvas

    # ------------------------------------------------------------------
    # Save QR images
    # ------------------------------------------------------------------
    def _save_qr_images(self) -> None:
        if self.total_chunks == 0:
            messagebox.showerror("Nothing to save", "Prepare a file first.")
            return
        directory = filedialog.askdirectory(title="Pick a directory to save QR images")
        if not directory:
            return
        try:
            output = Path(directory)
            output.mkdir(parents=True, exist_ok=True)
            cached = self.encoder.get_qr_images() if self.encoder else None
            count = 0
            for i in range(self.total_chunks):
                img = cached[i] if cached else self.encoder.generate_qr_for_chunk(i)
                img.save(output / f"qr_{i:04d}.png")
                count += 1
            self._log(f"Saved {count} QR images to {directory}")
            messagebox.showinfo("Saved", f"Saved {count} QR images to {directory}")
        except Exception as e:
            self._log(f"Save failed: {e}")
            messagebox.showerror("Save failed", str(e))

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _update_button_states(self) -> None:
        if self.is_encoding:
            self.encode_btn.configure(state=tk.DISABLED)
            self.display_btn.configure(state=tk.DISABLED)
            self.save_qr_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.DISABLED)
            return
        has_file = bool(self.current_file)
        has_chunks = self.total_chunks > 0
        self.encode_btn.configure(state=tk.NORMAL if has_file else tk.DISABLED)
        self.display_btn.configure(
            state=tk.NORMAL if has_chunks and not self.is_displaying else tk.DISABLED
        )
        self.save_qr_btn.configure(state=tk.NORMAL if has_chunks else tk.DISABLED)
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

    def _on_closing(self) -> None:
        if self.is_encoding:
            if not messagebox.askyesno("Quit", "Encoding in progress. Quit anyway?"):
                return
        self._stop_display()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        try:
            self.root.mainloop()
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
