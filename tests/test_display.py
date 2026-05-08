"""Tests for qrl_server.display.DisplayHandler.

Exercises the headless tick() loop without opening a Tk window.
"""

import unittest

from PIL import Image

from qrl_server.display import DisplayHandler


def _img(color: str = "white", size: int = 32) -> Image.Image:
    return Image.new("RGB", (size, size), color)


class TestInit(unittest.TestCase):
    def test_stores_settings(self):
        imgs = [_img(), _img()]
        h = DisplayHandler(imgs, duration=0.5, repeat=False, window_title="Test")
        self.assertEqual(h.duration, 0.5)
        self.assertFalse(h.repeat)
        self.assertEqual(h.window_title, "Test")
        self.assertFalse(h.is_running())

    def test_set_duration(self):
        h = DisplayHandler([_img()])
        h.set_duration(0.25)
        self.assertEqual(h.duration, 0.25)


class TestTick(unittest.TestCase):
    def test_tick_returns_none_when_not_running(self):
        h = DisplayHandler([_img(), _img()])
        self.assertIsNone(h.tick())

    def test_tick_advances_through_images(self):
        imgs = [_img("red"), _img("green"), _img("blue")]
        h = DisplayHandler(imgs, repeat=False)
        h._running = True
        seen = []
        for _ in range(3):
            seen.append(h.tick())
        self.assertEqual(len(seen), 3)
        self.assertIsNotNone(seen[0])
        self.assertEqual(h.current_index(), 3)

    def test_tick_stops_when_repeat_false(self):
        imgs = [_img(), _img()]
        h = DisplayHandler(imgs, repeat=False)
        h._running = True
        for _ in range(2):
            h.tick()
        # Next tick should signal end of sequence
        self.assertIsNone(h.tick())
        self.assertFalse(h.is_running())

    def test_tick_loops_when_repeat_true(self):
        imgs = [_img(), _img()]
        h = DisplayHandler(imgs, repeat=True)
        h._running = True
        for _ in range(2):
            h.tick()
        self.assertIsNotNone(h.tick())  # cycle 2 begins
        self.assertEqual(h.cycle_count(), 1)
        self.assertTrue(h.is_running())

    def test_on_frame_callback(self):
        imgs = [_img(), _img(), _img()]
        seen = []
        h = DisplayHandler(imgs, repeat=False, on_frame=seen.append)
        h._running = True
        for _ in range(3):
            h.tick()
        self.assertEqual(seen, [0, 1, 2])


class TestStartValidation(unittest.TestCase):
    def test_start_with_no_images_raises(self):
        h = DisplayHandler([])
        with self.assertRaises(ValueError):
            h.start()


if __name__ == "__main__":
    unittest.main()
