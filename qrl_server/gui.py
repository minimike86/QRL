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

# Parallel mode presets
MODE_PRESETS = [
    ("Single stream", 1),
    ("2×2 grid (4×)", 4),
    ("3×3 grid (9×)", 9),
    ("4×4 grid (16×)", 16),
]


class QRLServerGUI:
    """Modern QRL server GUI."""

    def __init__(self, master: Optional[tk.Misc] = None):
        # Tests share a single Tk root via a Toplevel; production creates its own.
        if master is None:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(master)
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

        # Display state
        self.current_qr_index = 0
        self.display_cycle = 0
        self.qr_window: Optional[tk.Toplevel] = None
        self.qr_display_label: Optional[tk.Label] = None
        self.qr_photo: Optional[ImageTk.PhotoImage] = None

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
        ttk.Entry(file_row, textvariable=self.file_path_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, ipady=2
        )
        ttk.Button(file_row, text="Browse…", command=self._browse_file).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self.file_info_var = tk.StringVar(value="")
        ttk.Label(file_card, textvariable=self.file_info_var, style="CardMuted.TLabel").pack(
            anchor="w", pady=(8, 0)
        )

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

    def _set_mode_preset(self, num_streams: int, refresh_only: bool = False) -> None:
        if not refresh_only:
            self.use_parallel_encoding = num_streams > 1
            self._mode_streams = num_streams
            grid_size = int(num_streams ** 0.5)
            self.config.qr_grid_size = grid_size
        else:
            self._mode_streams = getattr(self, "_mode_streams", 1)
        for btn, (_, value) in zip(self.mode_buttons, MODE_PRESETS):
            style = "ChipActive.TButton" if value == self._mode_streams else "Chip.TButton"
            btn.configure(style=style)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        if not self.current_file:
            self.summary_var.set("Pick a file to begin.")
            return
        size = Path(self.current_file).stat().st_size if Path(self.current_file).exists() else 0
        size_mb = size / (1024 * 1024)
        streams = getattr(self, "_mode_streams", 1)
        bytes_per_sec = (self.config.chunk_size * streams) / max(self.config.duration, 1e-6)
        self.summary_var.set(
            f"{Path(self.current_file).name}  ·  {size_mb:.2f} MB  ·  "
            f"{self.config.chunk_size} B/QR @ {1/self.config.duration:.0f} FPS × {streams} stream{'s' if streams > 1 else ''}  →  "
            f"~{bytes_per_sec/1024:.1f} KB/s"
        )

    # ------------------------------------------------------------------
    # File picker
    # ------------------------------------------------------------------
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
            self.file_path_var.set(filename)
            self.current_file = filename
            size = Path(filename).stat().st_size
            self.file_info_var.set(f"{size:,} bytes  ·  {size/1024/1024:.2f} MB")
            self._refresh_summary()
            self._update_button_states()

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

            if self.use_parallel_encoding:
                streams = getattr(self, "_mode_streams", 4)
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
                    self.root.after(0, lambda: self.progress_label_var.set("Pre-generating QR images…"))
                    t0 = time.time()
                    self.encoder.prefetch_qr_images()
                    elapsed = time.time() - t0
                    self._log(
                        f"Pre-generated {self.total_chunks} QR images in {elapsed:.2f}s "
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
        self._update_button_states()
        self.current_qr_index = 0
        self.display_cycle = 0
        self._create_qr_display_window()
        self._show_next_qr()

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

        # Reasonable default geometry; user can resize and the QR auto-fits
        screen_w = self.qr_window.winfo_screenwidth()
        screen_h = self.qr_window.winfo_screenheight()
        size = min(self.config.qr_physical_size + 80, int(min(screen_w, screen_h) * 0.85))
        x = (screen_w - size) // 2
        y = (screen_h - size) // 2
        self.qr_window.geometry(f"{size}x{size}+{x}+{y}")

        if self.config.fullscreen:
            self.qr_window.attributes("-fullscreen", True)

        self.qr_display_label = tk.Label(self.qr_window, bg="white", text="…")
        self.qr_display_label.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

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
        self.qr_window.lift()
        self.qr_window.focus_force()

    def _show_next_qr(self) -> None:
        if not self.is_displaying or not self.qr_window:
            return
        try:
            if self.use_parallel_encoding and self.parallel_encoder:
                grid = self.parallel_encoder.generate_qr_grid(self.current_qr_index)
                qr_images = [img for row in grid for img in row]
                grid_size = int(getattr(self, "_mode_streams", 4) ** 0.5)
                self.current_qr_index += 1
            else:
                grid_size = self.config.qr_grid_size
                qr_images = []
                cached = self.encoder.get_qr_images() if self.encoder else None
                for i in range(grid_size * grid_size):
                    chunk_idx = (self.current_qr_index + i) % self.total_chunks
                    qr_images.append(
                        cached[chunk_idx] if cached else self.encoder.generate_qr_for_chunk(chunk_idx)
                    )
                self.current_qr_index += grid_size * grid_size

            combined = self._compose_grid(qr_images, grid_size)
            self.qr_photo = ImageTk.PhotoImage(combined)
            self.qr_display_label.configure(image=self.qr_photo)
            self.qr_display_label.image = self.qr_photo

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

    def _compose_grid(self, qr_images: List[Image.Image], grid_size: int) -> Image.Image:
        if not qr_images:
            raise ValueError("No QR images")
        # Auto-size the QR codes to fit the window
        spacing = 8
        win_w = max(self.qr_window.winfo_width(), 200) - 30
        win_h = max(self.qr_window.winfo_height(), 200) - 30
        per_qr = max(
            min(
                (win_w - spacing * (grid_size - 1)) // grid_size,
                (win_h - spacing * (grid_size - 1)) // grid_size,
            ),
            64,
        )

        resized = [img.resize((per_qr, per_qr), Image.Resampling.NEAREST) for img in qr_images]
        # Pad with white if fewer QRs than grid cells
        while len(resized) < grid_size * grid_size:
            resized.append(Image.new("RGB", (per_qr, per_qr), "white"))

        total = per_qr * grid_size + spacing * (grid_size - 1)
        canvas = Image.new("RGB", (total, total), "white")
        for r in range(grid_size):
            for c in range(grid_size):
                idx = r * grid_size + c
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
