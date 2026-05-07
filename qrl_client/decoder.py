"""
QRL Client Decoder

Reconstructs files from streamed QR captures. Handles single-stream and
parallel-stream encodings uniformly via the shared 9-byte wire header
defined in qrl_server.chunk.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Shared wire format with the server. Both packages ship together.
from qrl_server.chunk import HEADER_SIZE, unpack_header  # noqa: F401

from .qr_reader import QRReader


class QRLDecoder:
    """Decodes QR sequences back into files."""

    def __init__(self, output_path: str, timeout: int = 300):
        self.output_path = output_path
        self.timeout = timeout

        self.reader = QRReader()
        # streams: {stream_id: {sequence: data_bytes}}
        self._streams: Dict[int, Dict[int, bytes]] = {}
        # totals[stream_id] = expected number of chunks in that stream
        self._totals: Dict[int, int] = {}

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
        # Same stream may be re-seen with same total — that's fine; mismatched totals
        # are protocol errors, but we tolerate them by trusting the latest.
        self._totals[stream_id] = total
        bucket = self._streams.setdefault(stream_id, {})
        if sequence not in bucket:
            self._unique_chunks += 1
        bucket[sequence] = data
        self._qrs_decoded_total += 1

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------
    def is_complete(self) -> bool:
        if not self._totals:
            return False
        for stream_id, total in self._totals.items():
            if len(self._streams.get(stream_id, {})) < total:
                return False
        return True

    def get_progress(self) -> dict:
        total = sum(self._totals.values()) if self._totals else 0
        decoded = sum(len(c) for c in self._streams.values())
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
        elapsed = (time.time() - self._started_at) if self._started_at else 0.0
        elapsed = max(elapsed, 1e-3)

        bytes_received = sum(
            sum(len(d) for d in chunks.values()) for chunks in self._streams.values()
        )

        return {
            "total_frames_processed": self._frames_processed,
            "qr_read_success_rate": self.reader.get_success_rate(),
            "qrs_decoded": self._qrs_decoded_total,
            "unique_chunks": self._unique_chunks,
            "elapsed_time": elapsed,
            "bytes_received": bytes_received,
            "bytes_per_second": bytes_received / elapsed,
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
        out = Path(self.output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
