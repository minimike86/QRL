"""
QRL Client Decoder

Reconstructs files from streamed QR captures. Handles both transfer modes
produced by the qrl_web sender:

  Sequential (stream_id=0): chunks cycle 0…N-1; reassembled by concatenation.
  Fountain   (stream_id=2): infinite XOR-coded LT-code packets; reassembled
                            via iterative belief-propagation (peeling decoder).

The manifest (stream_id=255) carries filename, size, and mode metadata.
Directories arrive as a .zip archive (web sender) or .tar archive (legacy).
"""

import gzip
import io
import json
import struct
import tarfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .qr_reader import QRReader

# ── Wire format ───────────────────────────────────────────────────────────────
HEADER_SIZE = 9
MANIFEST_STREAM_ID = 255
FOUNTAIN_STREAM_ID = 2


def _unpack_header(payload: bytes) -> Optional[Tuple[int, int, int, bytes]]:
    """Return (stream_id, sequence, total_chunks, data) or None if too short."""
    if len(payload) < HEADER_SIZE:
        return None
    stream_id = payload[0]
    sequence = struct.unpack_from(">I", payload, 1)[0]
    total_chunks = struct.unpack_from(">I", payload, 5)[0]
    return stream_id, sequence, total_chunks, payload[HEADER_SIZE:]


def _decompress(data: bytes) -> bytes:
    return gzip.decompress(data)


# ── Fountain coding (LT code) — must match qrl_web sender.js exactly ─────────

def _lcg_next(s: int) -> Tuple[float, int]:
    """One step of the seeded LCG. Returns (float in [0,1), next state)."""
    s = (1664525 * s + 1013904223) & 0xFFFFFFFF
    return s / 4294967296.0, s


