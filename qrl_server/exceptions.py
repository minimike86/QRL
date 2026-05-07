#!/usr/bin/env python3
"""
QRL Server Custom Exceptions
Custom exception classes for better error handling and user feedback.
"""


class QRLError(Exception):
    """Base exception class for all QRL-related errors."""

    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message}\nDetails: {self.details}"
        return self.message


class ValidationError(QRLError):
    """Raised when validation fails."""
    pass


class EncodingError(QRLError):
    """Raised when encoding fails."""
    pass


class FileError(QRLError):
    """Raised when file operations fail."""
    pass


class QRGenerationError(QRLError):
    """Raised when QR code generation fails."""
    pass


class DisplayError(QRLError):
    """Raised when display operations fail."""
    pass


class ConfigurationError(QRLError):
    """Raised when configuration is invalid."""
    pass


class ChunkingError(QRLError):
    """Raised when data chunking fails."""
    pass


class ResourceError(QRLError):
    """Raised when system resources are insufficient."""
    pass


class TimeoutError(QRLError):
    """Raised when operations timeout."""
    pass


# Error severity levels
class ErrorSeverity:
    """Error severity levels for logging and user feedback."""
    CRITICAL = "critical"  # Application cannot continue
    ERROR = "error"        # Operation failed but application can continue
    WARNING = "warning"    # Potential issue that might affect quality
    INFO = "info"         # Informational message
    DEBUG = "debug"       # Debug information


class QRLErrorHandler:
    """Central error handling and logging utility."""

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
        if isinstance(error, QRLError):
            message = str(error)
        else:
            message = f"{type(error).__name__}: {str(error)}"

        if context:
            message = f"[{context}] {message}"

        if self.log_callback:
            self.log_callback(f"{severity.upper()}: {message}")

    def handle_file_error(self, file_path: str, operation: str,
                         original_error: Exception = None) -> FileError:
        """
        Create and log a file operation error.

        Args:
            file_path: Path to the file that caused the error
            operation: Description of the operation that failed
            original_error: The original exception that caused this error

        Returns:
            FileError instance
        """
        details = None
        if original_error:
            details = f"Original error: {type(original_error).__name__}: {original_error}"

        error = FileError(
            f"Failed to {operation} file: {file_path}",
            details=details
        )

        self.log_error(error, ErrorSeverity.ERROR, "File Operation")
        return error

    def handle_validation_error(self, field: str, value: any,
                               expected: str) -> ValidationError:
        """
        Create and log a validation error.

        Args:
            field: Name of the field that failed validation
            value: The invalid value
            expected: Description of what was expected

        Returns:
            ValidationError instance
        """
        error = ValidationError(
            f"Validation failed for {field}",
            details=f"Got: {value}, Expected: {expected}"
        )

        self.log_error(error, ErrorSeverity.ERROR, "Validation")
        return error

    def handle_encoding_error(self, stage: str,
                             original_error: Exception = None) -> EncodingError:
        """
        Create and log an encoding error.

        Args:
            stage: The stage of encoding where the error occurred
            original_error: The original exception that caused this error

        Returns:
            EncodingError instance
        """
        details = None
        if original_error:
            details = f"Original error: {type(original_error).__name__}: {original_error}"

        error = EncodingError(
            f"Encoding failed during {stage}",
            details=details
        )

        self.log_error(error, ErrorSeverity.ERROR, "Encoding")
        return error

    def handle_resource_error(self, resource: str,
                             requirement: str) -> ResourceError:
        """
        Create and log a resource error.

        Args:
            resource: The resource that is insufficient
            requirement: What is required

        Returns:
            ResourceError instance
        """
        error = ResourceError(
            f"Insufficient {resource}",
            details=f"Required: {requirement}"
        )

        self.log_error(error, ErrorSeverity.CRITICAL, "Resources")
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
            QRLError: If the operation fails and cannot be handled
        """
        try:
            return operation(*args, **kwargs)
        except QRLError:
            # Re-raise QRL errors as-is
            raise
        except MemoryError as e:
            raise self.handle_resource_error("memory", "More RAM available")
        except PermissionError as e:
            raise self.handle_file_error(str(e), "access due to permissions", e)
        except FileNotFoundError as e:
            raise self.handle_file_error(str(e), "find", e)
        except OSError as e:
            raise self.handle_file_error(str(e), "perform OS operation on", e)
        except ValueError as e:
            raise ValidationError(f"Invalid value: {e}")
        except Exception as e:
            # Log unexpected errors and re-raise as QRLError
            self.log_error(e, ErrorSeverity.CRITICAL, "Unexpected Error")
            raise QRLError(f"Unexpected error: {type(e).__name__}", details=str(e))


def with_error_handling(log_callback=None):
    """
    Decorator for adding comprehensive error handling to functions.

    Args:
        log_callback: Optional callback for logging errors

    Returns:
        Decorated function with error handling
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            handler = QRLErrorHandler(log_callback)
            return handler.safe_execute(func, *args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


def validate_file_path(path: str, must_exist: bool = True,
                      must_be_readable: bool = True) -> None:
    """
    Validate a file path with comprehensive checks.

    Args:
        path: File path to validate
        must_exist: Whether the file must exist
        must_be_readable: Whether the file must be readable

    Raises:
        ValidationError: If validation fails
    """
    from pathlib import Path

    if not path:
        raise ValidationError("File path cannot be empty")

    path_obj = Path(path)

    if must_exist and not path_obj.exists():
        raise ValidationError(f"File does not exist: {path}")

    if path_obj.exists():
        if not path_obj.is_file():
            raise ValidationError(f"Path is not a file: {path}")

        if must_be_readable:
            try:
                with open(path, 'rb') as f:
                    f.read(1)  # Try to read one byte
            except PermissionError:
                raise ValidationError(f"File is not readable: {path}")
            except Exception as e:
                raise ValidationError(f"Cannot access file: {path}", details=str(e))


def validate_positive_integer(value: any, name: str, min_value: int = 1,
                             max_value: int = None) -> int:
    """
    Validate a positive integer value.

    Args:
        value: Value to validate
        name: Name of the field for error messages
        min_value: Minimum allowed value (default: 1)
        max_value: Maximum allowed value (optional)

    Returns:
        Validated integer value

    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise ValidationError(f"{name} must be an integer",
                                details=f"Got: {type(value).__name__}")

    if value < min_value:
        raise ValidationError(f"{name} must be at least {min_value}",
                            details=f"Got: {value}")

    if max_value is not None and value > max_value:
        raise ValidationError(f"{name} must be at most {max_value}",
                            details=f"Got: {value}")

    return value


def validate_choice(value: any, name: str, choices: list) -> any:
    """
    Validate that a value is one of the allowed choices.

    Args:
        value: Value to validate
        name: Name of the field for error messages
        choices: List of allowed choices

    Returns:
        Validated value

    Raises:
        ValidationError: If validation fails
    """
    if value not in choices:
        raise ValidationError(f"{name} must be one of {choices}",
                            details=f"Got: {value}")

    return value