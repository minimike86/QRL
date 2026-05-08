# Server

The server encodes a file or folder into a sequence of QR codes and flashes them on screen.

## Launching

```bash
# GUI
python -m qrl_server --gui

# Headless CLI
qrl-server myfile.bin
```

---

## GUI walkthrough

### 1. File or folder

Pick a source with the **File…** or **Folder…** buttons, or drag-and-drop onto the panel (requires `tkinterdnd2`).

- **File** — encoded as-is (after optional compression).
- **Folder** — recursively tar-archived first. The client detects the tar and extracts it into a subdirectory automatically.

The file size and type are shown below the picker.

---

### 2. Display speed

Controls how quickly frames advance. Faster sends more data per second but the client must be able to decode a QR within one frame interval.

| Preset | FPS | Frame interval |
|--------|-----|----------------|
| Slow | 2 | 500 ms |
| Balanced | 10 | 100 ms |
| Fast | 20 | 50 ms |
| Max | 30 | 33 ms |

The active preset is highlighted. Selecting a new preset takes effect on the next **Prepare**.

---

### 3. QR quality

Trades bytes per QR against resistance to scan errors. Higher error correction uses more redundancy, leaving less room for payload.

| Preset | Error correction | Chunk size | Use when… |
|--------|-----------------|------------|-----------|
| Maximum throughput | L | 2670 B | Clean local screen |
| Balanced | Q | 1490 B | General use |
| Robust | H | 1140 B | Compressed RDP/VNC stream |

---

### 4. Pixel density

Pixels rendered per QR module (the black/white cells). Higher density produces larger, crisper codes that pyzbar can lock onto even after codec compression.

| Preset | px / module | Native QR size (approx) |
|--------|------------|------------------------|
| Standard | 10 | ~370 px |
| High | 16 | ~590 px |
| Extra | 24 | ~885 px |

Use **High** or **Extra** when the client is reading through a remote desktop connection.

---

### 5. Throughput mode

Displays multiple independent QR streams simultaneously in a grid, multiplying throughput by the number of cells.

| Mode | Streams | Grid |
|------|---------|------|
| Single stream | 1 | 1×1 |
| 2×2 grid | 4 | 2×2 |
| 3×3 grid | 9 | 3×3 |
| 4×4 grid | 16 | 4×4 |
| Auto-fit screen | varies | fills monitor |

**Auto-fit** computes the largest grid where each QR is at least 400 px wide on the current monitor, recalculated at display start.

---

### 6. Prepare

Splits the file into chunks, initialises the encoder, and kicks off background QR prefetch. For most files this completes in under a second. The activity log shows compression ratio and chunk count.

---

### 7. Start display

Opens a dedicated fullscreen QR display window on the same monitor as the server GUI. A manifest QR appears first on every cycle; data QRs follow.

- **Esc** — close the display window.
- **F11** — toggle fullscreen.

The progress bar and cycle counter update live.

---

### 8. Stop

Stops the display loop and closes the QR window. The encoded data remains in memory; you can restart display without re-encoding.

---

### 9. Export

Available after **Prepare**.

- **Export PDF…** — saves all QR frames as a multi-page PDF (150 DPI). Useful for sharing the stream offline or printing.
- **Export video…** — saves as MP4 at the configured FPS using OpenCV. Requires `opencv-python` with a working `mp4v` codec.

---

## Settings summary panel

The right-hand panel shows a live one-line summary of the current settings:

```
myfile.bin  ·  4.23 MB  ·  1490 B/QR @ 10 FPS × 2×2 grid  →  ~58.2 KB/s
```

Stats grid shows **Chunks**, **Bytes / QR**, **Throughput**, and **Cycle** once display is running.

---

## Activity log

Timestamped log of every significant event — encoding completion, compression ratio, QR generation progress (logged at each 10% decile), and display errors. Use **Clear** to reset it, or watch it to confirm the prefetch thread is keeping up.
