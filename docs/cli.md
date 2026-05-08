# CLI reference

## qrl-server

```
usage: qrl-server [-h] [--config FILE] [--save-config FILE] [--create-config FILE]
                  [--chunk-size N] [--error-correction {L,M,Q,H}] [--qr-version 1-40]
                  [--duration SECS] [--no-repeat] [--repeat]
                  [--window-title TITLE] [--fullscreen]
                  [--save-qr DIR] [--output-format {PNG,JPEG,BMP}]
                  [--gui] [--verbose]
                  [file]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `file` | — | Path to the file or directory to encode. Required unless using `--gui`, `--create-config`, or `--save-config`. |
| `--config FILE` | auto-discovered | Load settings from a YAML or JSON config file. |
| `--save-config FILE` | — | Write the resolved settings (config + CLI overrides) to a file and exit. |
| `--create-config FILE` | — | Write an annotated example config file and exit. |
| `--chunk-size N` | 1490 | Bytes per QR payload. Must not exceed the capacity for the chosen error-correction level. |
| `--error-correction` | Q | QR error correction level. `L` = max throughput, `H` = max robustness. |
| `--qr-version 1–40` | auto | Force a specific QR version. Auto-selects the smallest version that fits the chunk by default. |
| `--duration SECS` | 0.1 | Display time per frame in seconds (0.033 ≈ 30 fps). |
| `--no-repeat` | — | Display the sequence once and exit. |
| `--repeat` | — | Force repeat even if the config says otherwise. |
| `--window-title TITLE` | "QRL Server" | Title of the QR display window. |
| `--fullscreen` | false | Open the display window in fullscreen mode. |
| `--save-qr DIR` | — | Save each QR image to this directory as well as displaying it. |
| `--output-format` | PNG | Image format when `--save-qr` is used. |
| `--gui` | — | Launch the graphical interface. All other flags are ignored. |
| `--verbose` / `-v` | false | Print detailed progress to stdout. |

### Examples

```bash
# Fastest transfer on a clean local screen
qrl-server archive.zip --chunk-size 2670 --error-correction L --duration 0.033

# Robust transfer over a compressed RDP stream
qrl-server report.pdf --chunk-size 1140 --error-correction H --duration 0.1

# Send a whole folder
qrl-server ./project_src/

# Save QR images as PNG for offline use
qrl-server data.bin --save-qr ./qr_frames/ --output-format PNG

# Export the config you used for reproducibility
qrl-server data.bin --chunk-size 1490 --duration 0.05 --save-config run_settings.yaml
```

---

## qrl-client

```
usage: qrl-client [-h] [--config FILE] [--create-config FILE]
                  [--output DIR] [--monitor N] [--region X,Y,W,H]
                  [--interval SECS] [--timeout SECS]
                  [--gui] [--verbose]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--config FILE` | auto-discovered | Load settings from a YAML or JSON config file. |
| `--create-config FILE` | — | Write an annotated example config file and exit. |
| `--output DIR` | `~/Downloads/qrl_received` | Folder where decoded files are saved. Created if it does not exist. |
| `--monitor N` | 0 | Monitor index to capture (0 = primary). |
| `--region X,Y,W,H` | full screen | Capture only this screen rectangle. Coordinates are absolute screen pixels. |
| `--interval SECS` | 0.05 | How often to capture and decode a frame (0.05 = 20 fps). |
| `--timeout SECS` | 86400 | Stop after this many seconds even if decoding is incomplete. |
| `--gui` | — | Launch the graphical interface. All other flags are ignored. |
| `--verbose` / `-v` | false | Print detailed progress to stdout. |

### Examples

```bash
# Capture from the primary monitor at default settings
qrl-client --output ~/received/

# Capture a tight region around the QR display window for better performance
qrl-client --output ~/received/ --region 0,0,1920,1080

# Capture from a second monitor at 30 fps
qrl-client --output ~/received/ --monitor 1 --interval 0.033

# Long-running session with a 2-hour timeout
qrl-client --output ~/received/ --timeout 7200

# Use a saved config
qrl-client --config config/client.yaml
```
