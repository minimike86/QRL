# Architecture

## Data flow

```
 WEB SENDER (browser)                         RECEIVER
 ─────────────────────────────────────────    ──────────────────────────────────────────────
 Source file / folder
       │
       ▼
 Auto-compress (gzip level 6)
 Skip if result ≥ 95% of raw size
 Skip if payload < 256 bytes
       │
       ▼
 Split into N fixed-size chunks
       │
       ├── Sequential mode (stream_id 0)
       │     Chunks cycle 0…N-1 continuously
       │     Manifest re-shown at start of each cycle
       │
       └── Fountain mode (stream_id 2)
             Generate infinite XOR-coded packets
             Each packet = deterministic XOR of
             k source chunks (k chosen by degree
             distribution from seeded PRNG)
       │
       ▼
 Prepend 9-byte wire header to each frame
       │
       ▼
 Encode as byte-mode QR (qrcode.js)          ──► Web receiver: webcam → jsQR decode
 Flash on screen at configured FPS               Python client: mss capture → pyzbar decode
                                                       │
                                                       ▼
                                               Strip 9-byte header
                                               Route by stream_id:
                                                 255 → parse manifest
                                                   0 → sequential buffer[sequence]
                                                   2 → fountain decoder
                                                       │
                                               Sequential: all N chunks received?
                                               Fountain:   belief-propagation complete?
                                                       │
                                               ┌───────┴────────┐
                                               No               Yes
                                               │                 │
                                               Keep scanning     Decompress if flagged
                                                                 Unpack zip if directory
                                                                 Save / auto-download file
```

---

## Wire format

Every QR payload begins with a fixed 9-byte header:

| Bytes | Field | Type | Notes |
|-------|-------|------|-------|
| 0 | `stream_id` | uint8 | **0** = sequential chunk; **2** = fountain packet; **255** = manifest |
| 1–4 | `sequence` | uint32 BE | Sequential: zero-based chunk index. Fountain: packet seed value. |
| 5–8 | `total_chunks` | uint32 BE | Sequential: total chunk count. Fountain: total source chunk count N. |

The header is followed immediately by the raw chunk payload.

---

## QR encoding

The web sender uses `qrcode.js` with `mode: 'byte'`. Binary data is converted to a Latin-1 string via `String.fromCharCode` and passed to the library, which internally UTF-8 encodes the string into the QR byte stream.

The web receiver decodes with `jsQR`, which UTF-8 decodes byte-mode QR data into `code.data`. Each byte is recovered with `code.data.charCodeAt(k) & 0xFF`, which correctly round-trips all byte values 0–255 regardless of UTF-8 expansion.

The Python client decodes with `pyzbar`, which returns raw bytes directly — no encoding round-trip.

---

## Manifest QR

`stream_id = 255` is reserved for the manifest. It is shown as the first QR of every transfer and (in sequential mode) at the start of every display cycle, so a late-joining receiver picks up stream metadata before processing data frames.

The sender auto-pauses on the manifest QR and waits for the user to press **Resume**, giving the receiver time to scan it before data chunks begin.

Manifest body (UTF-8 JSON):

```json
{
  "v": 1,
  "filename": "report.pdf",
  "size": 2097152,
  "original_size": 3145728,
  "compressed": true,
  "is_directory": false,
  "num_streams": 1,
  "total_chunks": 512,
  "chunk_size": 600,
  "error_correction": "L",
  "fountain": false
}
```

| Field | Description |
|-------|-------------|
| `size` | Bytes of transferred data (post-compression if `compressed = true`) |
| `original_size` | Bytes of the original file before compression |
| `total_chunks` | Number of source chunks (sequential) or source chunks N (fountain) |
| `fountain` | `true` = fountain mode; `false` = sequential mode |

---

## Fountain coding

Fountain mode implements a simplified LT code:

### Packet generation (sender)

For each packet with seed `s`:

1. Initialise a seeded LCG: `s = (1664525 × s + 1013904223) mod 2³²`
2. Draw a degree `k` from the distribution:
   - 50% → k = 1
   - 25% → k = 2
   - 15% → k = 3
   - 10% → k = 3 + ⌈rng() × min(N−3, 5)⌉ (capped at N)
3. Draw k distinct source chunk indices uniformly at random (without replacement).
4. XOR the k zero-padded source chunks together to produce the packet payload.
5. Pack header: `[2][seed:4 BE][N:4 BE]` + XOR payload.

All source chunks are zero-padded to `chunk_size` bytes for XOR compatibility. The last chunk is trimmed to its true length using `manifest.size` during reassembly.

### Packet decoding (receiver)

The receiver runs iterative belief-propagation (peeling decoder):

1. For each received packet, cancel out any already-recovered source chunks by XOR.
2. If only one unknown source chunk remains → recover it immediately.
3. If multiple unknowns remain → store the packet for later.
4. Whenever a source chunk is recovered, revisit all stored packets: XOR the chunk away and check if any reduce to a single unknown.
5. Repeat until all N source chunks are recovered or no further progress is possible.

Both sender and receiver use the same LCG with identical call order (`chooseDegree` then `chooseIndices`), so the same seed always produces the same set of XOR indices.

---

## Compression

Compression runs automatically before chunking:

1. Gzip the source data at level 6.
2. If the compressed size is less than 95% of the original, use the compressed bytes and set `compressed = true` in the manifest.
3. Otherwise send the original — avoids overhead for already-compressed formats (JPEG, MP4, ZIP, etc.).
4. Payloads smaller than 256 bytes skip compression entirely.

The receiver decompresses transparently after reassembly when `compressed = true`.

---

## Folder transfer

Folders are packed as a `.zip` archive (web sender using JSZip) before chunking. The manifest carries the zip filename. The web receiver auto-downloads the `.zip`; the Python client unpacks it into a subdirectory in the output folder when `is_directory = true`.
