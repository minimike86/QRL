#!/usr/bin/env python3
"""
Basic QRL Client Example

This example demonstrates how to capture QR codes from screen
and decode them back into the original file.
"""

import sys
import time
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from qrl_client import QRLDecoder, CaptureHandler


def main():
    parser = argparse.ArgumentParser(
        description="Basic QRL Client - Capture and decode QR codes"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path for decoded data"
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=0,
        help="Monitor index (default: 0 = primary)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout in seconds (default: 300)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Capture interval in seconds (default: 0.5)"
    )

    args = parser.parse_args()

    print("QRL Client - QR Code Decoder")
    print(f"Output file: {args.output}")
    print(f"Monitor: {args.monitor}")
    print(f"Timeout: {args.timeout} seconds")
    print(f"Capture interval: {args.interval} seconds")

    try:
        # Create capture handler
        print("\nInitializing screen capture...")
        capture = CaptureHandler(
            monitor=args.monitor,
            interval=args.interval
        )

        # Create decoder
        print("Initializing decoder...")
        decoder = QRLDecoder(
            args.output,
            timeout=args.timeout
        )

        # Start capturing
        print("Starting capture... (press Ctrl+C to stop)")
        capture.start()

        start_time = time.time()
        last_progress = None

        # Capture and decode loop
        while time.time() - start_time < args.timeout:
            # Get captured frames
            frames = capture.get_frames()

            if frames:
                # Attempt to decode
                if decoder.decode(frames):
                    print(f"\n✓ Successfully decoded!")
                    print(f"Output file: {args.output}")
                    break

                # Show progress
                progress = decoder.get_progress()
                if progress != last_progress:
                    print(f"Progress: {progress['percentage']:.1f}% "
                          f"({progress['decoded_chunks']}/{progress['total_chunks']})")
                    last_progress = progress

            time.sleep(1)

        else:
            # Timeout reached
            print("\n✗ Timeout reached")
            progress = decoder.get_progress()
            print(f"Final progress: {progress['percentage']:.1f}%")

            missing = decoder.get_missing_chunks()
            if missing:
                print(f"Missing chunks: {missing}")

        capture.stop()

    except KeyboardInterrupt:
        print("\n\nCapture stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
