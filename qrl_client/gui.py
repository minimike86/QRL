#!/usr/bin/env python3
"""
QRL Client GUI

A modernized capture-and-decode interface. Workflow-first layout: pick an
output file, optionally pick a region, hit Start. Live preview shows what
the capture loop is seeing right now.
"""

import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import List, Optional

import cv2
import numpy as np
from PIL import Image, ImageTk

from qrl_server.ui_theme import (
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

from .capture import CaptureHandler
from .config import ClientConfig, ClientConfigManager
from .decoder import QRLDecoder
from .monitors import MonitorInfo, list_monitors
from .region_picker import pick_region


# Capture cadence presets — each tuple is (display name, interval seconds)
CAPTURE_PRESETS = [
    ("Slow (5 fps)", 0.2),
    ("Balanced (10 fps)", 0.1),
    ("Fast (20 fps)", 0.05),
    ("Max (30 fps)", 0.033),
]


class QRLClientGUI:
    """Modern QRL client GUI."""

    def __init__(self, master: Optional[tk.Misc] = None):
        if master is None:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(master)
        self.root.title("QRL Client — QR Stream Decoder")
        self.root.geometry("1100x780")
        self.root.minsize(960, 680)

        self.fonts = apply_theme(self.root)

        # Application state
        self.config = ClientConfig()
        self.decoder: Optional[QRLDecoder] = None
        self.capture_handler: Optional[CaptureHandler] = None
        self.output_file: Optional[str] = None
        self.capture_thread: Optional[threading.Thread] = None
        self.is_capturing = False
        self._latest_preview: Optional[np.ndarray] = None
        self._preview_photo: Optional[ImageTk.PhotoImage] = None
        self._capture_started_at: Optional[float] = None

        self._build_ui()
        self._bind_events()
        self._load_default_config()
        self._schedule_preview_refresh()
        self._update_button_states()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Header bar
        header = ttk.Frame(self.root, padding=(20, 16, 20, 12))
        header.pack(side=tk.TOP, fill=tk.X)

        title = ttk.Label(header, text="QRL Client", style="H1.TLabel")
        title.pack(side=tk.LEFT)

        subtitle = ttk.Label(
            header,
            text="Capture flashing QR codes from the screen and rebuild the file.",
            style="Muted.TLabel",
        )
        subtitle.pack(side=tk.LEFT, padx=(12, 0), pady=(8, 0))

        self.status_label = status_pill(header)
        self.status_label.pack(side=tk.RIGHT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # Body: two columns
        body = ttk.Frame(self.root, padding=(20, 16))
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=2, uniform="cols")
        body.columnconfigure(1, weight=3, uniform="cols")
        body.rowconfigure(0, weight=1)

        # Left column: workflow controls
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_workflow_panel(left)

        # Right column: live preview + progress + logs
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        self._build_preview_panel(right)

        # Status bar at the very bottom
        self._build_status_bar()

    def _build_workflow_panel(self, parent: ttk.Frame) -> None:
        # === 1. Output file ===
        out_card = card(parent)
        out_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(out_card, "1. Output file", on_card=True).pack(anchor="w")
        ttk.Label(
            out_card,
            text="Where the decoded data will be written.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        out_row = ttk.Frame(out_card, style="Card.TFrame")
        out_row.pack(fill=tk.X)
        self.output_path_var = tk.StringVar()
        self.output_entry = ttk.Entry(out_row, textvariable=self.output_path_var)
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        ttk.Button(out_row, text="Browse…", command=self._browse_output_file).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        # === 2. Capture region ===
        region_card = card(parent)
        region_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(region_card, "2. Capture region", on_card=True).pack(anchor="w")
        ttk.Label(
            region_card,
            text="Tighter is faster. Skip to capture the whole screen.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        region_row = ttk.Frame(region_card, style="Card.TFrame")
        region_row.pack(fill=tk.X)
        self.region_summary_var = tk.StringVar(value="Whole screen")
        ttk.Label(region_row, textvariable=self.region_summary_var, style="Card.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Button(region_row, text="Pick region…", command=self._select_region).pack(
            side=tk.RIGHT
        )
        ttk.Button(region_row, text="Reset", command=self._reset_region).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        # Screen selector — used when no custom region is picked.
        # Populated with friendly names from monitors.list_monitors().
        mon_row = ttk.Frame(region_card, style="Card.TFrame")
        mon_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(mon_row, text="Screen:", style="Card.TLabel").pack(side=tk.LEFT)

        self._monitor_list: list[MonitorInfo] = list_monitors()
        labels = [m.name for m in self._monitor_list] or ["Primary"]
        self.monitor_label_var = tk.StringVar(value=labels[0])
        self.monitor_combo = ttk.Combobox(
            mon_row,
            textvariable=self.monitor_label_var,
            values=labels,
            state="readonly",
            width=42,
        )
        self.monitor_combo.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)
        self.monitor_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_monitor_selected())

        # === 3. Capture speed (preset chips) ===
        speed_card = card(parent)
        speed_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(speed_card, "3. Capture speed", on_card=True).pack(anchor="w")
        ttk.Label(
            speed_card,
            text="Faster catches more QRs but uses more CPU.",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 8))

        chips_row = ttk.Frame(speed_card, style="Card.TFrame")
        chips_row.pack(fill=tk.X)
        self.preset_buttons: List[ttk.Button] = []
        for label, interval in CAPTURE_PRESETS:
            btn = ttk.Button(
                chips_row,
                text=label,
                style="Chip.TButton",
                command=lambda i=interval: self._set_speed_preset(i),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self.preset_buttons.append(btn)
        self._set_speed_preset(self.config.interval, refresh_only=True)

        # Timeout
        timeout_row = ttk.Frame(speed_card, style="Card.TFrame")
        timeout_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(timeout_row, text="Stop after:", style="Card.TLabel").pack(side=tk.LEFT)
        self.timeout_var = tk.IntVar(value=self.config.timeout)
        ttk.Spinbox(
            timeout_row,
            from_=10,
            to=3600,
            increment=10,
            width=6,
            textvariable=self.timeout_var,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            timeout_row, text="seconds", style="CardMuted.TLabel"
        ).pack(side=tk.LEFT, padx=(6, 0))

        # === 4. Primary action ===
        action_card = card(parent)
        action_card.pack(fill=tk.X, pady=(0, 12))
        action_row = ttk.Frame(action_card, style="Card.TFrame")
        action_row.pack(fill=tk.X)
        self.start_btn = ttk.Button(
            action_row,
            text="▶  Start capture",
            style="Primary.TButton",
            command=self._start_capture,
        )
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(
            action_row,
            text="■  Stop",
            style="Danger.TButton",
            command=self._stop_capture,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            action_row,
            text="Save log…",
            command=self._save_log,
        ).pack(side=tk.RIGHT)

    def _build_preview_panel(self, parent: ttk.Frame) -> None:
        # Live preview
        preview_card = card(parent)
        preview_card.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        head_row = ttk.Frame(preview_card, style="Card.TFrame")
        head_row.pack(fill=tk.X)
        section_heading(head_row, "Live preview", on_card=True).pack(side=tk.LEFT)
        self.preview_info_var = tk.StringVar(value="Waiting for capture…")
        ttk.Label(head_row, textvariable=self.preview_info_var, style="CardMuted.TLabel").pack(
            side=tk.RIGHT
        )

        self.preview_canvas = tk.Canvas(
            preview_card,
            bg=BG_INPUT,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        # Progress card
        progress_card = card(parent)
        progress_card.pack(fill=tk.X, pady=(0, 12))
        section_heading(progress_card, "Decoding progress", on_card=True).pack(anchor="w")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            progress_card, variable=self.progress_var, maximum=100, length=400
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

        self.frames_processed_var = tk.StringVar(value="0")
        self.qr_success_rate_var = tk.StringVar(value="–")
        self.chunks_decoded_var = tk.StringVar(value="0 / 0")
        self.time_remaining_var = tk.StringVar(value="–")

        stat(stats, "Frames", self.frames_processed_var).grid(row=0, column=0, sticky="w")
        stat(stats, "QR success", self.qr_success_rate_var).grid(row=0, column=1, sticky="w")
        stat(stats, "Chunks", self.chunks_decoded_var).grid(row=0, column=2, sticky="w")
        stat(stats, "ETA", self.time_remaining_var).grid(row=0, column=3, sticky="w")

        # Logs (collapsible-ish area at bottom)
        logs_card = card(parent)
        logs_card.pack(fill=tk.BOTH, expand=False)
        section_heading(logs_card, "Activity log", on_card=True).pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(
            logs_card,
            height=7,
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
        bar = ttk.Frame(self.root, padding=(20, 6))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(side=tk.BOTTOM, fill=tk.X)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.status_var, style="Muted.TLabel").pack(side=tk.LEFT)

        ttk.Label(
            bar,
            text="QRL  ·  press Esc inside region picker to cancel",
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

    def _bind_events(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.timeout_var.trace("w", lambda *_: self._update_config_from_ui())

    # ------------------------------------------------------------------
    # Config plumbing
    # ------------------------------------------------------------------
    def _load_default_config(self) -> None:
        try:
            self.config = ClientConfigManager.load_config()
        except Exception as e:
            self._log(f"Using default config: {e}")
        self._update_ui_from_config()

    def _update_config_from_ui(self) -> None:
        try:
            self.config.timeout = self.timeout_var.get()
        except (tk.TclError, ValueError):
            pass

    def _on_monitor_selected(self) -> None:
        label = self.monitor_label_var.get()
        for m in self._monitor_list:
            if m.name == label:
                self.config.monitor = m.index
                break

    def _update_ui_from_config(self) -> None:
        self.timeout_var.set(self.config.timeout)
        self._set_speed_preset(self.config.interval, refresh_only=True)
        # Sync the screen combobox with the saved config monitor index
        if self._monitor_list:
            for m in self._monitor_list:
                if m.index == self.config.monitor:
                    self.monitor_label_var.set(m.name)
                    break
            else:
                # Saved index doesn't match any current monitor; pick primary
                primary = next((m for m in self._monitor_list if m.is_primary), self._monitor_list[0])
                self.config.monitor = primary.index
                self.monitor_label_var.set(primary.name)
        if self.config.region:
            x, y, w, h = self.config.region
            self.region_summary_var.set(f"{w}×{h} at ({x}, {y})")
        else:
            self.region_summary_var.set("Whole screen")

    def _set_speed_preset(self, interval: float, refresh_only: bool = False) -> None:
        if not refresh_only:
            self.config.interval = interval
        # Highlight matching chip
        for btn, (_, value) in zip(self.preset_buttons, CAPTURE_PRESETS):
            style = "ChipActive.TButton" if abs(value - self.config.interval) < 1e-3 else "Chip.TButton"
            btn.configure(style=style)

    # ------------------------------------------------------------------
    # File / region pickers
    # ------------------------------------------------------------------
    def _browse_output_file(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="Save decoded data to…",
            filetypes=[
                ("All files", "*.*"),
                ("Binary files", "*.bin"),
                ("Text files", "*.txt"),
            ],
        )
        if filename:
            self.output_path_var.set(filename)
            self.output_file = filename
            self._update_button_states()

    def _select_region(self) -> None:
        self.root.iconify()
        self.root.update_idletasks()
        # Tiny delay so the parent window is actually minimized before the
        # picker grabs the screen.
        self.root.after(150, self._open_region_picker)

    def _open_region_picker(self) -> None:
        try:
            region = pick_region(self.root)
        except Exception as e:
            self.root.deiconify()
            messagebox.showerror("Region picker failed", str(e))
            return
        self.root.deiconify()
        self.root.lift()
        if region is None:
            self._log("Region selection cancelled")
            return
        self.config.region = region
        x, y, w, h = region
        self.region_summary_var.set(f"{w}×{h} at ({x}, {y})")
        self._log(f"Region set: {w}×{h} at ({x}, {y})")

    def _reset_region(self) -> None:
        self.config.region = None
        self.region_summary_var.set("Whole screen")
        self._log("Region reset — capturing whole screen")

    # ------------------------------------------------------------------
    # Capture lifecycle
    # ------------------------------------------------------------------
    def _start_capture(self) -> None:
        if not self.output_file:
            messagebox.showerror("Missing output file", "Pick an output file first.")
            return
        if self.is_capturing:
            return
        self._update_config_from_ui()
        try:
            self.config.validate()
        except ValueError as e:
            messagebox.showerror("Configuration error", str(e))
            return

        self.is_capturing = True
        self._capture_started_at = time.time()
        self._update_button_states()
        set_status(self.status_label, "running", "Capturing")
        self._update_status("Capturing…")
        self._log(f"Capture started → {self.output_file}")

        self.capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.capture_thread.start()

    def _capture_worker(self) -> None:
        try:
            self.capture_handler = CaptureHandler(
                monitor=self.config.monitor,
                region=self.config.region,
                interval=self.config.interval,
            )
            self.decoder = QRLDecoder(self.output_file, timeout=self.config.timeout)
            self.capture_handler.start()

            start_time = time.time()
            while self.is_capturing and (time.time() - start_time) < self.config.timeout:
                frames = self.capture_handler.get_frames()
                if frames:
                    self._latest_preview = frames[-1]  # picked up by preview refresh on main thread
                    success = self.decoder.decode(frames)
                    self.root.after(0, self._update_progress)
                    if success:
                        self.root.after(0, self._decoding_complete)
                        return
                time.sleep(0.02)
            # Loop exited without completion
            self.root.after(0, self._capture_finished_without_success)
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._capture_error(err))
        finally:
            if self.capture_handler is not None:
                self.capture_handler.stop()
            self.is_capturing = False
            self.root.after(0, self._update_button_states)

    def _stop_capture(self) -> None:
        if not self.is_capturing:
            return
        self.is_capturing = False
        self._update_status("Stopping…")
        self._log("Stop requested")

    # ------------------------------------------------------------------
    # Live preview (runs on main thread via root.after)
    # ------------------------------------------------------------------
    def _schedule_preview_refresh(self) -> None:
        self._refresh_preview()
        # 30 FPS preview refresh — independent of capture rate
        self.root.after(33, self._schedule_preview_refresh)

    def _refresh_preview(self) -> None:
        frame = self._latest_preview
        if frame is None:
            return
        try:
            if frame.ndim == 3 and frame.shape[2] >= 3:
                # capture frames are BGR (cv2 convention)
                rgb = cv2.cvtColor(frame[:, :, :3], cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb)
            else:
                pil = Image.fromarray(frame)

            cw = max(self.preview_canvas.winfo_width(), 100)
            ch = max(self.preview_canvas.winfo_height(), 100)
            pil.thumbnail((cw - 4, ch - 4), Image.Resampling.LANCZOS)
            self._preview_photo = ImageTk.PhotoImage(pil)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(cw // 2, ch // 2, image=self._preview_photo)
            self.preview_info_var.set(f"{pil.size[0]}×{pil.size[1]}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Progress / completion
    # ------------------------------------------------------------------
    def _update_progress(self) -> None:
        if self.decoder is None:
            return
        progress = self.decoder.get_progress()
        stats = self.decoder.get_statistics()

        pct = progress.get("percentage", 0)
        decoded = progress.get("decoded_chunks", 0)
        total = progress.get("total_chunks", 0)
        self.progress_var.set(pct)
        if total > 0:
            self.progress_label_var.set(f"Decoded {decoded:,} of {total:,} chunks ({pct:.1f}%)")
        else:
            self.progress_label_var.set("Waiting for first QR…")

        self.frames_processed_var.set(f"{stats.get('total_frames_processed', 0):,}")
        self.qr_success_rate_var.set(f"{stats.get('qr_read_success_rate', 0):.0f}%")
        self.chunks_decoded_var.set(f"{decoded:,} / {total:,}")

        if 0 < pct < 100:
            elapsed = stats.get("elapsed_time", 0)
            remaining = (elapsed / pct) * (100 - pct)
            self.time_remaining_var.set(f"{remaining:.0f}s")
        elif pct >= 100:
            self.time_remaining_var.set("done")
        else:
            self.time_remaining_var.set("–")

    def _decoding_complete(self) -> None:
        self.progress_var.set(100)
        self.progress_label_var.set("Complete — file decoded successfully.")
        set_status(self.status_label, "ok", "Complete")
        self._update_status("Decoding complete")
        self._log(f"✓ Decoded → {self.output_file}")
        self.is_capturing = False
        self._update_button_states()
        messagebox.showinfo("Success", f"File decoded to:\n{self.output_file}")

    def _capture_finished_without_success(self) -> None:
        progress = self.decoder.get_progress() if self.decoder else {"percentage": 0}
        missing = self.decoder.get_missing_chunks() if self.decoder else []
        self._log(f"Capture stopped at {progress.get('percentage', 0):.1f}%, missing {len(missing)} chunks")
        if missing:
            set_status(self.status_label, "error", "Incomplete")
            self._update_status("Stopped — incomplete")
        else:
            set_status(self.status_label, "idle", "Idle")
            self._update_status("Stopped")

    def _capture_error(self, msg: str) -> None:
        self.progress_label_var.set(f"Error: {msg}")
        set_status(self.status_label, "error", "Error")
        self._update_status("Error")
        self._log(f"✗ {msg}")
        messagebox.showerror("Capture error", msg)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _update_button_states(self) -> None:
        if self.is_capturing:
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
        else:
            self.start_btn.configure(state=tk.NORMAL if self.output_file else tk.DISABLED)
            self.stop_btn.configure(state=tk.DISABLED)

    def _update_status(self, text: str) -> None:
        self.status_var.set(text)

    def _log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _save_log(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="Save log",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            content = self.log_text.get("1.0", tk.END)
            Path(filename).write_text(content, encoding="utf-8")
            messagebox.showinfo("Saved", f"Log written to {filename}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _on_closing(self) -> None:
        if self.is_capturing:
            if not messagebox.askyesno(
                "Quit", "Capture is running. Quit anyway?"
            ):
                return
            self.is_capturing = False
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
        app = QRLClientGUI()
        app.run()
    except Exception as e:
        print(f"Error starting QRL Client GUI: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
