# QRL — QR Link

QRL transfers files across a screen boundary by encoding them as a flashing sequence of QR codes. The **server** chunks, compresses, and displays the codes; the **client** screen-captures and reassembles them into the original file.

No network connection, no clipboard, and no agent is needed on the receiving end — only a screen you can see. Typical scenarios: pulling a file out of a remote desktop session, VNC, Citrix, or any environment where the only shared channel is a rendered screen.

---

## Quick start

**Combined GUI — send and receive in one window:**
```bash
python qrl_gui.py
```

**Standalone GUIs:**
```bash
python -m qrl_server --gui   # encode and display
python -m qrl_client --gui   # capture and decode
```

**CLI:**
```bash
qrl-server myfile.bin                          # display with defaults
qrl-server myfile.bin --chunk-size 1490 --duration 0.1 --error-correction Q
qrl-client --output /tmp/received/             # capture to folder
```

---

## How it works

1. The server reads the source file (or tar-packs a folder), optionally gzips it, and splits it into fixed-size chunks.
2. Each chunk gets a 9-byte binary header and is rendered as a QR code.
3. A **manifest QR** is shown at the start of every display cycle carrying the filename, size, and stream metadata so a late-joining client can catch up.
4. The client captures the screen on a configurable interval, decodes every visible QR per frame, and writes the file when the last chunk arrives.

See [docs/architecture.md](docs/architecture.md) for the full wire format and data flow.

---

## Features at a glance

| Area | Feature |
|------|---------|
| Encoding | Auto gzip compression (skipped if it doesn't help) |
| Encoding | Folder support — tar-packed, auto-extracted on arrival |
| Display | Configurable FPS (2 / 10 / 20 / 30) and QR quality presets |
| Display | Parallel grid mode — 4, 9, 16, or auto-fit streams for multiplied throughput |
| Display | Background prefetch with a bounded LRU cache |
| Display | Export QR sequence as PDF or MP4 for offline replay |
| GUI | Drag-and-drop file loading (server tab) |
| Capture | Whole screen, specific monitor, or hand-drawn region |
| Capture | Live preview at 5 fps while decoding runs |
| Capture | Partial-progress save — resume an interrupted session |
| Config | YAML / JSON config files with auto-discovery search paths |

---

## Documentation

| File | Contents |
|------|---------|
| [docs/architecture.md](docs/architecture.md) | Wire format, data flow, compression, LRU cache, manifest |
| [docs/server.md](docs/server.md) | All server settings, speed/quality/density/mode presets, export |
| [docs/client.md](docs/client.md) | All client settings, region picker, monitor selection, progress |
| [docs/parallel-streams.md](docs/parallel-streams.md) | How parallel grid mode works, throughput estimates |
| [docs/configuration.md](docs/configuration.md) | Full config file reference and search path order |
| [docs/cli.md](docs/cli.md) | All CLI flags for `qrl-server` and `qrl-client` |

---

## Installation

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

- [QRxfil](https://github.com/OverkillGuy/qrxfil) — QR-code-based file transfer, outputs a static PDF.
- [QRExfil](https://github.com/Shell-Company/QRExfil) — QR code transfer with animated GIF output.
