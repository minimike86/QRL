# Configuration files

The Python client supports YAML and JSON configuration files. Settings in a config file are overridden by CLI flags when both are present.

---

## Config file discovery

Files are searched in this order; the first one found is loaded:

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
# Use a saved config
qrl-client --config config/client.yaml

# CLI flags override config file values
qrl-client --config config/client.yaml --interval 0.033 --monitor 1
```

---

## Validation

The config manager validates all values before capture starts and raises a descriptive error if any are out of range (e.g. `monitor` is not a valid index, `interval` is non-positive). Validation runs at startup, not at load time.
