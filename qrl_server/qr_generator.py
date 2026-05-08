"""
QRL QR Code Generator

Low-level QR code generation utilities.
"""

from typing import Optional

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
    """Generates QR codes from binary data using byte (binary) mode."""

    # Maps EC letter to the qrcode library's integer constant.
    # NOTE: qrcode's constants are NOT in alphabetical order:
    #   ERROR_CORRECT_L = 1, ERROR_CORRECT_M = 0,
    #   ERROR_CORRECT_Q = 3, ERROR_CORRECT_H = 2
    # BIT_LIMIT_TABLE is indexed by these integer values, so always use
    # ERROR_LEVELS[ec] rather than a hand-written {L:0, M:1, Q:2, H:3} dict.
    ERROR_LEVELS = {
        'L': ERROR_CORRECT_L,
        'M': ERROR_CORRECT_M,
        'Q': ERROR_CORRECT_Q,
        'H': ERROR_CORRECT_H,
    }

    # Total QR capacity in bytes (byte/binary mode, version 40).
    # Source: ISO/IEC 18004, version 40 binary-mode data capacity.
    # Formula: (BIT_LIMIT_TABLE[ERROR_LEVELS[ec]][40] - 4 - 16) // 8
    #   where 4 = mode indicator bits, 16 = char-count bits for v10+.
    MAX_CAPACITY_BYTES = {
        'L': 2953,
        'M': 2331,
        'Q': 1663,
        'H': 1273,
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
        """Total QR capacity in bytes for the given EC level at version 40."""
        return cls.MAX_CAPACITY_BYTES.get(error_correction, 900)

    @classmethod
    def validate_chunk_size(cls, chunk_size: int, error_correction: str) -> bool:
        """True if chunk_size bytes fit in a version-40 QR at this EC level."""
        return chunk_size <= cls.get_max_chunk_size(error_correction)

    def generate(self) -> Image.Image:
        """Generate a QR code as a PIL Image using byte (binary) mode."""
        qr = qrcode.QRCode(
            version=self.version,
            error_correction=self.ERROR_LEVELS[self.error_correction],
            box_size=self.box_size,
            border=self.border,
        )
        qr.add_data(self.data)
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
            error_correction=self.ERROR_LEVELS[self.error_correction],
        )
        qr.add_data(self.data)
        qr.make(fit=True)
        return qr.version

    @classmethod
    def get_version_chunk_capacity(cls, version: int, error_correction: str) -> int:
        """Total bytes a QR of the given version + EC can hold in binary mode.

        Uses the correct qrcode library index (via ERROR_LEVELS) rather than
        an alphabetical mapping which would silently swap Q↔H capacities.
        """
        from qrcode.util import BIT_LIMIT_TABLE
        if not 1 <= version <= 40:
            return 0
        level_idx = cls.ERROR_LEVELS.get(error_correction)
        if level_idx is None:
            return 0
        total_bits = BIT_LIMIT_TABLE[level_idx][version]
        # Binary (byte) mode: 4-bit mode indicator + 8-bit char count (v1-9)
        # or 16-bit char count (v10-40), per ISO/IEC 18004.
        char_count_bits = 8 if version <= 9 else 16
        return max(0, (total_bits - 4 - char_count_bits) // 8)

    @classmethod
    def get_capacity(cls, version: int, error_correction: str = "L") -> int:
        """Maximum binary-mode payload bytes for a QR version + error level."""
        if not 1 <= version <= 40:
            raise ValueError(f"version must be 1-40, got {version}")
        if error_correction not in cls.ERROR_LEVELS:
            raise ValueError(f"Invalid error correction level: {error_correction}")
        return cls.get_version_chunk_capacity(version, error_correction)
