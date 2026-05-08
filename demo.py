#!/usr/bin/env python3
"""
QRL Demo Script
Demonstrates the complete QRL encoding and decoding pipeline.
"""

import tempfile
import sys
import hashlib
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from qrl_server import QRLEncoder
from qrl_client import QRLDecoder


def create_demo_file(size_kb: int = 5) -> str:
    """Create a demo file with specified size."""
    content = []
    content.append("QRL Demo File")
    content.append("=" * 50)
    content.append("")
    content.append("This file demonstrates the QRL (QR Code Data Exfiltration) system.")
    content.append("")
    content.append("QRL can encode any file into a sequence of QR codes that can be")
    content.append("displayed on screen and captured by another device.")
    content.append("")
    content.append("Technical details:")
    content.append("- Data is chunked into small pieces")
    content.append("- Each chunk is encoded with sequence numbers and checksums")
    content.append("- QR codes are generated for each chunk")
    content.append("- The sequence can be displayed and captured")
    content.append("")

    # Add padding to reach desired size
    base_content = "\n".join(content)
    current_size = len(base_content.encode('utf-8'))
    target_size = size_kb * 1024

    if current_size < target_size:
        padding_needed = target_size - current_size
        padding_lines = padding_needed // 80  # ~80 chars per line

        content.append("Padding data to reach target size:")
        content.append("-" * 40)

        for i in range(padding_lines):
            line = f"Line {i+1:04d}: " + "A" * 70
            content.append(line)

    final_content = "\n".join(content)

    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as tmp_file:
        tmp_file.write(final_content)
        return tmp_file.name


def main():
    """Run the demo."""
    print("QRL (QR Code Data Exfiltration) Demo")
    print("=" * 50)

    # Create demo file
    print("\n1. Creating demo file...")
    demo_file = create_demo_file(3)  # 3KB file
    file_size = Path(demo_file).stat().st_size
    print(f"   Created demo file: {demo_file}")
    print(f"   File size: {file_size} bytes")

    # Calculate file hash for verification
    original_hash = hashlib.md5(Path(demo_file).read_bytes()).hexdigest()
    print(f"   Original MD5: {original_hash}")

    try:
        # Encode the file
        print("\n2. Encoding file to QR codes...")
        encoder = QRLEncoder(demo_file, chunk_size=200)

        if not encoder.validate():
            print("   ERROR: File validation failed")
            return False

        qr_images = encoder.encode()
        metadata = encoder.get_metadata()

        print(f"   Encoding complete:")
        print(f"   - Total chunks: {metadata['total_chunks']}")
        print(f"   - QR version: {metadata['qr_version']}")
        print(f"   - Generated {len(qr_images)} QR codes")

        # Save QR images for inspection
        with tempfile.TemporaryDirectory() as tmp_dir:
            qr_dir = Path(tmp_dir) / "qr_codes"
            qr_dir.mkdir()
            saved_paths = encoder.save_qr_images(str(qr_dir))
            print(f"   - Saved QR images to: {qr_dir}")

            # Decode the QR codes
            print("\n3. Decoding QR codes back to file...")
            output_file = Path(tmp_dir) / "decoded_file.txt"
            decoder = QRLDecoder(str(output_file))

            success = decoder.decode(qr_images)

            if success:
                print("   Decoding successful!")

                # Verify the decoded file
                decoded_size = output_file.stat().st_size
                decoded_hash = hashlib.md5(output_file.read_bytes()).hexdigest()

                print(f"   Decoded file size: {decoded_size} bytes")
                print(f"   Decoded MD5: {decoded_hash}")

                if original_hash == decoded_hash:
                    print("   ✓ Verification PASSED - Files are identical!")
                    print(f"\n4. Demo completed successfully!")
                    print(f"   Original file: {file_size} bytes")
                    print(f"   QR codes generated: {len(qr_images)}")
                    print(f"   Chunk size: {metadata['chunk_size']} bytes")
                    print(f"   Error correction: {metadata['error_correction']}")
                    return True
                else:
                    print("   ✗ Verification FAILED - Hash mismatch!")
                    return False
            else:
                print("   Decoding failed!")
                progress = decoder.get_progress()
                print(f"   Progress: {progress.get('percentage', 0):.1f}%")
                return False

    except Exception as e:
        print(f"   ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean up demo file
        try:
            Path(demo_file).unlink()
        except Exception:
            pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)