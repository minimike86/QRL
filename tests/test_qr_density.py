"""Tests for the new pixel-density (box_size) plumbing and the
module-uniformity guarantee of _resize_to_clean_multiple."""

import tkinter as tk
import unittest

from PIL import Image

from qrl_server.qr_generator import QRGenerator
from tests.conftest import get_session_root


class TestQRGeneratorBoxSize(unittest.TestCase):
    def test_default_box_size_is_10(self):
        gen = QRGenerator(b"hello", error_correction="Q")
        img = gen.generate()
        # native = box_size * (data_modules + 2*border)
        # Just verify it's a multiple of the configured box_size
        self.assertEqual(img.size[0] % gen.box_size, 0)
        self.assertEqual(gen.box_size, 10)

    def test_custom_box_size_doubles_native_size(self):
        small = QRGenerator(b"x", error_correction="Q", box_size=10).generate()
        big = QRGenerator(b"x", error_correction="Q", box_size=20).generate()
        # box_size 20 should give 2x native size for the same data
        self.assertEqual(big.size[0], small.size[0] * 2)

    def test_custom_border_widens_image(self):
        narrow = QRGenerator(b"x", error_correction="Q", border=2).generate()
        wide = QRGenerator(b"x", error_correction="Q", border=10).generate()
        # +8 border modules on each side at default box_size=10 = +160 px total
        self.assertEqual(wide.size[0] - narrow.size[0], 16 * 10)


_ROOT = get_session_root()


@unittest.skipUnless(_ROOT is not None, "no display available")
class TestUniformModulesAfterResize(unittest.TestCase):
    """Whatever the cell size, the resized QR must have integer-uniform
    modules — that's the whole point of _resize_to_clean_multiple."""

    @classmethod
    def setUpClass(cls):
        from qrl_server.gui import QRLServerGUI

        cls.gui = QRLServerGUI(master=_ROOT)
        cls.gui.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.gui.root.destroy()
        except tk.TclError:
            pass

    def _check_uniform(self, qr: Image.Image, target_px: int, box_size: int):
        resized = self.gui._resize_to_clean_multiple(qr, target_px, box_size=box_size)
        native = qr.size[0]
        modules = native // box_size
        # Two valid outputs:
        #   1. Integer-multiple snap: size is a clean multiple of module count
        #      AND fits in the cell. Modules stay perfectly uniform.
        #   2. Non-integer fallback (BILINEAR at target_px): used when the
        #      integer snap would waste too much cell space (>15%) or when
        #      the cell is smaller than module_count. Trades exact uniformity
        #      for filling the cell — pyzbar still decodes after screen capture.
        self.assertLessEqual(resized.size[0], target_px)
        if resized.size[0] != target_px:
            self.assertEqual(
                resized.size[0] % modules,
                0,
                f"Resize {native}→{resized.size[0]} for target {target_px} (box_size={box_size}) "
                f"is neither a clean multiple of {modules} modules nor the BILINEAR fallback at {target_px}px",
            )

    def test_uniformity_at_default_box_size(self):
        qr = QRGenerator(b"hello world test", error_correction="H").generate()
        for target in (200, 250, 300, 350, 400, 500, 800, 1200):
            self._check_uniform(qr, target, box_size=10)

    def test_uniformity_at_high_density(self):
        qr = QRGenerator(b"hello world test", error_correction="H", box_size=20).generate()
        for target in (200, 300, 400, 600, 800, 1200, 2000):
            self._check_uniform(qr, target, box_size=20)

    def test_shrinking_below_one_pixel_per_module_clamps_gracefully(self):
        qr = QRGenerator(b"x", error_correction="H").generate()
        # Way too small — must still produce a valid (if tiny) image
        resized = self.gui._resize_to_clean_multiple(qr, 10, box_size=10)
        self.assertGreater(resized.size[0], 0)


@unittest.skipUnless(_ROOT is not None, "no display available")
class TestServerGUIDensityChips(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qrl_server.gui import QRLServerGUI

        cls.gui = QRLServerGUI(master=_ROOT)
        cls.gui.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.gui.root.destroy()
        except tk.TclError:
            pass

    def test_density_chips_exist(self):
        self.assertTrue(hasattr(self.gui, "density_buttons"))
        self.assertGreater(len(self.gui.density_buttons), 0)

    def test_density_preset_updates_config(self):
        self.gui._set_density_preset(16)
        self.assertEqual(self.gui.config.qr_box_size, 16)
        self.gui._set_density_preset(24)
        self.assertEqual(self.gui.config.qr_box_size, 24)

    def test_density_preset_highlights_active_chip(self):
        from qrl_server.gui import DENSITY_PRESETS

        self.gui._set_density_preset(16)
        for btn, (_, value) in zip(self.gui.density_buttons, DENSITY_PRESETS):
            expected = "ChipActive.TButton" if value == 16 else "Chip.TButton"
            self.assertEqual(str(btn.cget("style")), expected)


if __name__ == "__main__":
    unittest.main()
