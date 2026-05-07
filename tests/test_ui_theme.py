"""Smoke tests for the shared UI theme module."""

import tkinter as tk
import unittest

from tests.conftest import get_session_root


_ROOT = get_session_root()


class TestThemeImport(unittest.TestCase):
    def test_imports_palette_constants(self):
        from qrl_server import ui_theme

        self.assertTrue(ui_theme.BG.startswith("#"))
        self.assertTrue(ui_theme.ACCENT.startswith("#"))
        self.assertTrue(ui_theme.FG.startswith("#"))


@unittest.skipUnless(_ROOT is not None, "no display available for tk.Tk()")
class TestThemeApplication(unittest.TestCase):
    def test_apply_theme_returns_fonts_dict(self):
        from qrl_server.ui_theme import apply_theme

        fonts = apply_theme(_ROOT)
        for key in ("h1", "h2", "body", "body_bold", "small", "mono"):
            self.assertIn(key, fonts)

    def test_status_pill_widget_creates_and_updates(self):
        from qrl_server.ui_theme import apply_theme, set_status, status_pill

        apply_theme(_ROOT)  # ensure styles defined
        label = status_pill(_ROOT)
        self.assertIn("Idle", str(label.cget("text")))

        set_status(label, "running", "Capturing")
        self.assertIn("Capturing", str(label.cget("text")))
        self.assertEqual(str(label.cget("style")), "StatusRunning.TLabel")

        set_status(label, "ok", "Complete")
        self.assertEqual(str(label.cget("style")), "StatusOk.TLabel")

        set_status(label, "error", "Failed")
        self.assertEqual(str(label.cget("style")), "StatusError.TLabel")

        label.destroy()

    def test_card_returns_styled_frame(self):
        from qrl_server.ui_theme import apply_theme, card

        apply_theme(_ROOT)
        c = card(_ROOT)
        self.assertEqual(str(c.cget("style")), "Card.TFrame")
        c.destroy()


if __name__ == "__main__":
    unittest.main()
