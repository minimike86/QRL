"""Tests for qrl_client.decoder.QRLDecoder."""

import tempfile
import unittest
from pathlib import Path

from qrl_client.decoder import QRLDecoder
from qrl_server.chunk import pack_header
from qrl_server.qr_generator import QRGenerator


class TestInit(unittest.TestCase):
    def test_stores_output_path_and_timeout(self):
        decoder = QRLDecoder("out.bin", timeout=120)
        self.assertEqual(decoder.output_path, "out.bin")
        self.assertEqual(decoder.timeout, 120)

    def test_default_timeout(self):
        decoder = QRLDecoder("out.bin")
        self.assertEqual(decoder.timeout, 300)


class TestEmptyState(unittest.TestCase):
    def test_decode_empty_frames_returns_false(self):
        d = QRLDecoder("out.bin")
        self.assertFalse(d.decode([]))

    def test_initial_progress_is_dict(self):
        d = QRLDecoder("out.bin")
        progress = d.get_progress()
        self.assertIsInstance(progress, dict)
        self.assertEqual(progress["percentage"], 0.0)
        self.assertEqual(progress["decoded_chunks"], 0)
        self.assertEqual(progress["total_chunks"], 0)

    def test_initial_state_not_complete(self):
        self.assertFalse(QRLDecoder("out.bin").is_complete())

    def test_initial_missing_chunks_is_list(self):
        self.assertEqual(QRLDecoder("out.bin").get_missing_chunks(), [])

    def test_initial_statistics_dict(self):
        stats = QRLDecoder("out.bin").get_statistics()
        self.assertIn("total_frames_processed", stats)
        self.assertIn("qr_read_success_rate", stats)
        self.assertIn("elapsed_time", stats)


class TestSyntheticPayloadConsumption(unittest.TestCase):
    """Drive the decoder via _consume_qr_payload to test wire-format handling
    without depending on screen capture / pyzbar round-trip."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        Path(self.path).unlink(missing_ok=True)
        Path(self.path + ".progress.json").unlink(missing_ok=True)

    def test_single_stream_round_trip(self):
        original = b"hello world this is a test payload"
        chunk_size = 8
        chunks = [original[i : i + chunk_size] for i in range(0, len(original), chunk_size)]
        total = len(chunks)

        decoder = QRLDecoder(self.path)
        for i, c in enumerate(chunks):
            decoder._consume_qr_payload(pack_header(0, i, total) + c)

        self.assertTrue(decoder.is_complete())
        decoder._write_output()
        self.assertEqual(Path(self.path).read_bytes(), original)

    def test_progress_reporting(self):
        decoder = QRLDecoder(self.path)
        decoder._consume_qr_payload(pack_header(0, 0, 4) + b"abc")
        decoder._consume_qr_payload(pack_header(0, 2, 4) + b"def")
        progress = decoder.get_progress()
        self.assertEqual(progress["total_chunks"], 4)
        self.assertEqual(progress["decoded_chunks"], 2)
        self.assertAlmostEqual(progress["percentage"], 50.0)

    def test_missing_chunks(self):
        decoder = QRLDecoder(self.path)
        decoder._consume_qr_payload(pack_header(0, 0, 3) + b"a")
        decoder._consume_qr_payload(pack_header(0, 2, 3) + b"c")
        missing = decoder.get_missing_chunks()
        self.assertEqual(missing, [(0, 1)])

    def test_duplicate_chunks_dont_inflate_count(self):
        decoder = QRLDecoder(self.path)
        decoder._consume_qr_payload(pack_header(0, 0, 2) + b"a")
        decoder._consume_qr_payload(pack_header(0, 0, 2) + b"a")  # duplicate
        progress = decoder.get_progress()
        self.assertEqual(progress["decoded_chunks"], 1)

    def test_parallel_streams_round_trip(self):
        decoder = QRLDecoder(self.path)
        # Stream 0: "hello" in 2 chunks of "hel" + "lo"
        decoder._consume_qr_payload(pack_header(0, 0, 2) + b"hel")
        decoder._consume_qr_payload(pack_header(0, 1, 2) + b"lo")
        # Stream 1: "world" in 1 chunk
        decoder._consume_qr_payload(pack_header(1, 0, 1) + b"world")
        self.assertTrue(decoder.is_complete())
        decoder._write_output()
        self.assertEqual(Path(self.path).read_bytes(), b"hello" + b"world")

    def test_save_partial_progress(self):
        decoder = QRLDecoder(self.path)
        decoder._consume_qr_payload(pack_header(0, 0, 3) + b"a")
        decoder.save_partial_progress()
        self.assertTrue(Path(self.path + ".progress.json").exists())

    def test_truncated_payload_ignored(self):
        decoder = QRLDecoder(self.path)
        decoder._consume_qr_payload(b"\x00\x01")  # too short for header
        self.assertEqual(decoder.get_progress()["decoded_chunks"], 0)


class TestDecodeViaImages(unittest.TestCase):
    """End-to-end round-trip: encode payload as QR images, then decode."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        self.tmp.close()
        self.path = self.tmp.name

    def tearDown(self):
        Path(self.path).unlink(missing_ok=True)

    def test_round_trip_through_pyzbar(self):
        from PIL import Image

        original = b"round-trip test data " * 5
        chunks = [original[i : i + 16] for i in range(0, len(original), 16)]
        total = len(chunks)
        qr_images: list = []
        for i, c in enumerate(chunks):
            payload = pack_header(0, i, total) + c
            qr_images.append(QRGenerator(payload, error_correction="Q").generate())

        decoder = QRLDecoder(self.path)
        # Simulate frames being captured one per QR
        for img in qr_images:
            decoder.decode([img.convert("RGB")])

        self.assertTrue(decoder.is_complete())
        self.assertEqual(Path(self.path).read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
