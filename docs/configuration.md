# Configuration files

Both the server and client support YAML and JSON configuration files. Settings in a config file are overridden by CLI flags when both are present.

---

## Config file discovery

Files are searched in this order; the first one found is loaded:

**Server:**
```
./qrl_server.yaml
./qrl_server.yml
./qrl_server.json
./config/qrl_server.yaml
./config/qrl_server.yml
./config/qrl_server.json
~/.qrl/server_config.yaml
~/.qrl/server_config.yml
~/.qrl/server_config.json
```

**Client:**
```
./qrl_client.yaml
./qrl_client.yml
./qrl_client.json
./config/qrl_client.yaml
./config/qrl_client.yml
./config/qrl_client.json
~/.qrl/client_config.yaml
~/.qrl/client_config.yml
~/.qrl/client_config.json
```

Pass `--config <path>` to load a specific file instead.

---

## Server config reference

```yaml
# ── Chunking ──────────────────────────────────────────────────────────────────
chunk_size: 1490            # bytes per QR payload
                            # max depends on error_correction:
                            #   L → 2670  M → 2110  Q → 1490  H → 1140
error_correction: Q         # L | M | Q | H
compression_level: 6        # gzip level 1–9; 0 disables compression entirely

# ── Display ───────────────────────────────────────────────────────────────────
duration: 0.1               # seconds per frame  (0.033 ≈ 30 fps)
repeat: true                # loop the QR sequence until manually stopped

# ── QR rendering ──────────────────────────────────────────────────────────────
qr_box_size: 10             # pixels per QR module  (10 = standard, 16 = high, 24 = extra)
qr_border: 6                # quiet-zone width in modules
qr_grid_cols: 1             # display grid width  (cols × rows = parallel streams)
qr_grid_rows: 1             # display grid height (1×1 = single QR, 2×4 = 8 streams, etc.)
qr_grid_auto: false         # ignore cols/rows and fit as many cells as the screen allows

# ── Limits ────────────────────────────────────────────────────────────────────
max_file_size: 104857600    # 100 MB hard cap; raise for larger files
```

### Generating an example file

```bash
qrl-server --create-config config/server.yaml
```

### Saving the current CLI settings

```bash
qrl-server myfile.bin --chunk-size 1490 --duration 0.1 --save-config my_settings.yaml
```

---

## Client config reference

```yaml
# ── Capture ───────────────────────────────────────────────────────────────────
monitor: 0                  # monitor index (0 = primary, 1 = second, …)
interval: 0.05              # capture interval in seconds  (0.05 = 20 fps)
timeout: 86400              # give up after this many seconds  (default: 24 h)
region: null                # [x, y, width, height] bounding box, or null for full screen
                            # example: [100, 200, 1600, 900]

# ── Output ────────────────────────────────────────────────────────────────────
output_dir: null            # destination folder; null → ~/Downloads/qrl_received
```

### Generating an example file

```bash
qrl-client --create-config config/client.yaml
```

---

## Using a config file

```bash
# Server
qrl-server --config config/server.yaml myfile.bin

# Client
qrl-client --config config/client.yaml

# CLI flags override config values
qrl-server --config config/server.yaml --duration 0.033 myfile.bin
```

---

## Validation

Both config managers validate the loaded values and raise a descriptive error if any are out of range (e.g., `chunk_size` exceeds the maximum for the chosen `error_correction` level, or `monitor` is not a valid index). Validation runs before encoding or capture starts, not at load time.
