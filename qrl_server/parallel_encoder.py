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

from .chunk import ChunkManager
from .qr_generator import QRGenerator


class ParallelQREncoder:
    """Encodes data into multiple parallel QR streams for simultaneous display."""

    def __init__(self, source_path: str, num_streams: int = 4,
                 chunk_size: int = 1024, error_correction: str = "Q"):
        """
        Initialize parallel encoder.

        Args:
            source_path: Path to file/directory to encode
            num_streams: Number of parallel streams (1, 4, 9, 16 for grid layouts)
            chunk_size: Base chunk size per QR code
            error_correction: Error correction level
        """
        self.source_path = Path(source_path)
        self.num_streams = num_streams
        self.chunk_size = chunk_size
        self.error_correction = error_correction

        # Validate stream count for grid layouts
        valid_streams = [1, 4, 9, 16]  # 1x1, 2x2, 3x3, 4x4
        if num_streams not in valid_streams:
            raise ValueError(f"num_streams must be one of {valid_streams}")

        self._data = None
        self._stream_chunks = {}  # {stream_id: [chunks]}
        self._total_chunks_per_stream = 0
        self._metadata = None

    def prepare_parallel_streams(self) -> Dict[int, int]:
        """
        Prepare data for parallel streaming.

        Returns:
            Dict mapping stream_id to number of chunks in that stream
        """
        if not self.source_path.exists():
            raise ValueError(f"Source path does not exist: {self.source_path}")

        # Load data
        if self.source_path.is_file():
            self._data = ChunkManager.read_file(str(self.source_path))
        elif self.source_path.is_dir():
            self._data = ChunkManager.read_directory(str(self.source_path))
        else:
            raise ValueError(f"Unsupported source type: {self.source_path}")

        if not self._data:
            raise ValueError("No data to encode")

        # Calculate effective chunk size accounting for metadata overhead
        # Each chunk needs: stream_id(1) + sequence_number(4) + total_chunks(4) + data
        metadata_overhead = 9  # bytes
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

        # Store metadata
        self._metadata = {
            'source_path': str(self.source_path),
            'total_data_size': total_data_size,
            'num_streams': self.num_streams,
            'chunks_per_stream': stream_info,
            'total_chunks_per_stream': self._total_chunks_per_stream,
            'chunk_size': self.chunk_size,
            'effective_chunk_size': effective_chunk_size,
            'error_correction': self.error_correction
        }

        print(f"Parallel encoding prepared:")
        print(f"  Data size: {total_data_size:,} bytes")
        print(f"  Streams: {self.num_streams}")
        print(f"  Max chunks per stream: {self._total_chunks_per_stream}")
        print(f"  Total QR codes: {self._total_chunks_per_stream * self.num_streams}")

        return stream_info

    def _create_chunk_with_metadata(self, stream_id: int, sequence: int,
                                   total_chunks: int, data: bytes) -> bytes:
        """Create chunk with embedded metadata."""
        # Format: [stream_id:1][sequence:4][total_chunks:4][data:remaining]
        metadata = (
            stream_id.to_bytes(1, 'big') +
            sequence.to_bytes(4, 'big') +
            total_chunks.to_bytes(4, 'big')
        )
        return metadata + data

    def generate_qr_grid(self, chunk_index: int) -> List[List[Image.Image]]:
        """
        Generate QR grid for a specific chunk index across all streams.

        Args:
            chunk_index: Which chunk set to generate (0 to max_chunks-1)

        Returns:
            2D list of PIL Images arranged in grid format
        """
        if not self._stream_chunks:
            raise ValueError("Streams not prepared. Call prepare_parallel_streams() first.")

        grid_size = int(math.sqrt(self.num_streams))
        qr_grid = []

        for row in range(grid_size):
            qr_row = []
            for col in range(grid_size):
                stream_id = row * grid_size + col

                # Get chunk for this stream at this index
                if (stream_id in self._stream_chunks and
                    chunk_index < len(self._stream_chunks[stream_id])):
                    chunk_data = self._stream_chunks[stream_id][chunk_index]

                    # Validate chunk size
                    if not QRGenerator.validate_chunk_size(len(chunk_data), self.error_correction):
                        raise ValueError(f"Chunk too large for QR code: {len(chunk_data)} bytes")

                    generator = QRGenerator(chunk_data, error_correction=self.error_correction)
                    qr_image = generator.generate()
                else:
                    # Generate empty/padding QR for streams that have finished
                    padding_data = f"STREAM_{stream_id}_COMPLETE".encode()
                    generator = QRGenerator(padding_data, error_correction=self.error_correction)
                    qr_image = generator.generate()

                qr_row.append(qr_image)
            qr_grid.append(qr_row)

        return qr_grid

    def get_total_chunks(self) -> int:
        """Get total number of chunk sets needed."""
        return self._total_chunks_per_stream

    def get_metadata(self) -> dict:
        """Get encoding metadata."""
        return self._metadata or {}

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