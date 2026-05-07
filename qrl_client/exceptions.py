#!/usr/bin/env python3
"""
QRL Client Custom Exceptions
Custom exception classes for better error handling and user feedback.
"""

import os


class QRLClientError(Exception):
    """Base exception class for all QRL client-related errors."""

    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message}\nDetails: {self.details}"
        return self.message


class CaptureError(QRLClientError):
    """Raised when screen capture fails."""
    pass


class DecodingError(QRLClientError):
    """Raised when QR code decoding fails."""
    pass


class QRReadError(QRLClientError):
    """Raised when QR code reading fails."""
    pass


class OutputError(QRLClientError):
    """Raised when output operations fail."""
    pass


class ConfigurationError(QRLClientError):
    """Raised when client configuration is invalid."""
    pass


class ReconstructionError(QRLClientError):
    """Raised when data reconstruction fails."""
    pass


class TimeoutError(QRLClientError):
    """Raised when operations timeout."""
    pass


class MonitorError(QRLClientError):
    """Raised when monitor/display operations fail."""
    pass


class FrameProcessingError(QRLClientError):
    """Raised when frame processing fails."""
    pass


# Error severity levels
class ErrorSeverity:
    """Error severity levels for logging and user feedback."""
    CRITICAL = "critical"  # Application cannot continue
    ERROR = "error"        # Operation failed but application can continue
    WARNING = "warning"    # Potential issue that might affect quality
    INFO = "info"         # Informational message
    DEBUG = "debug"       # Debug information


class QRLClientErrorHandler:
    """Central error handling and logging utility for client operations."""

    def __init__(self, log_callback=None):
        """
        Initialize error handler.

        Args:
            log_callback: Optional callback function for logging messages
        """
        self.log_callback = log_callback

    def log_error(self, error: Exception, severity: str = ErrorSeverity.ERROR,
                  context: str = None):
        """
        Log an error with context information.

        Args:
            error: The exception that occurred
            severity: Error severity level
            context: Additional context about where the error occurred
        """
        if isinstance(error, QRLClientError):
            message = str(error)
        else:
            message = f"{type(error).__name__}: {str(error)}"

        if context:
            message = f"[{context}] {message}"

        if self.log_callback:
            self.log_callback(f"{severity.upper()}: {message}")

    def handle_capture_error(self, operation: str,
                           original_error: Exception = None) -> CaptureError:
        """
        Create and log a capture error.

        Args:
            operation: Description of the capture operation that failed
            original_error: The original exception that caused this error

        Returns:
            CaptureError instance
        """
        details = None
        if original_error:
            details = f"Original error: {type(original_error).__name__}: {original_error}"

        error = CaptureError(
            f"Screen capture failed during {operation}",
            details=details
        )

        self.log_error(error, ErrorSeverity.ERROR, "Capture")
        return error

    def handle_decoding_error(self, stage: str,
                            original_error: Exception = None) -> DecodingError:
        """
        Create and log a decoding error.

        Args:
            stage: The stage of decoding where the error occurred
            original_error: The original exception that caused this error

        Returns:
            DecodingError instance
        """
        details = None
        if original_error:
            details = f"Original error: {type(original_error).__name__}: {original_error}"

        error = DecodingError(
            f"Decoding failed during {stage}",
            details=details
        )

        self.log_error(error, ErrorSeverity.ERROR, "Decoding")
        return error

    def handle_qr_read_error(self, frame_info: str = None,
                           original_error: Exception = None) -> QRReadError:
        """
        Create and log a QR reading error.

        Args:
            frame_info: Information about the frame that failed to read
            original_error: The original exception that caused this error

        Returns:
            QRReadError instance
        """
        details = None
        if original_error:
            details = f"Original error: {type(original_error).__name__}: {original_error}"

        frame_desc = f" from {frame_info}" if frame_info else ""
        error = QRReadError(
            f"Failed to read QR code{frame_desc}",
            details=details
        )

        self.log_error(error, ErrorSeverity.WARNING, "QR Reading")
        return error

    def handle_output_error(self, file_path: str, operation: str,
                          original_error: Exception = None) -> OutputError:
        """
        Create and log an output error.

        Args:
            file_path: Path to the output file
            operation: Description of the operation that failed
            original_error: The original exception that caused this error

        Returns:
            OutputError instance
        """
        details = None
        if original_error:
            details = f"Original error: {type(original_error).__name__}: {original_error}"

        error = OutputError(
            f"Failed to {operation} output file: {file_path}",
            details=details
        )

        self.log_error(error, ErrorSeverity.ERROR, "Output")
        return error

    def handle_reconstruction_error(self, chunk_info: str = None,
                                  original_error: Exception = None) -> ReconstructionError:
        """
        Create and log a data reconstruction error.

        Args:
            chunk_info: Information about the chunk that failed
            original_error: The original exception that caused this error

        Returns:
            ReconstructionError instance
        """
        details = None
        if original_error:
            details = f"Original error: {type(original_error).__name__}: {original_error}"

        chunk_desc = f" for {chunk_info}" if chunk_info else ""
        error = ReconstructionError(
            f"Data reconstruction failed{chunk_desc}",
            details=details
        )

        self.log_error(error, ErrorSeverity.ERROR, "Reconstruction")
        return error

    def handle_monitor_error(self, monitor_id: int = None,
                           original_error: Exception = None) -> MonitorError:
        """
        Create and log a monitor error.

        Args:
            monitor_id: ID of the monitor that caused the error
            original_error: The original exception that caused this error

        Returns:
            MonitorError instance
        """
        details = None
        if original_error:
            details = f"Original error: {type(original_error).__name__}: {original_error}"

        monitor_desc = f" {monitor_id}" if monitor_id is not None else ""
        error = MonitorError(
            f"Monitor{monitor_desc} access failed",
            details=details
        )

        self.log_error(error, ErrorSeverity.ERROR, "Monitor")
        return error

    def safe_execute(self, operation, *args, **kwargs):
        """
        Execute an operation with comprehensive error handling.

        Args:
            operation: Function to execute
            *args: Arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the operation or None if it failed

        Raises:
            QRLClientError: If the operation fails and cannot be handled
        """
        try:
            return operation(*args, **kwargs)
        except QRLClientError:
            # Re-raise QRL client errors as-is
            raise
        except MemoryError as e:
            raise QRLClientError("Insufficient memory for operation",
                                details="Try reducing buffer sizes or image resolution")
        except PermissionError as e:
            raise CaptureError("Permission denied for screen capture",
                             details="Check screen recording permissions")
        except FileNotFoundError as e:
            raise OutputError(f"Output location not found: {e}")
        except OSError as e:
            raise QRLClientError(f"System error: {e}")
        except ImportError as e:
            raise QRLClientError("Missing required dependency",
                                details=f"Please install: {e}")
        except Exception as e:
            # Log unexpected errors and re-raise as QRLClientError
            self.log_error(e, ErrorSeverity.CRITICAL, "Unexpected Error")
            raise QRLClientError(f"Unexpected error: {type(e).__name__}",
                                details=str(e))

    def is_recoverable_error(self, error: Exception) -> bool:
        """
        Determine if an error is recoverable.

        Args:
            error: The error to check

        Returns:
            True if the error might be recoverable with retry
        """
        recoverable_errors = (
            QRReadError,      # QR reading can be retried
            CaptureError,     # Screen capture can be retried
            FrameProcessingError,  # Frame processing can be retried
        )

        # Some specific errors are not recoverable
        non_recoverable_messages = [
            "permission denied",
            "insufficient memory",
            "file not found",
            "invalid configuration",
        ]

        if isinstance(error, recoverable_errors):
            error_message = str(error).lower()
            for non_recoverable in non_recoverable_messages:
                if non_recoverable in error_message:
                    return False
            return True

        return False


