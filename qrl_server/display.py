"""
QRL Display Handler

Manages QR code display on screen.
"""


class DisplayHandler:
    """Displays QR codes on screen in sequence."""

    def __init__(self, qr_images: list, duration: float = 2.0,
                 repeat: bool = True, window_title: str = "QRL"):
        """
        Initialize the display handler.

        Args:
            qr_images: List of PIL Image objects to display
            duration: Duration to display each QR code (seconds)
            repeat: Whether to repeat the sequence
            window_title: Title for the display window
        """
        self.qr_images = qr_images
        self.duration = duration
        self.repeat = repeat
        self.window_title = window_title
        self._running = False

    def start(self) -> None:
        """Start displaying QR codes."""
        self._running = True
        raise NotImplementedError("Implementation required")

    def stop(self) -> None:
        """Stop displaying QR codes."""
        self._running = False

    def set_duration(self, duration: float) -> None:
        """Update the display duration."""
        self.duration = duration

    def is_running(self) -> bool:
        """Check if display is running."""
        return self._running
