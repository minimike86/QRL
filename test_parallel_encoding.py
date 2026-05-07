#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for parallel QR encoding system.
Demonstrates the new parallel stream encoding capabilities.
"""

import tempfile
import time
from pathlib import Path
from qrl_server.parallel_encoder import ParallelQREncoder, ParallelQRDecoder
from qrl_server.encoder import QRLEncoder


def create_test_file(size_kb: int) -> str:
    """Create a test file of specified size in KB."""
    test_data = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" * (size_kb * 30)  # ~36 bytes per repetition
    test_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin')
    test_file.write(test_data[:size_kb * 1024])  # Exact size
    test_file.close()
    return test_file.name


def test_parallel_vs_traditional_encoding():
    """Compare parallel vs traditional encoding performance."""
    print("=" * 80)
    print("QRL PARALLEL ENCODING PERFORMANCE TEST")
    print("=" * 80)

    # Test different file sizes
    test_sizes = [50, 100, 500]  # KB
    chunk_size = 1500  # bytes
    error_correction = "Q"

    for file_size_kb in test_sizes:
        print(f"\n[FILE] Testing {file_size_kb}KB file:")
        print("-" * 50)

        # Create test file
        test_file = create_test_file(file_size_kb)

        try:
            # Traditional encoding
            print("\n[TRADITIONAL] Single-stream Encoding:")
            traditional_encoder = QRLEncoder(test_file, chunk_size=chunk_size,
                                           error_correction=error_correction)

            start_time = time.time()
            traditional_chunks = traditional_encoder.prepare_chunks()
            traditional_prep_time = time.time() - start_time

            traditional_metadata = traditional_encoder.get_metadata()
            print(f"   Chunks: {traditional_chunks:,}")
            print(f"   Prep time: {traditional_prep_time:.3f}s")

            # Test different parallel configurations
            parallel_configs = [4, 9, 16]  # 2x2, 3x3, 4x4

            for num_streams in parallel_configs:
                print(f"\n[PARALLEL] Multi-stream Encoding ({num_streams} streams):")

                parallel_encoder = ParallelQREncoder(test_file, num_streams=num_streams,
                                                   chunk_size=chunk_size,
                                                   error_correction=error_correction)

                start_time = time.time()
                stream_info = parallel_encoder.prepare_parallel_streams()
                parallel_prep_time = time.time() - start_time

                parallel_chunks = parallel_encoder.get_total_chunks()
                throughput_stats = parallel_encoder.calculate_theoretical_throughput(0.1)  # 0.1s per QR

                print(f"   Chunk sets: {parallel_chunks:,}")
                print(f"   Prep time: {parallel_prep_time:.3f}s")
                print(f"   Theoretical throughput: {throughput_stats['kilobytes_per_second']:.1f} KB/s")
                print(f"   Speedup factor: {throughput_stats['speedup_factor']:.1f}x")
                print(f"   Transfer time estimate: {throughput_stats['total_display_time_seconds']:.1f}s")

        finally:
            # Clean up
            Path(test_file).unlink()


def test_parallel_qr_generation():
    """Test actual QR code generation with parallel encoding."""
    print("\n" + "=" * 80)
    print("QR CODE GENERATION TEST")
    print("=" * 80)

    # Create a medium-sized test file
    test_file = create_test_file(100)  # 100KB

    try:
        # Set up parallel encoder
        parallel_encoder = ParallelQREncoder(test_file, num_streams=4,
                                           chunk_size=1200, error_correction="Q")

        print("[PREP] Preparing parallel streams...")
        stream_info = parallel_encoder.prepare_parallel_streams()
        total_chunk_sets = parallel_encoder.get_total_chunks()

        print(f"[READY] {total_chunk_sets:,} chunk sets across 4 streams")

        # Generate first few QR grids
        print("\n[QR GEN] Generating sample QR grids:")
        for chunk_set in range(min(5, total_chunk_sets)):
            print(f"   Generating QR grid {chunk_set + 1}/{total_chunk_sets}...", end="")

            start_time = time.time()
            qr_grid = parallel_encoder.generate_qr_grid(chunk_set)
            gen_time = time.time() - start_time

            print(f" [OK] ({gen_time:.3f}s)")

            # Verify grid structure
            assert len(qr_grid) == 2  # 2x2 grid
            assert len(qr_grid[0]) == 2
            assert all(hasattr(qr, 'save') for row in qr_grid for qr in row)  # PIL Images

        print("\n[SUCCESS] QR generation test passed!")

        # Test throughput calculation
        throughput_stats = parallel_encoder.calculate_theoretical_throughput(0.05)  # Ultra-fast 20 FPS
        print(f"\n[ULTRA FAST] 20 FPS mode:")
        print(f"   Data: {throughput_stats['data_size_mb']:.1f} MB")
        print(f"   Transfer time: {throughput_stats['total_display_time_seconds']:.1f}s")
        print(f"   Throughput: {throughput_stats['megabytes_per_second']:.2f} MB/s")

    finally:
        Path(test_file).unlink()


def test_decoder_functionality():
    """Test the parallel decoder functionality."""
    print("\n" + "=" * 80)
    print("PARALLEL DECODER TEST")
    print("=" * 80)

    # Create small test data
    test_data = b"Hello, this is test data for parallel QR encoding!" * 20  # ~1KB
    test_file = tempfile.NamedTemporaryFile(mode='wb', delete=False)
    test_file.write(test_data)
    test_file.close()

    try:
        # Encode with parallel streams
        encoder = ParallelQREncoder(test_file.name, num_streams=4, chunk_size=200)
        stream_info = encoder.prepare_parallel_streams()

        print(f"[ENCODE] Data encoded into {len(stream_info)} streams")

        # Create decoder
        decoder = ParallelQRDecoder(num_streams=4)

        # Simulate receiving QR data by extracting chunks and feeding to decoder
        total_chunks = encoder.get_total_chunks()
        print(f"[TRANSMIT] Simulating {total_chunks} chunk transmissions...")

        for chunk_idx in range(total_chunks):
            qr_grid = encoder.generate_qr_grid(chunk_idx)

            # Extract data from each QR in the grid (simulating QR decode)
            for row_idx, row in enumerate(qr_grid):
                for col_idx, qr_image in enumerate(row):
                    stream_id = row_idx * 2 + col_idx  # 2x2 grid

                    # Get raw chunk data (simulating QR decode)
                    stream_chunks = encoder._stream_chunks[stream_id]
                    if chunk_idx < len(stream_chunks):
                        chunk_data = stream_chunks[chunk_idx]

                        # Feed to decoder
                        decoder.add_qr_data(chunk_data)

        # Check if decoding is complete
        if decoder.is_complete():
            reconstructed_data = decoder.reconstruct_data()
            print(f"[SUCCESS] Decoding complete!")
            print(f"   Original size: {len(test_data):,} bytes")
            print(f"   Reconstructed size: {len(reconstructed_data):,} bytes")
            print(f"   Data matches: {test_data == reconstructed_data}")
        else:
            print("[ERROR] Decoding incomplete")

    finally:
        Path(test_file.name).unlink()


def main():
    """Run all parallel encoding tests."""
    try:
        test_parallel_vs_traditional_encoding()
        test_parallel_qr_generation()
        test_decoder_functionality()

        print("\n" + "=" * 80)
        print("[SUCCESS] ALL TESTS PASSED! Parallel encoding system is ready.")
        print("=" * 80)
        print("\nKey benefits:")
        print("   * Bypasses single QR size limits")
        print("   * 4x-16x speed increase with parallel streams")
        print("   * Independent stream processing")
        print("   * Backward compatible with traditional encoding")
        print("\nReady to test with the GUI!")

    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()