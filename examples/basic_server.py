#!/usr/bin/env python3
"""
Basic QRL Server Example

This example demonstrates how to encode a file into QR codes
and display them on screen.
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from qrl_server import QRLEncoder, DisplayHandler


def main():
    parser = argparse.ArgumentParser(
        description="Basic QRL Server - Encode files as QR codes"
    )
    parser.add_argument(
        "file",
        help="Path to file to encode"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1024,
        help="Chunk size in bytes (default: 1024)"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=2.0,
        help="Display duration per QR code in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--error-correction",
        default="Q",
        choices=["L", "M", "Q", "H"],
        help="QR error correction level (default: Q)"
    )

    args = parser.parse_args()

    # Verify file exists
    if not Path(args.file).exists():
        print(f"Error: File '{args.file}' not found")
        sys.exit(1)

    print(f"Encoding file: {args.file}")
    print(f"Chunk size: {args.chunk_size} bytes")
    print(f"Display duration: {args.duration} seconds")
    print(f"Error correction: {args.error_correction}")

    try:
        # Create encoder
        encoder = QRLEncoder(
            args.file,
            chunk_size=args.chunk_size,
            error_correction=args.error_correction
        )

        # Generate QR codes
        print("\nGenerating QR codes...")
        qr_images = encoder.encode()

        # Get metadata
        metadata = encoder.get_metadata()
        print(f"\nEncoding complete:")
        print(f"  Total chunks: {metadata['total_chunks']}")
        print(f"  Total size: {metadata['total_size']} bytes")
        print(f"  QR version: {metadata['qr_version']}")

        # Create display handler
        print(f"\nStarting display (press Ctrl+C to stop)...")
        display = DisplayHandler(
            qr_images,
            duration=args.duration,
            repeat=True,
            window_title="QRL Server"
        )

        # Start display
        display.start()

    except KeyboardInterrupt:
        print("\n\nDisplay stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
