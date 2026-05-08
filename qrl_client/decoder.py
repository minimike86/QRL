"""
QRL Client Decoder

Reconstructs files from streamed QR captures. Handles single-stream and
parallel-stream encodings uniformly via the shared 9-byte wire header
defined in qrl_server.chunk.

If the stream's manifest declares is_directory=True, the decoded payload
(a tar archive built by ChunkManager.read_directory) is automatically
extracted into output_dir/<filename>/.
"""

import io
import json
import tarfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Shared wire format with the server. Both packages ship together.
from qrl_server.chunk import (
    HEADER_SIZE,  # noqa: F401
    MANIFEST_STREAM_ID,
    decompress,
    parse_manifest_payload,
    unpack_header,
)

from .qr_reader import QRReader


class QRLDecoder:
    """Decodes QR sequences back into files.

    `output_path` may be either:
      * a file path  — output is always written there (legacy mode)
      * a directory  — output filename is read from the stream's manifest
                       (or "decoded.bin" if no manifest is seen)
    """

    def __init__(self, output_path: str, timeout: int = 300, preprocess: bool = True):
        self.output_path = output_path
        self.timeout = timeout
        self.start_time = time.time()
        self.last_chunk_time = time.time()
        self._processed_frames = 0
        self._successful_reads = 0

        self.reader = QRReader(preprocess=preprocess)
        # streams: {stream_id: {sequence: data_bytes}}
        self._streams: Dict[int, Dict[int, bytes]] = {}
        # totals[stream_id] = expected number of chunks in that stream
        self._totals: Dict[int, int] = {}

        # Running counters — kept in sync by _consume_qr_payload so that
        # get_progress() and get_statistics() are O(1) instead of O(chunks).
        self._received_chunks: int = 0   # unique chunks stored so far
        self._total_chunks: int = 0      # sum of all known _totals values
        self._bytes_received: int = 0    # raw bytes stored so far

        # Manifest received from a stream_id=255 chunk (if any)
        self._manifest: Optional[dict] = None
        # Final resolved output path (only known after manifest seen, if applicable)
        self._resolved_output_path: Optional[str] = None

        self._started_at: Optional[float] = None
        self._frames_processed = 0
        self._qrs_decoded_total = 0
        self._unique_chunks = 0
        self._completed = False

    # ------------------------------------------------------------------
    # Decode entry point
    # ------------------------------------------------------------------
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
        parsed = unpack_header(payload)
        if parsed is None:
            return
        stream_id, sequence, total, data = parsed

        # Manifest channel — extract metadata, don't store as data
        if stream_id == MANIFEST_STREAM_ID:
            if self._manifest is None:
                try:
                    self._manifest = parse_manifest_payload(data)
                except Exception:
                    pass  # ignore malformed manifest
            return

        # Update running total counter when a stream reports a new (or changed) total.
        old_total = self._totals.get(stream_id, 0)
        if total != old_total:
            self._total_chunks += total - old_total
            self._totals[stream_id] = total

        bucket = self._streams.setdefault(stream_id, {})
        if sequence not in bucket:
            self._received_chunks += 1
            self._unique_chunks += 1
            self._bytes_received += len(data)
            self.last_chunk_time = time.time()
        bucket[sequence] = data
        self._qrs_decoded_total += 1

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------
    def is_complete(self) -> bool:
        if not self._totals:
            return False
        # Fast path: running counters let us short-circuit without iterating streams.
        if self._received_chunks < self._total_chunks:
            return False
        # Slow path: verify per-stream in case totals are uneven across streams.
        for stream_id, total in self._totals.items():
            if len(self._streams.get(stream_id, {})) < total:
                return False
        # If manifest declared more streams than we've received, wait for them.
        if self._manifest is not None:
            expected_streams = self._manifest.get("num_streams", 0)
            if expected_streams and len(self._totals) < expected_streams:
                return False
        return True

    def get_manifest(self) -> Optional[dict]:
        """Returns the parsed manifest dict if one has been seen, else None."""
        return self._manifest

    def resolve_output_path(self) -> str:
        """Pick the actual output path, honoring the manifest filename when
        the configured output_path is a directory."""
        if self._resolved_output_path is not None:
            return self._resolved_output_path

        out = Path(self.output_path)
        treat_as_dir = out.is_dir() or (not out.exists() and out.suffix == "")
        if treat_as_dir:
            filename = (self._manifest or {}).get("filename") if self._manifest else None
            if not filename:
                filename = "decoded.bin"
            filename = Path(filename).name
            self._resolved_output_path = str(out / filename)
        else:
            self._resolved_output_path = str(out)
        return self._resolved_output_path

    def get_progress(self) -> dict:
        """O(1) — uses running counters maintained by _consume_qr_payload."""
        total = self._total_chunks
        decoded = self._received_chunks
        percentage = (decoded / total * 100.0) if total > 0 else 0.0
        return {
            "percentage": percentage,
            "decoded_chunks": decoded,
            "total_chunks": total,
            "streams": len(self._totals),
            "complete": self._completed,
        }

    def get_missing_chunks(self) -> List[Tuple[int, int]]:
        """Returns a list of (stream_id, sequence) for chunks not yet received."""
        missing: List[Tuple[int, int]] = []
        for stream_id, total in self._totals.items():
            received = self._streams.get(stream_id, {})
            for seq in range(total):
                if seq not in received:
                    missing.append((stream_id, seq))
        return missing

    def get_statistics(self) -> dict:
        """O(1) — uses running counters; keys are a superset of what both
        the CLI and GUI expect."""
        elapsed = (time.time() - self._started_at) if self._started_at else 0.0
        elapsed = max(elapsed, 1e-3)
        time_since_last = time.time() - self.last_chunk_time

        progress = self.get_progress()
        return {
            # Core counters
            "total_frames_processed": self._frames_processed,
            "qr_read_success_rate": self.reader.get_success_rate(),
            "qrs_decoded": self._qrs_decoded_total,
            "successful_qr_reads": self._qrs_decoded_total,
            "unique_chunks": self._unique_chunks,
            "elapsed_time": elapsed,
            "bytes_received": self._bytes_received,
            "bytes_per_second": self._bytes_received / elapsed,
            # Convenience aliases used by the CLI
            "completion_percentage": progress["percentage"],
            "time_since_last_chunk": time_since_last,
        }

    def save_partial_progress(self) -> None:
        """Persist current decoding progress next to the output path."""
        progress_path = Path(str(self.output_path) + ".progress.json")
        progress = {
            "totals": {str(k): v for k, v in self._totals.items()},
            "received_per_stream": {
                str(sid): sorted(seqs.keys()) for sid, seqs in self._streams.items()
            },
            "frames_processed": self._frames_processed,
            "elapsed_time": (time.time() - self._started_at) if self._started_at else 0.0,
        }
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps(progress, indent=2))

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    def _write_output(self) -> None:
        # Concatenate streams in stream_id order (matches ParallelQREncoder layout).
        parts: List[bytes] = []
        for stream_id in sorted(self._totals):
            chunks = self._streams[stream_id]
            for seq in range(self._totals[stream_id]):
                parts.append(chunks[seq])
        data = b"".join(parts)

        # Manifest tells us the wire size — strip stream-padding if present.
        if self._manifest is not None:
            declared_size = self._manifest.get("size")
            if isinstance(declared_size, int) and 0 < declared_size <= len(data):
                data = data[:declared_size]

        # If the server compressed the data, decompress it now.
        if self._manifest is not None and self._manifest.get("compressed"):
            try:
                data = decompress(data)
            except Exception as e:
                self._decompress_error = str(e)

        # If the manifest declared this was a directory, the data is a tar
        # archive — extract it into the output folder.
        if (
            self._manifest is not None
            and self._manifest.get("is_directory")
            and Path(self.output_path).is_dir()
        ):
            target_dir = Path(self.output_path)
            target_dir.mkdir(parents=True, exist_ok=True)
            try:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r") as tar:
                    try:
                        tar.extractall(target_dir, filter="data")
                    except TypeError:
                        tar.extractall(target_dir)
                folder_name = self._manifest.get("filename", "decoded")
                self._resolved_output_path = str(target_dir / Path(folder_name).name)
                return
            except (tarfile.TarError, OSError) as e:
                self._extract_error = str(e)

        out = Path(self.resolve_output_path())
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
