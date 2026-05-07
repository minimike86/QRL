"""End-to-end test: server encodes a directory as tar, client extracts it."""

import tempfile
import unittest
from pathlib import Path

from qrl_client.decoder import QRLDecoder
from qrl_server.encoder import QRLEncoder


class TestDirectoryRoundTrip(unittest.TestCase):
    def test_directory_extracted_on_client(self):
        # Create a small source directory tree
        src_root = tempfile.mkdtemp()
        try:
            (Path(src_root) / "hello.txt").write_text("Hello, world!")
            (Path(src_root) / "numbers.bin").write_bytes(bytes(range(50)))
            sub = Path(src_root) / "sub"
            sub.mkdir()
            (sub / "nested.md").write_text("# Nested file")

            # Encode the directory
            encoder = QRLEncoder(src_root, chunk_size=200, error_correction="Q")
            encoder.encode()
            manifest_qr = encoder.generate_manifest_qr(num_streams=1)

            with tempfile.TemporaryDirectory() as out_dir:
                decoder = QRLDecoder(out_dir)
                # Feed manifest first, then data
                decoder.decode([manifest_qr.convert("RGB")])
                for img in encoder.get_qr_images():
                    decoder.decode([img.convert("RGB")])
                self.assertTrue(decoder.is_complete())

                manifest = decoder.get_manifest()
                self.assertIsNotNone(manifest)
                self.assertTrue(manifest["is_directory"])

                # Files should have been extracted under out_dir/<src folder>/
                src_name = Path(src_root).name
                extracted_root = Path(out_dir) / src_name
                self.assertTrue(extracted_root.is_dir(), "extracted dir missing")
                self.assertEqual(
                    (extracted_root / "hello.txt").read_text(), "Hello, world!"
                )
                self.assertEqual(
                    (extracted_root / "numbers.bin").read_bytes(), bytes(range(50))
                )
                self.assertEqual(
                    (extracted_root / "sub" / "nested.md").read_text(), "# Nested file"
                )
        finally:
            import shutil
            shutil.rmtree(src_root, ignore_errors=True)


class TestDirectoryEmptyRejected(unittest.TestCase):
    def test_empty_directory_invalid(self):
        with tempfile.TemporaryDirectory() as src:
            encoder = QRLEncoder(src, chunk_size=200)
            self.assertFalse(encoder.validate())


if __name__ == "__main__":
    unittest.main()
