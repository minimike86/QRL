# QRL — QR Link

QRL transfers files across a screen boundary by encoding them as a sequence of QR codes. The **web sender** encodes, chunks, and displays the codes in the browser; the **receiver** scans and reassembles — either via the web receiver (camera) or the Python client (screen capture).

No network connection, no clipboard, and no agent is needed on the receiving end — only a screen you can see. Typical scenarios: pulling a file out of a remote desktop session, VNC, Citrix, or any environment where the only shared channel is a rendered screen.

---

## Web version (recommended — no install)

`qrl_web/` is a browser-only implementation. Both sender and receiver run entirely in the browser — no Python, no build step.

**Live on GitHub Pages:**

| Page | URL |
|------|-----|
| Home | https://minimike86.github.io/QRL/qrl_web |
| Sender | https://minimike86.github.io/QRL/qrl_web/sender.html |
| Receiver | https://minimike86.github.io/QRL/qrl_web/receiver.html |

**Or serve locally:**
```bash
cd qrl_web
python -m http.server 8765
# open http://localhost:8765
```

The receiver requires HTTPS or `localhost` for camera access — GitHub Pages and the local server both satisfy this.

### Workflow

1. Open **Sender** on the source device and select a file or folder.
2. Configure settings (chunk size, FPS, error correction, QR size, fountain mode).
3. Press **Start Transfer** — a manifest QR appears first. Press **Resume** once the receiver is ready.
4. Open **Receiver** on the destination device and press **Start Camera**.
5. Point the camera at the sender's screen. The file downloads automatically when all chunks arrive.

### Sender settings

| Setting | Default | Description |
|---------|---------|-------------|
| Chunk size (B) | 600 | Payload bytes per QR frame. Smaller = more reliable; larger = fewer total frames. |
| FPS | 3 | Target frames per second. Increase in good lighting conditions. |
| Error correction | L | Reed-Solomon redundancy baked into each QR (L / M / Q / H). |
| QR size (px) | 420 | Rendered canvas size. Larger aids scanning from a distance. |
| Frames per chunk | 1 | Hold each chunk for N consecutive frames before advancing (sequential mode only). |
| Fountain mode | off | XOR-coded infinite packet stream — no replay needed (see below). |

### Fountain mode

When **Fountain mode** is on the sender generates an infinite stream of XOR-coded packets using LT codes. The receiver reconstructs the full file from any sufficient subset of packets via belief propagation — scanning can be intermittent without requiring a manual replay step.

The sender display shows `fountain pkt N` (packet counter), **CYCLES** (completed equivalent-sets), and a cycling progress bar showing position within the current cycle.

In sequential mode, the **Replay missing chunks** field lets you send only specific chunk numbers again by entering numbers, ranges, or comparisons (e.g. `3,7,5-10,>=50`).

---

## Python client (receive only)

The Python client captures the screen with `mss` and decodes QR codes with `pyzbar`. It is fully compatible with the web sender — same wire format, same manifest, same fountain protocol.

**GUI:**
```bash
python qrl_gui.py
# or
python -m qrl_client --gui
```

**CLI:**
```bash
qrl-client --output ~/received/
```

---

## How it works

1. The sender reads the source file (or zip-packs a folder), optionally gzips it, and splits it into fixed-size chunks.
2. Each chunk gets a 9-byte binary wire header and is encoded as a QR code in byte mode.
3. A **manifest QR** (stream_id = 255) is shown first, carrying the filename, size, chunk count, and transfer mode so a late-joining receiver can catch up.
4. **Sequential mode**: chunks cycle continuously until stopped. The receiver collects until the full set arrives, then auto-downloads.
5. **Fountain mode**: an infinite stream of XOR-coded packets (stream_id = 2) is generated. The receiver runs iterative belief-propagation decoding and finalises as soon as all source chunks are recovered.
6. The receiver decompresses and saves the file on completion.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full wire format, fountain coding details, and data flow.

---

## Features

| Area | Feature |
|------|---------|
| **Web sender** | Browser-only — no install, no Python |
| **Web sender** | Fountain mode: LT-code XOR packets, infinite stream, no replay needed |
| **Web sender** | Sequential mode with targeted missing-chunk replay |
| **Web sender** | Auto gzip compression (skipped when not beneficial) |
| **Web sender** | Folder support — packed as .zip, extracted on arrival |
| **Web sender** | Responsive two-column desktop layout and mobile-optimised UI |
| **Web sender** | Contextual setting hints and QR flash animation |
| **Web receiver** | Webcam-based scanning, chunk map, ETA, duplicate detection |
| **Web receiver** | Auto-download on completion |
| **Python client** | Screen capture via `mss` — no GUI required on remote end |
| **Python client** | Whole screen, specific monitor, or hand-drawn capture region |
| **Python client** | Live preview, partial-progress resume |
| Config | YAML / JSON config files for the Python client |

---

## Documentation

| File | Contents |
|------|---------|
| [qrl_web/](qrl_web/) | Browser sender + receiver source |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Wire format, fountain coding, data flow, compression |
| [docs/server.md](docs/server.md) | Web sender settings, workflow, and display panel |
| [docs/client.md](docs/client.md) | Python client settings, region picker, progress panel |
| [docs/configuration.md](docs/configuration.md) | Python client config file reference and search paths |
| [docs/cli.md](docs/cli.md) | `qrl-client` CLI flags |

---

## Installation (Python client)

```bash
git clone https://github.com/minimike86/QRL.git
cd QRL
pip install -e .
```

Requires Python 3.9+. On Windows, `pyzbar` needs the ZBar DLLs — `pip install pyzbar[scripts]` includes them.

---

## Running tests

```bash
pytest tests/
```

---

## Similar projects

- [txqr](https://github.com/divan/txqr)
- [QRxfil](https://github.com/OverkillGuy/qrxfil) 
- [QRExfil](https://github.com/Shell-Company/QRExfil)
- [qrterminal](https://github.com/mdp/qrterminal)
