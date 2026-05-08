#!/usr/bin/env python3
"""
Basic functionality tests for QRL.
"""

import tempfile
import shutil
from pathlib import Path
import pytest

from qrl_server.encoder import QRLEncoder
from qrl_server.qr_generator import QRGenerator
from qrl_server.chunk import ChunkManager
from qrl_client.decoder import QRLDecoder
from qrl_client.qr_reader import QRReader


class TestChunkManager:
    """Test the chunking functionality."""

    def test_basic_chunking(self):
        """Test basic data chunking."""
        test_data = b"Hello, World!" * 100  # ~1300 bytes
        chunk_size = 100

        chunker = ChunkManager(test_data, chunk_size)
        chunks = chunker.chunk()

        # Should have 13 chunks for ~1300 bytes with 100-byte chunks
        assert len(chunks) == 13
        assert len(chunks[0]) == chunk_size
        assert len(chunks[-1]) <= chunk_size

        # Verify chunks can be reassembled
        reassembled = b''.join(chunks)
        assert reassembled == test_data

    def test_chunking_metadata(self):
        """Test chunk metadata generation."""
        test_data = b"Test data for metadata"
        chunk_size = 10

        chunker = ChunkManager(test_data, chunk_size)
        metadata = chunker.get_metadata()

        assert metadata['total_size'] == len(test_data)
        assert metadata['total_chunks'] == chunker.total_chunks
        assert metadata['chunk_size'] == chunk_size
        assert 'data_checksum' in metadata

    def test_metadata_chunks(self):
        """Test adding metadata to chunks."""
        test_data = b"Test data"
        chunker = ChunkManager(test_data, 5)
        raw_chunks = chunker.chunk()
        meta_chunks = chunker.add_metadata(raw_chunks)

        assert len(meta_chunks) == len(raw_chunks)

        # Each chunk should have 12-byte header (3 * 4-byte ints)
        for chunk in meta_chunks:
            assert len(chunk) >= 12


class TestQRGenerator:
    """Test QR code generation."""

    def test_basic_qr_generation(self):
        """Test basic QR code generation."""
        test_data = b"Hello, QR World!"
        generator = QRGenerator(test_data)
        qr_image = generator.generate()

        # Should return a PIL Image
        assert hasattr(qr_image, 'save')
        assert qr_image.size[0] > 0
        assert qr_image.size[1] > 0

    def test_qr_capacity(self):
        """Test QR capacity calculation."""
        capacity_v1 = QRGenerator.get_capacity(1, "Q")
        capacity_v10 = QRGenerator.get_capacity(10, "Q")

        assert capacity_v1 > 0
        assert capacity_v10 > capacity_v1

    def test_version_finding(self):
        """Test finding optimal QR version."""
        small_data_size = 10
        large_data_size = 1000

        version_small = QRGenerator.find_optimal_version(small_data_size)
        version_large = QRGenerator.find_optimal_version(large_data_size)

        assert version_small >= 1
        assert version_large >= version_small


class TestEndToEndEncoding:
    """Test the complete encoding pipeline."""

    def test_file_encoding(self):
        """Test encoding a temporary file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_file:
            test_content = "This is a test file for QRL encoding.\nLine 2\nLine 3"
            tmp_file.write(test_content)
            tmp_file_path = tmp_file.name

        try:
            encoder = QRLEncoder(tmp_file_path, chunk_size=50)
            assert encoder.validate()

            qr_images = encoder.encode()
            assert len(qr_images) > 0

            metadata = encoder.get_metadata()
            assert metadata['total_size'] > 0
            assert metadata['total_chunks'] == len(qr_images)

        finally:
            Path(tmp_file_path).unlink()

    def test_qr_reader_basic(self):
        """Test QR code reading."""
        # Create a simple QR code
        test_data = b"Test QR data"
        generator = QRGenerator(test_data)
        qr_image = generator.generate()

        # Try to read it back
        reader = QRReader()
        decoded_data = reader.read(qr_image)

        # Should be able to decode
        assert decoded_data is not None

        # The reader should decode back to the original data
        assert decoded_data == test_data


class TestEndToEndDecoding:
    """Test the complete decoding pipeline."""

    def test_full_encode_decode_cycle(self):
        """Test complete encode-decode cycle."""
        # Create test data
        test_data = "This is test data for full encode-decode testing.\n" * 10

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_file:
            tmp_file.write(test_data)
            tmp_file_path = tmp_file.name

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                # Encode
                encoder = QRLEncoder(tmp_file_path, chunk_size=100)
                qr_images = encoder.encode()

                # Decode
                output_path = Path(tmp_dir) / "decoded.txt"
                decoder = QRLDecoder(str(output_path))

                success = decoder.decode(qr_images)
                assert success

                # Verify content matches
                decoded_content = output_path.read_text()
                assert decoded_content == test_data

            finally:
                Path(tmp_file_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__])