def with_client_error_handling(log_callback=None):
    """
    Decorator for adding comprehensive error handling to client functions.

    Args:
        log_callback: Optional callback for logging errors

    Returns:
        Decorated function with error handling
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            handler = QRLClientErrorHandler(log_callback)
            return handler.safe_execute(func, *args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


def validate_output_path(path: str) -> None:
    """
    Validate an output file path.

    Args:
        path: Output file path to validate

    Raises:
        ConfigurationError: If validation fails
    """
    from pathlib import Path

    if not path:
        raise ConfigurationError("Output file path cannot be empty")

    path_obj = Path(path)

    # Check if parent directory exists
    parent_dir = path_obj.parent
    if not parent_dir.exists():
        raise ConfigurationError(f"Output directory does not exist: {parent_dir}")

    # Check if parent directory is writable
    if not os.access(parent_dir, os.W_OK):
        raise ConfigurationError(f"Output directory is not writable: {parent_dir}")

    # If file already exists, check if it's writable
    if path_obj.exists() and not os.access(path_obj, os.W_OK):
        raise ConfigurationError(f"Output file is not writable: {path}")


def validate_region(region: tuple) -> None:
    """
    Validate a capture region tuple.

    Args:
        region: Region tuple (x, y, width, height)

    Raises:
        ConfigurationError: If validation fails
    """
    if not isinstance(region, (tuple, list)) or len(region) != 4:
        raise ConfigurationError("Region must be a 4-tuple (x, y, width, height)")

    x, y, width, height = region

    for i, (name, value) in enumerate([("x", x), ("y", y), ("width", width), ("height", height)]):
        if not isinstance(value, int) or value < 0:
            raise ConfigurationError(f"Region {name} must be a non-negative integer, got: {value}")

    if width == 0 or height == 0:
        raise ConfigurationError("Region width and height must be positive")


def validate_monitor_index(monitor_index: int, max_monitors: int = None) -> None:
    """
    Validate a monitor index.

    Args:
        monitor_index: Monitor index to validate
        max_monitors: Maximum number of available monitors (optional)

    Raises:
        ConfigurationError: If validation fails
    """
    if not isinstance(monitor_index, int) or monitor_index < 0:
        raise ConfigurationError("Monitor index must be a non-negative integer")

    if max_monitors is not None and monitor_index >= max_monitors:
        raise ConfigurationError(f"Monitor index {monitor_index} exceeds available monitors (0-{max_monitors-1})")