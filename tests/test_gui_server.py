"""Server GUI tests for the redesigned UI."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.conftest import get_session_root


_ROOT = get_session_root()


@unittest.skipUnless(_ROOT is not None, "no display available for tk.Tk()")
class TestServerGUI(unittest.TestCase):
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

    def setUp(self):
        self.gui.is_encoding = False
        self.gui.is_displaying = False
        self.gui.encoder = None
        self.gui.parallel_encoder = None
        self.gui.qr_images = []
        self.gui.current_file = None
        self.gui.total_chunks = 0
        self.gui.progress_var.set(0)

    def test_initial_state(self):
        self.assertFalse(self.gui.is_encoding)
        self.assertFalse(self.gui.is_displaying)
        self.assertIsNone(self.gui.encoder)

    def test_default_config_loaded(self):
        # Default is now "Robust" (H-level): better tolerance for
        # screen-capture compression artefacts and partial occlusion.
        self.assertEqual(self.gui.config.chunk_size, 1140)
        self.assertAlmostEqual(self.gui.config.duration, 0.1)
        self.assertEqual(self.gui.config.error_correction, "H")

    def test_speed_preset_updates_config(self):
        self.gui._set_speed_preset(0.05)
        self.assertAlmostEqual(self.gui.config.duration, 0.05)
        self.gui._set_speed_preset(0.1)
        self.assertAlmostEqual(self.gui.config.duration, 0.1)

    def test_quality_preset_updates_config(self):
        self.gui._set_quality_preset("L", 2670)
        self.assertEqual(self.gui.config.error_correction, "L")
        self.assertEqual(self.gui.config.chunk_size, 2670)
        self.gui._set_quality_preset("H", 1140)
        self.assertEqual(self.gui.config.error_correction, "H")
        self.assertEqual(self.gui.config.chunk_size, 1140)

    def test_mode_preset_toggles_parallel(self):
        self.gui._set_mode_preset(1)
        self.assertFalse(self.gui.use_parallel_encoding)
        self.gui._set_mode_preset(4)
        self.assertTrue(self.gui.use_parallel_encoding)
        self.assertEqual(self.gui._mode_streams, 4)
        self.assertEqual(self.gui.config.qr_grid_size, 2)

    def test_button_states_idle_no_file(self):
        self.gui._update_button_states()
        self.assertEqual(str(self.gui.encode_btn["state"]), "disabled")
        self.assertEqual(str(self.gui.display_btn["state"]), "disabled")
        self.assertEqual(str(self.gui.stop_btn["state"]), "disabled")

    def test_button_states_with_file(self):
        self.gui.current_file = "/tmp/whatever"
        self.gui._update_button_states()
        self.assertEqual(str(self.gui.encode_btn["state"]), "normal")

    def test_log_appends(self):
        self.gui._log("server test message")
        contents = self.gui.log_text.get("1.0", tk.END)
        self.assertIn("server test message", contents)

    def test_encode_without_file_shows_error(self):
        self.gui.current_file = None
        with patch("tkinter.messagebox.showerror") as mock_err:
            self.gui._encode_file()
        mock_err.assert_called()

    def test_status_pill_exists(self):
        self.assertIsNotNone(self.gui.status_label)


@unittest.skipUnless(_ROOT is not None, "no display available for tk.Tk()")
class TestServerGUIEncodingFlow(unittest.TestCase):
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

    def test_worker_prepares_chunks_without_prefetch(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(b"GUI encoding test payload " * 50)
        tmp.close()
        try:
            self.gui.current_file = tmp.name
            self.gui._current_size_bytes = Path(tmp.name).stat().st_size
            self.gui.file_path_var.set(tmp.name)
            self.gui._encode_worker()  # synchronous

            self.assertIsNotNone(self.gui.encoder)
            self.assertGreater(self.gui.encoder.get_total_chunks(), 0)
            self.assertEqual(self.gui.total_chunks, self.gui.encoder.get_total_chunks())
            # Prefetch is gone — QR images are generated on the fly during
            # display. The lazy cache exists but is empty until display starts.
            self.assertEqual(self.gui._qr_cache, {})
            # Lazy generation works on demand:
            img = self.gui._lazy_qr_image(0)
            self.assertTrue(hasattr(img, "save"))
            self.assertIn(0, self.gui._qr_cache)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
