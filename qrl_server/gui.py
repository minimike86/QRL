#!/usr/bin/env python3
"""
QRL Server GUI Application
Graphical interface for the QRL server using tkinter.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
import time
from typing import Optional, List
from PIL import Image, ImageTk

from .encoder import QRLEncoder
from .display import DisplayHandler
from .config import ServerConfig, ConfigManager
from .qr_generator import QRGenerator
from .parallel_encoder import ParallelQREncoder


class QRLServerGUI:
    """Main GUI application for QRL Server."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("QRL Server - QR Code Data Transfer")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Application state
        self.config = ServerConfig()
        self.encoder: Optional[QRLEncoder] = None
        self.parallel_encoder: Optional[ParallelQREncoder] = None
        self.display_handler: Optional[DisplayHandler] = None
        self.qr_images: List[Image.Image] = []
        self.current_file: Optional[str] = None
        self.encoding_thread: Optional[threading.Thread] = None
        self.display_thread: Optional[threading.Thread] = None
        self.is_encoding = False
        self.is_displaying = False
        self.use_parallel_encoding = False

        # Display state
        self.current_qr_index = 0
        self.display_cycle = 0
        self.qr_window = None
        self.qr_display_label = None
        self.qr_photo = None

        self._setup_ui()
        self._setup_bindings()
        self._load_default_config()

    def _setup_ui(self):
        """Set up the user interface."""
        # Create main notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Main tab
        self.main_frame = ttk.Frame(notebook)
        notebook.add(self.main_frame, text="Main")
        self._setup_main_tab()

        # Settings tab
        self.settings_frame = ttk.Frame(notebook)
        notebook.add(self.settings_frame, text="Settings")
        self._setup_settings_tab()

        # Log tab
        self.log_frame = ttk.Frame(notebook)
        notebook.add(self.log_frame, text="Logs")
        self._setup_log_tab()

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _setup_main_tab(self):
        """Set up the main tab."""
        # File selection frame
        file_frame = ttk.LabelFrame(self.main_frame, text="File Selection", padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        # File path entry
        ttk.Label(file_frame, text="File to encode:").pack(anchor=tk.W)
        file_entry_frame = ttk.Frame(file_frame)
        file_entry_frame.pack(fill=tk.X, pady=(5, 0))

        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_entry_frame, textvariable=self.file_path_var)
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.browse_btn = ttk.Button(file_entry_frame, text="Browse...", command=self._browse_file)
        self.browse_btn.pack(side=tk.RIGHT)

        # Quick settings frame
        quick_settings_frame = ttk.LabelFrame(self.main_frame, text="Quick Settings", padding=10)
        quick_settings_frame.pack(fill=tk.X, pady=(0, 10))

        # Chunk size
        chunk_frame = ttk.Frame(quick_settings_frame)
        chunk_frame.pack(fill=tk.X, pady=(0, 5))

        chunk_label_frame = ttk.Frame(chunk_frame)
        chunk_label_frame.pack(side=tk.LEFT)
        ttk.Label(chunk_label_frame, text="Chunk size (bytes):").pack(side=tk.LEFT)

        chunk_control_frame = ttk.Frame(chunk_frame)
        chunk_control_frame.pack(side=tk.RIGHT)

        self.chunk_size_var = tk.IntVar(value=self.config.chunk_size)
        chunk_spinbox = ttk.Spinbox(chunk_control_frame, from_=512, to=65536, width=8,
                                   textvariable=self.chunk_size_var)
        chunk_spinbox.pack(side=tk.RIGHT, padx=(0, 5))

        # Preset buttons
        preset_frame = ttk.Frame(chunk_control_frame)
        preset_frame.pack(side=tk.RIGHT)

        presets = [
            ("Small", 800),     # Error level H - very safe
            ("Medium", 1500),   # Error level Q - balanced
            ("Large", 2200),    # Error level M - efficient
            ("XL", 2900)        # Error level L - maximum capacity
        ]

        for name, size in presets:
            btn = ttk.Button(preset_frame, text=name, width=6,
                           command=lambda s=size: self.chunk_size_var.set(s))
            btn.pack(side=tk.LEFT, padx=(0, 2))

        # Duration
        duration_frame = ttk.Frame(quick_settings_frame)
        duration_frame.pack(fill=tk.X, pady=(0, 5))

        duration_label_frame = ttk.Frame(duration_frame)
        duration_label_frame.pack(side=tk.LEFT)
        ttk.Label(duration_label_frame, text="Display duration (seconds):").pack(side=tk.LEFT)

        duration_control_frame = ttk.Frame(duration_frame)
        duration_control_frame.pack(side=tk.RIGHT)

        self.duration_var = tk.DoubleVar(value=self.config.duration)
        duration_spinbox = ttk.Spinbox(duration_control_frame, from_=0.01, to=10.0, increment=0.01,
                                      width=10, textvariable=self.duration_var)
        duration_spinbox.pack(side=tk.RIGHT, padx=(0, 5))

        # Fast preset buttons
        fast_frame = ttk.Frame(duration_control_frame)
        fast_frame.pack(side=tk.RIGHT)

        fast_presets = [
            ("Ultra", 0.05),    # 20 FPS
            ("Fast", 0.1),      # 10 FPS
            ("Quick", 0.2),     # 5 FPS
            ("Normal", 1.0)     # 1 FPS
        ]

        for name, duration in fast_presets:
            btn = ttk.Button(fast_frame, text=name, width=6,
                           command=lambda d=duration: self._set_duration_with_warning(d))
            btn.pack(side=tk.LEFT, padx=(0, 2))

        # Error correction
        error_frame = ttk.Frame(quick_settings_frame)
        error_frame.pack(fill=tk.X)
        ttk.Label(error_frame, text="Error correction:").pack(side=tk.LEFT)
        self.error_correction_var = tk.StringVar(value=self.config.error_correction)
        error_combo = ttk.Combobox(error_frame, values=["L", "M", "Q", "H"],
                                  textvariable=self.error_correction_var, width=8, state="readonly")
        error_combo.pack(side=tk.RIGHT)

        # Control frame
        control_frame = ttk.LabelFrame(self.main_frame, text="Control", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)

        self.encode_btn = ttk.Button(button_frame, text="Encode File", command=self._encode_file)
        self.encode_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.display_btn = ttk.Button(button_frame, text="Start Display", command=self._start_display,
                                     state=tk.DISABLED)
        self.display_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_btn = ttk.Button(button_frame, text="Stop Display", command=self._stop_display,
                                  state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.save_qr_btn = ttk.Button(button_frame, text="Save QR Images", command=self._save_qr_images,
                                     state=tk.DISABLED)
        self.save_qr_btn.pack(side=tk.RIGHT)

        # Progress frame
        progress_frame = ttk.LabelFrame(self.main_frame, text="Progress", padding=10)
        progress_frame.pack(fill=tk.BOTH, expand=True)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                           maximum=100, length=400)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.progress_label_var = tk.StringVar()
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_label_var)
        self.progress_label.pack(anchor=tk.W)

        # Info display
        info_frame = ttk.Frame(progress_frame)
        info_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.info_text = scrolledtext.ScrolledText(info_frame, height=10, state=tk.DISABLED)
        self.info_text.pack(fill=tk.BOTH, expand=True)

    def _setup_settings_tab(self):
        """Set up the settings tab."""
        # Create scrollable frame
        canvas = tk.Canvas(self.settings_frame)
        scrollbar = ttk.Scrollbar(self.settings_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # QR Settings
        qr_frame = ttk.LabelFrame(scrollable_frame, text="QR Code Settings", padding=10)
        qr_frame.pack(fill=tk.X, pady=(0, 10))

        # QR Version
        qr_version_frame = ttk.Frame(qr_frame)
        qr_version_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(qr_version_frame, text="QR Version (1-40, 0=auto):").pack(side=tk.LEFT)
        self.qr_version_var = tk.IntVar(value=self.config.qr_version or 0)
        ttk.Spinbox(qr_version_frame, from_=0, to=40, width=10,
                   textvariable=self.qr_version_var).pack(side=tk.RIGHT)

        # QR Border
        qr_border_frame = ttk.Frame(qr_frame)
        qr_border_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(qr_border_frame, text="QR Border:").pack(side=tk.LEFT)
        self.qr_border_var = tk.IntVar(value=self.config.qr_border)
        ttk.Spinbox(qr_border_frame, from_=0, to=20, width=10,
                   textvariable=self.qr_border_var).pack(side=tk.RIGHT)

        # QR Box Size
        qr_box_frame = ttk.Frame(qr_frame)
        qr_box_frame.pack(fill=tk.X)
        ttk.Label(qr_box_frame, text="QR Box Size:").pack(side=tk.LEFT)
        self.qr_box_size_var = tk.IntVar(value=self.config.qr_box_size)
        ttk.Spinbox(qr_box_frame, from_=1, to=50, width=10,
                   textvariable=self.qr_box_size_var).pack(side=tk.RIGHT)

        # Display Settings
        display_frame = ttk.LabelFrame(scrollable_frame, text="Display Settings", padding=10)
        display_frame.pack(fill=tk.X, pady=(0, 10))

        # Window Title
        title_frame = ttk.Frame(display_frame)
        title_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(title_frame, text="Window Title:").pack(side=tk.LEFT)
        self.window_title_var = tk.StringVar(value=self.config.window_title)
        ttk.Entry(title_frame, textvariable=self.window_title_var, width=20).pack(side=tk.RIGHT)

        # Repeat
        self.repeat_var = tk.BooleanVar(value=self.config.repeat)
        ttk.Checkbutton(display_frame, text="Repeat QR sequence",
                       variable=self.repeat_var).pack(anchor=tk.W, pady=(0, 5))

        # Fullscreen
        self.fullscreen_var = tk.BooleanVar(value=self.config.fullscreen)
        ttk.Checkbutton(display_frame, text="Fullscreen display",
                       variable=self.fullscreen_var).pack(anchor=tk.W)

        # Advanced Settings
        advanced_frame = ttk.LabelFrame(scrollable_frame, text="Advanced Settings", padding=10)
        advanced_frame.pack(fill=tk.X, pady=(0, 10))

        # Max file size
        max_size_frame = ttk.Frame(advanced_frame)
        max_size_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(max_size_frame, text="Max file size (MB):").pack(side=tk.LEFT)
        self.max_file_size_var = tk.IntVar(value=self.config.max_file_size // (1024 * 1024))
        ttk.Spinbox(max_size_frame, from_=1, to=1000, width=10,
                   textvariable=self.max_file_size_var).pack(side=tk.RIGHT)

        # High-Speed Transfer Settings
        speed_frame = ttk.LabelFrame(scrollable_frame, text="High-Speed Transfer", padding=10)
        speed_frame.pack(fill=tk.X, pady=(0, 10))

        # QR Grid Size
        grid_frame = ttk.Frame(speed_frame)
        grid_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(grid_frame, text="QR Grid (for parallel transfer):").pack(side=tk.LEFT)
        self.qr_grid_var = tk.IntVar(value=self.config.qr_grid_size)
        grid_combo = ttk.Combobox(grid_frame, values=["1x1 (1 QR)", "2x2 (4 QRs)", "3x3 (9 QRs)", "4x4 (16 QRs)"],
                                 width=15, state="readonly")
        grid_combo.pack(side=tk.RIGHT)
        grid_combo.set(f"{self.config.qr_grid_size}x{self.config.qr_grid_size} ({self.config.qr_grid_size**2} QR{'s' if self.config.qr_grid_size > 1 else ''})")

        def update_grid_size(event):
            selection = grid_combo.get()
            if "1x1" in selection:
                self.qr_grid_var.set(1)
            elif "2x2" in selection:
                self.qr_grid_var.set(2)
            elif "3x3" in selection:
                self.qr_grid_var.set(3)
            elif "4x4" in selection:
                self.qr_grid_var.set(4)

        grid_combo.bind("<<ComboboxSelected>>", update_grid_size)

        # QR Physical Size
        qr_size_frame = ttk.Frame(speed_frame)
        qr_size_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(qr_size_frame, text="QR size (pixels):").pack(side=tk.LEFT)
        self.qr_physical_size_var = tk.IntVar(value=self.config.qr_physical_size)
        ttk.Spinbox(qr_size_frame, from_=200, to=800, increment=50, width=10,
                   textvariable=self.qr_physical_size_var).pack(side=tk.RIGHT)

        # Throughput info
        throughput_info = ttk.Label(speed_frame, text="4x4 grid = 16x faster data transfer!",
                                   foreground="green")
        throughput_info.pack(pady=(5, 0))

        # Parallel Stream Encoding Settings
        parallel_frame = ttk.LabelFrame(scrollable_frame, text="Parallel Stream Encoding (Experimental)", padding=10)
        parallel_frame.pack(fill=tk.X, pady=(0, 10))

        # Enable parallel encoding
        self.parallel_encoding_var = tk.BooleanVar(value=False)
        parallel_check = ttk.Checkbutton(parallel_frame, text="Enable parallel stream encoding",
                       variable=self.parallel_encoding_var, command=self._toggle_parallel_encoding)
        parallel_check.pack(anchor=tk.W, pady=(0, 10))

        # Parallel streams
        streams_frame = ttk.Frame(parallel_frame)
        streams_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(streams_frame, text="Number of parallel streams:").pack(side=tk.LEFT)
        self.parallel_streams_var = tk.IntVar(value=4)
        streams_combo = ttk.Combobox(streams_frame, values=["1 stream", "4 streams (2x2)", "9 streams (3x3)", "16 streams (4x4)"],
                                    width=18, state="readonly")
        streams_combo.pack(side=tk.RIGHT)
        streams_combo.set("4 streams (2x2)")

        def update_streams(event):
            selection = streams_combo.get()
            if "1 stream" in selection:
                self.parallel_streams_var.set(1)
            elif "4 streams" in selection:
                self.parallel_streams_var.set(4)
            elif "9 streams" in selection:
                self.parallel_streams_var.set(9)
            elif "16 streams" in selection:
                self.parallel_streams_var.set(16)

        streams_combo.bind("<<ComboboxSelected>>", update_streams)

        # Info about parallel encoding
        parallel_info_text = """Parallel encoding splits data into independent streams that can be
processed simultaneously by multiple QR scanners. This can dramatically
increase throughput for large files by bypassing single-QR size limits."""

        parallel_info = ttk.Label(parallel_frame, text=parallel_info_text,
                                 wraplength=400, justify=tk.LEFT, foreground="blue")
        parallel_info.pack(pady=(5, 0), anchor=tk.W)

        # Configuration file management
        config_frame = ttk.LabelFrame(scrollable_frame, text="Configuration", padding=10)
        config_frame.pack(fill=tk.X, pady=(0, 10))

        config_buttons = ttk.Frame(config_frame)
        config_buttons.pack(fill=tk.X)

        ttk.Button(config_buttons, text="Load Config",
                  command=self._load_config_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(config_buttons, text="Save Config",
                  command=self._save_config_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(config_buttons, text="Reset to Defaults",
                  command=self._reset_config).pack(side=tk.LEFT)

    def _setup_log_tab(self):
        """Set up the log tab."""
        log_frame = ttk.Frame(self.log_frame)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(log_frame, text="Application Logs:").pack(anchor=tk.W, pady=(0, 5))

        self.log_text = scrolledtext.ScrolledText(log_frame, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Log controls
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill=tk.X)

        ttk.Button(log_controls, text="Clear Log", command=self._clear_log).pack(side=tk.LEFT)
        ttk.Button(log_controls, text="Save Log", command=self._save_log).pack(side=tk.LEFT, padx=(5, 0))

    def _setup_bindings(self):
        """Set up event bindings."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Update config when settings change
        self.chunk_size_var.trace('w', self._update_config_from_ui)
        self.duration_var.trace('w', self._update_config_from_ui)
        self.error_correction_var.trace('w', self._update_config_from_ui)

    def _load_default_config(self):
        """Load default configuration."""
        try:
            self.config = ConfigManager.load_config()
            self._update_ui_from_config()
            self._log("Configuration loaded successfully")
        except Exception as e:
            self._log(f"Warning: Could not load config, using defaults: {e}")

    def _update_config_from_ui(self, *args):
        """Update config object from UI values."""
        try:
            self.config.chunk_size = self.chunk_size_var.get()
            self.config.duration = self.duration_var.get()
            self.config.error_correction = self.error_correction_var.get()

            if hasattr(self, 'qr_version_var'):
                qr_version = self.qr_version_var.get()
                self.config.qr_version = qr_version if qr_version > 0 else None

            if hasattr(self, 'qr_border_var'):
                self.config.qr_border = self.qr_border_var.get()

            if hasattr(self, 'qr_box_size_var'):
                self.config.qr_box_size = self.qr_box_size_var.get()

            if hasattr(self, 'window_title_var'):
                self.config.window_title = self.window_title_var.get()

            if hasattr(self, 'repeat_var'):
                self.config.repeat = self.repeat_var.get()

            if hasattr(self, 'fullscreen_var'):
                self.config.fullscreen = self.fullscreen_var.get()

            if hasattr(self, 'max_file_size_var'):
                self.config.max_file_size = self.max_file_size_var.get() * 1024 * 1024

            if hasattr(self, 'qr_grid_var'):
                self.config.qr_grid_size = self.qr_grid_var.get()

            if hasattr(self, 'qr_physical_size_var'):
                self.config.qr_physical_size = self.qr_physical_size_var.get()

        except (tk.TclError, ValueError):
            # Ignore invalid values during typing
            pass

    def _update_ui_from_config(self):
        """Update UI values from config object."""
        self.chunk_size_var.set(self.config.chunk_size)
        self.duration_var.set(self.config.duration)
        self.error_correction_var.set(self.config.error_correction)

        if hasattr(self, 'qr_version_var'):
            self.qr_version_var.set(self.config.qr_version or 0)

        if hasattr(self, 'qr_border_var'):
            self.qr_border_var.set(self.config.qr_border)

        if hasattr(self, 'qr_box_size_var'):
            self.qr_box_size_var.set(self.config.qr_box_size)

        if hasattr(self, 'window_title_var'):
            self.window_title_var.set(self.config.window_title)

        if hasattr(self, 'repeat_var'):
            self.repeat_var.set(self.config.repeat)

        if hasattr(self, 'fullscreen_var'):
            self.fullscreen_var.set(self.config.fullscreen)

        if hasattr(self, 'max_file_size_var'):
            self.max_file_size_var.set(self.config.max_file_size // (1024 * 1024))

        if hasattr(self, 'qr_grid_var'):
            self.qr_grid_var.set(self.config.qr_grid_size)

        if hasattr(self, 'qr_physical_size_var'):
            self.qr_physical_size_var.set(self.config.qr_physical_size)

    def _browse_file(self):
        """Open file dialog to select file for encoding."""
        filename = filedialog.askopenfilename(
            title="Select file to encode",
            filetypes=[
                ("All files", "*.*"),
                ("Text files", "*.txt"),
                ("Image files", "*.jpg *.jpeg *.png *.bmp"),
                ("Document files", "*.pdf *.doc *.docx"),
            ]
        )
        if filename:
            self.file_path_var.set(filename)
            self.current_file = filename

    def _encode_file(self):
        """Start file encoding in a separate thread."""
        if not self.current_file or not Path(self.current_file).exists():
            messagebox.showerror("Error", "Please select a valid file to encode")
            return

        if self.is_encoding:
            messagebox.showwarning("Warning", "Encoding is already in progress")
            return

        try:
            self.config.validate()
        except ValueError as e:
            messagebox.showerror("Configuration Error", str(e))
            return

        self.is_encoding = True
        self._update_button_states()
        self.encoding_thread = threading.Thread(target=self._encode_file_worker)
        self.encoding_thread.daemon = True
        self.encoding_thread.start()

    def _encode_file_worker(self):
        """Worker thread for file encoding."""
        try:
            self._update_status("Encoding file...")
            self._log(f"Starting encoding of: {self.current_file}")

            # Update config from UI
            self._update_config_from_ui()

            # Validate chunk size against QR capacity
            if not QRGenerator.validate_chunk_size(self.config.chunk_size, self.config.error_correction):
                max_size = QRGenerator.get_max_chunk_size(self.config.error_correction)
                raise ValueError(
                    f"Chunk size ({self.config.chunk_size:,} bytes) exceeds QR code capacity "
                    f"for error correction level '{self.config.error_correction}'.\n\n"
                    f"Maximum chunk size for level '{self.config.error_correction}': {max_size:,} bytes\n\n"
                    f"Solutions:\n"
                    f"• Reduce chunk size to {max_size:,} bytes or less\n"
                    f"• Change error correction to 'L' (allows ~2,200 bytes)\n"
                    f"• Use smaller preset buttons (Small/Medium)"
                )

            # Check file size
            file_size = Path(self.current_file).stat().st_size
            self._log(f"File size: {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")

            if file_size > self.config.max_file_size:
                raise ValueError(
                    f"File size ({file_size / 1024 / 1024:.1f} MB) exceeds maximum allowed "
                    f"({self.config.max_file_size / 1024 / 1024:.1f} MB). "
                    f"Increase max_file_size in settings or choose a smaller file."
                )

            if file_size == 0:
                raise ValueError("File is empty")

            # Update progress
            self.root.after(0, lambda: self.progress_label_var.set("Validating file..."))

            # Choose encoding method based on settings
            if self.use_parallel_encoding:
                # Use parallel stream encoding
                num_streams = self.parallel_streams_var.get()
                self._log(f"Using parallel encoding with {num_streams} streams")

                self.parallel_encoder = ParallelQREncoder(
                    self.current_file,
                    num_streams=num_streams,
                    chunk_size=self.config.chunk_size,
                    error_correction=self.config.error_correction
                )

                # Update progress
                self.root.after(0, lambda: self.progress_label_var.set("Preparing parallel streams..."))

                # Prepare parallel streams
                stream_info = self.parallel_encoder.prepare_parallel_streams()
                total_chunks = self.parallel_encoder.get_total_chunks()

                # Calculate throughput statistics
                throughput_stats = self.parallel_encoder.calculate_theoretical_throughput(self.config.duration)

                self._log(f"Parallel streams prepared:")
                for stream_id, chunk_count in stream_info.items():
                    self._log(f"  Stream {stream_id}: {chunk_count:,} chunks")

                self._log(f"Total chunk sets: {total_chunks:,}")
                self._log(f"Theoretical throughput: {throughput_stats.get('kilobytes_per_second', 0):.1f} KB/s")
                self._log(f"Speedup factor: {throughput_stats.get('speedup_factor', 1):.1f}x")

                metadata = self.parallel_encoder.get_metadata()
                metadata['encoding_type'] = 'parallel'
                metadata['throughput_stats'] = throughput_stats

            else:
                # Use traditional single-stream encoding
                self._log("Using traditional single-stream encoding")

                self.encoder = QRLEncoder(
                    self.current_file,
                    chunk_size=self.config.chunk_size,
                    error_correction=self.config.error_correction
                )

                if not self.encoder.validate():
                    raise ValueError("File validation failed")

                # Calculate estimated QR codes
                estimated_qrs = (file_size // self.config.chunk_size) + 1
                self._log(f"Estimated QR codes: {estimated_qrs:,}")

                # Update progress
                self.root.after(0, lambda: self.progress_label_var.set("Preparing data chunks..."))

                # Prepare chunks for on-the-fly QR generation (memory efficient)
                total_chunks = self.encoder.prepare_chunks()
                self._log(f"Data prepared: {total_chunks:,} chunks ready for streaming QR generation")

                metadata = self.encoder.get_metadata()
                metadata['encoding_type'] = 'traditional'

            # Clear any previous QR images and use streaming mode
            self.qr_images = []  # Not used in streaming mode
            self.total_chunks = total_chunks

            # Update UI
            self.root.after(0, lambda: self._encoding_complete(metadata))

        except Exception as e:
            self._log(f"Encoding error: {e}")
            self.root.after(0, lambda: self._encoding_error(str(e)))

        finally:
            self.is_encoding = False
            self.root.after(0, self._update_button_states)

    def _encoding_complete(self, metadata):
        """Called when encoding completes successfully."""
        self._update_status("Preparation complete")
        self.progress_var.set(100)
        self.progress_label_var.set(f"Complete - {metadata['total_chunks']} chunks prepared for streaming")

        info = f"""Data Preparation Complete!

File: {self.current_file}
Total size: {metadata['total_size']} bytes
Total chunks: {metadata['total_chunks']}
Error correction: {self.config.error_correction}
Generation mode: On-the-fly (memory efficient)

Ready to display QR codes. QR codes will be generated as needed during display."""

        self._update_info(info)
        self._log(f"Data preparation complete: {metadata['total_chunks']} chunks ready for streaming QR generation")

    def _encoding_error(self, error_msg):
        """Called when encoding fails."""
        self._update_status("Encoding failed")
        self.progress_var.set(0)
        self.progress_label_var.set(f"Error: {error_msg}")
        self._update_info(f"Encoding failed: {error_msg}")
        self._log(f"Encoding error: {error_msg}")
        messagebox.showerror("Encoding Error", error_msg)

    def _start_display(self):
        """Start QR code display."""
        if not hasattr(self, 'total_chunks') or self.total_chunks == 0:
            messagebox.showerror("Error", "No data to display. Please encode a file first.")
            return

        if self.is_displaying:
            messagebox.showwarning("Warning", "Display is already running")
            return

        self.is_displaying = True
        self._update_button_states()
        self.display_thread = threading.Thread(target=self._display_worker)
        self.display_thread.daemon = True
        self.display_thread.start()

    def _display_worker(self):
        """Worker thread for QR display."""
        try:
            self._update_status("Starting display...")
            self._log("Starting QR code display")

            # Start embedded display in GUI
            self.root.after(0, self._start_embedded_display)

        except Exception as e:
            self.root.after(0, lambda: self._log(f"Display error: {e}"))
            self.root.after(0, lambda: messagebox.showerror("Display Error", str(e)))

            self.is_displaying = False
            self.root.after(0, lambda: self._update_status("Display stopped"))
            self.root.after(0, self._update_button_states)

    def _stop_display(self):
        """Stop QR code display."""
        self.is_displaying = False

        # Close QR display window if open
        try:
            if hasattr(self, 'qr_window') and self.qr_window and self.qr_window.winfo_exists():
                self.qr_window.destroy()
        except (AttributeError, tk.TclError):
            pass  # Window already destroyed or doesn't exist

        # Reset QR window reference
        self.qr_window = None

        self._update_button_states()
        self._update_status("Display stopped")
        self._log("QR code display stopped")

    def _start_embedded_display(self):
        """Start embedded QR display within the GUI."""
        if not hasattr(self, 'total_chunks') or self.total_chunks == 0:
            self._log("Error: No chunks available for display")
            return

        self._log(f"Starting embedded display with {self.total_chunks} chunks")
        self.current_qr_index = 0
        self.display_cycle = 0
        self._show_next_qr()

    def _show_next_qr(self):
        """Show the next QR code in sequence."""
        if not self.is_displaying or not hasattr(self, 'total_chunks') or self.total_chunks == 0:
            # Clean up if display was stopped
            if hasattr(self, 'qr_window') and self.qr_window:
                try:
                    if self.qr_window.winfo_exists():
                        self.qr_window.destroy()
                except (AttributeError, tk.TclError):
                    pass
                self.qr_window = None
            return

        try:
            # Create a popup window for QR display
            if not hasattr(self, 'qr_window') or self.qr_window is None or not self.qr_window.winfo_exists():
                self._create_qr_display_window()

            # Generate QR codes based on encoding mode
            if self.use_parallel_encoding and hasattr(self, 'parallel_encoder') and self.parallel_encoder:
                # Parallel encoding mode - generate grid from parallel streams
                qr_grid_2d = self.parallel_encoder.generate_qr_grid(self.current_qr_index)

                # Flatten the 2D grid for compatibility with existing grid display code
                qr_images = []
                for row in qr_grid_2d:
                    qr_images.extend(row)

                grid_size = int(self.parallel_streams_var.get() ** 0.5)  # sqrt for grid dimensions

            else:
                # Traditional encoding mode - generate sequential QR codes
                grid_size = self.config.qr_grid_size
                qr_images = []

                for i in range(grid_size * grid_size):
                    chunk_idx = (self.current_qr_index + i) % self.total_chunks
                    qr_image = self.encoder.generate_qr_for_chunk(chunk_idx)
                    qr_images.append(qr_image)

            # Create grid layout
            combined_image = self._create_qr_grid(qr_images, grid_size)

            # Convert to PhotoImage
            self.qr_photo = ImageTk.PhotoImage(combined_image)

            # Update display
            self.qr_display_label.configure(image=self.qr_photo)
            self.qr_display_label.image = self.qr_photo

            # Update progress in main window
            progress = ((self.current_qr_index + 1) / self.total_chunks) * 100
            self.progress_var.set(progress)

            status_text = f"Displaying QR {self.current_qr_index + 1}/{self.total_chunks}"
            if self.display_cycle > 0:
                status_text += f" (cycle {self.display_cycle + 1})"
            self.progress_label_var.set(status_text)

            # Update window title
            self.qr_window.title(f"{self.config.window_title} - {status_text}")

            # Schedule next QR code(s) based on encoding mode
            if self.use_parallel_encoding:
                # In parallel mode, advance by 1 chunk set (all streams advance together)
                self.current_qr_index += 1
            else:
                # In traditional mode, advance by grid size for sequential parallel transfer
                grid_size = self.config.qr_grid_size
                self.current_qr_index += (grid_size * grid_size)

            if self.current_qr_index >= self.total_chunks:
                self.current_qr_index = 0
                self.display_cycle += 1
                if not self.config.repeat:
                    self.is_displaying = False
                    self._update_button_states()
                    self._update_status("Display complete")
                    self._log("QR code display completed")
                    if hasattr(self, 'qr_window'):
                        self.qr_window.destroy()
                    return

            if self.is_displaying:
                # Schedule next image
                delay_ms = int(self.config.duration * 1000)
                self.root.after(delay_ms, self._show_next_qr)

        except Exception as e:
            self._log(f"Display error: {e}")
            self.is_displaying = False
            self._update_button_states()
            self._update_status("Display error")

    def _create_qr_display_window(self):
        """Create the QR code display window."""
        try:
            self.qr_window = tk.Toplevel(self.root)
            self.qr_window.title(self.config.window_title)
            self.qr_window.configure(bg='white')

            # Set window size and position
            if self.config.fullscreen:
                self.qr_window.attributes('-fullscreen', True)
                self._log("QR display window created in fullscreen mode")
            else:
                # Calculate required window size based on grid and QR size
                if self.use_parallel_encoding:
                    # For parallel encoding, calculate based on stream grid
                    grid_size = int(self.parallel_streams_var.get() ** 0.5)
                else:
                    # For traditional encoding, use config grid size
                    grid_size = self.config.qr_grid_size

                qr_size = self.config.qr_physical_size
                spacing = 10  # Pixels between QR codes
                required_size = (qr_size * grid_size) + (spacing * (grid_size - 1))

                # Add padding for window borders and controls
                padding = 50
                required_width = required_size + padding
                required_height = required_size + padding

                # Get screen dimensions
                self.qr_window.update_idletasks()  # Ensure window is ready
                screen_width = self.qr_window.winfo_screenwidth()
                screen_height = self.qr_window.winfo_screenheight()

                # Limit window size to 90% of screen to leave room for taskbar
                max_width = int(screen_width * 0.9)
                max_height = int(screen_height * 0.9)

                # Use calculated size or fall back to config/screen limits
                width = min(required_width, max_width, self.config.window_width if required_width <= self.config.window_width else required_width)
                height = min(required_height, max_height, self.config.window_height if required_height <= self.config.window_height else required_height)

                # If the calculated size is too big, we might need to scale down QR codes
                if required_width > max_width or required_height > max_height:
                    # Calculate maximum QR size that will fit
                    max_qr_size = min(
                        (max_width - padding - (spacing * (grid_size - 1))) // grid_size,
                        (max_height - padding - (spacing * (grid_size - 1))) // grid_size
                    )
                    self._log(f"QR grid too large for screen, scaling down from {qr_size}px to {max_qr_size}px per QR")
                    # We'll handle the scaling in _create_qr_grid by passing the target size

                # Center on screen
                pos_x = (screen_width // 2) - (width // 2)
                pos_y = (screen_height // 2) - (height // 2)
                self.qr_window.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

                self._log(f"QR display window created: {width}x{height} (grid: {grid_size}x{grid_size}, QR size: {qr_size}px)")

            # Create QR display label
            self.qr_display_label = tk.Label(self.qr_window, bg='white', text="Preparing QR code...")
            self.qr_display_label.pack(expand=True, fill=tk.BOTH)

            # Handle window close
            def on_qr_window_close():
                self.is_displaying = False
                self._update_button_states()
                self._update_status("Display stopped")
                self._log("Display window closed by user")
                try:
                    if self.qr_window and self.qr_window.winfo_exists():
                        self.qr_window.destroy()
                except (AttributeError, tk.TclError):
                    pass  # Window already destroyed
                finally:
                    self.qr_window = None

            self.qr_window.protocol("WM_DELETE_WINDOW", on_qr_window_close)

            # Bind escape key to stop
            self.qr_window.bind('<Escape>', lambda e: on_qr_window_close())

            # Force window to front and focus
            self.qr_window.lift()
            self.qr_window.focus_force()

            # Ensure window is visible
            self.qr_window.deiconify()

            self._log("QR display window setup complete")

        except Exception as e:
            self._log(f"Error creating QR display window: {e}")
            self.is_displaying = False
            self._update_button_states()
            raise

    def _create_qr_grid(self, qr_images: List[Image.Image], grid_size: int, target_qr_size: Optional[int] = None) -> Image.Image:
        """Create a grid layout of QR codes for parallel display."""
        if not qr_images:
            raise ValueError("No QR images provided")

        # Determine QR size - use target size if provided, otherwise config
        qr_size = target_qr_size or self.config.qr_physical_size

        # Auto-scale if grid would be too large
        spacing = 10
        window_width = self.qr_window.winfo_width() if hasattr(self, 'qr_window') and self.qr_window else 800
        window_height = self.qr_window.winfo_height() if hasattr(self, 'qr_window') and self.qr_window else 600

        # Calculate maximum QR size that will fit in the window
        max_width_per_qr = (window_width - 50 - (spacing * (grid_size - 1))) // grid_size
        max_height_per_qr = (window_height - 50 - (spacing * (grid_size - 1))) // grid_size
        max_qr_size = min(max_width_per_qr, max_height_per_qr)

        # Use the smaller of configured size or maximum that fits
        if qr_size > max_qr_size and max_qr_size > 50:  # Don't go below 50px
            qr_size = max_qr_size
            self._log(f"Auto-scaling QR codes to {qr_size}px to fit window")

        # Resize individual QR codes
        resized_qrs = []
        for qr in qr_images:
            resized = qr.resize((qr_size, qr_size), Image.Resampling.NEAREST)
            resized_qrs.append(resized)

        # Pad with blank images if needed
        total_needed = grid_size * grid_size
        while len(resized_qrs) < total_needed:
            blank = Image.new('RGB', (qr_size, qr_size), 'white')
            resized_qrs.append(blank)

        # Calculate grid dimensions
        spacing = 10  # Pixels between QR codes
        total_width = (qr_size * grid_size) + (spacing * (grid_size - 1))
        total_height = total_width  # Square grid

        # Create combined image
        combined = Image.new('RGB', (total_width, total_height), 'white')

        # Place QR codes in grid
        for row in range(grid_size):
            for col in range(grid_size):
                idx = row * grid_size + col
                if idx < len(resized_qrs):
                    x = col * (qr_size + spacing)
                    y = row * (qr_size + spacing)
                    combined.paste(resized_qrs[idx], (x, y))

        return combined

    def _save_qr_images(self):
        """Save QR images to directory."""
        if not hasattr(self, 'total_chunks') or self.total_chunks == 0:
            messagebox.showerror("Error", "No data to save. Please encode a file first.")
            return

        directory = filedialog.askdirectory(title="Select directory to save QR images")
        if not directory:
            return

        try:
            # Generate and save all QR images
            output_path = Path(directory)
            output_path.mkdir(parents=True, exist_ok=True)

            saved_paths = []
            self._log(f"Generating and saving {self.total_chunks} QR images...")

            for i in range(self.total_chunks):
                # Generate QR code on-demand
                qr_image = self.encoder.generate_qr_for_chunk(i)

                # Save image
                file_path = output_path / f"qr_{i:04d}.png"
                qr_image.save(file_path)
                saved_paths.append(str(file_path))

                # Update progress for large batches
                if (i + 1) % 100 == 0:
                    self._log(f"Saved {i + 1}/{self.total_chunks} QR images")

            self._log(f"Saved {len(saved_paths)} QR images to {directory}")
            messagebox.showinfo("Success", f"Saved {len(saved_paths)} QR images to {directory}")
        except Exception as e:
            self._log(f"Error saving QR images: {e}")
            messagebox.showerror("Save Error", f"Failed to save QR images: {e}")

    def _load_config_file(self):
        """Load configuration from file."""
        filename = filedialog.askopenfilename(
            title="Load Configuration",
            filetypes=[
                ("YAML files", "*.yaml *.yml"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ]
        )
        if filename:
            try:
                self.config = ConfigManager.load_config(filename)
                self._update_ui_from_config()
                self._log(f"Configuration loaded from: {filename}")
                messagebox.showinfo("Success", "Configuration loaded successfully")
            except Exception as e:
                self._log(f"Error loading config: {e}")
                messagebox.showerror("Load Error", f"Failed to load configuration: {e}")

    def _save_config_file(self):
        """Save configuration to file."""
        filename = filedialog.asksaveasfilename(
            title="Save Configuration",
            defaultextension=".yaml",
            filetypes=[
                ("YAML files", "*.yaml"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ]
        )
        if filename:
            try:
                self._update_config_from_ui()
                ConfigManager.save_config(self.config, filename)
                self._log(f"Configuration saved to: {filename}")
                messagebox.showinfo("Success", "Configuration saved successfully")
            except Exception as e:
                self._log(f"Error saving config: {e}")
                messagebox.showerror("Save Error", f"Failed to save configuration: {e}")

    def _toggle_parallel_encoding(self):
        """Toggle parallel encoding mode."""
        self.use_parallel_encoding = self.parallel_encoding_var.get()
        if self.use_parallel_encoding:
            self._log("Parallel stream encoding enabled - this mode splits data across multiple independent QR streams")
        else:
            self._log("Traditional encoding enabled - single QR stream mode")

    def _reset_config(self):
        """Reset configuration to defaults."""
        if messagebox.askyesno("Reset Configuration",
                              "Are you sure you want to reset all settings to defaults?"):
            self.config = ServerConfig()
            self._update_ui_from_config()
            self._log("Configuration reset to defaults")

    def _set_duration_with_warning(self, duration):
        """Set duration with performance warning for very fast speeds."""
        self.duration_var.set(duration)

        if duration < 0.2:
            self._log(f"Warning: Very fast duration ({duration}s) may cause capture issues. "
                     f"Ensure client can capture at {1/duration:.0f} FPS.")

    def _update_button_states(self):
        """Update button states based on current application state."""
        # Encode button
        if self.is_encoding:
            self.encode_btn.configure(state=tk.DISABLED)
        else:
            self.encode_btn.configure(state=tk.NORMAL)

        # Display buttons
        has_data = (hasattr(self, 'total_chunks') and self.total_chunks > 0) or (self.qr_images and len(self.qr_images) > 0)
        if has_data and not self.is_encoding:
            self.display_btn.configure(state=tk.NORMAL if not self.is_displaying else tk.DISABLED)
            self.save_qr_btn.configure(state=tk.NORMAL)
        else:
            self.display_btn.configure(state=tk.DISABLED)
            self.save_qr_btn.configure(state=tk.DISABLED)

        # Stop button
        self.stop_btn.configure(state=tk.NORMAL if self.is_displaying else tk.DISABLED)

    def _update_status(self, message):
        """Update status bar message."""
        self.status_var.set(message)

    def _update_info(self, message):
        """Update info display."""
        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, message)
        self.info_text.configure(state=tk.DISABLED)

    def _log(self, message):
        """Add message to log."""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _clear_log(self):
        """Clear the log display."""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _save_log(self):
        """Save log to file."""
        filename = filedialog.asksaveasfilename(
            title="Save Log",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                log_content = self.log_text.get(1.0, tk.END)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                messagebox.showinfo("Success", f"Log saved to {filename}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save log: {e}")

    def _on_closing(self):
        """Handle application closing."""
        if self.is_displaying:
            self._stop_display()

        # Close QR display window if open
        try:
            if hasattr(self, 'qr_window') and self.qr_window and self.qr_window.winfo_exists():
                self.qr_window.destroy()
        except (AttributeError, tk.TclError):
            pass  # Window already destroyed or doesn't exist

        if self.is_encoding:
            if messagebox.askyesno("Quit", "Encoding is in progress. Do you really want to quit?"):
                self.root.destroy()
        else:
            self.root.destroy()

    def run(self):
        """Run the GUI application."""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._on_closing()


def main():
    """Main entry point for GUI application."""
    try:
        app = QRLServerGUI()
        app.run()
    except Exception as e:
        print(f"Error starting QRL Server GUI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()