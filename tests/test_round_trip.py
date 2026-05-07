"""End-to-end round-trip tests: server encodes a file, client decodes it.

This is the headline correctness test for QRL: prove the wire protocol
between QRLEncoder and QRLDecoder reconstructs the exact original bytes,
both for single-stream and parallel-stream encodings.
"""

import os
import tempfile
import unittest
from pathlib import Path

from qrl_client.decoder import QRLDecoder
from qrl_server.encoder import QRLEncoder
from qrl_server.parallel_encoder import ParallelQREncoder


class _TmpFiles:
    def __init__(self):
        self._paths = []

    def make(self, payload: bytes, suffix: str = ".bin") -> str:
        f = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=suffix)
        f.write(payload)
        f.close()
        self._paths.append(f.name)
        return f.name

    def cleanup(self):
        for p in self._paths:
            Path(p).unlink(missing_ok=True)


class TestSingleStreamRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = _TmpFiles()

    def tearDown(self):
        self.tmp.cleanup()

    def _round_trip(self, payload: bytes, chunk_size: int = 256, error_correction: str = "Q"):
        src = self.tmp.make(payload)
        out = self.tmp.make(b"")  # output target

        encoder = QRLEncoder(src, chunk_size=chunk_size, error_correction=error_correction)
        qr_images = encoder.encode()
        self.assertGreater(len(qr_images), 0)

        decoder = QRLDecoder(out)
        for img in qr_images:
            decoder.decode([img.convert("RGB")])

        self.assertTrue(decoder.is_complete(), "decoder did not complete")
        self.assertEqual(Path(out).read_bytes(), payload)

    def test_short_text(self):
        self._round_trip(b"Hello, QRL!")

    def test_binary_data(self):
        self._round_trip(bytes(range(256)) * 4, chunk_size=128)

    def test_random_payload(self):
        self._round_trip(os.urandom(2048), chunk_size=400, error_correction="L")

    def test_chunk_at_capacity_boundary(self):
        # Q-level cap is 1505 raw bytes; leave 9 for the wire-format header
        self._round_trip(os.urandom(3000), chunk_size=1490)


class TestParallelStreamRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = _TmpFiles()

    def tearDown(self):
        self.tmp.cleanup()

    def _round_trip(self, payload: bytes, num_streams: int, chunk_size: int = 400):
        src = self.tmp.make(payload)
        out = self.tmp.make(b"")

        encoder = ParallelQREncoder(
            src, num_streams=num_streams, chunk_size=chunk_size, error_correction="Q"
        )
        encoder.prepare_parallel_streams()
        total_sets = encoder.get_total_chunks()

        decoder = QRLDecoder(out)
        for set_idx in range(total_sets):
            grid = encoder.generate_qr_grid(set_idx)
            frames = []
            for row in grid:
                for img in row:
                    frames.append(img.convert("RGB"))
            decoder.decode(frames)

        self.assertTrue(decoder.is_complete(), "decoder did not complete parallel round-trip")
        self.assertEqual(Path(out).read_bytes(), payload)

    def test_4_streams(self):
        self._round_trip(os.urandom(2000), num_streams=4, chunk_size=300)

    def test_1_stream_via_parallel(self):
        self._round_trip(b"parallel-as-single-stream test " * 10, num_streams=1, chunk_size=200)


if __name__ == "__main__":
    unittest.main()
