"""Tests for auto-grid sizing and non-square parallel encoder layouts."""

import os
import tempfile
import unittest
from pathlib import Path

from qrl_client.decoder import QRLDecoder
from qrl_server.gui import auto_grid_for_screen
from qrl_server.parallel_encoder import ParallelQREncoder


class TestAutoGridForScreen(unittest.TestCase):
    def test_1080p_with_240px_qrs(self):
        cols, rows = auto_grid_for_screen(1920, 1080, qr_target_px=240)
        # 7 cols × 4 rows = 28 QRs roughly fits a 1080p screen
        self.assertGreaterEqual(cols, 6)
        self.assertGreaterEqual(rows, 4)
        self.assertLessEqual(cols, 8)
        self.assertLessEqual(rows, 5)

    def test_1440p_with_240px_qrs(self):
        cols, rows = auto_grid_for_screen(2560, 1440, qr_target_px=240)
        self.assertGreaterEqual(cols, 9)
        self.assertGreaterEqual(rows, 5)

    def test_minimum_is_1x1(self):
        # Tiny screen still yields at least one QR
        cols, rows = auto_grid_for_screen(100, 100, qr_target_px=240)
        self.assertEqual((cols, rows), (1, 1))

    def test_larger_qr_target_means_fewer_cells(self):
        small = auto_grid_for_screen(1920, 1080, qr_target_px=200)
        big = auto_grid_for_screen(1920, 1080, qr_target_px=400)
        self.assertGreater(small[0] * small[1], big[0] * big[1])


class TestNonSquareParallelEncoder(unittest.TestCase):
    """Non-square stream counts (e.g. 6 = 2×3) are now supported."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        Path(self.path).unlink(missing_ok=True)

    def test_6_stream_round_trip(self):
        original = os.urandom(900)
        Path(self.path).write_bytes(original)
        with tempfile.TemporaryDirectory() as out_dir:
            encoder = ParallelQREncoder(
                self.path, num_streams=6, chunk_size=200, error_correction="Q"
            )
            encoder.prepare_parallel_streams()
            decoder = QRLDecoder(out_dir)
            for set_idx in range(encoder.get_total_chunks()):
                images = encoder.generate_qr_set(set_idx)
                decoder.decode([img.convert("RGB") for img in images])
            self.assertTrue(decoder.is_complete())
            decoder._write_output()
            written = Path(decoder.resolve_output_path()).read_bytes()
            self.assertEqual(written, original)

    def test_50_stream_count_accepted(self):
        # Was previously rejected — only 1/4/9/16 allowed
        ParallelQREncoder(self.path, num_streams=50, chunk_size=300)


if __name__ == "__main__":
    unittest.main()
