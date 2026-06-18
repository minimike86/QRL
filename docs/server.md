# Web Sender

The web sender encodes a file or folder into a sequence of QR codes and displays them in the browser at a configurable frame rate. No installation required.

**Open at:** https://minimike86.github.io/QRL/qrl_web/sender.html  
**Or locally:** `cd qrl_web && python -m http.server 8765` → http://localhost:8765/sender.html

---

## Workflow

1. **Select a file or folder** using the file or folder picker buttons.
2. **Adjust settings** as needed (see below). The ETA estimate updates live.
3. **Press Start Transfer.** The manifest QR appears first and the sender auto-pauses.
4. **Open the receiver** on the destination device and start its camera.
5. **Press Resume** on the sender when the receiver is ready. QR codes begin cycling.
6. The receiver auto-downloads the file when the transfer completes.

In sequential mode, if the receiver reports missing chunks, enter them in the **Replay missing chunks** field and press **Replay** to re-transmit only those chunks.

---

## Settings

### Chunk size (bytes)

Payload bytes per QR frame. Default: **600 B**.

- Smaller values produce more reliable, lower-density QR codes that are easier to scan.
- Larger values reduce the total number of frames (faster transfers in ideal conditions).
- Recommended range: 400–800 B. Reduce if codes fail to scan consistently.

### FPS

Target frames per second. Default: **3**.

- Higher FPS transfers faster but the receiver camera must keep up.
- 3–5 fps is reliable in most lighting; increase only in good conditions.
- The sender displays actual FPS alongside the target.

### Error correction

Reed-Solomon redundancy baked into each QR code. Default: **L**.

| Level | Redundancy | Notes |
|-------|-----------|-------|
| L | 7% | Maximum payload capacity. Use in clean, direct lighting. |
| M | 15% | Light noise tolerance. |
| Q | 25% | Good for compressed remote desktop streams. |
| H | 30% | Maximum robustness. Use when scanning through heavy compression. |

Higher levels recover from more scan noise but reduce usable payload per frame, increasing chunk count.

### QR size (px)

Rendered canvas size in pixels. Default: **420 px**.

- Larger codes are easier to scan from a distance or through a low-resolution camera.
- 420–600 px suits most setups. Increase if the receiver struggles to focus.

### Frames per chunk

How many consecutive frames each chunk is held before advancing. Default: **1** (sequential mode only).

- Set to 2–3 if the receiver is missing many chunks at your configured FPS.
- ETA scales proportionally with this setting.

### Fountain mode

When enabled, the sender generates an **infinite stream of XOR-coded packets** (LT codes) instead of cycling through sequential chunks. Default: **off**.

**Use fountain mode when:**
- Scanning is intermittent or unreliable.
- You want hands-off operation with no replay step.
- The receiver may join late.

**Sequential mode** is preferable when the transfer environment is stable and you want predictable chunk-by-chunk progress with a clear completion point.

See [ARCHITECTURE.md](ARCHITECTURE.md#fountain-coding) for the technical details.

---

## Display panel

The right-hand panel shows the current QR code alongside live statistics:

| Stat | Description |
|------|-------------|
| **FRAME** | Current chunk number (sequential) or packet number (fountain) |
| **TOTAL CHUNKS** | Total source chunks N |
| **CYCLES** | Sequential: full loops completed. Fountain: equivalent packet-sets sent. |
| **ACTUAL FPS** | Measured frame rate |
| Progress bar | Sequential: position in current cycle. Fountain: position within current cycle (wraps). |
| Chunk label | `chunk N / total` (sequential) or `fountain pkt N` (fountain) |

The manifest frame is labelled **MANIFEST** and appears first. The sender pauses here automatically.

---

## Compression

Compression runs automatically before chunking:

- Files ≥ 256 bytes are gzip-compressed at level 6.
- If the result is ≥ 95% of the original size (e.g. already-compressed JPEG, ZIP, MP4), the original is sent uncompressed.
- The manifest records whether compression was applied; the receiver decompresses transparently.

---

## Folder transfers

Select a folder with **Select Folder**. The sender packs the entire directory into a `.zip` archive in memory before chunking. The web receiver downloads the `.zip`; the Python client unpacks it automatically.
