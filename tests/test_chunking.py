"""Tests for qrl_server.chunk.ChunkManager."""

import tempfile
import unittest
from pathlib import Path

from qrl_server.chunk import ChunkManager


class TestChunkManagerInit(unittest.TestCase):
    def test_stores_data_and_chunk_size(self):
        data = b"hello world"
        cm = ChunkManager(data, chunk_size=4)
        self.assertEqual(cm.data, data)
        self.assertEqual(cm.chunk_size, 4)


class TestChunk(unittest.TestCase):
    def test_splits_into_equal_chunks(self):
        cm = ChunkManager(b"abcdefghij", chunk_size=2)
        chunks = cm.chunk()
        self.assertEqual(len(chunks), 5)
        self.assertEqual(b"".join(chunks), b"abcdefghij")

    def test_handles_uneven_final_chunk(self):
        cm = ChunkManager(b"abcdefg", chunk_size=3)
        chunks = cm.chunk()
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[-1], b"g")
        self.assertEqual(b"".join(chunks), b"abcdefg")

    def test_chunk_size_larger_than_data(self):
        cm = ChunkManager(b"abc", chunk_size=100)
        self.assertEqual(cm.chunk(), [b"abc"])

    def test_empty_data(self):
        cm = ChunkManager(b"", chunk_size=10)
        self.assertEqual(cm.chunk(), [])


class TestAddMetadata(unittest.TestCase):
    def test_returns_one_entry_per_chunk(self):
        cm = ChunkManager(b"abcdef", chunk_size=2)
        raw = cm.chunk()
        with_meta = cm.add_metadata(raw)
        self.assertEqual(len(with_meta), len(raw))

    def test_metadata_chunks_differ_from_raw(self):
        cm = ChunkManager(b"abcdef", chunk_size=2)
        raw = cm.chunk()
        with_meta = cm.add_metadata(raw)
        self.assertNotEqual(with_meta[0], raw[0])


class TestGetMetadata(unittest.TestCase):
    def test_returns_dict(self):
        cm = ChunkManager(b"abcdef", chunk_size=2)
        cm.chunk()
        self.assertIsInstance(cm.get_metadata(), dict)


class TestReadFile(unittest.TestCase):
    def test_read_file_roundtrip(self):
        payload = b"some bytes for testing"
        tmp = tempfile.NamedTemporaryFile(delete=False)
        try:
            tmp.write(payload)
            tmp.close()
            self.assertEqual(ChunkManager.read_file(tmp.name), payload)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
