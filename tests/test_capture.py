"""Tests for qrl_client.capture.CaptureHandler.

Avoids actual screen-grabbing by using push_frame() to inject test frames.
"""

import threading
import time
import unittest

import numpy as np

from qrl_client.capture import CaptureHandler


class TestInit(unittest.TestCase):
    def test_defaults(self):
        h = CaptureHandler()
        self.assertEqual(h.monitor, 0)
        self.assertIsNone(h.region)
        self.assertFalse(h.is_running())

    def test_set_region(self):
        h = CaptureHandler()
        h.set_region((10, 20, 100, 200))
        self.assertEqual(h.region, (10, 20, 100, 200))


class TestFrameBuffer(unittest.TestCase):
    def test_get_frames_drains_buffer(self):
        h = CaptureHandler()
        for i in range(3):
            h.push_frame(np.zeros((10, 10, 3), dtype=np.uint8))
        frames = h.get_frames()
        self.assertEqual(len(frames), 3)
        # Second drain should be empty
        self.assertEqual(h.get_frames(), [])

    def test_buffer_size_caps_oldest(self):
        h = CaptureHandler(buffer_size=5)
        for i in range(10):
            arr = np.full((4, 4, 3), i, dtype=np.uint8)
            h.push_frame(arr)
        frames = h.get_frames()
        self.assertEqual(len(frames), 5)
        # Oldest 5 dropped → first remaining is i=5
        self.assertEqual(int(frames[0][0, 0, 0]), 5)

    def test_thread_safety(self):
        h = CaptureHandler(buffer_size=200)

        def producer():
            for _ in range(50):
                h.push_frame(np.zeros((4, 4, 3), dtype=np.uint8))

        threads = [threading.Thread(target=producer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 4 threads × 50 frames = 200 frames pushed (cap is 200, so all retained)
        self.assertEqual(len(h.get_frames()), 200)


class TestFramesCaptured(unittest.TestCase):
    def test_counter_increments(self):
        h = CaptureHandler()
        h.push_frame(np.zeros((1, 1, 3), dtype=np.uint8))
        h.push_frame(np.zeros((1, 1, 3), dtype=np.uint8))
        self.assertEqual(h.get_frames_captured(), 2)


if __name__ == "__main__":
    unittest.main()
