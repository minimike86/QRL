#!/usr/bin/env python3
"""
Simple test script to decode QR images directly from files.
"""

import sys
from pathlib import Path
from PIL import Image

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from qrl_client import QRLDecoder


def test_decode_qr_images(qr_dir: str, output_file: str):
    """Test decoding QR images from a directory."""
    qr_path = Path(qr_dir)
    if not qr_path.exists():
        print(f"Error: QR directory '{qr_dir}' not found")
        return False

    # Get all QR image files
    qr_files = sorted(qr_path.glob("*.png"))
    if not qr_files:
        print(f"Error: No PNG files found in '{qr_dir}'")
        return False

    print(f"Found {len(qr_files)} QR image files")

    # Create decoder
    decoder = QRLDecoder(output_file, timeout=60)

    # Load images
    images = []
    for qr_file in qr_files:
        try:
            img = Image.open(qr_file)
            images.append(img)
            print(f"Loaded: {qr_file.name}")
        except Exception as e:
            print(f"Error loading {qr_file.name}: {e}")

    if not images:
        print("Error: No valid images loaded")
        return False

    print(f"\nAttempting to decode {len(images)} QR codes...")

    # Try to decode
    success = decoder.decode(images)

    # Show results
    if success:
        print("SUCCESS: Successfully decoded!")
        print(f"Output saved to: {output_file}")

        # Show file size comparison
        output_path = Path(output_file)
        if output_path.exists():
            size = output_path.stat().st_size
            print(f"Decoded file size: {size} bytes")
    else:
        print("FAILED: Decoding failed or incomplete")
        progress = decoder.get_progress()
        print(f"Progress: {progress.get('percentage', 0):.1f}%")

        missing = decoder.get_missing_chunks()
        if missing:
            print(f"Missing chunks: {missing}")

    return success


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_decode.py <qr_directory> <output_file>")
        print("Example: python test_decode.py qr_output decoded_test.txt")
        sys.exit(1)

    qr_dir = sys.argv[1]
    output_file = sys.argv[2]

    success = test_decode_qr_images(qr_dir, output_file)
    sys.exit(0 if success else 1)