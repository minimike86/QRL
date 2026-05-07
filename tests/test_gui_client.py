"""Client GUI tests for the redesigned UI."""

import tkinter as tk
import unittest
from unittest.mock import patch

from tests.conftest import get_session_root


_ROOT = get_session_root()


@unittest.skipUnless(_ROOT is not None, "no display available for tk.Tk()")
class TestClientGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qrl_client.gui import QRLClientGUI

        cls.gui = QRLClientGUI(master=_ROOT)
        cls.gui.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.gui.root.destroy()
        except tk.TclError:
            pass

    def setUp(self):
        self.gui.is_capturing = False
        self.gui.decoder = None
        self.gui.capture_handler = None
        self.gui.output_file = None
        self.gui.config.region = None
        self.gui._reset_region()

    def test_initial_state(self):
        self.assertFalse(self.gui.is_capturing)
        self.assertIsNone(self.gui.decoder)
        self.assertIsNone(self.gui.capture_handler)

    def test_default_config_loaded(self):
        self.assertAlmostEqual(self.gui.config.interval, 0.05)
        self.assertEqual(self.gui.config.monitor, 0)

    def test_speed_preset_updates_config(self):
        self.gui._set_speed_preset(0.1)
        self.assertAlmostEqual(self.gui.config.interval, 0.1)
        self.gui._set_speed_preset(0.033)
        self.assertAlmostEqual(self.gui.config.interval, 0.033)

    def test_speed_preset_highlights_active_chip(self):
        from qrl_client.gui import CAPTURE_PRESETS

        self.gui._set_speed_preset(0.05)
        for btn, (_, value) in zip(self.gui.preset_buttons, CAPTURE_PRESETS):
            expected = "ChipActive.TButton" if abs(value - 0.05) < 1e-3 else "Chip.TButton"
            self.assertEqual(str(btn.cget("style")), expected)

    def test_region_summary_when_no_region(self):
        self.gui._reset_region()
        self.assertEqual(self.gui.region_summary_var.get(), "Whole screen")

    def test_region_summary_when_region_set(self):
        self.gui.config.region = (100, 200, 800, 600)
        self.gui._update_ui_from_config()
        self.assertIn("800", self.gui.region_summary_var.get())
        self.assertIn("600", self.gui.region_summary_var.get())

    def test_button_states_idle_no_output(self):
        self.gui._update_button_states()
        self.assertEqual(str(self.gui.start_btn["state"]), "disabled")
        self.assertEqual(str(self.gui.stop_btn["state"]), "disabled")

    def test_button_states_idle_with_output(self):
        self.gui.output_file = "/tmp/decoded.bin"
        self.gui._update_button_states()
        self.assertEqual(str(self.gui.start_btn["state"]), "normal")

    def test_log_appends(self):
        self.gui._log("client test message")
        contents = self.gui.log_text.get("1.0", tk.END)
        self.assertIn("client test message", contents)

    def test_capture_without_output_file_shows_error(self):
        self.gui.output_file = None
        with patch("tkinter.messagebox.showerror") as mock_err:
            self.gui._start_capture()
        mock_err.assert_called()

    def test_status_pill_exists(self):
        self.assertIsNotNone(self.gui.status_label)


if __name__ == "__main__":
    unittest.main()
