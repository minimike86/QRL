#!/usr/bin/env python3
"""
QRL Server CLI
Command-line interface for the QRL server.
"""

import collections
import sys
import argparse
from pathlib import Path

from .config import ServerConfig, ConfigManager
from .exceptions import QRLError, ValidationError, QRLErrorHandler

_CACHE_MAX = 4096


class _LRUDict:
    def __init__(self, max_size: int):
        self._d: "collections.OrderedDict" = collections.OrderedDict()
        self._max = max_size

    def __contains__(self, key) -> bool:
        return key in self._d

    def __getitem__(self, key):
        value = self._d[key]
        self._d.move_to_end(key)
        return value

    def __setitem__(self, key, value) -> None:
        if key in self._d:
            self._d.move_to_end(key)
        self._d[key] = value
        while len(self._d) > self._max:
            self._d.popitem(last=False)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="QRL Server - Encode files as QR codes and display them",
        prog="qrl-server",
        epilog="Configuration files are searched in the current directory and ~/.qrl/"
    )

    parser.add_argument(
        "file",
        nargs="?",
        help="Path to file or directory to encode"
    )

    parser.add_argument("--config", "-c", metavar="FILE",
                        help="Path to configuration file (YAML/JSON)")
    parser.add_argument("--save-config", metavar="FILE",
                        help="Save current settings to configuration file and exit")
    parser.add_argument("--create-config", metavar="FILE",
                        help="Create example configuration file and exit")

    parser.add_argument("--chunk-size", type=int,
                        help="Chunk size in bytes (default from config)")
    parser.add_argument("--error-correction", choices=["L", "M", "Q", "H"],
                        help="QR error correction level (default from config)")
    parser.add_argument("--qr-version", type=int, choices=range(1, 41),
                        metavar="{1..40}", help="QR code version (default: auto)")
    parser.add_argument("--box-size", type=int, metavar="PX",
                        help="Pixels per QR module, e.g. 10 (Normal), 16 (Sharp), 24 (Ultra)")

    parser.add_argument("--duration", type=float,
                        help="Seconds per QR code (default from config)")
    parser.add_argument("--no-repeat", action="store_true",
                        help="Stop after one pass instead of looping")
    parser.add_argument("--window-title", help="Display window title")
    parser.add_argument("--fullscreen", action="store_true",
                        help="Display fullscreen")

    parser.add_argument("--grid-cols", type=int, metavar="N",
                        help="Parallel QR stream grid columns (default 1)")
    parser.add_argument("--grid-rows", type=int, metavar="N",
                        help="Parallel QR stream grid rows (default 1)")
    parser.add_argument("--grid-auto", action="store_true",
                        help="Auto-fit grid size to primary monitor")

    parser.add_argument("--save-qr", metavar="DIR",
                        help="Save QR images to directory and exit (no display)")
    parser.add_argument("--output-format", choices=["PNG", "JPEG", "BMP"],
                        help="Format for --save-qr (default: PNG)")

    parser.add_argument("--gui", action="store_true", help="Launch GUI mode")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")

    args = parser.parse_args()

    error_handler = QRLErrorHandler(
        log_callback=lambda msg: print(msg) if args.verbose else None
    )

    try:
        if args.create_config:
            ConfigManager.create_example_config(args.create_config)
            print(f"Example configuration file created: {args.create_config}")
            return

        if args.gui:
            from .gui import QRLServerGUI
            app = QRLServerGUI()
            app.run()
            return

        try:
            config = ConfigManager.load_config(args.config)
        except Exception as e:
            error_handler.log_error(e, "warning", "Configuration")
            config = ServerConfig()

        if args.chunk_size is not None:
            config.chunk_size = args.chunk_size
        if args.duration is not None:
            config.duration = args.duration
        if args.error_correction is not None:
            config.error_correction = args.error_correction
        if args.qr_version is not None:
            config.qr_version = args.qr_version
        if args.box_size is not None:
            config.qr_box_size = args.box_size
        if args.window_title is not None:
            config.window_title = args.window_title
        if args.output_format is not None:
            config.output_format = args.output_format
        if args.fullscreen:
            config.fullscreen = True
        if args.no_repeat:
            config.repeat = False
        if args.grid_cols is not None:
            config.qr_grid_cols = args.grid_cols
        if args.grid_rows is not None:
            config.qr_grid_rows = args.grid_rows
        if args.grid_auto:
            config.qr_grid_auto = True

        try:
            config.validate()
        except ValueError as e:
            print(f"Configuration error: {e}", file=sys.stderr)
            sys.exit(1)

        if args.save_config:
            try:
                ConfigManager.save_config(config, args.save_config)
                print(f"Configuration saved to: {args.save_config}")
                return
            except Exception as e:
                print(f"Error saving configuration: {e}", file=sys.stderr)
                sys.exit(1)

        if not args.file:
            parser.error(
                "file argument is required "
                "(unless using --gui, --create-config, or --save-config)"
            )

        src = Path(args.file)
        if not src.exists():
            print(f"Error: '{args.file}' not found", file=sys.stderr)
            sys.exit(1)

        # Grid layout
        grid_cols = config.qr_grid_cols
        grid_rows = config.qr_grid_rows
        use_grid = (grid_cols * grid_rows) > 1

        if config.qr_grid_auto:
            grid_cols, grid_rows = _auto_grid()
            use_grid = (grid_cols * grid_rows) > 1

        print(f"QRL Server")
        print(f"  Source          : {src}{'  (folder -> tar)' if src.is_dir() else ''}")
        print(f"  Chunk size      : {config.chunk_size} B")
        print(f"  Error correction: {config.error_correction}")
        print(f"  QR version      : {config.qr_version or 'auto'}")
        print(f"  Duration        : {config.duration} s  ({1/config.duration:.0f} fps)")
        print(f"  Grid            : {grid_cols}x{grid_rows}  ({grid_cols*grid_rows} stream{'s' if grid_cols*grid_rows != 1 else ''})")
        print(f"  Repeat          : {'yes' if config.repeat else 'no'}")

        if use_grid:
            from .parallel_encoder import ParallelQREncoder
            encoder = ParallelQREncoder(
                str(src),
                num_streams=grid_cols * grid_rows,
                chunk_size=config.chunk_size,
                error_correction=config.error_correction,
                box_size=config.qr_box_size,
                border=config.qr_border,
                qr_version=config.qr_version,
            )
            print("\nPreparing parallel streams...")
            encoder.prepare_parallel_streams()
            total = encoder.get_total_chunks()
            if encoder._compressed:
                ratio = encoder._original_size / max(len(encoder._data), 1)
                print(f"  Compressed {encoder._original_size:,} -> {len(encoder._data):,} bytes  ({ratio:.1f}x)")
            else:
                print(f"  Skipping compression (data wouldn't shrink)")
            streams = grid_cols * grid_rows
            bps = (config.chunk_size * streams) / max(config.duration, 1e-6)
            print(f"  {total:,} chunks/stream  |  ~{bps/1024:.1f} KB/s throughput")

            if args.save_qr:
                out_dir = Path(args.save_qr)
                out_dir.mkdir(parents=True, exist_ok=True)
                print(f"\nSaving {total * streams} QR images to {out_dir} ...")
                for i in range(total):
                    qr_set = encoder.generate_qr_set(i)
                    for s, img in enumerate(qr_set):
                        img.save(out_dir / f"qr_{i:04d}_s{s:02d}.png")
                    if (i + 1) % 50 == 0 or i + 1 == total:
                        print(f"  {i+1}/{total} sets")
                print("Done.")
                return

            print("\nStarting display  (Esc: close | F11: fullscreen)...")
            _run_display_grid(encoder, total, grid_cols, grid_rows, config)
        else:
            from .encoder import QRLEncoder
            encoder = QRLEncoder(
                str(src),
                chunk_size=config.chunk_size,
                qr_version=config.qr_version,
                error_correction=config.error_correction,
                box_size=config.qr_box_size,
                border=config.qr_border,
            )

            if not encoder.validate():
                raise ValidationError(f"File validation failed: {src}")

            print("\nPreparing chunks...")
            total = encoder.prepare_chunks()

            orig = encoder._original_size
            wire = len(encoder._data)
            if encoder._compressed:
                print(f"  Compressed {orig:,} -> {wire:,} bytes  ({orig/wire:.1f}x ratio)")
            else:
                print(f"  Skipping compression (data wouldn't shrink)")

            bps = config.chunk_size / max(config.duration, 1e-6)
            print(f"  {total:,} chunks ready  |  ~{bps/1024:.1f} KB/s throughput")

            if args.save_qr:
                out_dir = Path(args.save_qr)
                out_dir.mkdir(parents=True, exist_ok=True)
                print(f"\nSaving {total} QR images to {out_dir} ...")
                for i in range(total):
                    img = encoder.generate_qr_for_chunk(i)
                    img.save(out_dir / f"qr_{i:04d}.png")
                    if (i + 1) % 50 == 0 or i + 1 == total:
                        print(f"  {i+1}/{total}")
                print("Done.")
                return

            print("\nStarting display  (Esc: close | F11: fullscreen)...")
            _run_display(encoder, total, config)

    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
    except QRLError as e:
        print(f"\nQRL Error: {e}", file=sys.stderr)
        if args.verbose and e.details:
            print(f"Details: {e.details}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error_handler.log_error(e, "critical", "Main")
        print(f"\nError: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _auto_grid() -> tuple:
    """Compute (cols, rows) to fill the primary monitor at ~400 px/QR."""
    try:
        from qrl_client.monitors import primary_monitor
        mon = primary_monitor()
        if mon is None:
            return 1, 1
        QR_TARGET = 400
        spacing = 8
        margin = 24
        usable_w = max(mon.width - margin, QR_TARGET)
        usable_h = max(mon.height - margin, QR_TARGET)
        cols = max(1, (usable_w + spacing) // (QR_TARGET + spacing))
        rows = max(1, (usable_h + spacing) // (QR_TARGET + spacing))
        print(f"  Auto-grid: {cols}x{rows} for {mon.width}x{mon.height} monitor")
        return int(cols), int(rows)
    except Exception as e:
        print(f"  Auto-grid failed ({e}), using 1x1")
        return 1, 1


def _resize_to_clean_multiple(qr_img, target_px: int, box_size: int):
    """Resize QR image keeping every module the same pixel width."""
    from PIL import Image
    native = qr_img.size[0]
    if native == 0:
        return qr_img
    module_count = max(1, native // max(box_size, 1))
    per_module = target_px // module_count
    new_size = per_module * module_count
    if new_size <= 0 or new_size > target_px:
        return qr_img.resize((target_px, target_px), Image.Resampling.BILINEAR)
    if new_size < target_px * 0.85:
        return qr_img.resize((target_px, target_px), Image.Resampling.BILINEAR)
    if new_size == native:
        return qr_img
    return qr_img.resize((new_size, new_size), Image.Resampling.NEAREST)


def _compose_grid(qr_images, cols: int, rows: int, target_w: int, target_h: int,
                  box_size: int):
    """Compose QR images into a cols×rows grid scaled to fit target_w×target_h."""
    from PIL import Image
    spacing = 8
    per_w = max((target_w - spacing * (cols - 1)) // cols, 64)
    per_h = max((target_h - spacing * (rows - 1)) // rows, 64)
    per_qr = min(per_w, per_h)

    resized = [_resize_to_clean_multiple(img, per_qr, box_size) for img in qr_images]
    while len(resized) < cols * rows:
        resized.append(Image.new("RGB", (per_qr, per_qr), "white"))

    total_w = per_qr * cols + spacing * (cols - 1)
    total_h = per_qr * rows + spacing * (rows - 1)
    canvas = Image.new("RGB", (total_w, total_h), "white")
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            qr = resized[idx]
            ox = c * (per_qr + spacing) + (per_qr - qr.size[0]) // 2
            oy = r * (per_qr + spacing) + (per_qr - qr.size[1]) // 2
            canvas.paste(qr, (ox, oy))
    return canvas


def _fit_image(image, win_w: int, win_h: int):
    """Scale image to fit window, NEAREST for upscale, BICUBIC for downscale."""
    from PIL import Image
    iw, ih = image.size
    if iw == 0 or ih == 0:
        return image
    scale = min(win_w / iw, win_h / ih)
    if abs(scale - 1.0) <= 0.01:
        return image
    new_w = max(int(iw * scale), 1)
    new_h = max(int(ih * scale), 1)
    resample = Image.Resampling.NEAREST if scale > 1.0 else Image.Resampling.BICUBIC
    return image.resize((new_w, new_h), resample)


def _run_display(encoder, total: int, config: ServerConfig) -> None:
    """Single-stream display loop."""
    import tkinter as tk
    from PIL import ImageTk

    cache: _LRUDict = _LRUDict(_CACHE_MAX)

    def _get_qr(i: int):
        if i not in cache:
            cache[i] = encoder.generate_qr_for_chunk(i)
        return cache[i]

    manifest_qr = encoder.generate_manifest_qr()
    duration_ms = max(int(config.duration * 1000), 1)

    state = {"index": 0, "cycle": 0, "show_manifest": True}

    root = tk.Tk()
    root.title(config.window_title)
    root.configure(bg="black")
    if config.fullscreen:
        root.attributes("-fullscreen", True)
    root.bind("<Escape>", lambda _e: _on_escape(root))
    root.bind("<F11>", lambda _e: _toggle_fullscreen(root))
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    label = tk.Label(root, bg="black")
    label.pack(expand=True, fill=tk.BOTH)

    def _advance():
        import traceback as _tb
        stop = False
        try:
            if state["show_manifest"]:
                img = manifest_qr
                state["show_manifest"] = False
                title = f"{config.window_title}  ·  manifest"
            else:
                idx = state["index"]
                # Advance index BEFORE generation so a bad frame is skipped,
                # not retried forever.
                state["index"] = idx + 1
                if state["index"] >= total:
                    state["index"] = 0
                    state["cycle"] += 1
                    state["show_manifest"] = True
                    if not config.repeat:
                        stop = True

                try:
                    img = _get_qr(idx)
                except Exception as qr_err:
                    print(f"\n[frame {idx} skipped] {qr_err}", file=sys.stderr)
                    _tb.print_exc(file=sys.stderr)
                    # Don't update the display — just reschedule.
                    if stop:
                        root.destroy()
                    else:
                        root.after(duration_ms, _advance)
                    return

                title = f"{config.window_title}  ·  {idx + 1}/{total}"
                if state["cycle"]:
                    title += f"  (cycle {state['cycle'] + 1})"

            win_w = max(root.winfo_width(), 200)
            win_h = max(root.winfo_height(), 200)
            img = _fit_image(img, win_w, win_h)
            photo = ImageTk.PhotoImage(img)
            label.configure(image=photo)
            label.image = photo
            root.title(title)
        except Exception as e:
            print(f"\n[display error] {e}", file=sys.stderr)
            _tb.print_exc(file=sys.stderr)

        if stop:
            root.destroy()
        else:
            root.after(duration_ms, _advance)

    _advance()
    try:
        root.mainloop()
    except Exception:
        pass


def _run_display_grid(encoder, total: int, cols: int, rows: int,
                      config: ServerConfig) -> None:
    """Multi-stream grid display loop using ParallelQREncoder."""
    import tkinter as tk
    from PIL import ImageTk

    qr_set_cache: _LRUDict = _LRUDict(_CACHE_MAX)
    manifest_qr = encoder.generate_manifest_qr()
    duration_ms = max(int(config.duration * 1000), 1)

    state = {"index": 0, "cycle": 0, "show_manifest": True}

    root = tk.Tk()
    root.title(config.window_title)
    root.configure(bg="black")
    if config.fullscreen:
        root.attributes("-fullscreen", True)
    root.bind("<Escape>", lambda _e: _on_escape(root))
    root.bind("<F11>", lambda _e: _toggle_fullscreen(root))
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    label = tk.Label(root, bg="black")
    label.pack(expand=True, fill=tk.BOTH)

    def _get_qr_set(i: int):
        if i not in qr_set_cache:
            qr_set_cache[i] = encoder.generate_qr_set(i)
        return qr_set_cache[i]

    def _advance():
        import traceback as _tb
        stop = False
        try:
            win_w = max(root.winfo_width(), 400)
            win_h = max(root.winfo_height(), 400)

            if state["show_manifest"]:
                img = _fit_image(manifest_qr, win_w, win_h)
                title = f"{config.window_title}  ·  manifest"
                state["show_manifest"] = False
            else:
                idx = state["index"]
                state["index"] = idx + 1
                if state["index"] >= total:
                    state["index"] = 0
                    state["cycle"] += 1
                    state["show_manifest"] = True
                    if not config.repeat:
                        stop = True

                try:
                    qr_images = _get_qr_set(idx)
                except Exception as qr_err:
                    print(f"\n[frame {idx} skipped] {qr_err}", file=sys.stderr)
                    _tb.print_exc(file=sys.stderr)
                    if stop:
                        root.destroy()
                    else:
                        root.after(duration_ms, _advance)
                    return

                img = _compose_grid(qr_images, cols, rows, win_w, win_h, config.qr_box_size)
                title = f"{config.window_title}  ·  {idx + 1}/{total}  ·  {cols}×{rows}"
                if state["cycle"]:
                    title += f"  (cycle {state['cycle'] + 1})"

            photo = ImageTk.PhotoImage(img)
            label.configure(image=photo)
            label.image = photo
            root.title(title)
        except Exception as e:
            print(f"\n[display error] {e}", file=sys.stderr)
            _tb.print_exc(file=sys.stderr)

        if stop:
            root.destroy()
        else:
            root.after(duration_ms, _advance)

    _advance()
    try:
        root.mainloop()
    except Exception:
        pass


def _on_escape(root) -> None:
    import tkinter as tk
    try:
        if root.attributes("-fullscreen"):
            root.attributes("-fullscreen", False)
        else:
            root.destroy()
    except tk.TclError:
        pass


def _toggle_fullscreen(root) -> None:
    try:
        root.attributes("-fullscreen", not root.attributes("-fullscreen"))
    except Exception:
        pass


if __name__ == "__main__":
    main()
