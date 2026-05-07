"""
QRL Server Encoder

Handles encoding of files into QR code sequences.
"""

from pathlib import Path
from typing import List, Optional

from PIL import Image

from .chunk import ChunkManager, build_manifest_chunk


class QRLEncoder:
    """Encodes files or directories into QR code sequences."""

    def __init__(self, source_path: str, chunk_size: int = 1024,
                 qr_version: int = None, error_correction: str = "Q"):
        """
        Initialize the encoder.

        Args:
            source_path: Path to file or directory to encode
            chunk_size: Size of each data chunk in bytes
            qr_version: QR code version (1-40), None for auto
            error_correction: Error correction level (L/M/Q/H)
        """
        self.source_path = Path(source_path)
        self.chunk_size = chunk_size
        self.qr_version = qr_version
        self.error_correction = error_correction
        self._data: Optional[bytes] = None
        self._chunks: Optional[List[bytes]] = None
        self._qr_images: Optional[List[Image.Image]] = None
        self._metadata: Optional[dict] = None

    def encode(self) -> List[Image.Image]:
        """Prepare chunks and pre-generate every QR image. Returns the list of images."""
        total = self.prepare_chunks()
        self._qr_images = [self.generate_qr_for_chunk(i) for i in range(total)]
        return self._qr_images

    def get_metadata(self) -> dict:
        """Get encoding metadata. Empty until prepare_chunks() / encode() runs."""
        return self._metadata or {}

    def validate(self) -> bool:
        """
        Validate the source file.

        Returns:
            True if source is valid, False otherwise
        """
        if not self.source_path.exists():
            return False

        if self.source_path.is_file():
            return True

        if self.source_path.is_dir():
            # Check if directory has content
            try:
                return any(self.source_path.iterdir())
            except PermissionError:
                return False

        return False

    def _load_data(self) -> None:
        """Load data from source path."""
        if self._data is not None:
            return

        try:
            if self.source_path.is_file():
                self._data = ChunkManager.read_file(str(self.source_path))
            elif self.source_path.is_dir():
                self._data = ChunkManager.read_directory(str(self.source_path))
            else:
                raise ValueError(f"Unsupported source type: {self.source_path}")

        except Exception as e:
            raise ValueError(f"Failed to load data from {self.source_path}: {e}")

    def get_qr_images(self) -> Optional[List[Image.Image]]:
        """Get the generated QR images."""
        return self._qr_images

    def prepare_chunks(self) -> int:
        """
        Prepare data chunks without generating QR codes.
        Use this for on-the-fly QR generation to save memory.

        Returns:
            Number of chunks prepared
        """
        if not self.validate():
            raise ValueError(f"Invalid source path: {self.source_path}")

        from .qr_generator import QRGenerator
        from .chunk import HEADER_SIZE

        max_payload = QRGenerator.get_max_chunk_size(self.error_correction)
        if self.chunk_size + HEADER_SIZE > max_payload:
            raise ValueError(
                f"Chunk size ({self.chunk_size}) + header ({HEADER_SIZE}) exceeds "
                f"QR capacity for error level '{self.error_correction}' "
                f"(max payload: {max_payload}). Reduce chunk_size to "
                f"{max_payload - HEADER_SIZE} or lower."
            )

        # Load data
        self._load_data()

        if not self._data:
            raise ValueError("File is empty or contains no data")

        # Create chunk manager
        chunk_manager = ChunkManager(self._data, self.chunk_size)

        # Split into chunks
        raw_chunks = chunk_manager.chunk()

        # Add metadata to chunks
        self._chunks = chunk_manager.add_metadata(raw_chunks)

        # Store metadata (without QR version info yet)
        chunk_metadata = chunk_manager.get_metadata()
        self._metadata = {
            **chunk_metadata,
            'error_correction': self.error_correction,
            'source_path': str(self.source_path),
            'is_directory': self.source_path.is_dir()
        }

        print(f"Data prepared: {len(self._chunks)} chunks ready for on-demand QR generation")
        return len(self._chunks)

    def generate_qr_for_chunk(self, chunk_index: int) -> Image.Image:
        """
        Generate QR code for a specific chunk on-demand.

        Args:
            chunk_index: Index of the chunk to generate QR for

        Returns:
            PIL Image object containing the QR code
        """
        if not self._chunks:
            raise ValueError("Chunks not prepared. Call prepare_chunks() first.")

        if chunk_index >= len(self._chunks):
            raise ValueError(f"Invalid chunk index: {chunk_index} (max: {len(self._chunks) - 1})")

        chunk = self._chunks[chunk_index]
        from .qr_generator import QRGenerator
        max_size = QRGenerator.get_max_chunk_size(self.error_correction)
        if len(chunk) > max_size:
            raise ValueError(
                f"Encoded chunk ({len(chunk)} bytes including header) exceeds QR capacity "
                f"for error level '{self.error_correction}' (max: {max_size})"
            )

        generator = QRGenerator(chunk, self.qr_version, self.error_correction)
        return generator.generate()

    def get_total_chunks(self) -> int:
        """Get total number of chunks."""
        return len(self._chunks) if self._chunks else 0

    def build_manifest(self, num_streams: int = 1) -> dict:
        """Manifest dict that the client uses to derive output filename + sanity-check."""
        return {
            "v": 1,
            "filename": self.source_path.name,
            "size": len(self._data) if self._data else 0,
            "is_directory": self.source_path.is_dir() if self.source_path.exists() else False,
            "num_streams": num_streams,
            "total_chunks": self.get_total_chunks(),
            "chunk_size": self.chunk_size,
            "error_correction": self.error_correction,
        }

    def generate_manifest_qr(self, num_streams: int = 1) -> Image.Image:
        """Build a single-frame QR carrying the file manifest. Use stream_id=255."""
        from .qr_generator import QRGenerator
        manifest = self.build_manifest(num_streams=num_streams)
        payload = build_manifest_chunk(manifest)
        return QRGenerator(payload, self.qr_version, self.error_correction).generate()

    def prefetch_qr_images(
        self,
        max_workers: Optional[int] = None,
        use_processes: bool = False,
    ) -> List[Image.Image]:
        """Generate every QR image upfront and cache them.

        Uses ThreadPoolExecutor by default. ProcessPool is faster in theory
        (true parallelism vs GIL-limited threads) but on Windows it deadlocks
        when launched via console_scripts entry points that lack a
        `if __name__ == '__main__': freeze_support()` guard — child processes
        re-import the entry module and try to re-run main(). Set use_processes=
        True only when you've ensured the entry point is multiprocessing-safe.
        """
        if not self._chunks:
            raise ValueError("Chunks not prepared. Call prepare_chunks() first.")

        import os
        from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

        from .qr_generator import _pool_worker_generate

        total = len(self._chunks)
        if max_workers is None:
            max_workers = max(2, (os.cpu_count() or 4))

        args_iter = [
            (self._chunks[i], self.qr_version, self.error_correction)
            for i in range(total)
        ]

        Pool = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
        try:
            with Pool(max_workers=max_workers) as pool:
                self._qr_images = list(pool.map(_pool_worker_generate, args_iter))
        except Exception:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                self._qr_images = list(pool.map(_pool_worker_generate, args_iter))
        return self._qr_images

    def save_qr_images(self, output_dir: str) -> List[str]:
        """Save QR images to directory. Generates them on-the-fly if needed."""
        if self._qr_images is None and not self._chunks:
            raise ValueError("No data to save. Run prepare_chunks() or encode() first.")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        images = self._qr_images if self._qr_images is not None else (
            self.generate_qr_for_chunk(i) for i in range(len(self._chunks))
        )

        saved_paths = []
        for i, img in enumerate(images):
            file_path = output_path / f"qr_{i:04d}.png"
            img.save(file_path)
            saved_paths.append(str(file_path))

        return saved_paths
