"""Tests for qrl_client.qr_reader.QRReader."""

import unittest

import numpy as np
from PIL import Image

from qrl_client.qr_reader import QRReader
from qrl_server.qr_generator import QRGenerator


def _make_qr_image(payload: bytes, error_correction: str = "Q") -> Image.Image:
    return QRGenerator(payload, error_correction=error_correction).generate()


class TestRead(unittest.TestCase):
    def test_reads_single_qr_from_pil(self):
        payload = b"hello world"
        img = _make_qr_image(payload)
        reader = QRReader()
        self.assertEqual(reader.read(img), payload)

    def test_reads_single_qr_from_numpy_bgr(self):
        payload = b"\x00\x01\x02\x03\xff\xfe"
        img = _make_qr_image(payload).convert("RGB")
        bgr = np.array(img)[:, :, ::-1].copy()  # RGB → BGR
        reader = QRReader()
        self.assertEqual(reader.read(bgr), payload)

    def test_returns_none_when_no_qr(self):
        blank = Image.new("RGB", (200, 200), "white")
        reader = QRReader()
        self.assertIsNone(reader.read(blank))


class TestReadMultiple(unittest.TestCase):
    def test_returns_list(self):
        img = _make_qr_image(b"x")
        reader = QRReader()
        results = reader.read_multiple(img)
        self.assertIsInstance(results, list)
        self.assertEqual(results, [b"x"])

    def test_empty_when_no_qr(self):
        blank = Image.new("RGB", (200, 200), "white")
        reader = QRReader()
        self.assertEqual(reader.read_multiple(blank), [])


class TestStatistics(unittest.TestCase):
    def test_success_rate_tracking(self):
        reader = QRReader()
        good = _make_qr_image(b"ok")
        blank = Image.new("RGB", (200, 200), "white")

        reader.read(good)
        reader.read(blank)
        reader.read(good)

        rate = reader.get_success_rate()
        self.assertAlmostEqual(rate, (2 / 3) * 100, places=1)

    def test_reset_statistics(self):
        reader = QRReader()
        reader.read(_make_qr_image(b"ok"))
        reader.reset_statistics()
        self.assertEqual(reader.get_success_rate(), 0.0)


if __name__ == "__main__":
    unittest.main()
