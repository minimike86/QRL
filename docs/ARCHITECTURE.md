# Architecture

## Data flow

```
 SERVER                                        CLIENT
 ─────────────────────────────────────────     ─────────────────────────────────────────
 Source file / folder
       │
       ▼
 Auto-compress (gzip level 6)
 Skip if result ≥ 95% of raw size
       │
       ▼
 Split into N chunks (fixed chunk_size bytes)
       │
       ├── Single stream: one QR per frame
       └── Parallel: N streams, one QR per
           stream per frame (grid layout)
       │
       ▼
 Prepend 9-byte wire header to each chunk
       │
       ▼
 Encode chunk → QR image (PIL)
 Background prefetch + LRU cache
       │
       ▼
 Flash QR sequence on screen ─────────────►  Screen capture (mss, configurable interval)
 Manifest QR at start of every cycle              │
 Repeat until stopped                             ▼
                                            pyzbar decodes all visible QR codes per frame
                                                  │
                                                  ▼
                                            Strip 9-byte header, slot chunk into buffer
                                            Parse manifest on stream_id = 255
                                                  │
                                            All chunks received?
                                                  │
                                            ┌─────┴──────┐
                                            No           Yes
                                            │             │
                                            Wait          Decompress if flagged
                                            next frame    Extract tar if directory
                                                          Write file to output folder
```

---

## Wire format

Every QR payload begins with a fixed 9-byte header:

| Bytes | Field | Type | Notes |
|-------|-------|------|-------|
| 0 | `stream_id` | uint8 | 0–253 = data stream; **255 = manifest** |
| 1–4 | `sequence` | uint32 BE | Zero-based chunk index within this stream |
| 5–8 | `total_chunks` | uint32 BE | Total chunk count for this stream |

The header is followed immediately by the raw chunk payload (after compression, before base32 encoding).

---

## QR encoding

Raw bytes cannot be stored directly in the QR alphanumeric character set (A–Z, 0–9, and a handful of symbols). QRL uses a base32-strip encoding: every 5 raw bytes are mapped to 8 alphanumeric characters, giving a density of 5/8 bytes per character vs. 1 byte per character in binary mode. This is more space-efficient for the payload sizes QRL uses because the QR alphanumeric mode stores 2 characters per 11 bits rather than 1 byte per 8 bits.

Maximum payload per QR at version 40 (the largest):

| Error correction | Max raw bytes |
|-----------------|--------------|
| L | 2670 |
| Q | 1490 |
| H | 1140 |

---

## Manifest QR

`stream_id = 255` is reserved for the manifest. It is generated once per encode and displayed as the first QR of every display cycle so a late-joining client picks up the stream metadata before processing any data chunks.

Manifest body (UTF-8 JSON):

```json
{
  "v": 1,
  "filename": "report.tar",
  "size": 2097152,
  "original_size": 3145728,
  "compressed": true,
  "is_directory": true,
  "num_streams": 4,
  "total_chunks": 512,
  "chunk_size": 1490,
  "error_correction": "Q"
}
```

The client uses this to derive the output filename, detect whether decompression is needed, and know how many total chunks to expect across all streams.

---

## Compression

Compression runs automatically before chunking:

1. Gzip the source data at level 6 with `mtime = 0` (deterministic output).
2. If the compressed size is less than 95% of the original size, use the compressed bytes and set `compressed = true` in the manifest.
3. Otherwise discard the compressed bytes and send the original — this avoids overhead for already-compressed formats (JPEG, MP4, ZIP, etc.).
4. Payloads smaller than 256 bytes skip compression entirely (header overhead dominates).

The client decompresses transparently after reassembly when `compressed = true`.

---

## Background prefetch and LRU cache

QR images are rendered on demand rather than all at once before display starts, keeping "Prepare" nearly instant regardless of file size. A background thread fills an LRU cache of up to **4096 entries** ahead of the display position:

- For files with fewer than 4096 chunks the cache fills completely and every display frame is a cache hit.
- For larger files the prefetch thread stays within a **256-frame lookahead** window of the current display index. Old entries are evicted as new ones arrive; the display loop still gets a cache hit on every frame because prefetch stays ahead.

A monotonically-increasing generation counter (`_prefetch_gen`) cancels in-flight prefetch workers when the user starts a new encode or closes the window.

---

## Parallel streams

In parallel mode the source data is split into `N` independent sub-streams, each chunked and encoded separately. At each display tick one QR from each stream is shown simultaneously in an `cols × rows` grid. The client decodes all QR codes in the frame and routes each chunk to its stream buffer by `stream_id`.

Because each stream covers 1/N of the data, the effective throughput scales linearly with the number of streams — a 3×3 (9-stream) grid transfers roughly 9× the data per display cycle compared to single-stream mode at the same frame rate.

See [parallel-streams.md](parallel-streams.md) for throughput estimates and grid layout details.
