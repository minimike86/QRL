"""Tests for qrl_server.parallel_encoder."""

import os
import tempfile
import unittest
from pathlib import Path

from qrl_server.parallel_encoder import ParallelQRDecoder, ParallelQREncoder


class TestParallelEncoderValidation(unittest.TestCase):
    def test_rejects_zero_or_negative_stream_count(self):
        with self.assertRaises(ValueError):
            ParallelQREncoder("anything", num_streams=0)
        with self.assertRaises(ValueError):
            ParallelQREncoder("anything", num_streams=-1)

    def test_rejects_above_reserved_manifest_id(self):
        # 255 is reserved for the manifest channel
        with self.assertRaises(ValueError):
            ParallelQREncoder("anything", num_streams=255)

    def test_accepts_arbitrary_stream_counts(self):
        # Non-square layouts (e.g. 10x5 = 50) are now allowed
        for n in (1, 3, 4, 7, 9, 16, 50, 100, 254):
            ParallelQREncoder("anything", num_streams=n)


class TestParallelEncoderRoundTrip(unittest.TestCase):
    """End-to-end: split via encoder, reassemble via parallel decoder."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        Path(self.path).unlink(missing_ok=True)

    def _round_trip(self, payload: bytes, num_streams: int, chunk_size: int):
        Path(self.path).write_bytes(payload)
        encoder = ParallelQREncoder(
            self.path, num_streams=num_streams, chunk_size=chunk_size, error_correction="Q"
        )
        encoder.prepare_parallel_streams()

        decoder = ParallelQRDecoder(num_streams=num_streams)
        for stream_id, chunks in encoder._stream_chunks.items():
            for chunk in chunks:
                decoder.add_qr_data(chunk)

        self.assertTrue(decoder.is_complete())
        self.assertEqual(decoder.reconstruct_data(), payload)

    def test_4_stream_round_trip(self):
        self._round_trip(os.urandom(2000), num_streams=4, chunk_size=300)

    def test_9_stream_round_trip(self):
        self._round_trip(os.urandom(3000), num_streams=9, chunk_size=300)


class TestParallelEncoderMetadata(unittest.TestCase):
    def test_metadata_keys_aligned_with_single_stream(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(b"x" * 500)
        tmp.close()
        try:
            encoder = ParallelQREncoder(tmp.name, num_streams=4, chunk_size=200)
            encoder.prepare_parallel_streams()
            meta = encoder.get_metadata()
            # GUI reads these keys; both single and parallel must provide them.
            self.assertIn("total_size", meta)
            self.assertIn("total_chunks", meta)
            self.assertIn("num_streams", meta)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class TestThroughputStats(unittest.TestCase):
    def test_calculates_speedup_factor_above_1_for_parallel(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(b"x" * 2000)
        tmp.close()
        try:
            encoder = ParallelQREncoder(tmp.name, num_streams=4, chunk_size=300)
            encoder.prepare_parallel_streams()
            stats = encoder.calculate_theoretical_throughput(display_duration=0.1)
            self.assertGreater(stats["speedup_factor"], 1.0)
            self.assertGreater(stats["bytes_per_second"], 0)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
