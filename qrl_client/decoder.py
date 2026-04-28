"""
QRL Client Decoder

Handles decoding of QR code sequences back into files.
"""


class QRLDecoder:
    """Decodes QR code sequences into files."""

    def __init__(self, output_path: str, timeout: int = 300):
        """
        Initialize the decoder.

        Args:
            output_path: Path to write decoded file
            timeout: Timeout in seconds for capture
        """
        self.output_path = output_path
        self.timeout = timeout

    def decode(self, frames: list) -> bool:
        """
        Decode QR codes from frames.

        Args:
            frames: List of PIL Image frames

        Returns:
            True if decoding successful, False otherwise
        """
        raise NotImplementedError("Implementation required")

    def get_progress(self) -> dict:
        """
        Get decoding progress.

        Returns:
            Dictionary with progress information
        """
        raise NotImplementedError("Implementation required")

    def get_missing_chunks(self) -> list:
        """
        Get list of missing chunk numbers.

        Returns:
            List of missing chunk indices
        """
        raise NotImplementedError("Implementation required")

    def is_complete(self) -> bool:
        """Check if decoding is complete."""
        raise NotImplementedError("Implementation required")
