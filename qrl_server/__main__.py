#!/usr/bin/env python3
"""
QRL Server CLI
Command-line interface for the QRL server.
"""

import sys
import argparse
from pathlib import Path

from .encoder import QRLEncoder
from .display import DisplayHandler
from .config import ServerConfig, ConfigManager
from .exceptions import QRLError, ValidationError, QRLErrorHandler


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="QRL Server - Encode files as QR codes and display them",
        prog="qrl-server",
        epilog="Configuration files are searched in the current directory and ~/.qrl/"
    )

    # Required arguments
    parser.add_argument(
        "file",
        nargs="?",
        help="Path to file or directory to encode"
    )

    # Configuration file arguments
    parser.add_argument(
        "--config",
        "-c",
        metavar="FILE",
        help="Path to configuration file (YAML/JSON)"
    )

    parser.add_argument(
        "--save-config",
        metavar="FILE",
        help="Save current settings to configuration file and exit"
    )

    parser.add_argument(
        "--create-config",
        metavar="FILE",
        help="Create example configuration file and exit"
    )

    # Encoding arguments
    parser.add_argument(
        "--chunk-size",
        type=int,
        help="Chunk size in bytes (default from config: 1024)"
    )

    parser.add_argument(
        "--error-correction",
        choices=["L", "M", "Q", "H"],
        help="QR error correction level (default from config: Q)"
    )

    parser.add_argument(
        "--qr-version",
        type=int,
        choices=range(1, 41),
        help="QR code version 1-40 (default: auto-detect)"
    )

    # Display arguments
    parser.add_argument(
        "--duration",
        type=float,
        help="Display duration per QR code in seconds (default from config: 2.0)"
    )

    parser.add_argument(
        "--no-repeat",
        action="store_true",
        help="Don't repeat the QR sequence"
    )

    parser.add_argument(
        "--repeat",
        action="store_true",
        help="Repeat the QR sequence (overrides config)"
    )

    parser.add_argument(
        "--window-title",
        help="Window title for display (default from config: 'QRL Server')"
    )

    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Display in fullscreen mode"
    )

    # Output arguments
    parser.add_argument(
        "--save-qr",
        metavar="DIR",
        help="Save QR images to directory (optional)"
    )

    parser.add_argument(
        "--output-format",
        choices=["PNG", "JPEG", "BMP"],
        help="Output format for saved QR images (default: PNG)"
    )

    # GUI mode
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch GUI mode"
    )

    # Verbose mode
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    # Initialize error handler
    error_handler = QRLErrorHandler(
        log_callback=lambda msg: print(msg) if args.verbose else None
    )

    try:
        # Handle special commands first
        if args.create_config:
            ConfigManager.create_example_config(args.create_config)
            print(f"Example configuration file created: {args.create_config}")
            return

        if args.gui:
            # Launch GUI mode
            from .gui import QRLServerGUI
            app = QRLServerGUI()
            app.run()
            return

        # Load configuration
        try:
            config = ConfigManager.load_config(args.config)
            if args.verbose:
                config_source = args.config if args.config else "default locations"
                print(f"Configuration loaded from: {config_source}")
        except Exception as e:
            error_handler.log_error(e, "warning", "Configuration")
            config = ServerConfig()  # Use defaults

        # Override config with command-line arguments
        if args.chunk_size is not None:
            config.chunk_size = args.chunk_size
        if args.duration is not None:
            config.duration = args.duration
        if args.error_correction is not None:
            config.error_correction = args.error_correction
        if args.qr_version is not None:
            config.qr_version = args.qr_version
        if args.window_title is not None:
            config.window_title = args.window_title
        if args.save_qr is not None:
            config.save_qr = args.save_qr
        if args.output_format is not None:
            config.output_format = args.output_format
        if args.fullscreen:
            config.fullscreen = args.fullscreen

        # Handle repeat options
        if args.repeat:
            config.repeat = True
        elif args.no_repeat:
            config.repeat = False

        # Validate configuration
        try:
            config.validate()
        except ValueError as e:
            print(f"Configuration error: {e}", file=sys.stderr)
            sys.exit(1)

        # Save configuration if requested
        if args.save_config:
            try:
                ConfigManager.save_config(config, args.save_config)
                print(f"Configuration saved to: {args.save_config}")
                return
            except Exception as e:
                print(f"Error saving configuration: {e}", file=sys.stderr)
                sys.exit(1)

        # Verify file argument
        if not args.file:
            parser.error("file argument is required (unless using --gui, --create-config, or --save-config)")

        if not Path(args.file).exists():
            print(f"Error: File '{args.file}' not found", file=sys.stderr)
            sys.exit(1)

        # Display configuration summary
        print(f"QRL Server - QR Code Data Transfer")
        print(f"Source: {args.file}")
        print(f"Configuration:")
        print(f"  Chunk size: {config.chunk_size} bytes")
        print(f"  Display duration: {config.duration} seconds")
        print(f"  Error correction: {config.error_correction}")
        print(f"  QR version: {config.qr_version or 'auto-detect'}")
        print(f"  Repeat: {'Yes' if config.repeat else 'No'}")
        print(f"  Window title: {config.window_title}")
        if config.fullscreen:
            print(f"  Display mode: Fullscreen")

        # Create encoder
        print("\nInitializing encoder...")
        encoder = QRLEncoder(
            args.file,
            chunk_size=config.chunk_size,
            error_correction=config.error_correction
        )

        if not encoder.validate():
            raise ValidationError(f"File validation failed: {args.file}")

        # Generate QR codes
        print("Generating QR codes...")
        qr_images = encoder.encode()

        # Get metadata
        metadata = encoder.get_metadata()
        print(f"\nEncoding complete:")
        print(f"  Total chunks: {metadata['total_chunks']}")
        print(f"  Total size: {metadata['total_size']} bytes")
        print(f"  Actual QR version: {metadata['qr_version']}")

        # Save QR images if requested
        if config.save_qr:
            print(f"\nSaving QR images to: {config.save_qr}")
            try:
                saved_paths = encoder.save_qr_images(config.save_qr)
                print(f"Saved {len(saved_paths)} QR images ({config.output_format} format)")
            except Exception as e:
                error_handler.log_error(e, "warning", "QR Save")
                print(f"Warning: Failed to save QR images: {e}")

        # Create display handler
        print(f"\nStarting display (press Ctrl+C to stop)...")
        display = DisplayHandler(
            qr_images,
            duration=config.duration,
            repeat=config.repeat,
            window_title=config.window_title
        )

        # Start display
        display.start()

    except KeyboardInterrupt:
        print("\n\nDisplay stopped by user")
        sys.exit(0)
    except QRLError as e:
        print(f"\nQRL Error: {e}", file=sys.stderr)
        if args.verbose and e.details:
            print(f"Details: {e.details}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error_handler.log_error(e, "critical", "Main")
        print(f"\nUnexpected error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()