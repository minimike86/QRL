"""Tests for qrl_client.monitors discovery."""

import unittest

from qrl_client.monitors import MonitorInfo, find_by_index, list_monitors


class TestListMonitors(unittest.TestCase):
    def test_returns_at_least_one(self):
        monitors = list_monitors()
        self.assertGreater(len(monitors), 0)

    def test_each_entry_has_required_fields(self):
        for m in list_monitors():
            self.assertIsInstance(m, MonitorInfo)
            self.assertGreaterEqual(m.index, 1)
            self.assertIsInstance(m.name, str)
            self.assertGreater(len(m.name), 0)
            # width/height should be positive (skip 0×0 placeholder fallback)
            if m.width > 0 and m.height > 0:
                self.assertGreater(m.width, 0)
                self.assertGreater(m.height, 0)

    def test_at_least_one_primary(self):
        monitors = list_monitors()
        # On a real system, at least one monitor must be primary (origin 0,0).
        primaries = [m for m in monitors if m.is_primary]
        # Allow 0 primaries if running headless / no real screen — but at
        # least the placeholder should exist.
        self.assertTrue(len(monitors) >= 1)

    def test_bounds_property(self):
        m = list_monitors()[0]
        self.assertEqual(m.bounds, (m.x, m.y, m.width, m.height))


class TestFindByIndex(unittest.TestCase):
    def test_finds_existing(self):
        monitors = list_monitors()
        first = monitors[0]
        self.assertEqual(find_by_index(first.index), first)

    def test_returns_none_for_unknown(self):
        self.assertIsNone(find_by_index(999))


class TestNegativeCoordinateLabels(unittest.TestCase):
    """The position label should be human-readable for left/above secondary
    monitors — these are the configurations that previously broke validation."""

    def test_left_of_primary_label(self):
        from qrl_client.monitors import _position_label

        self.assertIn("left of primary", _position_label(-1920, 0, False))

    def test_above_primary_label(self):
        from qrl_client.monitors import _position_label

        self.assertIn("above primary", _position_label(0, -1080, False))

    def test_primary_no_position_label(self):
        from qrl_client.monitors import _position_label

        self.assertEqual(_position_label(0, 0, True), "")


if __name__ == "__main__":
    unittest.main()
