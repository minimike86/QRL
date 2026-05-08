"""
QRL QR Code Generator

Low-level QR code generation utilities.
"""

import base64
from typing import Optional


def _b32_encode_stripped(data: bytes) -> str:
    """base32-encode without '=' padding so the result is pure QR-alphanumeric
    (uppercase A-Z + digits 2-7 + nothing else). Letting qrcode pack the QR in
    alphanumeric mode roughly doubles per-QR throughput vs byte mode."""
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _b32_decode_stripped(text: str) -> bytes:
    pad = (-len(text)) % 8
    return base64.b32decode(text + ("=" * pad))

import qrcode
from PIL import Image
from qrcode.constants import (
    ERROR_CORRECT_H,
    ERROR_CORRECT_L,
    ERROR_CORRECT_M,
    ERROR_CORRECT_Q,
)


def _pool_worker_generate(args) -> Image.Image:
    """Top-level worker callable for ProcessPoolExecutor (must be picklable).

    args: tuple of (chunk_bytes, version_or_None, error_correction)
    """
    chunk, version, error_correction = args
    return QRGenerator(chunk, version, error_correction).generate()


class QRGenerator:
    """Generates QR codes from binary data."""

    # Error correction level mapping
    ERROR_LEVELS = {
        'L': ERROR_CORRECT_L,
        'M': ERROR_CORRECT_M,
        'Q': ERROR_CORRECT_Q,
        'H': ERROR_CORRECT_H,
    }

    # Maximum *raw payload* bytes per QR at version 40 after base32-stripped
    # encoding (5 raw bytes -> 8 alphanumeric chars) packed in QR alphanumeric
    # mode. Capacity = floor(alpha_chars_at_v40 * 5 / 8), rounded down with
    # a few bytes of safety margin for QR mode/length headers.
    MAX_CAPACITY_BYTES = {
        'L': 2680,  # v40 L alpha cap 4296 -> 2685 raw bytes
        'M': 2110,  # v40 M alpha cap 3391 -> 2119
        'Q': 1505,  # v40 Q alpha cap 2420 -> 1512
        'H': 1150,  # v40 H alpha cap 1852 -> 1157
    }

    # Generous quiet zone (white border in modules). The QR spec requires 4
    # modules minimum but screen-captured QRs benefit from more — the bigger
    # margin gives the client's QR detector a stronger signal to lock onto
    # the finder patterns even with surrounding visual noise.
    DEFAULT_BORDER = 6
    DEFAULT_BOX_SIZE = 10

    def __init__(self, data: bytes, version: Optional[int] = None,
                 error_correction: str = "Q",
                 border: Optional[int] = None,
                 box_size: Optional[int] = None):
        """
        Initialize the QR generator.

        Args:
            data: Binary data to encode
            version: QR code version (1-40), None for auto
            error_correction: Error correction level (L/M/Q/H)
            border: Quiet-zone width in modules (default DEFAULT_BORDER)
            box_size: Pixel size per module (default DEFAULT_BOX_SIZE)
        """
        self.data = data
        self.version = version
        self.error_correction = error_correction
        self.border = self.DEFAULT_BORDER if border is None else border
        self.box_size = self.DEFAULT_BOX_SIZE if box_size is None else box_size

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
        """Generate a QR code as a PIL Image. Binary payload is base32-stripped
        first so it survives zbar's text-mode decoding while still fitting
        into the QR's efficient alphanumeric mode."""
        qr = qrcode.QRCode(
            version=self.version,
            error_correction=self.ERROR_LEVELS[self.error_correction],
            box_size=self.box_size,
            border=self.border,
        )
        qr.add_data(_b32_encode_stripped(self.data))
        qr.make(fit=True)

        wrapper = qr.make_image(fill_color="black", back_color="white")
        # qrcode returns a PilImage wrapper; unwrap to a real PIL.Image.Image.
        if hasattr(wrapper, "get_image"):
            return wrapper.get_image()
        if hasattr(wrapper, "_img"):
            return wrapper._img
        return wrapper

    def get_actual_version(self) -> int:
        """Get the actual QR version used (after auto-sizing)."""
        qr = qrcode.QRCode(
            version=self.version,
            error_correction=self.ERROR_LEVELS[self.error_correction]
        )
        qr.add_data(self.data)
        qr.make(fit=True)
        return qr.version

    @classmethod
    def get_capacity(cls, version: int, error_correction: str = "L") -> int:
        """Maximum binary-mode payload bytes for a QR version + error level."""
        if not 1 <= version <= 40:
            raise ValueError(f"version must be 1-40, got {version}")
        if error_correction not in cls.ERROR_LEVELS:
            raise ValueError(f"Invalid error correction level: {error_correction}")
        from qrcode.util import BIT_LIMIT_TABLE

        level_idx = {"L": 0, "M": 1, "Q": 2, "H": 3}[error_correction]
        total_bits = BIT_LIMIT_TABLE[level_idx][version]
        # Binary (byte) mode overhead: 4-bit mode indicator + char-count bits
        # (8 for v1-9, 16 for v10-40), per ISO/IEC 18004.
        char_count_bits = 16 if version >= 10 else 8
        available_bits = total_bits - 4 - char_count_bits
        return max(available_bits // 8, 0)
