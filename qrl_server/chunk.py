"""
QRL Chunking Utilities

Handles data chunking and metadata management.

Wire format per chunk (shared with ParallelQREncoder so the client decoder
only needs one parsing path):
    [stream_id : 1 byte][sequence : 4 bytes BE][total_chunks : 4 bytes BE][data : N bytes]
"""

import io
import tarfile
from pathlib import Path
from typing import List

HEADER_SIZE = 9


def pack_header(stream_id: int, sequence: int, total_chunks: int) -> bytes:
    if not 0 <= stream_id <= 255:
        raise ValueError(f"stream_id must fit in one byte, got {stream_id}")
    if not 0 <= sequence < 2**32:
        raise ValueError(f"sequence out of range: {sequence}")
    if not 0 <= total_chunks < 2**32:
        raise ValueError(f"total_chunks out of range: {total_chunks}")
    return (
        stream_id.to_bytes(1, "big")
        + sequence.to_bytes(4, "big")
        + total_chunks.to_bytes(4, "big")
    )


def unpack_header(chunk: bytes):
    """Returns (stream_id, sequence, total_chunks, data) or None if too short."""
    if len(chunk) < HEADER_SIZE:
        return None
    return (
        chunk[0],
        int.from_bytes(chunk[1:5], "big"),
        int.from_bytes(chunk[5:9], "big"),
        chunk[HEADER_SIZE:],
    )


class ChunkManager:
    """Splits raw bytes into chunks and prefixes each with a wire-format header."""

    def __init__(self, data: bytes, chunk_size: int):
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        self.data = data
        self.chunk_size = chunk_size
        self._raw_chunks: List[bytes] = []

    def chunk(self) -> List[bytes]:
        """Split data into raw byte chunks of size self.chunk_size (last may be smaller)."""
        self._raw_chunks = [
            self.data[i : i + self.chunk_size]
            for i in range(0, len(self.data), self.chunk_size)
        ]
        return self._raw_chunks

    def add_metadata(self, chunks: List[bytes], stream_id: int = 0) -> List[bytes]:
        """Prefix each chunk with [stream_id, sequence, total_chunks]."""
        total = len(chunks)
        return [pack_header(stream_id, i, total) + c for i, c in enumerate(chunks)]

    def get_metadata(self) -> dict:
        return {
            "total_chunks": len(self._raw_chunks),
            "total_size": len(self.data),
            "chunk_size": self.chunk_size,
            "header_size": HEADER_SIZE,
        }

    @staticmethod
    def read_file(path: str) -> bytes:
        return Path(path).read_bytes()

    @staticmethod
    def read_directory(path: str) -> bytes:
        """Pack a directory into a tar archive in memory."""
        root = Path(path)
        if not root.is_dir():
            raise ValueError(f"Not a directory: {path}")
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            tar.add(str(root), arcname=root.name)
        return buf.getvalue()
