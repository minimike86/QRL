#!/usr/bin/env python3
"""
QRL Combined GUI

Single window with two tabs — Server (encoder) and Client (decoder) — so you
can switch between sending and receiving without juggling two processes.

Each tab embeds the existing ``QRLServerGUI`` / ``QRLClientGUI`` into its
frame; their workflow, theme, and behavior are unchanged.
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox

from qrl_client.gui import QRLClientGUI
from qrl_server.gui import QRLServerGUI
from qrl_server.ui_theme import ACCENT, BG, BG_ELEVATED, FG, FG_MUTED, apply_theme


class QRLCombinedGUI:
    def __init__(self) -> None:
        # Prefer TkinterDnD root so the server tab can still accept dropped files.
        try:
            from tkinterdnd2 import TkinterDnD

            self.root = TkinterDnD.Tk()
            self._dnd_root = True
        except Exception:
            self.root = tk.Tk()
            self._dnd_root = False

        self.root.title("QRL — QR Stream Server & Client")
        self.root.geometry("1180x820")
        self.root.minsize(980, 700)

        self.fonts = apply_theme(self.root)
        self._style_notebook()

        self.notebook = ttk.Notebook(self.root, style="QRL.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 8))

        self.server_tab = ttk.Frame(self.notebook)
        self.client_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.server_tab, text="  Server — Send  ")
        self.notebook.add(self.client_tab, text="  Client — Receive  ")

        self.server = QRLServerGUI(parent=self.server_tab)
        self.client = QRLClientGUI(parent=self.client_tab)

        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _style_notebook(self) -> None:
        style = ttk.Style(self.root)
        style.configure(
            "QRL.TNotebook",
            background=BG,
            borderwidth=0,
            tabmargins=(8, 6, 8, 0),
        )
        style.configure(
            "QRL.TNotebook.Tab",
            background=BG_ELEVATED,
            foreground=FG_MUTED,
            padding=(18, 10),
            borderwidth=0,
            font=self.fonts["body_bold"],
        )
        style.map(
            "QRL.TNotebook.Tab",
            background=[("selected", ACCENT)],
            foreground=[("selected", FG)],
        )

    def _on_closing(self) -> None:
        busy_msgs = []
        if getattr(self.server, "is_encoding", False):
            busy_msgs.append("the server is encoding")
        if getattr(self.server, "is_displaying", False):
            busy_msgs.append("the server is displaying QR codes")
        if getattr(self.client, "is_capturing", False):
            busy_msgs.append("the client is capturing")
        if busy_msgs:
            msg = "Quit anyway?\n\nIn progress: " + ", ".join(busy_msgs) + "."
            if not messagebox.askyesno("Quit QRL", msg):
                return
        try:
            self.server.shutdown()
        except Exception:
            pass
        try:
            self.client.shutdown()
        except Exception:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._on_closing()


def main() -> None:
    try:
        QRLCombinedGUI().run()
    except Exception as e:
        print(f"Error starting QRL combined GUI: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
