# CLI reference

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
