"""Tests for monitor_at_point and primary_monitor helpers."""

import unittest
from unittest.mock import patch

from qrl_client import monitors
from qrl_client.monitors import MonitorInfo


class TestMonitorAtPoint(unittest.TestCase):
    def setUp(self):
        # Two-monitor virtual desktop: secondary is to the LEFT of primary.
        self.fake_monitors = [
            MonitorInfo(1, "Primary", 0, 0, 1920, 1080, True),
            MonitorInfo(2, "Display 2", -2560, 0, 2560, 1440, False),
        ]
        self.patcher = patch.object(
            monitors, "list_monitors", return_value=self.fake_monitors
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_point_on_primary(self):
        m = monitors.monitor_at_point(100, 100)
        self.assertIsNotNone(m)
        self.assertTrue(m.is_primary)

    def test_point_on_secondary_left_of_primary(self):
        m = monitors.monitor_at_point(-1000, 500)
        self.assertIsNotNone(m)
        self.assertEqual(m.index, 2)
        self.assertFalse(m.is_primary)

    def test_point_outside_any_monitor(self):
        # Above virtual desktop (negative y outside any monitor)
        m = monitors.monitor_at_point(0, -5000)
        self.assertIsNone(m)

    def test_primary_monitor_helper(self):
        p = monitors.primary_monitor()
        self.assertIsNotNone(p)
        self.assertTrue(p.is_primary)


if __name__ == "__main__":
    unittest.main()
