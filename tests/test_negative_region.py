"""Regression tests for the multi-monitor negative-region bug.

The user reported: capturing a region on a secondary monitor positioned to
the LEFT of the primary monitor (so x < 0) failed with
"Configuration validation failed: region values must be non-negative".
"""

import unittest

from qrl_client.capture import CaptureHandler
from qrl_client.config import ClientConfig


class TestNegativeRegionValidation(unittest.TestCase):
    def test_negative_x_passes_validation(self):
        config = ClientConfig()
        config.region = (-1920, 100, 800, 600)  # left of primary
        config.validate()  # must not raise

    def test_negative_y_passes_validation(self):
        config = ClientConfig()
        config.region = (100, -1080, 800, 600)  # above primary
        config.validate()

    def test_both_negative_passes(self):
        config = ClientConfig()
        config.region = (-2560, -1440, 1920, 1080)
        config.validate()

    def test_zero_width_fails(self):
        config = ClientConfig()
        config.region = (0, 0, 0, 600)
        with self.assertRaises(ValueError):
            config.validate()

    def test_zero_height_fails(self):
        config = ClientConfig()
        config.region = (0, 0, 800, 0)
        with self.assertRaises(ValueError):
            config.validate()

    def test_negative_width_fails(self):
        config = ClientConfig()
        config.region = (0, 0, -100, 600)
        with self.assertRaises(ValueError):
            config.validate()


class TestCaptureHandlerWithNegativeRegion(unittest.TestCase):
    def test_monitor_def_passes_negative_coords_through(self):
        """The capture handler must forward negative left/top to mss verbatim."""
        handler = CaptureHandler(region=(-1920, -100, 800, 600))

        class _FakeMSS:
            monitors = [
                {"left": -1920, "top": -100, "width": 3840, "height": 1180},
                {"left": 0, "top": 0, "width": 1920, "height": 1080},
                {"left": -1920, "top": -100, "width": 1920, "height": 1080},
            ]

        mon = handler._monitor_def(_FakeMSS())
        self.assertEqual(mon["left"], -1920)
        self.assertEqual(mon["top"], -100)
        self.assertEqual(mon["width"], 800)
        self.assertEqual(mon["height"], 600)


if __name__ == "__main__":
    unittest.main()