def _choose_degree(s: int, N: int) -> Tuple[int, int]:
    """Draw degree from the LT distribution. Returns (degree, new_state)."""
    if N == 1:
        return 1, s
    r, s = _lcg_next(s)
    if r < 0.50:
        return 1, s
    if r < 0.75:
        return min(2, N), s
    if r < 0.90:
        return min(3, N), s
    # High-degree branch — consumes a second RNG call (same as JS).
    r2, s = _lcg_next(s)
    degree = 3 + int(-(-r2 * max(min(N - 3, 5), 0) // 1))  # equivalent to Math.ceil
    return min(N, degree), s


def _choose_indices(s: int, N: int, degree: int) -> Tuple[List[int], int]:
    """Draw `degree` distinct indices in [0, N). Returns (sorted list, new_state)."""
    idxs: Set[int] = set()
    while len(idxs) < min(degree, N):
        r, s = _lcg_next(s)
        idxs.add(int(r * N))
    return sorted(idxs), s


def _derive_packet(seed: int, N: int) -> List[int]:
    """Return the source-chunk indices XOR'd together to form packet `seed`."""
    s = seed & 0xFFFFFFFF
    degree, s = _choose_degree(s, N)
    indices, _ = _choose_indices(s, N, degree)
    return indices


def _xor_into(dst: bytearray, src: bytes) -> None:
    for i in range(min(len(dst), len(src))):
        dst[i] ^= src[i]


# ── Decoder ───────────────────────────────────────────────────────────────────

class QRLDecoder:
    """Decodes QR sequences back into files.

    `output_path` may be:
      * a file path  — output written there directly
      * a directory  — output filename taken from the manifest
    """

    def __init__(self, output_path: str, timeout: int = 300, preprocess: bool = True):
        self.output_path = output_path
        self.timeout = timeout
        self.start_time = time.time()
        self.last_chunk_time = time.time()

        self.reader = QRReader(preprocess=preprocess)

        # ── Sequential state ──────────────────────────────────────────────────
        # streams[stream_id][sequence] = payload bytes
        self._streams: Dict[int, Dict[int, bytes]] = {}
        self._totals: Dict[int, int] = {}

        # ── Fountain state ────────────────────────────────────────────────────
        # source_recovered[chunk_index] = zero-padded chunk bytes
        self._source_recovered: Dict[int, bytearray] = {}
        # Pending packets where >1 source chunk is still unknown
        self._fountain_packets: List[Dict] = []
        self._seen_seeds: Set[int] = set()

        # ── Running counters (O(1) progress queries) ──────────────────────────
        self._frames_processed: int = 0
        self._qrs_decoded_total: int = 0
        self._unique_chunks: int = 0
        self._received_chunks: int = 0
        self._total_chunks: int = 0
        self._bytes_received: int = 0

        # ── Manifest + status ─────────────────────────────────────────────────
        self._manifest: Optional[dict] = None
        self._resolved_output_path: Optional[str] = None
        self._started_at: Optional[float] = None
        self._completed: bool = False

    # ── Decode entry point ────────────────────────────────────────────────────

    def decode(self, frames: List) -> bool:
        """Process frames; returns True when the output file is fully written."""
        if not frames:
            return self._completed

        if self._started_at is None:
            self._started_at = time.time()

        for frame in frames:
            if frame is None:
                continue
            self._frames_processed += 1
            for raw in self.reader.read_multiple(frame):
                self._consume_qr_payload(bytes(raw))

        if self.is_complete() and not self._completed:
            self._write_output()
            self._completed = True
        return self._completed

    def _consume_qr_payload(self, payload: bytes) -> None:
        parsed = _unpack_header(payload)
        if parsed is None:
            return
        stream_id, sequence, total_chunks, data = parsed

        # ── Manifest ──────────────────────────────────────────────────────────
        if stream_id == MANIFEST_STREAM_ID:
            if self._manifest is None:
                try:
                    self._manifest = json.loads(data.decode("utf-8"))
                    expected = self._manifest.get("total_chunks", 0)
                    if not self._manifest.get("fountain"):
                        self._total_chunks = expected
                except Exception:
                    pass
            return

        # ── Fountain packet (stream_id == 2) ──────────────────────────────────
        if stream_id == FOUNTAIN_STREAM_ID:
            seed = sequence
            if seed in self._seen_seeds:
                self._qrs_decoded_total += 1
                return
            self._seen_seeds.add(seed)
            N = total_chunks
            indices = _derive_packet(seed, N)
            self._add_fountain_packet(indices, bytearray(data))
            self._qrs_decoded_total += 1
            self.last_chunk_time = time.time()
            return

        # ── Sequential chunk (stream_id == 0, or legacy multi-stream) ────────
        old_total = self._totals.get(stream_id, 0)
        if total_chunks != old_total:
            self._total_chunks += total_chunks - old_total
            self._totals[stream_id] = total_chunks

        bucket = self._streams.setdefault(stream_id, {})
        if sequence not in bucket:
            self._received_chunks += 1
            self._unique_chunks += 1
            self._bytes_received += len(data)
            self.last_chunk_time = time.time()
        bucket[sequence] = data
        self._qrs_decoded_total += 1

    # ── Fountain belief-propagation decoder ───────────────────────────────────

    def _add_fountain_packet(self, all_indices: List[int], payload: bytearray) -> None:
        """Integrate one fountain packet into the decoder."""
        pending: List[int] = []
        for idx in all_indices:
            recovered = self._source_recovered.get(idx)
            if recovered is not None:
                _xor_into(payload, recovered)
            else:
                pending.append(idx)

        if not pending:
            return
        if len(pending) == 1:
            self._recover_source_chunk(pending[0], payload)
            return
        self._fountain_packets.append({"indices": pending, "payload": payload})

    def _recover_source_chunk(self, start_idx: int, start_payload: bytearray) -> None:
        """Recover a source chunk and propagate through pending packets."""
        queue: List[Tuple[int, bytearray]] = [(start_idx, start_payload)]
        while queue:
            idx, pl = queue.pop(0)
            if idx in self._source_recovered:
                continue
            self._source_recovered[idx] = pl
            self._unique_chunks += 1
            self._bytes_received += len(pl)

            remaining = []
            for pkt in self._fountain_packets:
                if idx not in pkt["indices"]:
                    remaining.append(pkt)
                    continue
                _xor_into(pkt["payload"], pl)
                pkt["indices"].remove(idx)
                if len(pkt["indices"]) == 1:
                    queue.append((pkt["indices"][0], pkt["payload"]))
                elif len(pkt["indices"]) > 1:
                    remaining.append(pkt)
            self._fountain_packets = remaining

    # ── Completion ────────────────────────────────────────────────────────────

    def is_complete(self) -> bool:
        if self._manifest is None:
            return False

        if self._manifest.get("fountain"):
            expected = self._manifest.get("total_chunks", 0)
            return expected > 0 and len(self._source_recovered) >= expected

        # Sequential: all streams fully received
        if not self._totals:
            return False
        if self._received_chunks < self._total_chunks:
            return False
        for stream_id, total in self._totals.items():
            if len(self._streams.get(stream_id, {})) < total:
                return False
        expected_streams = self._manifest.get("num_streams", 0)
        if expected_streams and len(self._totals) < expected_streams:
            return False
        return True

    # ── Progress / statistics ─────────────────────────────────────────────────

    def get_manifest(self) -> Optional[dict]:
        return self._manifest

    def resolve_output_path(self) -> str:
        if self._resolved_output_path is not None:
            return self._resolved_output_path
        out = Path(self.output_path)
        treat_as_dir = out.is_dir() or (not out.exists() and out.suffix == "")
        if treat_as_dir:
            filename = (self._manifest or {}).get("filename") or "decoded.bin"
            self._resolved_output_path = str(out / Path(filename).name)
        else:
            self._resolved_output_path = str(out)
        return self._resolved_output_path

    def get_progress(self) -> dict:
        if self._manifest and self._manifest.get("fountain"):
            expected = self._manifest.get("total_chunks", 0)
            decoded = len(self._source_recovered)
            pct = (decoded / expected * 100.0) if expected > 0 else 0.0
            return {
                "percentage": pct,
                "decoded_chunks": decoded,
                "total_chunks": expected,
                "streams": 1,
                "complete": self._completed,
            }
        total = self._total_chunks
        decoded = self._received_chunks
        pct = (decoded / total * 100.0) if total > 0 else 0.0
        return {
            "percentage": pct,
            "decoded_chunks": decoded,
            "total_chunks": total,
            "streams": len(self._totals),
            "complete": self._completed,
        }

    def get_missing_chunks(self) -> List[Tuple[int, int]]:
        """Returns (stream_id, sequence) pairs not yet received (sequential only)."""
        missing: List[Tuple[int, int]] = []
        for stream_id, total in self._totals.items():
            received = self._streams.get(stream_id, {})
            for seq in range(total):
                if seq not in received:
                    missing.append((stream_id, seq))
        return missing

    def get_statistics(self) -> dict:
        elapsed = max((time.time() - self._started_at) if self._started_at else 0.0, 1e-3)
        progress = self.get_progress()
        return {
            "total_frames_processed": self._frames_processed,
            "qr_read_success_rate": self.reader.get_success_rate(),
            "qrs_decoded": self._qrs_decoded_total,
            "successful_qr_reads": self._qrs_decoded_total,
            "unique_chunks": self._unique_chunks,
            "elapsed_time": elapsed,
            "bytes_received": self._bytes_received,
            "bytes_per_second": self._bytes_received / elapsed,
            "completion_percentage": progress["percentage"],
            "time_since_last_chunk": time.time() - self.last_chunk_time,
        }

    def save_partial_progress(self) -> None:
        progress_path = Path(str(self.output_path) + ".progress.json")
        progress = {
            "totals": {str(k): v for k, v in self._totals.items()},
            "received_per_stream": {
                str(sid): sorted(seqs.keys()) for sid, seqs in self._streams.items()
            },
            "fountain_recovered": sorted(self._source_recovered.keys()),
            "frames_processed": self._frames_processed,
            "elapsed_time": (time.time() - self._started_at) if self._started_at else 0.0,
        }
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps(progress, indent=2))

    # ── Output ────────────────────────────────────────────────────────────────

    def _write_output(self) -> None:
        data = self._reassemble()
        if data is None:
            return

        if self._manifest and self._manifest.get("compressed"):
            try:
                data = _decompress(data)
            except Exception as e:
                self._decompress_error = str(e)

        if self._manifest and self._manifest.get("is_directory"):
            self._extract_directory(data)
            return

        out = Path(self.resolve_output_path())
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)

    def _reassemble(self) -> Optional[bytes]:
        """Build the raw (possibly still compressed) byte stream."""
        if self._manifest and self._manifest.get("fountain"):
            return self._reassemble_fountain()
        return self._reassemble_sequential()

    def _reassemble_fountain(self) -> Optional[bytes]:
        """Concatenate zero-padded source chunks, trim to manifest.size."""
        N = self._manifest.get("total_chunks", 0)
        chunk_size = self._manifest.get("chunk_size", 0)
        total_bytes = self._manifest.get("size", 0)
        if not (N and chunk_size and total_bytes):
            return None

        result = bytearray(total_bytes)
        offset = 0
        for i in range(N):
            chunk = self._source_recovered.get(i)
            if chunk is None:
                return None
            actual = min(chunk_size, total_bytes - offset)
            result[offset:offset + actual] = chunk[:actual]
            offset += actual
        return bytes(result)

    def _reassemble_sequential(self) -> Optional[bytes]:
        """Concatenate variable-length sequential payloads in stream/sequence order."""
        parts: List[bytes] = []
        for stream_id in sorted(self._totals):
            chunks = self._streams[stream_id]
            for seq in range(self._totals[stream_id]):
                parts.append(chunks[seq])
        data = b"".join(parts)

        if self._manifest is not None:
            declared_size = self._manifest.get("size")
            if isinstance(declared_size, int) and 0 < declared_size <= len(data):
                data = data[:declared_size]
        return data

    def _extract_directory(self, data: bytes) -> None:
        """Extract a zip (web sender) or tar (legacy) directory archive."""
        out_dir = Path(self.output_path) if Path(self.output_path).is_dir() else Path(self.output_path).parent
        out_dir.mkdir(parents=True, exist_ok=True)

        # Try zip first (web sender packs folders as .zip via JSZip).
        if zipfile.is_zipfile(io.BytesIO(data)):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    zf.extractall(out_dir)
                folder = self._manifest.get("filename", "decoded")
                self._resolved_output_path = str(out_dir / Path(folder).stem)
                return
            except (zipfile.BadZipFile, OSError):
                pass

        # Fallback: tar archive (Python legacy sender).
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
                try:
                    tar.extractall(out_dir, filter="data")
                except TypeError:
                    tar.extractall(out_dir)
            folder = self._manifest.get("filename", "decoded")
            self._resolved_output_path = str(out_dir / Path(folder).name)
        except (tarfile.TarError, OSError) as e:
            self._extract_error = str(e)
