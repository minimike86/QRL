"""Test the LRU cache used to bound QR-image memory on large transfers."""

import unittest

from qrl_server.gui import _LRUDict


class TestLRUDict(unittest.TestCase):
    def test_evicts_oldest_when_full(self):
        cache = _LRUDict(max_size=3)
        for i in range(5):
            cache[i] = f"v{i}"
        # Only the 3 most-recent insertions should remain
        self.assertEqual(set(cache.keys()), {2, 3, 4})

    def test_get_marks_recently_used(self):
        cache = _LRUDict(max_size=3)
        cache[0] = "a"
        cache[1] = "b"
        cache[2] = "c"
        # Touch 0 to mark as recently used
        _ = cache[0]
        # Now insert a new entry — 1 should be evicted, not 0
        cache[3] = "d"
        self.assertIn(0, cache)
        self.assertNotIn(1, cache)
        self.assertIn(2, cache)
        self.assertIn(3, cache)

    def test_overwrite_does_not_grow(self):
        cache = _LRUDict(max_size=2)
        cache["x"] = 1
        cache["x"] = 2
        cache["x"] = 3
        self.assertEqual(len(cache), 1)
        self.assertEqual(cache["x"], 3)

    def test_contains_does_not_promote(self):
        # `in` checks shouldn't reorder entries — that would be surprising
        cache = _LRUDict(max_size=2)
        cache["a"] = 1
        cache["b"] = 2
        self.assertIn("a", cache)
        cache["c"] = 3  # should evict the least-recently-USED, which is "a"
        self.assertNotIn("a", cache)
        self.assertIn("b", cache)
        self.assertIn("c", cache)


if __name__ == "__main__":
    unittest.main()
