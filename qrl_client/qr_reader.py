"""
QRL QR Code Reader

Detects and decodes QR codes from screen-captured frames using pyzbar.
Accepts numpy arrays (BGR or grayscale) or PIL Images.

Payloads are base32-stripped by the server (see qrl_server.qr_generator) so
that they fit QR alphanumeric mode; we re-pad and base32-decode here.
"""

import base64
from typing import List, Optional, Union

import cv2
import numpy as np
from PIL import Image
from pyzbar.pyzbar import ZBarSymbol
from pyzbar.pyzbar import decode as pyzbar_decode

ImageInput = Union[np.ndarray, Image.Image]


class QRReader:
    """Reads QR codes from images using pyzbar."""

    def __init__(self, preprocess: bool = True):
        self.preprocess = preprocess
        self._last_confidence = 0.0
        self._total_reads = 0
        self._successful_reads = 0

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
            enhanced = self._enhance(gray)
            decoded = pyzbar_decode(enhanced, symbols=[ZBarSymbol.QRCODE])

        if decoded:
            self._successful_reads += 1
            self._last_confidence = 1.0
        else:
            self._last_confidence = 0.0

        payloads: List[bytes] = []
        for d in decoded:
            text = d.data.decode("ascii", errors="ignore")
            try:
                pad = (-len(text)) % 8
                payloads.append(base64.b32decode(text + ("=" * pad)))
            except Exception:
                payloads.append(d.data)  # foreign QR — let the decoder skip it
        return payloads

    def get_confidence(self) -> float:
        return self._last_confidence

    def get_success_rate(self) -> float:
        if self._total_reads == 0:
            return 0.0
        return (self._successful_reads / self._total_reads) * 100.0

    def reset_statistics(self) -> None:
        self._total_reads = 0
        self._successful_reads = 0
        self._last_confidence = 0.0

    @staticmethod
    def _to_grayscale(image: ImageInput) -> np.ndarray:
        if isinstance(image, Image.Image):
            arr = np.array(image.convert("L"))
            return arr
        if image.ndim == 2:
            return image
        if image.shape[2] == 4:  # BGRA from mss
            return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    @staticmethod
    def _enhance(gray: np.ndarray) -> np.ndarray:
        """Adaptive threshold — robust against uneven screen brightness."""
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 5
        )
