"""Server GUI tests.

Each test creates a real tkinter root and exercises the GUI class. Tests are
skipped if the platform can't open a display (e.g. headless CI without Xvfb).
"""

import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch


def _can_open_display() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@unittest.skipUnless(_can_open_display(), "no display available for tk.Tk()")
class TestServerGUI(unittest.TestCase):
    def setUp(self):
        from qrl_server.gui import QRLServerGUI

        self.gui = QRLServerGUI()
        # Hide the window during tests
        self.gui.root.withdraw()

    def tearDown(self):
        try:
            self.gui.root.destroy()
        except tk.TclError:
            pass

    def test_initial_state(self):
        self.assertFalse(self.gui.is_encoding)
        self.assertFalse(self.gui.is_displaying)
        self.assertIsNone(self.gui.encoder)
        self.assertEqual(self.gui.qr_images, [])

    def test_default_config_loaded(self):
        # Defaults from ServerConfig - chunk_size 1490 (Q-level optimal) and 0.1s
        self.assertEqual(self.gui.config.chunk_size, 1490)
        self.assertAlmostEqual(self.gui.config.duration, 0.1)
        self.assertEqual(self.gui.config.error_correction, "Q")

    def test_update_config_from_ui_reflects_changes(self):
        self.gui.chunk_size_var.set(800)
        self.gui.duration_var.set(0.05)
        self.gui.error_correction_var.set("L")
        self.gui._update_config_from_ui()
        self.assertEqual(self.gui.config.chunk_size, 800)
        self.assertAlmostEqual(self.gui.config.duration, 0.05)
        self.assertEqual(self.gui.config.error_correction, "L")

    def test_button_states_idle(self):
        self.gui._update_button_states()
        self.assertEqual(str(self.gui.encode_btn["state"]), "normal")
        self.assertEqual(str(self.gui.display_btn["state"]), "disabled")
        self.assertEqual(str(self.gui.stop_btn["state"]), "disabled")

    def test_log_appends(self):
        self.gui._log("test message")
        contents = self.gui.log_text.get("1.0", tk.END)
        self.assertIn("test message", contents)

    def test_set_duration_with_warning_for_fast(self):
        self.gui._set_duration_with_warning(0.05)
        self.assertAlmostEqual(self.gui.duration_var.get(), 0.05)

    def test_encoding_complete_handler_with_traditional_metadata(self):
        # Mimic what _encoding_complete needs from metadata
        metadata = {
            "total_size": 1000,
            "total_chunks": 5,
            "encoding_type": "traditional",
        }
        self.gui.current_file = "/tmp/fake"
        self.gui._encoding_complete(metadata)
        self.assertEqual(int(self.gui.progress_var.get()), 100)

    def test_encoding_complete_handler_with_parallel_metadata(self):
        # Parallel encoder must provide the same keys; GUI shouldn't crash.
        metadata = {
            "total_size": 2000,
            "total_chunks": 3,
            "num_streams": 4,
            "encoding_type": "parallel",
        }
        self.gui.current_file = "/tmp/fake"
        self.gui._encoding_complete(metadata)
        self.assertEqual(int(self.gui.progress_var.get()), 100)

    def test_encode_without_file_shows_error(self):
        self.gui.current_file = None
        with patch("tkinter.messagebox.showerror") as mock_err:
            self.gui._encode_file()
        mock_err.assert_called()


@unittest.skipUnless(_can_open_display(), "no display available for tk.Tk()")
class TestServerGUIEncodingFlow(unittest.TestCase):
    """Drive the actual encode pipeline through the GUI worker (synchronous)."""

    def setUp(self):
        from qrl_server.gui import QRLServerGUI

        self.gui = QRLServerGUI()
        self.gui.root.withdraw()

        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        self.tmp.write(b"GUI encoding test payload " * 50)
        self.tmp.close()

    def tearDown(self):
        try:
            self.gui.root.destroy()
        except tk.TclError:
            pass
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_worker_prepares_chunks_and_caches_images(self):
        self.gui.current_file = self.tmp.name
        self.gui.file_path_var.set(self.tmp.name)
        # Run worker synchronously (the real flow runs it on a Thread)
        self.gui._encode_file_worker()

        self.assertIsNotNone(self.gui.encoder)
        self.assertGreater(self.gui.encoder.get_total_chunks(), 0)
        self.assertEqual(self.gui.total_chunks, self.gui.encoder.get_total_chunks())
        # Prefetch is enabled by default for small files
        self.assertIsNotNone(self.gui.encoder.get_qr_images())


if __name__ == "__main__":
    unittest.main()
