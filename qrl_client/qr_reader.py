"""
QRL QR Code Reader

Handles QR code detection and decoding from images.
"""


class QRReader:
    """Reads QR codes from images."""

    def __init__(self):
        """Initialize the QR reader."""
        self._last_confidence = 0.0

    def read(self, image) -> bytes:
        """
        Read a single QR code from an image.

        Args:
            image: PIL Image containing the QR code

        Returns:
            Decoded bytes, or None if no QR code found
        """
        raise NotImplementedError("Implementation required")

    def read_multiple(self, image) -> list:
        """
        Read multiple QR codes from a single image.

        Args:
            image: PIL Image containing QR codes

        Returns:
            List of decoded byte sequences
        """
        raise NotImplementedError("Implementation required")

    def get_confidence(self) -> float:
        """
        Get confidence of last read (0.0-1.0).

        Returns:
            Confidence score
        """
        return self._last_confidence
