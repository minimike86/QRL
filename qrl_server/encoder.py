"""
QRL Server Encoder

Handles encoding of files into QR code sequences.
"""


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
        self.source_path = source_path
        self.chunk_size = chunk_size
        self.qr_version = qr_version
        self.error_correction = error_correction

    def encode(self):
        """
        Encode the source file into QR codes.

        Returns:
            List of PIL Image objects containing QR codes
        """
        raise NotImplementedError("Implementation required")

    def get_metadata(self) -> dict:
        """
        Get encoding metadata.

        Returns:
            Dictionary with metadata about the encoding
        """
        raise NotImplementedError("Implementation required")

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

        # Validate chunk size against QR capacity before generating
        from .qr_generator import QRGenerator
        if not QRGenerator.validate_chunk_size(self.chunk_size, self.error_correction):
            max_size = QRGenerator.get_max_chunk_size(self.error_correction)
            raise ValueError(f"Chunk size ({self.chunk_size}) exceeds QR capacity for error level '{self.error_correction}' (max: {max_size})")

        chunk = self._chunks[chunk_index]
        generator = QRGenerator(chunk, self.qr_version, self.error_correction)
        return generator.generate()

    def get_total_chunks(self) -> int:
        """Get total number of chunks."""
        return len(self._chunks) if self._chunks else 0

    def save_qr_images(self, output_dir: str) -> List[str]:
        """
        Save QR images to directory.

        Args:
            output_dir: Directory to save images

        Returns:
            List of saved file paths
        """
        if self._qr_images is None:
            raise ValueError("No QR images to save. Run encode() first.")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for i, img in enumerate(self._qr_images):
            file_path = output_path / f"qr_{i:04d}.png"
            img.save(file_path)
            saved_paths.append(str(file_path))

        return saved_paths
