"""
QRL Capture Handler

Manages screen capture for QR code reading.
"""


class CaptureHandler:
    """Captures screen regions for QR code detection."""

    def __init__(self, monitor: int = 0, region: tuple = None,
                 interval: float = 0.5):
        """
        Initialize the capture handler.

        Args:
            monitor: Monitor index (0 = primary)
            region: Capture region (x, y, width, height)
            interval: Seconds between captures
        """
        self.monitor = monitor
        self.region = region
        self.interval = interval
        self._running = False

    def start(self) -> None:
        """Start capturing screen."""
        self._running = True
        raise NotImplementedError("Implementation required")

    def stop(self) -> None:
        """Stop capturing screen."""
        self._running = False

    def get_frames(self) -> list:
        """
        Get captured frames since last call.

        Returns:
            List of PIL Image frames
        """
        raise NotImplementedError("Implementation required")

    def set_region(self, region: tuple) -> None:
        """Update capture region."""
        self.region = region
