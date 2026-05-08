#!/usr/bin/env python3
"""
QRL Client CLI
Command-line interface for the QRL client.
"""

import sys
import time
import argparse
from pathlib import Path

from .decoder import QRLDecoder
from .capture import CaptureHandler
from .config import ClientConfig, ClientConfigManager
from .exceptions import QRLClientError, ConfigurationError, QRLClientErrorHandler


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="QRL Client - Capture and decode QR codes from screen",
        prog="qrl-client",
        epilog="Configuration files are searched in the current directory and ~/.qrl/"
    )

    # Required arguments
    parser.add_argument(
        "--output",
        help="Output file path for decoded data"
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

    # Capture settings
    parser.add_argument(
        "--monitor",
        type=int,
        help="Monitor index (default from config: 0 = primary)"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        help="Timeout in seconds (default from config: 300)"
    )

    parser.add_argument(
        "--interval",
        type=float,
        help="Capture interval in seconds (default from config: 0.5)"
    )

    parser.add_argument(
        "--region",
        metavar="X,Y,W,H",
        help="Capture region as x,y,width,height (default: full screen)"
    )

    # Processing settings
    parser.add_argument(
        "--progress-interval",
        type=float,
        help="Progress report interval in seconds (default from config: 5.0)"
    )

    parser.add_argument(
        "--save-progress",
        action="store_true",
        help="Save progress periodically for recovery"
    )

    parser.add_argument(
        "--max-decode-attempts",
        type=int,
        help="Maximum decode attempts per frame (default from config: 5)"
    )

    parser.add_argument(
        "--detection-threshold",
        type=float,
        help="QR detection threshold 0.0-1.0 (default from config: 0.3)"
    )

    # Image processing settings
    parser.add_argument(
        "--no-preprocessing",
        action="store_true",
        help="Disable image preprocessing"
    )

    parser.add_argument(
        "--no-contrast",
        action="store_true",
        help="Disable contrast enhancement"
    )

    parser.add_argument(
        "--no-noise-reduction",
        action="store_true",
        help="Disable noise reduction"
    )

    # GUI mode
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch GUI mode"
    )

    # Output settings
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # Initialize error handler
    error_handler = QRLClientErrorHandler(
        log_callback=lambda msg: print(msg) if args.verbose else None
    )

    try:
        # Handle special commands first
        if args.create_config:
            ClientConfigManager.create_example_config(args.create_config)
            print(f"Example configuration file created: {args.create_config}")
            return

        if args.gui:
            # Launch GUI mode
            from .gui import QRLClientGUI
            app = QRLClientGUI()
            app.run()
            return

        # Load configuration
        try:
            config = ClientConfigManager.load_config(args.config)
            if args.verbose:
                config_source = args.config if args.config else "default locations"
                print(f"Configuration loaded from: {config_source}")
        except Exception as e:
            error_handler.log_error(e, "warning", "Configuration")
            config = ClientConfig()  # Use defaults

        # Override config with command-line arguments
        if args.output is not None:
            # This is handled separately since it's required
            pass
        if args.monitor is not None:
            config.monitor = args.monitor
        if args.timeout is not None:
            config.timeout = args.timeout
        if args.interval is not None:
            config.interval = args.interval
        if args.progress_interval is not None:
            config.progress_interval = args.progress_interval
        if args.max_decode_attempts is not None:
            config.max_decode_attempts = args.max_decode_attempts
        if args.detection_threshold is not None:
            config.qr_detection_threshold = args.detection_threshold
        if args.save_progress:
            config.save_progress = True

        # Handle preprocessing flags
        if args.no_preprocessing:
            config.image_preprocessing = False
        if args.no_contrast:
            config.enhance_contrast = False
        if args.no_noise_reduction:
            config.noise_reduction = False

        # Parse region if provided
        if args.region:
            try:
                parts = [int(x.strip()) for x in args.region.split(',')]
                if len(parts) != 4:
                    raise ValueError("Region must have 4 components")
                config.region = tuple(parts)
            except ValueError as e:
                print(f"Error: Invalid region format. Use: x,y,width,height ({e})", file=sys.stderr)
                sys.exit(1)

        # Validate configuration
        try:
            config.validate()
        except ValueError as e:
            print(f"Configuration error: {e}", file=sys.stderr)
            sys.exit(1)

        # Save configuration if requested
        if args.save_config:
            try:
                ClientConfigManager.save_config(config, args.save_config)
                print(f"Configuration saved to: {args.save_config}")
                return
            except Exception as e:
                print(f"Error saving configuration: {e}", file=sys.stderr)
                sys.exit(1)

        # Check for required output argument
        if not args.output:
            parser.error("--output is required (unless using --gui, --create-config, or --save-config)")

        # Validate output path
        try:
            from .exceptions import validate_output_path
            validate_output_path(args.output)
        except ConfigurationError as e:
            print(f"Output path error: {e}", file=sys.stderr)
            sys.exit(1)

        # Display configuration summary
        print("QRL Client - QR Code Decoder")
        print(f"Output file: {args.output}")
        print(f"Configuration:")
        print(f"  Monitor: {config.monitor}")
        print(f"  Timeout: {config.timeout} seconds")
        print(f"  Capture interval: {config.interval} seconds")
        if config.region:
            x, y, w, h = config.region
            print(f"  Capture region: {x},{y} ({w}x{h})")
        else:
            print(f"  Capture region: Full screen")
        print(f"  Detection threshold: {config.qr_detection_threshold}")
        print(f"  Image preprocessing: {'Yes' if config.image_preprocessing else 'No'}")
        print(f"  Progress interval: {config.progress_interval} seconds")

        # Create capture handler
        print("\nInitializing screen capture...")
        capture = CaptureHandler(
            monitor=config.monitor,
            region=config.region,
            interval=config.interval
        )

        # Create decoder
        print("Initializing decoder...")
        decoder = QRLDecoder(
            args.output,
            timeout=config.timeout
        )

        # Start capturing
        print("Starting capture... (press Ctrl+C to stop)")
        capture.start()

        start_time = time.time()
        last_progress_time = 0

        # Capture and decode loop
        while time.time() - start_time < config.timeout:
            # Get captured frames
            frames = capture.get_frames()

            if frames:
                # Attempt to decode
                if decoder.decode(frames):
                    print(f"\n[OK] Successfully decoded!")
                    print(f"Output file: {args.output}")
                    break

                # Show progress periodically
                current_time = time.time()
                if current_time - last_progress_time >= config.progress_interval:
                    progress = decoder.get_progress()

                    if progress.get('total_chunks', 0) > 0:
                        print(f"\nProgress: {progress['percentage']:.1f}% "
                              f"({progress['decoded_chunks']}/{progress['total_chunks']} chunks)")

                        if args.verbose:
                            stats = decoder.get_statistics()
                            print(f"  Frames processed: {stats['total_frames_processed']}")
                            print(f"  QR read success rate: {stats['qr_read_success_rate']:.1f}%")
                            print(f"  Time since last chunk: {stats['time_since_last_chunk']:.1f}s")

                        # Save progress if requested
                        if config.save_progress:
                            decoder.save_partial_progress()

                    last_progress_time = current_time

            time.sleep(0.1)  # Reduced sleep time for better responsiveness

        else:
            # Timeout reached
            print("\n[!] Timeout reached")
            stats = decoder.get_statistics()
            print(f"Final progress: {stats['completion_percentage']:.1f}%")

            missing = decoder.get_missing_chunks()
            if missing and len(missing) <= 10:  # Show up to 10 missing chunks
                print(f"Missing chunks: {missing}")
            elif missing:
                print(f"Missing {len(missing)} chunks")

            if args.verbose:
                print(f"\nFinal statistics:")
                print(f"  Frames processed: {stats['total_frames_processed']}")
                print(f"  QR codes read: {stats['successful_qr_reads']}")
                print(f"  Success rate: {stats['qr_read_success_rate']:.1f}%")

        capture.stop()

    except KeyboardInterrupt:
        print("\n\nCapture stopped by user")
        if 'capture' in locals():
            capture.stop()

        # Show final progress
        if 'decoder' in locals():
            stats = decoder.get_statistics()
            print(f"Final progress: {stats['completion_percentage']:.1f}%")

        sys.exit(0)
    except QRLClientError as e:
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