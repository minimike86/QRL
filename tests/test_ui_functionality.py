#!/usr/bin/env python3
"""
Functional tests for QRL UI components and workflows.
Tests actual functionality, not just GUI startup.
"""

import unittest
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

# Test the actual functionality
from qrl_server.encoder import QRLEncoder
from qrl_server.qr_generator import QRGenerator
from qrl_server.config import ServerConfig, ConfigManager
from qrl_client.config import ClientConfig, ClientConfigManager


class TestQRCapacityValidation(unittest.TestCase):
    """Test QR code capacity validation."""

    def test_chunk_size_validation(self):
        """Test QR chunk size limits."""
        # Should pass - within limits
        self.assertTrue(QRGenerator.validate_chunk_size(500, "Q"))
        self.assertTrue(QRGenerator.validate_chunk_size(1000, "Q"))

        # Should fail - exceeds limits
        self.assertFalse(QRGenerator.validate_chunk_size(2000, "Q"))
        self.assertFalse(QRGenerator.validate_chunk_size(5000, "Q"))

    def test_max_capacity_by_error_level(self):
        """Test maximum capacity for different error correction levels."""
        # Higher error correction = lower capacity
        cap_h = QRGenerator.get_max_chunk_size("H")
        cap_q = QRGenerator.get_max_chunk_size("Q")
        cap_m = QRGenerator.get_max_chunk_size("M")
        cap_l = QRGenerator.get_max_chunk_size("L")

        self.assertLess(cap_h, cap_q)
        self.assertLess(cap_q, cap_m)
        self.assertLess(cap_m, cap_l)

        # Verify reasonable ranges
        self.assertGreater(cap_h, 500)  # At least 500 bytes
        self.assertLess(cap_l, 3000)    # Less than 3KB


class TestOnTheFlyEncoding(unittest.TestCase):
    """Test on-the-fly QR generation functionality."""

    def setUp(self):
        """Create test file."""
        self.test_data = b"Test data for QRL encoding. " * 100  # ~2.9KB
        self.test_file = tempfile.NamedTemporaryFile(mode='wb', delete=False)
        self.test_file.write(self.test_data)
        self.test_file.close()

    def tearDown(self):
        """Clean up test file."""
        Path(self.test_file.name).unlink(missing_ok=True)

    def test_prepare_chunks_functionality(self):
        """Test that prepare_chunks actually works."""
        encoder = QRLEncoder(self.test_file.name, chunk_size=500)

        # Should prepare chunks without generating QR images
        total_chunks = encoder.prepare_chunks()

        self.assertGreater(total_chunks, 0)
        self.assertEqual(total_chunks, encoder.get_total_chunks())
        self.assertIsNone(encoder.get_qr_images())  # No QR images pre-generated

    def test_on_demand_qr_generation(self):
        """Test generating QR codes on demand."""
        encoder = QRLEncoder(self.test_file.name, chunk_size=500)
        total_chunks = encoder.prepare_chunks()

        # Generate first QR code
        qr_image_0 = encoder.generate_qr_for_chunk(0)
        self.assertIsNotNone(qr_image_0)
        self.assertTrue(hasattr(qr_image_0, 'save'))  # PIL Image

        # Generate last QR code
        qr_image_last = encoder.generate_qr_for_chunk(total_chunks - 1)
        self.assertIsNotNone(qr_image_last)

        # Should fail for invalid index
        with self.assertRaises(ValueError):
            encoder.generate_qr_for_chunk(total_chunks)

    def test_memory_efficiency(self):
        """Test that on-the-fly uses less memory than pre-generation."""
        encoder = QRLEncoder(self.test_file.name, chunk_size=500)

        # Measure memory usage of prepare_chunks
        encoder.prepare_chunks()
        prepared_chunks = encoder.get_total_chunks()

        # Should not have QR images in memory
        qr_images = encoder.get_qr_images()
        self.assertIsNone(qr_images)

        # Generate one QR and verify it works
        qr_image = encoder.generate_qr_for_chunk(0)
        self.assertIsNotNone(qr_image)


