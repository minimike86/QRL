#!/usr/bin/env python3
"""
QRL Parallel Stream Encoder

Implements parallel QR streams to multiply data throughput beyond single QR limits.
Each stream carries independent data chunks with stream and sequence identifiers.
"""

from pathlib import Path
from typing import List, Dict, Tuple, Optional
from PIL import Image
import math

from .chunk import ChunkManager, build_manifest_chunk, maybe_compress
from .qr_generator import QRGenerator


class ParallelQREncoder:
    """Encodes data into multiple parallel QR streams for simultaneous display."""

    def __init__(self, source_path: str, num_streams: int = 4,
                 chunk_size: int = 1024, error_correction: str = "Q",
                 box_size: Optional[int] = None,
                 border: Optional[int] = None,
                 qr_version: Optional[int] = None):
        """
        Initialize parallel encoder.

        Args:
            source_path: Path to file/directory to encode
            num_streams: Number of parallel streams. Any positive integer up
                to 254 (255 is reserved for the manifest channel). Need not
                be a perfect square — non-square layouts (e.g. 10x5 = 50)
                fill widescreen displays much better than 4x4.
            chunk_size: Base chunk size per QR code
            error_correction: Error correction level
            qr_version: QR version (1–40), None for auto
        """
        self.source_path = Path(source_path)
        self.num_streams = num_streams
        self.chunk_size = chunk_size
        self.error_correction = error_correction
        self.box_size = box_size
        self.border = border
        self.qr_version = qr_version

        if num_streams < 1 or num_streams > 254:
            raise ValueError(f"num_streams must be in [1, 254], got {num_streams}")

        self._data = None
        self._stream_chunks = {}  # {stream_id: [chunks]}
        self._total_chunks_per_stream = 0
        self._metadata = None
        self._compressed: bool = False
        self._original_size: int = 0

    def prepare_parallel_streams(self) -> Dict[int, int]:
        """
        Prepare data for parallel streaming.

        Returns:
            Dict mapping stream_id to number of chunks in that stream
        """
        if not self.source_path.exists():
            raise ValueError(f"Source path does not exist: {self.source_path}")

        # Load data and optionally compress (auto-detected — falls back to
        # raw if data doesn't actually shrink, e.g. JPEGs or MP4s).
        if self.source_path.is_file():
            raw = ChunkManager.read_file(str(self.source_path))
        elif self.source_path.is_dir():
            raw = ChunkManager.read_directory(str(self.source_path))
        else:
            raise ValueError(f"Unsupported source type: {self.source_path}")

        if not raw:
            raise ValueError("No data to encode")
        self._original_size = len(raw)
        self._data, self._compressed = maybe_compress(raw)

        # Effective per-chunk data after the 9-byte wire-format header.
        from .chunk import HEADER_SIZE
        metadata_overhead = HEADER_SIZE
        effective_chunk_size = self.chunk_size - metadata_overhead

        if effective_chunk_size <= 0:
            raise ValueError(f"Chunk size {self.chunk_size} too small for metadata overhead")

        # Split data into parallel streams
        total_data_size = len(self._data)
        data_per_stream = math.ceil(total_data_size / self.num_streams)

        stream_info = {}

        for stream_id in range(self.num_streams):
            start_offset = stream_id * data_per_stream
            end_offset = min(start_offset + data_per_stream, total_data_size)

            if start_offset >= total_data_size:
                # This stream has no data
                stream_info[stream_id] = 0
                self._stream_chunks[stream_id] = []
                continue

            stream_data = self._data[start_offset:end_offset]

            # Chunk this stream's data
            chunks = []
            chunks_in_stream = math.ceil(len(stream_data) / effective_chunk_size)

            for chunk_idx in range(chunks_in_stream):
                chunk_start = chunk_idx * effective_chunk_size
                chunk_end = min(chunk_start + effective_chunk_size, len(stream_data))
                chunk_data = stream_data[chunk_start:chunk_end]

                # Create chunk with metadata
                chunk_with_metadata = self._create_chunk_with_metadata(
                    stream_id, chunk_idx, chunks_in_stream, chunk_data
                )
                chunks.append(chunk_with_metadata)

            self._stream_chunks[stream_id] = chunks
            stream_info[stream_id] = len(chunks)

        # Calculate total chunks needed (max across all streams)
        self._total_chunks_per_stream = max(stream_info.values()) if stream_info else 0

        # Store metadata. `total_size` and `total_chunks` mirror the single-stream
        # encoder's keys so the GUI can read both modes uniformly.
        self._metadata = {
            'source_path': str(self.source_path),
            'total_size': total_data_size,
            'total_data_size': total_data_size,
            'original_size': self._original_size,
            'compressed': self._compressed,
            'num_streams': self.num_streams,
            'chunks_per_stream': stream_info,
            'total_chunks': self._total_chunks_per_stream,
            'total_chunks_per_stream': self._total_chunks_per_stream,
            'chunk_size': self.chunk_size,
            'effective_chunk_size': effective_chunk_size,
            'error_correction': self.error_correction,
            'is_directory': self.source_path.is_dir(),
        }

        return stream_info

    def _create_chunk_with_metadata(self, stream_id: int, sequence: int,
                                   total_chunks: int, data: bytes) -> bytes:
        """Create chunk with embedded metadata using the shared wire format."""
        from .chunk import pack_header
        return pack_header(stream_id, sequence, total_chunks) + data

    def generate_qr_set(self, chunk_index: int) -> List[Image.Image]:
        """Return one QR image per stream for the given chunk index.

        Display layout (cols × rows) is the caller's responsibility — let the
        UI compute grid shape based on actual screen dimensions, not assume
        square layouts."""
        if not self._stream_chunks:
            raise ValueError("Streams not prepared. Call prepare_parallel_streams() first.")

        images: List[Image.Image] = []
        for stream_id in range(self.num_streams):
            chunks = self._stream_chunks.get(stream_id, [])
            if chunk_index < len(chunks):
                chunk_data = chunks[chunk_index]
                if not QRGenerator.validate_chunk_size(len(chunk_data), self.error_correction):
                    raise ValueError(f"Chunk too large for QR code: {len(chunk_data)} bytes")
                generator = QRGenerator(
                    chunk_data, self.qr_version,
                    error_correction=self.error_correction,
                    box_size=self.box_size, border=self.border,
                )
                images.append(generator.generate())
            elif chunks:
                # Stream finished early — re-emit its last chunk. Decoder
                # deduplicates, and re-sending real chunks gives the client
                # extra recovery opportunities.
                last = chunks[-1]
                generator = QRGenerator(
                    last, self.qr_version,
                    error_correction=self.error_correction,
                    box_size=self.box_size, border=self.border,
                )
                images.append(generator.generate())
            else:
                # Empty stream — emit the manifest as harmless filler
                images.append(self.generate_manifest_qr())
        return images

    def generate_qr_grid(self, chunk_index: int) -> List[List[Image.Image]]:
        """Backwards-compatible square-grid wrapper around generate_qr_set."""
        flat = self.generate_qr_set(chunk_index)
        grid_size = int(math.sqrt(len(flat)))
        if grid_size * grid_size != len(flat):
            # Not a perfect square — return as a single row
            return [flat]
        return [flat[r * grid_size:(r + 1) * grid_size] for r in range(grid_size)]

    def prefetch_all_qr_sets(
        self,
        max_workers: Optional[int] = None,
        progress_callback=None,
    ) -> List[List[Image.Image]]:
        """Pre-generate every QR for every chunk index, in parallel.

        Returns a list of length total_chunks_per_stream where each entry
        is a list of num_streams QR images.

        progress_callback(done_sets, total_sets) is invoked as sets finish."""
        if not self._stream_chunks:
            raise ValueError("Streams not prepared.")

        from concurrent.futures import ThreadPoolExecutor, as_completed
        import os

        if max_workers is None:
            max_workers = max(2, os.cpu_count() or 4)

        total = self._total_chunks_per_stream
        results: List[Optional[List[Image.Image]]] = [None] * total
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self.generate_qr_set, i): i for i in range(total)
            }
            done = 0
            for fut in as_completed(futures):
                i = futures[fut]
                results[i] = fut.result()
                done += 1
                if progress_callback is not None:
                    progress_callback(done, total)
        return results  # type: ignore[return-value]

    def get_total_chunks(self) -> int:
        """Get total number of chunk sets needed."""
        return self._total_chunks_per_stream

    def get_metadata(self) -> dict:
        """Get encoding metadata."""
        return self._metadata or {}

    def build_manifest(self) -> dict:
        return {
            "v": 1,
            "filename": self.source_path.name,
            "size": len(self._data) if self._data is not None else 0,
            "original_size": self._original_size,
            "compressed": self._compressed,
            "is_directory": self.source_path.is_dir() if self.source_path.exists() else False,
            "num_streams": self.num_streams,
            "total_chunks": self._total_chunks_per_stream,
            "chunk_size": self.chunk_size,
            "error_correction": self.error_correction,
        }

    def generate_manifest_qr(self) -> Image.Image:
        payload = build_manifest_chunk(self.build_manifest())
        return QRGenerator(
            payload, error_correction=self.error_correction,
            border=self.border, box_size=self.box_size,
        ).generate()

    def calculate_theoretical_throughput(self, display_duration: float) -> dict:
        """
        Calculate theoretical data transfer rates.

        Args:
            display_duration: Seconds per QR display

        Returns:
            Dict with throughput statistics
        """
        if not self._metadata:
            return {}

        data_size = self._metadata['total_data_size']
        total_display_time = self._total_chunks_per_stream * display_duration

        # Calculate throughput
        bytes_per_second = data_size / total_display_time if total_display_time > 0 else 0

        # Calculate improvement over single-stream
        single_stream_chunks = math.ceil(data_size / (self.chunk_size - 9))  # account for metadata
        single_stream_time = single_stream_chunks * display_duration
        speedup_factor = single_stream_time / total_display_time if total_display_time > 0 else 0

        return {
            'data_size_bytes': data_size,
            'data_size_mb': data_size / (1024 * 1024),
            'total_display_time_seconds': total_display_time,
            'bytes_per_second': bytes_per_second,
            'kilobytes_per_second': bytes_per_second / 1024,
            'megabytes_per_second': bytes_per_second / (1024 * 1024),
            'speedup_factor': speedup_factor,
            'num_streams': self.num_streams,
            'chunks_per_stream': self._total_chunks_per_stream,
            'total_qr_codes': self._total_chunks_per_stream * self.num_streams
        }


