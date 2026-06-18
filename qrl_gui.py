#!/usr/bin/env python3
"""QRL — QR Link Receiver GUI."""

import sys
import tkinter as tk
from tkinter import messagebox

from qrl_client.gui import QRLClientGUI
from qrl_client.ui_theme import apply_theme


def main() -> None:
    try:
        root = tk.Tk()
        root.title("QRL — QR Link Receiver")
        root.geometry("1100x780")
        root.minsize(900, 650)

        apply_theme(root)
        client = QRLClientGUI(parent=root)

        def on_closing() -> None:
            if getattr(client, "is_capturing", False):
                if not messagebox.askyesno("Quit QRL", "Capture is running. Quit anyway?"):
                    return
            try:
                client.shutdown()
            except Exception:
                pass
            try:
                root.destroy()
            except tk.TclError:
                pass

        root.protocol("WM_DELETE_WINDOW", on_closing)

        try:
            root.mainloop()
        except KeyboardInterrupt:
            on_closing()

    except Exception as e:
        print(f"Error starting QRL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