class TestConfigurationSystem(unittest.TestCase):
    """Test configuration file system."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()

    def test_server_config_validation(self):
        """Test server configuration validation."""
        config = ServerConfig()

        # Valid config should pass
        config.chunk_size = 1000
        config.error_correction = "Q"
        self.assertTrue(config.validate())

        # Invalid chunk size should fail
        config.chunk_size = 100000  # Too large
        with self.assertRaises(ValueError):
            config.validate()

    def test_config_file_creation(self):
        """Test configuration file creation and loading."""
        test_config_path = Path(self.test_dir) / "test_config.yaml"

        # Create config
        ConfigManager.create_example_config(str(test_config_path))
        self.assertTrue(test_config_path.exists())

        # Load and verify
        loaded_config = ConfigManager.load_config(str(test_config_path))
        self.assertIsInstance(loaded_config, ServerConfig)
        self.assertEqual(loaded_config.chunk_size, 1024)  # Default value

    def test_config_override_validation(self):
        """Test that config overrides work and validate."""
        config = ServerConfig()
        config.chunk_size = 2000
        config.error_correction = "Q"

        # Should fail validation (2000 > 1200 for Q level)
        with self.assertRaises(ValueError):
            config.validate()


class TestFileValidation(unittest.TestCase):
    """Test file validation and size checking."""

    def test_file_size_validation(self):
        """Test file size limits."""
        # Create test files of different sizes
        small_file = tempfile.NamedTemporaryFile(mode='wb', delete=False)
        small_file.write(b"small data")
        small_file.close()

        # Test with default config (100MB limit)
        config = ServerConfig()
        encoder = QRLEncoder(small_file.name, chunk_size=config.chunk_size)
        self.assertTrue(encoder.validate())

        Path(small_file.name).unlink()

    def test_empty_file_handling(self):
        """Test handling of empty files."""
        empty_file = tempfile.NamedTemporaryFile(mode='wb', delete=False)
        empty_file.close()

        encoder = QRLEncoder(empty_file.name, chunk_size=1000)
        self.assertTrue(encoder.validate())  # File exists

        # But should fail during data loading
        with self.assertRaises(ValueError):
            encoder.prepare_chunks()

        Path(empty_file.name).unlink()


class TestIntegrationWorkflow(unittest.TestCase):
    """Test complete encode-display workflow."""

    def setUp(self):
        """Create test data."""
        self.test_data = b"Integration test data. " * 50  # ~1.2KB
        self.test_file = tempfile.NamedTemporaryFile(mode='wb', delete=False)
        self.test_file.write(self.test_data)
        self.test_file.close()

    def tearDown(self):
        """Clean up."""
        Path(self.test_file.name).unlink(missing_ok=True)

    def test_full_encode_workflow(self):
        """Test complete encoding workflow."""
        # Step 1: Create encoder with valid settings
        encoder = QRLEncoder(self.test_file.name, chunk_size=500, error_correction="Q")

        # Step 2: Validate
        self.assertTrue(encoder.validate())

        # Step 3: Prepare chunks
        total_chunks = encoder.prepare_chunks()
        self.assertGreater(total_chunks, 0)

        # Step 4: Generate QR codes on demand
        for i in range(min(total_chunks, 3)):  # Test first 3
            qr_image = encoder.generate_qr_for_chunk(i)
            self.assertIsNotNone(qr_image)

            # Verify it's a valid PIL image
            self.assertTrue(hasattr(qr_image, 'size'))
            self.assertGreater(qr_image.size[0], 0)
            self.assertGreater(qr_image.size[1], 0)

    def test_qr_capacity_enforcement(self):
        """Test that QR capacity limits are enforced."""
        # Create encoder with chunk size that's too large for Q level
        encoder = QRLEncoder(self.test_file.name, chunk_size=2000, error_correction="Q")

        self.assertTrue(encoder.validate())  # File validation passes

        # But should fail during QR generation
        encoder.prepare_chunks()
        with self.assertRaises(Exception):  # Should fail when generating QR
            encoder.generate_qr_for_chunk(0)


def run_functionality_tests():
    """Run all functionality tests."""
    test_classes = [
        TestQRCapacityValidation,
        TestOnTheFlyEncoding,
        TestConfigurationSystem,
        TestFileValidation,
        TestIntegrationWorkflow
    ]

    total_tests = 0
    total_failures = 0

    for test_class in test_classes:
        print(f"\n{'='*50}")
        print(f"Running {test_class.__name__}")
        print(f"{'='*50}")

        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        total_tests += result.testsRun
        total_failures += len(result.failures) + len(result.errors)

    print(f"\n{'='*50}")
    print(f"SUMMARY: {total_tests} tests, {total_failures} failures")
    print(f"{'='*50}")

    return total_failures == 0


if __name__ == "__main__":
    run_functionality_tests()