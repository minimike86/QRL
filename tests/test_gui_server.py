"""Server GUI tests.

Tk on Windows doesn't tolerate creating/destroying multiple `tk.Tk()` roots
within the same process — the second creation hits a "tcl_findLibrary"
error. We work around that by sharing a single GUI instance across tests
(setUpClass) and resetting relevant state in setUp.
"""

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


_DISPLAY_OK = _can_open_display()


@unittest.skipUnless(_DISPLAY_OK, "no display available for tk.Tk()")
class TestServerGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qrl_server.gui import QRLServerGUI

        cls.gui = QRLServerGUI()
        cls.gui.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.gui.root.destroy()
        except tk.TclError:
            pass

    def setUp(self):
        # Reset transient state before every test
        self.gui.is_encoding = False
        self.gui.is_displaying = False
        self.gui.encoder = None
        self.gui.parallel_encoder = None
        self.gui.qr_images = []
        self.gui.current_file = None
        self.gui.progress_var.set(0)

    # ------------------------------------------------------------------
    # Initial state / config plumbing
    # ------------------------------------------------------------------
    def test_initial_state(self):
        self.assertFalse(self.gui.is_encoding)
        self.assertFalse(self.gui.is_displaying)
        self.assertIsNone(self.gui.encoder)
        self.assertEqual(self.gui.qr_images, [])

    def test_default_config_loaded(self):
        # Defaults from ServerConfig: 1490 raw bytes per chunk, 0.1s display
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

    # ------------------------------------------------------------------
    # Metadata-handling / completion
    # ------------------------------------------------------------------
    def test_encoding_complete_handler_with_traditional_metadata(self):
        metadata = {
            "total_size": 1000,
            "total_chunks": 5,
            "encoding_type": "traditional",
        }
        self.gui.current_file = "/tmp/fake"
        self.gui._encoding_complete(metadata)
        self.assertEqual(int(self.gui.progress_var.get()), 100)

    def test_encoding_complete_handler_with_parallel_metadata(self):
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

    # ------------------------------------------------------------------
    # End-to-end through the encoding worker (synchronous)
    # ------------------------------------------------------------------
    def test_worker_prepares_chunks_and_caches_images(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(b"GUI encoding test payload " * 50)
        tmp.close()
        try:
            self.gui.current_file = tmp.name
            self.gui.file_path_var.set(tmp.name)
            self.gui._encode_file_worker()

            self.assertIsNotNone(self.gui.encoder)
            self.assertGreater(self.gui.encoder.get_total_chunks(), 0)
            self.assertEqual(self.gui.total_chunks, self.gui.encoder.get_total_chunks())
            # Prefetch is enabled by default for small files
            self.assertIsNotNone(self.gui.encoder.get_qr_images())
        finally:
            Path(tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
