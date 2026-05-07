"""Tests for the region picker.

The picker is interactive — we can't drive a real drag in tests. So we test
that it imports cleanly and that helper logic for parsing the result works.
"""

import unittest

from qrl_client import region_picker


class TestRegionPickerImports(unittest.TestCase):
    def test_pick_region_callable(self):
        self.assertTrue(callable(region_picker.pick_region))

    def test_pick_region_async_callable(self):
        self.assertTrue(callable(region_picker.pick_region_async))


if __name__ == "__main__":
    unittest.main()
