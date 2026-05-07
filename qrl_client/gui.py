#!/usr/bin/env python3
"""
QRL Client GUI Application
Graphical interface for the QRL client using tkinter.
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
import threading
import time
import cv2
import numpy as np
from typing import Optional, List, Tuple
from PIL import Image, ImageTk

from .decoder import QRLDecoder
from .capture import CaptureHandler
from .config import ClientConfig, ClientConfigManager


class QRLClientGUI:
    """Main GUI application for QRL Client."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("QRL Client - QR Code Decoder")
        self.root.geometry("1000x800")
        self.root.minsize(900, 700)

        # Application state
        self.config = ClientConfig()
        self.decoder: Optional[QRLDecoder] = None
        self.capture_handler: Optional[CaptureHandler] = None
        self.output_file: Optional[str] = None
        self.capture_thread: Optional[threading.Thread] = None
        self.is_capturing = False
        self.is_decoding = False
        self.preview_image = None

        self._setup_ui()
        self._setup_bindings()
        self._load_default_config()
        self._start_preview_update()

    def _setup_ui(self):
        """Set up the user interface."""
        # Create main paned window
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left frame for controls
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)

        # Right frame for preview
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)

        self._setup_left_panel(left_frame)
        self._setup_right_panel(right_frame)

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _setup_left_panel(self, parent):
        """Set up the left control panel."""
        # Create notebook for tabs
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Main tab
        self.main_frame = ttk.Frame(notebook)
        notebook.add(self.main_frame, text="Capture")
        self._setup_main_tab()

        # Settings tab
        self.settings_frame = ttk.Frame(notebook)
        notebook.add(self.settings_frame, text="Settings")
        self._setup_settings_tab()

        # Log tab
        self.log_frame = ttk.Frame(notebook)
        notebook.add(self.log_frame, text="Logs")
        self._setup_log_tab()

    def _setup_right_panel(self, parent):
        """Set up the right preview panel."""
        preview_frame = ttk.LabelFrame(parent, text="Screen Preview", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        # Preview canvas
        self.preview_canvas = tk.Canvas(preview_frame, bg="black", width=400, height=300)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Preview info
        self.preview_info_var = tk.StringVar()
        self.preview_info_var.set("Preview not started")
        ttk.Label(preview_frame, textvariable=self.preview_info_var).pack(anchor=tk.W)

    def _setup_main_tab(self):
        """Set up the main capture tab."""
        # Output file frame
        output_frame = ttk.LabelFrame(self.main_frame, text="Output File", padding=10)
        output_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(output_frame, text="Save decoded file to:").pack(anchor=tk.W)
        file_entry_frame = ttk.Frame(output_frame)
        file_entry_frame.pack(fill=tk.X, pady=(5, 0))

        self.output_path_var = tk.StringVar()
        self.output_entry = ttk.Entry(file_entry_frame, textvariable=self.output_path_var)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.output_browse_btn = ttk.Button(file_entry_frame, text="Browse...",
                                           command=self._browse_output_file)
        self.output_browse_btn.pack(side=tk.RIGHT)

        # Capture settings frame
        capture_settings_frame = ttk.LabelFrame(self.main_frame, text="Capture Settings", padding=10)
        capture_settings_frame.pack(fill=tk.X, pady=(0, 10))

        # Monitor selection
        monitor_frame = ttk.Frame(capture_settings_frame)
        monitor_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(monitor_frame, text="Monitor:").pack(side=tk.LEFT)
        self.monitor_var = tk.IntVar(value=self.config.monitor)
        ttk.Spinbox(monitor_frame, from_=0, to=5, width=10,
                   textvariable=self.monitor_var).pack(side=tk.RIGHT)

        # Capture interval
        interval_frame = ttk.Frame(capture_settings_frame)
        interval_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(interval_frame, text="Capture interval (seconds):").pack(side=tk.LEFT)
        self.interval_var = tk.DoubleVar(value=self.config.interval)
        ttk.Spinbox(interval_frame, from_=0.1, to=5.0, increment=0.1, width=10,
                   textvariable=self.interval_var).pack(side=tk.RIGHT)

        # Timeout
        timeout_frame = ttk.Frame(capture_settings_frame)
        timeout_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(timeout_frame, text="Timeout (seconds):").pack(side=tk.LEFT)
        self.timeout_var = tk.IntVar(value=self.config.timeout)
        ttk.Spinbox(timeout_frame, from_=30, to=3600, width=10,
                   textvariable=self.timeout_var).pack(side=tk.RIGHT)

        # Region selection
        region_frame = ttk.Frame(capture_settings_frame)
        region_frame.pack(fill=tk.X)

        self.region_enabled_var = tk.BooleanVar(value=bool(self.config.region))
        region_check = ttk.Checkbutton(region_frame, text="Custom region:",
                                      variable=self.region_enabled_var,
                                      command=self._toggle_region)
        region_check.pack(anchor=tk.W)

        self.region_entry_frame = ttk.Frame(region_frame)
        self.region_entry_frame.pack(fill=tk.X, pady=(5, 0))

        region_labels = ["X:", "Y:", "Width:", "Height:"]
        self.region_vars = []
        for i, label in enumerate(region_labels):
            ttk.Label(self.region_entry_frame, text=label, width=8).grid(row=0, column=i*2, sticky=tk.W)
            var = tk.IntVar(value=(self.config.region[i] if self.config.region else 0))
            self.region_vars.append(var)
            entry = ttk.Entry(self.region_entry_frame, textvariable=var, width=8)
            entry.grid(row=0, column=i*2+1, padx=(0, 5), sticky=tk.W)

        self._toggle_region()

        # Control frame
        control_frame = ttk.LabelFrame(self.main_frame, text="Control", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)

        self.start_btn = ttk.Button(button_frame, text="Start Capture", command=self._start_capture)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.stop_btn = ttk.Button(button_frame, text="Stop Capture", command=self._stop_capture,
                                  state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.select_region_btn = ttk.Button(button_frame, text="Select Region",
                                           command=self._select_region)
        self.select_region_btn.pack(side=tk.RIGHT)

        # Progress frame
        progress_frame = ttk.LabelFrame(self.main_frame, text="Progress", padding=10)
        progress_frame.pack(fill=tk.BOTH, expand=True)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var,
                                           maximum=100, length=400)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.progress_label_var = tk.StringVar()
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_label_var)
        self.progress_label.pack(anchor=tk.W, pady=(0, 10))

        # Statistics
        stats_frame = ttk.Frame(progress_frame)
        stats_frame.pack(fill=tk.X)

        # Left column
        stats_left = ttk.Frame(stats_frame)
        stats_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.frames_processed_var = tk.StringVar(value="Frames processed: 0")
        ttk.Label(stats_left, textvariable=self.frames_processed_var).pack(anchor=tk.W)

        self.qr_success_rate_var = tk.StringVar(value="QR success rate: 0%")
        ttk.Label(stats_left, textvariable=self.qr_success_rate_var).pack(anchor=tk.W)

        # Right column
        stats_right = ttk.Frame(stats_frame)
        stats_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.chunks_decoded_var = tk.StringVar(value="Chunks decoded: 0/0")
        ttk.Label(stats_right, textvariable=self.chunks_decoded_var).pack(anchor=tk.W)

        self.time_remaining_var = tk.StringVar(value="Time remaining: --")
        ttk.Label(stats_right, textvariable=self.time_remaining_var).pack(anchor=tk.W)

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

        # Detection settings
        detection_frame = ttk.LabelFrame(scrollable_frame, text="QR Detection", padding=10)
        detection_frame.pack(fill=tk.X, pady=(0, 10))

        # Detection threshold
        threshold_frame = ttk.Frame(detection_frame)
        threshold_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(threshold_frame, text="Detection threshold:").pack(side=tk.LEFT)
        self.detection_threshold_var = tk.DoubleVar(value=self.config.qr_detection_threshold)
        ttk.Scale(threshold_frame, from_=0.0, to=1.0, variable=self.detection_threshold_var,
                 orient=tk.HORIZONTAL, length=150).pack(side=tk.RIGHT)

        # Image preprocessing
        self.preprocessing_var = tk.BooleanVar(value=self.config.image_preprocessing)
        ttk.Checkbutton(detection_frame, text="Enable image preprocessing",
                       variable=self.preprocessing_var).pack(anchor=tk.W, pady=(0, 5))

        self.enhance_contrast_var = tk.BooleanVar(value=self.config.enhance_contrast)
        ttk.Checkbutton(detection_frame, text="Enhance contrast",
                       variable=self.enhance_contrast_var).pack(anchor=tk.W, pady=(0, 5))

        self.noise_reduction_var = tk.BooleanVar(value=self.config.noise_reduction)
        ttk.Checkbutton(detection_frame, text="Noise reduction",
                       variable=self.noise_reduction_var).pack(anchor=tk.W)

        # Processing settings
        processing_frame = ttk.LabelFrame(scrollable_frame, text="Processing", padding=10)
        processing_frame.pack(fill=tk.X, pady=(0, 10))

        # Max decode attempts
        attempts_frame = ttk.Frame(processing_frame)
        attempts_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(attempts_frame, text="Max decode attempts:").pack(side=tk.LEFT)
        self.max_attempts_var = tk.IntVar(value=self.config.max_decode_attempts)
        ttk.Spinbox(attempts_frame, from_=1, to=20, width=10,
                   textvariable=self.max_attempts_var).pack(side=tk.RIGHT)

        # Frame buffer size
        buffer_frame = ttk.Frame(processing_frame)
        buffer_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(buffer_frame, text="Frame buffer size:").pack(side=tk.LEFT)
        self.buffer_size_var = tk.IntVar(value=self.config.frame_buffer_size)
        ttk.Spinbox(buffer_frame, from_=10, to=200, width=10,
                   textvariable=self.buffer_size_var).pack(side=tk.RIGHT)

        # Progress settings
        self.save_progress_var = tk.BooleanVar(value=self.config.save_progress)
        ttk.Checkbutton(processing_frame, text="Save progress for recovery",
                       variable=self.save_progress_var).pack(anchor=tk.W)

        # Configuration management
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
        self.monitor_var.trace('w', self._update_config_from_ui)
        self.interval_var.trace('w', self._update_config_from_ui)
        self.timeout_var.trace('w', self._update_config_from_ui)

    def _load_default_config(self):
        """Load default configuration."""
        try:
            self.config = ClientConfigManager.load_config()
            self._update_ui_from_config()
            self._log("Configuration loaded successfully")
        except Exception as e:
            self._log(f"Warning: Could not load config, using defaults: {e}")

    def _update_config_from_ui(self, *args):
        """Update config object from UI values."""
        try:
            self.config.monitor = self.monitor_var.get()
            self.config.interval = self.interval_var.get()
            self.config.timeout = self.timeout_var.get()

            if hasattr(self, 'region_enabled_var') and self.region_enabled_var.get():
                region = tuple(var.get() for var in self.region_vars)
                self.config.region = region if any(region) else None
            else:
                self.config.region = None

            # Update detection settings
            if hasattr(self, 'detection_threshold_var'):
                self.config.qr_detection_threshold = self.detection_threshold_var.get()

            if hasattr(self, 'preprocessing_var'):
                self.config.image_preprocessing = self.preprocessing_var.get()

            if hasattr(self, 'enhance_contrast_var'):
                self.config.enhance_contrast = self.enhance_contrast_var.get()

            if hasattr(self, 'noise_reduction_var'):
                self.config.noise_reduction = self.noise_reduction_var.get()

            if hasattr(self, 'max_attempts_var'):
                self.config.max_decode_attempts = self.max_attempts_var.get()

            if hasattr(self, 'buffer_size_var'):
                self.config.frame_buffer_size = self.buffer_size_var.get()

            if hasattr(self, 'save_progress_var'):
                self.config.save_progress = self.save_progress_var.get()

        except (tk.TclError, ValueError):
            # Ignore invalid values during typing
            pass

    def _update_ui_from_config(self):
        """Update UI values from config object."""
        self.monitor_var.set(self.config.monitor)
        self.interval_var.set(self.config.interval)
        self.timeout_var.set(self.config.timeout)

        if self.config.region:
            self.region_enabled_var.set(True)
            for i, var in enumerate(self.region_vars):
                var.set(self.config.region[i])
        else:
            self.region_enabled_var.set(False)

        if hasattr(self, 'detection_threshold_var'):
            self.detection_threshold_var.set(self.config.qr_detection_threshold)

        if hasattr(self, 'preprocessing_var'):
            self.preprocessing_var.set(self.config.image_preprocessing)

        if hasattr(self, 'enhance_contrast_var'):
            self.enhance_contrast_var.set(self.config.enhance_contrast)

        if hasattr(self, 'noise_reduction_var'):
            self.noise_reduction_var.set(self.config.noise_reduction)

        if hasattr(self, 'max_attempts_var'):
            self.max_attempts_var.set(self.config.max_decode_attempts)

        if hasattr(self, 'buffer_size_var'):
            self.buffer_size_var.set(self.config.frame_buffer_size)

        if hasattr(self, 'save_progress_var'):
            self.save_progress_var.set(self.config.save_progress)

    def _toggle_region(self):
        """Toggle region selection controls."""
        enabled = self.region_enabled_var.get()
        for widget in self.region_entry_frame.winfo_children():
            if isinstance(widget, ttk.Entry):
                widget.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _browse_output_file(self):
        """Open file dialog to select output file."""
        filename = filedialog.asksaveasfilename(
            title="Save decoded data to...",
            filetypes=[
                ("All files", "*.*"),
                ("Text files", "*.txt"),
                ("Binary files", "*.bin"),
            ]
        )
        if filename:
            self.output_path_var.set(filename)
            self.output_file = filename

    def _select_region(self):
        """Allow user to select capture region visually."""
        # This would implement a region selection overlay
        messagebox.showinfo("Region Selection",
                           "Region selection GUI not implemented yet.\n"
                           "Please enter coordinates manually in the settings.")

    def _start_capture(self):
        """Start capture and decoding."""
        if not self.output_file:
            messagebox.showerror("Error", "Please select an output file first")
            return

        if self.is_capturing:
            messagebox.showwarning("Warning", "Capture is already in progress")
            return

        try:
            self._update_config_from_ui()
            self.config.validate()
        except ValueError as e:
            messagebox.showerror("Configuration Error", str(e))
            return

        self.is_capturing = True
        self._update_button_states()
        self.capture_thread = threading.Thread(target=self._capture_worker)
        self.capture_thread.daemon = True
        self.capture_thread.start()

    def _capture_worker(self):
        """Worker thread for capture and decoding."""
        try:
            self._update_status("Starting capture...")
            self._log("Starting QR code capture and decoding")

            # Create capture handler
            self.capture_handler = CaptureHandler(
                monitor=self.config.monitor,
                region=self.config.region,
                interval=self.config.interval
            )

            # Create decoder
            self.decoder = QRLDecoder(
                self.output_file,
                timeout=self.config.timeout
            )

            # Start capturing
            self.capture_handler.start()

            start_time = time.time()
            last_progress_update = 0

            # Main capture loop
            while time.time() - start_time < self.config.timeout and self.is_capturing:
                frames = self.capture_handler.get_frames()

                if frames:
                    # Update preview with latest frame
                    if frames:
                        self._update_preview(frames[-1])

                    # Attempt to decode
                    success = self.decoder.decode(frames)

                    if success:
                        self.root.after(0, self._decoding_complete)
                        break

                    # Update progress periodically
                    current_time = time.time()
                    if current_time - last_progress_update >= self.config.progress_interval:
                        self.root.after(0, self._update_progress)
                        last_progress_update = current_time

                        # Save progress if enabled
                        if self.config.save_progress:
                            self.decoder.save_partial_progress()

                time.sleep(0.1)  # Small delay to prevent excessive CPU usage
            else:
                # Timeout or stopped
                self.root.after(0, self._capture_timeout)

        except Exception as e:
            self.root.after(0, lambda: self._capture_error(str(e)))

        finally:
            if self.capture_handler:
                self.capture_handler.stop()

            self.is_capturing = False
            self.root.after(0, self._update_button_states)

    def _update_preview(self, frame):
        """Update preview canvas with latest frame."""
        if not self.config.show_preview or frame is None:
            return

        try:
            # Convert frame to PIL Image
            if len(frame.shape) == 3:  # Color image
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
            else:  # Grayscale
                image = Image.fromarray(frame)

            # Resize to fit preview
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()

            if canvas_width > 1 and canvas_height > 1:  # Canvas is ready
                image.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)

                # Convert to PhotoImage
                self.preview_image = ImageTk.PhotoImage(image)

                # Update canvas
                self.preview_canvas.delete("all")
                self.preview_canvas.create_image(
                    canvas_width // 2, canvas_height // 2,
                    image=self.preview_image
                )

                # Update preview info
                self.preview_info_var.set(f"Frame: {image.size[0]}x{image.size[1]}")

        except Exception as e:
            self._log(f"Preview update error: {e}")

    def _update_progress(self):
        """Update progress display."""
        if not self.decoder:
            return

        try:
            progress = self.decoder.get_progress()
            stats = self.decoder.get_statistics()

            # Update progress bar
            percentage = progress.get('percentage', 0)
            self.progress_var.set(percentage)

            # Update labels
            decoded = progress.get('decoded_chunks', 0)
            total = progress.get('total_chunks', 0)

            if total > 0:
                self.progress_label_var.set(f"Progress: {percentage:.1f}% ({decoded}/{total} chunks)")
            else:
                self.progress_label_var.set("Waiting for QR codes...")

            # Update statistics
            self.frames_processed_var.set(f"Frames processed: {stats.get('total_frames_processed', 0)}")
            self.qr_success_rate_var.set(f"QR success rate: {stats.get('qr_read_success_rate', 0):.1f}%")
            self.chunks_decoded_var.set(f"Chunks decoded: {decoded}/{total}")

            # Estimate time remaining
            if percentage > 0 and percentage < 100:
                elapsed = stats.get('elapsed_time', 0)
                remaining = (elapsed / percentage) * (100 - percentage)
                self.time_remaining_var.set(f"Time remaining: {remaining/60:.1f} min")
            else:
                self.time_remaining_var.set("Time remaining: --")

        except Exception as e:
            self._log(f"Progress update error: {e}")

    def _decoding_complete(self):
        """Called when decoding completes successfully."""
        self._update_status("Decoding complete")
        self.progress_var.set(100)
        self.progress_label_var.set("Complete - File successfully decoded!")

        if self.decoder:
            stats = self.decoder.get_statistics()
            self._log(f"Decoding complete! Statistics: {stats}")

        messagebox.showinfo("Success", f"File successfully decoded to:\n{self.output_file}")

    def _capture_timeout(self):
        """Called when capture times out."""
        self._update_status("Capture timed out")

        if self.decoder:
            stats = self.decoder.get_statistics()
            progress = self.decoder.get_progress()
            missing = self.decoder.get_missing_chunks()

            self._log(f"Capture timed out. Progress: {progress.get('percentage', 0):.1f}%")

            if missing and len(missing) <= 10:
                messagebox.showwarning("Timeout",
                                     f"Capture timed out.\n"
                                     f"Progress: {progress.get('percentage', 0):.1f}%\n"
                                     f"Missing chunks: {missing}")
            else:
                messagebox.showwarning("Timeout",
                                     f"Capture timed out.\n"
                                     f"Progress: {progress.get('percentage', 0):.1f}%\n"
                                     f"Missing {len(missing) if missing else 0} chunks")

    def _capture_error(self, error_msg):
        """Called when capture fails."""
        self._update_status("Capture failed")
        self.progress_var.set(0)
        self.progress_label_var.set(f"Error: {error_msg}")
        self._log(f"Capture error: {error_msg}")
        messagebox.showerror("Capture Error", error_msg)

    def _stop_capture(self):
        """Stop capture and decoding."""
        self.is_capturing = False
        self._update_status("Stopping capture...")

    def _start_preview_update(self):
        """Start periodic preview updates."""
        self._update_preview_size()
        self.root.after(100, self._start_preview_update)

    def _update_preview_size(self):
        """Update preview canvas size info."""
        if not hasattr(self, 'preview_canvas'):
            return

        try:
            width = self.preview_canvas.winfo_width()
            height = self.preview_canvas.winfo_height()

            if width > 1 and height > 1 and not self.is_capturing:
                self.preview_info_var.set(f"Preview: {width}x{height} (ready)")

        except Exception:
            pass

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
                self.config = ClientConfigManager.load_config(filename)
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
                ClientConfigManager.save_config(self.config, filename)
                self._log(f"Configuration saved to: {filename}")
                messagebox.showinfo("Success", "Configuration saved successfully")
            except Exception as e:
                self._log(f"Error saving config: {e}")
                messagebox.showerror("Save Error", f"Failed to save configuration: {e}")

    def _reset_config(self):
        """Reset configuration to defaults."""
        if messagebox.askyesno("Reset Configuration",
                              "Are you sure you want to reset all settings to defaults?"):
            self.config = ClientConfig()
            self._update_ui_from_config()
            self._log("Configuration reset to defaults")

    def _update_button_states(self):
        """Update button states based on current application state."""
        if self.is_capturing:
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
        else:
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)

    def _update_status(self, message):
        """Update status bar message."""
        self.status_var.set(message)

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
        if self.is_capturing:
            if messagebox.askyesno("Quit", "Capture is in progress. Do you really want to quit?"):
                self.is_capturing = False
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
        app = QRLClientGUI()
        app.run()
    except Exception as e:
        print(f"Error starting QRL Client GUI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()