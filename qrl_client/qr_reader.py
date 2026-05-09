"""
QRL QR Code Reader

Detects and decodes QR codes from screen-captured frames using pyzbar.
Accepts numpy arrays (BGR or grayscale) or PIL Images.
"""

from typing import List, Optional, Union

import cv2
import numpy as np
from PIL import Image
from pyzbar.pyzbar import ZBarSymbol
from pyzbar.pyzbar import decode as pyzbar_decode

ImageInput = Union[np.ndarray, Image.Image]

# For single-QR, 1024px is plenty. For multi-QR grids (e.g. 3×3 at 200px
# per code on a 4K screen), individual codes shrink to ~53px at 1024 cap —
# below pyzbar's reliable threshold. 1920 keeps full-1080p frames unscaled
# and gives 4K frames ~2× more resolution than 1024 did.
_MAX_DECODE_DIM = 1920


class QRReader:
    """Reads QR codes from images using pyzbar."""

    def __init__(self, preprocess: bool = True):
        self.preprocess = preprocess
        self._last_confidence = 0.0
        self._total_reads = 0
        self._successful_reads = 0
        self._total_qrs_decoded = 0

    def read(self, image: ImageInput) -> Optional[bytes]:
        """Read the first QR code in image. Returns its raw bytes, or None."""
        results = self.read_multiple(image)
        return results[0] if results else None

    def read_multiple(self, image: ImageInput) -> List[bytes]:
        """Read every QR code in image. Returns a list of raw byte payloads."""
        gray = self._to_grayscale(image)
        self._total_reads += 1

        decoded = pyzbar_decode(gray, symbols=[ZBarSymbol.QRCODE])

        if not decoded and self.preprocess:
            # Try a contrast/threshold pass — helps with screen glare and motion blur.
            # Run it on the already-downscaled gray so it's fast even on large captures.
            enhanced = self._enhance(gray)
            decoded = pyzbar_decode(enhanced, symbols=[ZBarSymbol.QRCODE])

        if decoded:
            self._successful_reads += 1
            self._last_confidence = 1.0
        else:
            self._last_confidence = 0.0

        payloads: List[bytes] = []
        for d in decoded:
            try:
                # pyzbar re-encodes byte-mode QR data as UTF-8 (treating the
                # raw bytes as Latin-1/ISO-8859-1). Reverse that to recover
                # the original bytes exactly.
                payloads.append(d.data.decode("utf-8").encode("latin-1"))
            except (UnicodeDecodeError, UnicodeEncodeError):
                payloads.append(d.data)  # foreign/text QR — let decoder skip it
        self._total_qrs_decoded += len(payloads)
        return payloads

    def get_confidence(self) -> float:
        return self._last_confidence

    def get_success_rate(self) -> float:
        if self._total_reads == 0:
            return 0.0
        return (self._successful_reads / self._total_reads) * 100.0

    def get_avg_qrs_per_read(self) -> float:
        """Average number of QR codes decoded per frame (>1 means multi-QR is active)."""
        if self._total_reads == 0:
            return 0.0
        return self._total_qrs_decoded / self._total_reads

    def reset_statistics(self) -> None:
        self._total_reads = 0
        self._successful_reads = 0
        self._total_qrs_decoded = 0
        self._last_confidence = 0.0

    @staticmethod
    def _to_grayscale(image: ImageInput) -> np.ndarray:
        """Convert to grayscale and downsample to _MAX_DECODE_DIM if needed.

        Downsampling is applied with INTER_AREA (anti-aliased) before
        returning — smaller images decode 10-15× faster in pyzbar with no
        accuracy loss for screen-captured QR codes.
        """
        if isinstance(image, Image.Image):
            arr = np.array(image.convert("L"))
        elif image.ndim == 2:
            arr = image
        elif image.shape[2] == 4:  # BGRA from mss
            arr = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        else:
            arr = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        h, w = arr.shape[:2]
        largest = max(h, w)
        if largest > _MAX_DECODE_DIM:
            scale = _MAX_DECODE_DIM / largest
            arr = cv2.resize(
                arr,
                (max(1, int(w * scale)), max(1, int(h * scale))),
                interpolation=cv2.INTER_AREA,
            )
        return arr

    @staticmethod
    def _enhance(gray: np.ndarray) -> np.ndarray:
        """Adaptive threshold — robust against uneven screen brightness.

        Block size 11 (was 21) is sufficient after downscaling and avoids
        edge-case failures when the image is smaller than the block window.
        """
        # Ensure block size is odd and at least 3; adaptive threshold requires
        # blockSize > 1 and odd. After downscale the image may be small.
        h, w = gray.shape[:2]
        block = min(11, max(3, (min(h, w) // 20) | 1))
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 5
        )
