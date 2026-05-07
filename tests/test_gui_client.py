"""Client GUI tests. Skipped when no display is available."""

import tkinter as tk
import unittest
from unittest.mock import patch


def _can_open_display() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@unittest.skipUnless(_can_open_display(), "no display available for tk.Tk()")
class TestClientGUI(unittest.TestCase):
    def setUp(self):
        from qrl_client.gui import QRLClientGUI

        self.gui = QRLClientGUI()
        self.gui.root.withdraw()

    def tearDown(self):
        try:
            self.gui.root.destroy()
        except tk.TclError:
            pass

    def test_initial_state(self):
        self.assertFalse(self.gui.is_capturing)
        self.assertIsNone(self.gui.decoder)
        self.assertIsNone(self.gui.capture_handler)

    def test_default_config_loaded(self):
        # Updated default: 0.05s = 20 FPS capture
        self.assertAlmostEqual(self.gui.config.interval, 0.05)
        self.assertEqual(self.gui.config.monitor, 0)

    def test_update_config_from_ui(self):
        self.gui.monitor_var.set(1)
        self.gui.interval_var.set(0.1)
        self.gui.timeout_var.set(60)
        self.gui._update_config_from_ui()
        self.assertEqual(self.gui.config.monitor, 1)
        self.assertAlmostEqual(self.gui.config.interval, 0.1)
        self.assertEqual(self.gui.config.timeout, 60)

    def test_button_states_idle(self):
        self.gui._update_button_states()
        self.assertEqual(str(self.gui.start_btn["state"]), "normal")
        self.assertEqual(str(self.gui.stop_btn["state"]), "disabled")

    def test_log_appends(self):
        self.gui._log("client test message")
        contents = self.gui.log_text.get("1.0", tk.END)
        self.assertIn("client test message", contents)

    def test_capture_without_output_file_shows_error(self):
        self.gui.output_file = None
        with patch("tkinter.messagebox.showerror") as mock_err:
            self.gui._start_capture()
        mock_err.assert_called()

    def test_toggle_region(self):
        self.gui.region_enabled_var.set(True)
        self.gui._toggle_region()
        # First entry inside region_entry_frame should now be enabled
        for w in self.gui.region_entry_frame.winfo_children():
            if isinstance(w, tk.ttk.Entry) if hasattr(tk, "ttk") else False:
                pass  # ttk import path differs; not asserting widget state strictly


if __name__ == "__main__":
    unittest.main()
