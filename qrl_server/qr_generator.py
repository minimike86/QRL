"""
QRL QR Code Generator

Low-level QR code generation utilities.
"""


class QRGenerator:
    """Generates QR codes from binary data."""

    # Error correction level mapping
    ERROR_LEVELS = {
        'L': ERROR_CORRECT_L,
        'M': ERROR_CORRECT_M,
        'Q': ERROR_CORRECT_Q,
        'H': ERROR_CORRECT_H,
    }

    # Maximum data capacity in bytes for QR Version 40 (binary mode - no base64 overhead)
    MAX_CAPACITY_BYTES = {
        'L': 2953,  # Actual capacity for Level L (binary mode)
        'M': 2331,  # Actual capacity for Level M (binary mode)
        'Q': 1663,  # Actual capacity for Level Q (binary mode)
        'H': 1273,  # Actual capacity for Level H (binary mode)
    }

    def __init__(self, data: bytes, version: Optional[int] = None,
                 error_correction: str = "Q"):
        """
        Initialize the QR generator.

        Args:
            data: Binary data to encode
            version: QR code version (1-40), None for auto
            error_correction: Error correction level (L/M/Q/H)
        """
        self.data = data
        self.version = version
        self.error_correction = error_correction

        if error_correction not in self.ERROR_LEVELS:
            raise ValueError(f"Invalid error correction level: {error_correction}")

    @classmethod
    def get_max_chunk_size(cls, error_correction: str) -> int:
        """
        Get maximum chunk size in bytes for given error correction level.

        Args:
            error_correction: Error correction level (L/M/Q/H)

        Returns:
            Maximum chunk size in bytes
        """
        return cls.MAX_CAPACITY_BYTES.get(error_correction, 900)

    @classmethod
    def validate_chunk_size(cls, chunk_size: int, error_correction: str) -> bool:
        """
        Validate if chunk size fits in QR code capacity.

        Args:
            chunk_size: Size of data chunk in bytes
            error_correction: Error correction level (L/M/Q/H)

        Returns:
            True if chunk size is valid, False otherwise
        """
        max_size = cls.get_max_chunk_size(error_correction)
        return chunk_size <= max_size

    def generate(self) -> Image.Image:
        """
        Generate a QR code.

        Returns:
            PIL Image object containing the QR code
        """
        # Use binary mode for maximum efficiency (no base64 overhead)
        encoded_data = self.data

        # Create QR code instance
        qr = qrcode.QRCode(
            version=self.version,
            error_correction=self.ERROR_LEVELS[self.error_correction],
            box_size=10,
            border=4,
        )

        # Add data and generate
        qr.add_data(encoded_data)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        return img

    def get_actual_version(self) -> int:
        """Get the actual QR version used (after auto-sizing)."""
        # Create temporary QR to determine version
        encoded_data = base64.b64encode(self.data).decode('ascii')
        qr = qrcode.QRCode(
            version=self.version,
            error_correction=self.ERROR_LEVELS[self.error_correction]
        )
        qr.add_data(encoded_data)
        qr.make(fit=True)
        return qr.version

    @staticmethod
    def get_capacity(version: int) -> int:
        """
        Get the capacity of a QR code version.

        Args:
            version: QR code version (1-40)

        Returns:
            Maximum bytes that can fit in the version
        """
        raise NotImplementedError("Implementation required")