class ParallelQRDecoder:
    """Decodes parallel QR streams back into original data."""

    def __init__(self, num_streams: int):
        """
        Initialize parallel decoder.

        Args:
            num_streams: Expected number of parallel streams
        """
        self.num_streams = num_streams
        self.stream_data = {}  # {stream_id: {sequence: data}}
        self.stream_metadata = {}  # {stream_id: {'total_chunks': X}}

    def add_qr_data(self, qr_content: bytes) -> bool:
        """
        Add decoded QR content to the appropriate stream.

        Args:
            qr_content: Raw bytes from decoded QR code

        Returns:
            True if this completes a stream, False otherwise
        """
        if len(qr_content) < 9:
            return False  # Invalid chunk

        # Parse metadata
        stream_id = qr_content[0]
        sequence = int.from_bytes(qr_content[1:5], 'big')
        total_chunks = int.from_bytes(qr_content[5:9], 'big')
        data = qr_content[9:]

        # Initialize stream if needed
        if stream_id not in self.stream_data:
            self.stream_data[stream_id] = {}
            self.stream_metadata[stream_id] = {'total_chunks': total_chunks}

        # Store chunk data
        self.stream_data[stream_id][sequence] = data

        # Check if this stream is complete
        return len(self.stream_data[stream_id]) >= total_chunks

    def is_complete(self) -> bool:
        """Check if all streams are complete."""
        if len(self.stream_data) < self.num_streams:
            return False

        for stream_id in range(self.num_streams):
            if stream_id not in self.stream_metadata:
                return False
            expected_chunks = self.stream_metadata[stream_id]['total_chunks']
            actual_chunks = len(self.stream_data.get(stream_id, {}))
            if actual_chunks < expected_chunks:
                return False

        return True

    def reconstruct_data(self) -> bytes:
        """
        Reconstruct original data from all streams.

        Returns:
            Original binary data
        """
        if not self.is_complete():
            raise ValueError("Not all streams are complete")

        # Reconstruct each stream
        stream_contents = []
        for stream_id in range(self.num_streams):
            stream_chunks = self.stream_data[stream_id]
            total_chunks = self.stream_metadata[stream_id]['total_chunks']

            # Sort chunks by sequence and concatenate
            sorted_chunks = []
            for seq in range(total_chunks):
                if seq in stream_chunks:
                    sorted_chunks.append(stream_chunks[seq])
                else:
                    raise ValueError(f"Missing chunk {seq} in stream {stream_id}")

            stream_content = b''.join(sorted_chunks)
            stream_contents.append(stream_content)

        # Concatenate all streams
        return b''.join(stream_contents)