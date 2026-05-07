"""End-to-end manifest tests.

Verifies that:
  * Server emits a manifest QR with filename / size / num_streams
  * Client parses it and uses it to resolve the output filename
  * Decoder writes the file to `output_dir/<manifest filename>`
"""

import os
import tempfile
import unittest
from pathlib import Path

from qrl_client.decoder import QRLDecoder
from qrl_server.chunk import (
    MANIFEST_STREAM_ID,
    build_manifest_chunk,
    parse_manifest_payload,
    unpack_header,
)
from qrl_server.encoder import QRLEncoder
from qrl_server.parallel_encoder import ParallelQREncoder


class TestManifestWireFormat(unittest.TestCase):
    def test_manifest_chunk_round_trip(self):
        manifest = {"filename": "report.pdf", "size": 12345, "num_streams": 4}
        payload = build_manifest_chunk(manifest)
        parsed = unpack_header(payload)
        self.assertIsNotNone(parsed)
        stream_id, sequence, total, body = parsed
        self.assertEqual(stream_id, MANIFEST_STREAM_ID)
        self.assertEqual(sequence, 0)
        self.assertEqual(total, 1)
        self.assertEqual(parse_manifest_payload(body), manifest)


class TestEncoderManifest(unittest.TestCase):
    def test_single_stream_encoder_builds_manifest(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(b"hello manifest world " * 30)
        tmp.close()
        try:
            encoder = QRLEncoder(tmp.name, chunk_size=120, error_correction="Q")
            encoder.prepare_chunks()
            manifest = encoder.build_manifest(num_streams=1)
            self.assertEqual(manifest["filename"], Path(tmp.name).name)
            self.assertGreater(manifest["size"], 0)
            self.assertEqual(manifest["num_streams"], 1)
            self.assertEqual(manifest["chunk_size"], 120)
            self.assertEqual(manifest["error_correction"], "Q")

            qr = encoder.generate_manifest_qr(num_streams=1)
            self.assertTrue(hasattr(qr, "save"))
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_parallel_encoder_builds_manifest(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(b"x" * 800)
        tmp.close()
        try:
            encoder = ParallelQREncoder(tmp.name, num_streams=4, chunk_size=200)
            encoder.prepare_parallel_streams()
            manifest = encoder.build_manifest()
            self.assertEqual(manifest["num_streams"], 4)
            self.assertEqual(manifest["filename"], Path(tmp.name).name)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class TestDecoderManifestRouting(unittest.TestCase):
    def test_output_dir_plus_manifest_filename(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            decoder = QRLDecoder(tmp_dir)  # directory as output_path
            # Inject manifest first, then data chunks
            from qrl_server.chunk import pack_header

            decoder._consume_qr_payload(
                build_manifest_chunk({"filename": "vacation.jpg", "size": 11, "num_streams": 1})
            )
            decoder._consume_qr_payload(pack_header(0, 0, 1) + b"hello world")

            self.assertTrue(decoder.is_complete())
            decoder._write_output()
            expected = Path(tmp_dir) / "vacation.jpg"
            self.assertTrue(expected.exists())
            self.assertEqual(expected.read_bytes(), b"hello world")

    def test_output_file_overrides_manifest(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = str(Path(tmp_dir) / "explicit_name.bin")
            decoder = QRLDecoder(target)
            from qrl_server.chunk import pack_header

            decoder._consume_qr_payload(
                build_manifest_chunk({"filename": "ignored.jpg", "size": 3, "num_streams": 1})
            )
            decoder._consume_qr_payload(pack_header(0, 0, 1) + b"abc")
            decoder._write_output()
            self.assertTrue(Path(target).exists())
            self.assertFalse((Path(tmp_dir) / "ignored.jpg").exists())

    def test_no_manifest_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            decoder = QRLDecoder(tmp_dir)
            from qrl_server.chunk import pack_header

            decoder._consume_qr_payload(pack_header(0, 0, 1) + b"data")
            decoder._write_output()
            # Default fallback name
            self.assertTrue((Path(tmp_dir) / "decoded.bin").exists())

    def test_manifest_size_strips_padding(self):
        """If a stream sent more bytes than declared, output is trimmed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            decoder = QRLDecoder(tmp_dir)
            from qrl_server.chunk import pack_header

            decoder._consume_qr_payload(
                build_manifest_chunk({"filename": "a.bin", "size": 5, "num_streams": 1})
            )
            decoder._consume_qr_payload(pack_header(0, 0, 1) + b"abcdefgh")  # 8 bytes
            decoder._write_output()
            self.assertEqual((Path(tmp_dir) / "a.bin").read_bytes(), b"abcde")  # trimmed


class TestFullPipelineWithManifest(unittest.TestCase):
    """Server encodes → emits real QR images → client decodes → file lands at
    output_dir/<filename from manifest>."""

    def test_single_stream_pipeline(self):
        original = b"Pipeline test with manifest. " * 10
        src = tempfile.NamedTemporaryFile(delete=False, suffix=".dat")
        src.write(original)
        src.close()
        try:
            with tempfile.TemporaryDirectory() as out_dir:
                encoder = QRLEncoder(src.name, chunk_size=80, error_correction="Q")
                encoder.encode()
                manifest_qr = encoder.generate_manifest_qr(num_streams=1)

                decoder = QRLDecoder(out_dir)
                # Feed manifest first, then data
                decoder.decode([manifest_qr.convert("RGB")])
                for img in encoder.get_qr_images():
                    decoder.decode([img.convert("RGB")])

                self.assertTrue(decoder.is_complete())
                expected = Path(out_dir) / Path(src.name).name
                self.assertTrue(expected.exists())
                self.assertEqual(expected.read_bytes(), original)
        finally:
            Path(src.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
