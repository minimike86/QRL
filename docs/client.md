# Client

The Python client captures the screen on a configurable interval, decodes every visible QR code in each frame, and reassembles the chunks into the original file. It is fully compatible with the web sender — same wire format, same manifest, same fountain protocol.

## Launching

```bash
# GUI (recommended)
python qrl_gui.py
# or
python -m qrl_client --gui

# Headless CLI
qrl-client --output /path/to/folder/
```

---

## GUI walkthrough

### 1. Output folder

The destination folder for decoded files. Defaults to `~/Downloads/qrl_received` if not set.

The filename itself is determined by the **manifest QR** in the stream — the client reads the filename from the first QR code of each cycle and saves to `<output_folder>/<filename>`. You only need to choose the folder.

Once the manifest is received, the detected filename appears below the picker in the format:
```
📄  report.pdf  ·  4.2 KB
```

---

### 2. Capture region

Three options for what to capture:

- **Whole screen** — default. Scans the entire selected monitor.
- **Pick region…** — draws an interactive crosshair overlay on the screen. Click and drag to define a rectangle around the QR display area. The window minimises before the overlay appears and restores afterward. Press `Esc` to cancel.
- **Reset** — reverts to whole-screen capture.

Tighter regions are faster (fewer pixels to process per frame) and reduce false positives from unrelated QR codes on screen.

**Screen dropdown** — lists all physical monitors by name (e.g., `DELL U2723QE · 3840×2160`). Selects which monitor to capture when no custom region is set.

---

### 3. Capture speed

How often a frame is captured and passed to the QR decoder.

| Preset | FPS | Interval |
|--------|-----|----------|
| Slow | 5 | 200 ms |
| Balanced | 10 | 100 ms |
| Fast | 20 | 50 ms |
| Max | 30 | 33 ms |

Match this to the server's display speed or faster. If the client interval is longer than the server's frame interval, some unique QR frames will be missed and recovered on the next display cycle.

---

### 4. Start / Stop capture

**Start capture** begins the background capture thread. The live preview updates at 5 fps (independently of the capture rate) showing the raw captured frame.

**Stop** signals the capture thread to exit. Partial progress is written to a `.progress.json` sidecar file so a session can be resumed later.

**Save log…** dumps the activity log to a text file.

---

## Progress panel

Updated after every batch of frames:

| Stat | Description |
|------|-------------|
| **Frames** | Total frames captured and processed |
| **QR success** | Percentage of frames that contained at least one readable QR |
| **Chunks** | `decoded / total` |
| **ETA** | Estimated remaining time based on current rate |

The progress bar fills as chunks arrive. It resets if the stream has not yet sent a manifest (total unknown).

---

## Live preview

Shows the most recently captured frame, scaled to fit the preview panel at 5 fps. Use it to confirm the capture region is correct and the QR codes are visible and in focus. The info line shows the preview dimensions.

The preview runs on the main thread via `root.after` at a fixed 200 ms interval and does not compete with the capture/decode loop for CPU.

---

## Capture internals

- Frames are captured with `mss` (native Win32/X11/Cocoa screenshots, no Python copy).
- Captured as BGR numpy arrays and buffered in a thread-safe deque (default 120 frames).
- The decode loop drains the buffer in batches, calling `pyzbar.decode()` on each frame.
- Multiple QR codes per frame are supported — all decoded payloads from a single frame are processed before moving to the next.

---

## File assembly

- Each decoded payload is stripped of its 9-byte wire header.
- The chunk is stored in a dict keyed by `(stream_id, sequence)`.
- When all `total_chunks` chunks for a stream are present the stream is complete.
- If the manifest flagged `compressed = true`, the reassembled bytes are decompressed.
- If `is_directory = true`, the bytes are unpacked into `<output_folder>/<filename>/`.
- Otherwise the bytes are written directly to `<output_folder>/<filename>`.

The client handles both sequential (stream_id = 0) and fountain (stream_id = 2) packets transparently, routing by the `fountain` field in the manifest. See [ARCHITECTURE.md](ARCHITECTURE.md) for the wire format and fountain decoding algorithm.
