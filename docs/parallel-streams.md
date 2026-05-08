# Parallel streams

Parallel mode displays multiple independent QR codes simultaneously in a grid, with each cell carrying a separate slice of the data. The client decodes all cells in a single captured frame and routes each chunk to the correct stream buffer by `stream_id`.

---

## How the data is split

Given `N` streams and a source file of `total_bytes`:

1. The file is compressed (if it helps) producing `compressed_bytes`.
2. `compressed_bytes` are split evenly into `N` contiguous sub-streams, each of `ceil(compressed_bytes / N)` bytes.
3. Each sub-stream is then independently chunked at `chunk_size` bytes per chunk.
4. Each chunk gets a 9-byte header where `stream_id` identifies which sub-stream it belongs to (0 through N-1).

All streams have the same `total_chunks` (the maximum among them). Shorter streams pad with empty frames if needed, though in practice the last chunk of each stream simply carries fewer bytes.

---

## Grid layout

| Mode | Streams | Grid |
|------|---------|------|
| Single stream | 1 | 1×1 |
| 2×2 grid | 4 | 2×2 |
| 3×3 grid | 9 | 3×3 |
| 4×4 grid | 16 | 4×4 |
| Auto-fit | computed | fills monitor |

For perfect-square stream counts (4, 9, 16…) the grid is square. Non-square counts (e.g., 6) are laid out as a single row.

**Auto-fit** targets 400 px per QR cell and computes the largest grid that fits the current monitor:

```
cols = floor((monitor_width  - margin) / (400 + spacing))
rows = floor((monitor_height - margin) / (400 + spacing))
streams = cols × rows
```

This is recomputed at display start in case the server window has moved to a different monitor.

---

## Throughput estimates

Theoretical throughput = `chunk_size × streams / frame_interval`

| Quality | FPS | Streams | Chunk B | KB/s |
|---------|-----|---------|---------|------|
| Robust (H) | 10 | 1 | 1140 | ~11 |
| Balanced (Q) | 10 | 1 | 1490 | ~15 |
| Max (L) | 30 | 1 | 2670 | ~80 |
| Balanced (Q) | 20 | 4 | 1490 | ~116 |
| Balanced (Q) | 30 | 9 | 1490 | ~402 |
| Max (L) | 30 | 16 | 2670 | ~1280 |

These are upper bounds on a clean local screen. Actual throughput is determined by QR **read success rate** — the fraction of frames in which every QR in the grid is decoded correctly. One missed cell in a frame means that chunk must wait for the next cycle.

Factors that reduce read success rate:
- JPEG/H.264 compression in the remote desktop codec smearing module edges.
- Small QR size relative to display resolution.
- Misaligned capture interval (client slower than server frame rate).
- Motion blur from rapid display updates at high FPS.

Mitigation: use **High** (16 px/module) or **Extra** (24 px/module) pixel density to make each QR larger and more resistant to codec compression.

---

## Client-side handling

The client's decoder is stream-count-agnostic. It reads `stream_id` from every decoded chunk header and maintains one chunk buffer per stream. When a manifest QR (`stream_id = 255`) is received, the client learns `num_streams` and `total_chunks` and populates the expected buffer sizes. Completion is signalled when all streams have all their chunks.

Because chunks from different streams arrive interleaved (one of each per display tick), the client can make progress on all streams simultaneously and does not need to decode one stream at a time.
