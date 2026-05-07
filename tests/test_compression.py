"""Tests for the auto-compression layer.

Server compresses with gzip before chunking IFF the result actually shrinks
the data (>=5% reduction). Client decompresses based on the manifest's
`compressed` flag.
"""

import os
import tempfile
import unittest
from pathlib import Path

from qrl_client.decoder import QRLDecoder
from qrl_server.chunk import maybe_compress, decompress
from qrl_server.encoder import QRLEncoder


class TestMaybeCompress(unittest.TestCase):
    def test_highly_compressible_data_shrinks(self):
        data = b"hello world\n" * 1000  # very compressible
        out, was = maybe_compress(data)
        self.assertTrue(was)
        self.assertLess(len(out), len(data))

    def test_random_bytes_skipped(self):
        # urandom is incompressible; gzip would actually grow it
        data = os.urandom(10000)
        out, was = maybe_compress(data)
        self.assertFalse(was)
        self.assertEqual(out, data)

    def test_tiny_payload_skipped(self):
        # gzip header is ~20 bytes; not worth it for short data
        out, was = maybe_compress(b"hi")
        self.assertFalse(was)
        self.assertEqual(out, b"hi")

    def test_decompress_inverse(self):
        data = b"This is a test string repeated. " * 100
        compressed, was = maybe_compress(data)
        self.assertTrue(was)
        self.assertEqual(decompress(compressed), data)


class TestEncoderCompressionFlags(unittest.TestCase):
    def test_text_file_compresses(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        tmp.write(b"# Repeating log line\n" * 500)
        tmp.close()
        try:
            enc = QRLEncoder(tmp.name, chunk_size=200)
            enc.prepare_chunks()
            manifest = enc.build_manifest()
            self.assertTrue(manifest["compressed"])
            self.assertLess(manifest["size"], manifest["original_size"])
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_random_file_does_not_compress(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(os.urandom(5000))
        tmp.close()
        try:
            enc = QRLEncoder(tmp.name, chunk_size=200)
            enc.prepare_chunks()
            manifest = enc.build_manifest()
            self.assertFalse(manifest["compressed"])
            self.assertEqual(manifest["size"], manifest["original_size"])
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class TestCompressedRoundTrip(unittest.TestCase):
    """End-to-end: encode compressible text → QR images → decode → original bytes."""

    def test_text_round_trip_via_compression(self):
        # Highly compressible payload — should be flagged compressed
        payload = (b"def hello():\n    print('world')\n" * 200)
        src = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
        src.write(payload)
        src.close()
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                enc = QRLEncoder(src.name, chunk_size=200, error_correction="Q")
                enc.encode()
                manifest_qr = enc.generate_manifest_qr(num_streams=1)
                self.assertTrue(enc._compressed)

                dec = QRLDecoder(out_dir)
                dec.decode([manifest_qr.convert("RGB")])
                for img in enc.get_qr_images():
                    dec.decode([img.convert("RGB")])
                self.assertTrue(dec.is_complete())

                manifest = dec.get_manifest()
                self.assertTrue(manifest["compressed"])
                self.assertEqual(manifest["original_size"], len(payload))

                out_path = Path(dec.resolve_output_path())
                self.assertTrue(out_path.exists())
                self.assertEqual(out_path.read_bytes(), payload)
        finally:
            Path(src.name).unlink(missing_ok=True)

    def test_random_round_trip_skips_compression(self):
        payload = os.urandom(2000)
        src = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        src.write(payload)
        src.close()
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                enc = QRLEncoder(src.name, chunk_size=400, error_correction="Q")
                enc.encode()
                manifest_qr = enc.generate_manifest_qr(num_streams=1)
                self.assertFalse(enc._compressed)

                dec = QRLDecoder(out_dir)
                dec.decode([manifest_qr.convert("RGB")])
                for img in enc.get_qr_images():
                    dec.decode([img.convert("RGB")])
                self.assertTrue(dec.is_complete())
                self.assertFalse(dec.get_manifest()["compressed"])

                out_path = Path(dec.resolve_output_path())
                self.assertEqual(out_path.read_bytes(), payload)
        finally:
            Path(src.name).unlink(missing_ok=True)


class TestBackwardsCompatNoCompressedFlag(unittest.TestCase):
    """Old streams (or hand-built ones) without 'compressed' in the manifest
    must still decode correctly — defaults to no decompression."""

    def test_missing_compressed_flag_treated_as_uncompressed(self):
        from qrl_server.chunk import build_manifest_chunk, pack_header

        with tempfile.TemporaryDirectory() as out_dir:
            dec = QRLDecoder(out_dir)
            # Manifest WITHOUT a `compressed` key
            dec._consume_qr_payload(
                build_manifest_chunk({"filename": "old.bin", "size": 5, "num_streams": 1})
            )
            dec._consume_qr_payload(pack_header(0, 0, 1) + b"hello")
            dec._write_output()
            self.assertEqual((Path(out_dir) / "old.bin").read_bytes(), b"hello")


if __name__ == "__main__":
    unittest.main()
