"""Tests for qrl_server.encoder.QRLEncoder."""

import tempfile
import unittest
from pathlib import Path

from qrl_server.encoder import QRLEncoder


class _TmpFileMixin:
    def _make_file(self, payload: bytes) -> str:
        f = tempfile.NamedTemporaryFile(mode="wb", delete=False)
        f.write(payload)
        f.close()
        self._tmp_paths.append(f.name)
        return f.name

    def setUp(self):
        self._tmp_paths = []

    def tearDown(self):
        for p in self._tmp_paths:
            Path(p).unlink(missing_ok=True)


class TestValidate(_TmpFileMixin, unittest.TestCase):
    def test_valid_file(self):
        path = self._make_file(b"hello")
        encoder = QRLEncoder(Path(path), chunk_size=10)
        self.assertTrue(encoder.validate())

    def test_missing_file(self):
        encoder = QRLEncoder(Path("does_not_exist.bin"), chunk_size=10)
        self.assertFalse(encoder.validate())

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            encoder = QRLEncoder(Path(tmp), chunk_size=10)
            self.assertFalse(encoder.validate())

    def test_directory_with_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "file.txt").write_bytes(b"data")
            encoder = QRLEncoder(Path(tmp), chunk_size=10)
            self.assertTrue(encoder.validate())


class TestPrepareChunks(_TmpFileMixin, unittest.TestCase):
    def test_returns_chunk_count(self):
        path = self._make_file(b"x" * 1500)
        encoder = QRLEncoder(Path(path), chunk_size=500)
        n = encoder.prepare_chunks()
        self.assertGreater(n, 0)
        self.assertEqual(n, encoder.get_total_chunks())

    def test_no_qr_images_after_prepare(self):
        path = self._make_file(b"x" * 200)
        encoder = QRLEncoder(Path(path), chunk_size=100)
        encoder.prepare_chunks()
        self.assertIsNone(encoder.get_qr_images())

    def test_empty_file_raises(self):
        path = self._make_file(b"")
        encoder = QRLEncoder(Path(path), chunk_size=100)
        with self.assertRaises(ValueError):
            encoder.prepare_chunks()

    def test_invalid_path_raises(self):
        encoder = QRLEncoder(Path("does_not_exist.bin"), chunk_size=100)
        with self.assertRaises(ValueError):
            encoder.prepare_chunks()


class TestGenerateQrForChunk(_TmpFileMixin, unittest.TestCase):
    def test_generate_first_and_last(self):
        path = self._make_file(b"y" * 1500)
        encoder = QRLEncoder(Path(path), chunk_size=500, error_correction="Q")
        n = encoder.prepare_chunks()
        first = encoder.generate_qr_for_chunk(0)
        last = encoder.generate_qr_for_chunk(n - 1)
        self.assertTrue(hasattr(first, "save"))
        self.assertTrue(hasattr(last, "save"))

    def test_invalid_chunk_index_raises(self):
        path = self._make_file(b"y" * 200)
        encoder = QRLEncoder(Path(path), chunk_size=100)
        n = encoder.prepare_chunks()
        with self.assertRaises(ValueError):
            encoder.generate_qr_for_chunk(n)

    def test_oversized_chunk_for_error_level_raises(self):
        path = self._make_file(b"z" * 5000)
        encoder = QRLEncoder(Path(path), chunk_size=2000, error_correction="Q")
        with self.assertRaises(ValueError):
            encoder.prepare_chunks()

    def test_requires_prepare_first(self):
        path = self._make_file(b"y" * 200)
        encoder = QRLEncoder(Path(path), chunk_size=100)
        with self.assertRaises(ValueError):
            encoder.generate_qr_for_chunk(0)


class TestSaveQrImages(_TmpFileMixin, unittest.TestCase):
    def test_raises_when_no_images(self):
        path = self._make_file(b"y" * 100)
        encoder = QRLEncoder(Path(path), chunk_size=50)
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaises(ValueError):
                encoder.save_qr_images(out)


if __name__ == "__main__":
    unittest.main()
