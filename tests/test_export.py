"""Tests for the server's PDF + video export."""

import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from tests.conftest import get_session_root


_ROOT = get_session_root()


@unittest.skipUnless(_ROOT is not None, "no display available for tk.Tk()")
class TestExports(unittest.TestCase):
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
        # Prepare a small file through the encode worker so the GUI is in a
        # post-prepare state ready to export.
        self.tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        self.tmp_file.write(b"export test payload " * 30)
        self.tmp_file.close()
        self.gui.current_file = self.tmp_file.name
        self.gui._current_size_bytes = Path(self.tmp_file.name).stat().st_size
        self.gui.file_path_var.set(self.tmp_file.name)
        self.gui._apply_grid(1, 1, auto=False)  # single-stream mode for simplicity
        self.gui._encode_worker()

    def tearDown(self):
        Path(self.tmp_file.name).unlink(missing_ok=True)

    def test_export_pdf_writes_multipage_file(self):
        out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        out.close()
        try:
            self.gui._export_pdf_worker(out.name)
            self.assertTrue(Path(out.name).exists())
            self.assertGreater(Path(out.name).stat().st_size, 0)
            # Crude PDF magic bytes check
            self.assertEqual(Path(out.name).read_bytes()[:4], b"%PDF")
        finally:
            Path(out.name).unlink(missing_ok=True)

    def test_export_video_writes_mp4(self):
        out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        out.close()
        try:
            self.gui._export_video_worker(out.name)
            self.assertTrue(Path(out.name).exists())
            self.assertGreater(Path(out.name).stat().st_size, 0)
        finally:
            Path(out.name).unlink(missing_ok=True)

    def test_frames_for_export_includes_manifest_first(self):
        frames = list(self.gui._frames_for_export())
        self.assertGreater(len(frames), 1)
        # Manifest is the first frame; subsequent frames are the data QRs
        self.assertEqual(len(frames), 1 + self.gui.total_chunks)


@unittest.skipUnless(_ROOT is not None, "no display available for tk.Tk()")
class TestExportsParallelMode(unittest.TestCase):
    """Regression for the bug the user hit: Save in parallel mode crashed
    because self.encoder was None. Exports must work for parallel mode too."""

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

    def test_pdf_export_works_in_parallel_mode(self):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp.write(b"parallel export payload " * 40)
        tmp.close()
        out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        out.close()
        try:
            self.gui.current_file = tmp.name
            self.gui._current_size_bytes = Path(tmp.name).stat().st_size
            self.gui._apply_grid(2, 2, auto=False)  # 2x2 parallel
            self.gui._encode_worker()
            self.gui._export_pdf_worker(out.name)
            self.assertTrue(Path(out.name).exists())
            self.assertGreater(Path(out.name).stat().st_size, 0)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
            Path(out.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
