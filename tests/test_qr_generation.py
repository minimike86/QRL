"""Tests for qrl_server.qr_generator.QRGenerator."""

import unittest

from qrl_server.qr_generator import QRGenerator


class TestCapacityHelpers(unittest.TestCase):
    def test_max_chunk_size_known_levels(self):
        # Binary mode (byte mode) capacities at version 40, per ISO/IEC 18004.
        self.assertEqual(QRGenerator.get_max_chunk_size("L"), 2953)
        self.assertEqual(QRGenerator.get_max_chunk_size("M"), 2331)
        self.assertEqual(QRGenerator.get_max_chunk_size("Q"), 1663)
        self.assertEqual(QRGenerator.get_max_chunk_size("H"), 1273)

    def test_max_chunk_size_unknown_level_falls_back(self):
        self.assertEqual(QRGenerator.get_max_chunk_size("Z"), 900)

    def test_capacity_ordering_by_error_level(self):
        levels = ["L", "M", "Q", "H"]
        sizes = [QRGenerator.get_max_chunk_size(lvl) for lvl in levels]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_validate_chunk_size_within_limit(self):
        self.assertTrue(QRGenerator.validate_chunk_size(500, "Q"))
        self.assertTrue(QRGenerator.validate_chunk_size(1663, "Q"))

    def test_validate_chunk_size_exceeds_limit(self):
        self.assertFalse(QRGenerator.validate_chunk_size(1664, "Q"))
        self.assertFalse(QRGenerator.validate_chunk_size(5000, "H"))


class TestInit(unittest.TestCase):
    def test_accepts_valid_error_correction(self):
        for lvl in ("L", "M", "Q", "H"):
            gen = QRGenerator(b"data", error_correction=lvl)
            self.assertEqual(gen.error_correction, lvl)

    def test_rejects_invalid_error_correction(self):
        with self.assertRaises(ValueError):
            QRGenerator(b"data", error_correction="X")

    def test_stores_data_and_version(self):
        gen = QRGenerator(b"payload", version=5, error_correction="M")
        self.assertEqual(gen.data, b"payload")
        self.assertEqual(gen.version, 5)


class TestGenerate(unittest.TestCase):
    def test_returns_pil_image(self):
        gen = QRGenerator(b"hello", error_correction="Q")
        img = gen.generate()
        self.assertTrue(hasattr(img, "save"))
        self.assertTrue(hasattr(img, "size"))
        self.assertGreater(img.size[0], 0)
        self.assertGreater(img.size[1], 0)


class TestGetCapacity(unittest.TestCase):
    def test_returns_positive_int(self):
        cap = QRGenerator.get_capacity(40)
        self.assertIsInstance(cap, int)
        self.assertGreater(cap, 0)


if __name__ == "__main__":
    unittest.main()
