"""
Shared visual theme for QRL server and client GUIs.

Provides a small palette, font choices, and ttk style configuration so both
apps look like part of the same product. Call `apply_theme(root)` once after
creating the Tk root.
"""

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk


# --- Palette --------------------------------------------------------------
# Calm slate-blue with subtle accents. WCAG AA contrast for foreground/bg.
BG = "#1e2530"          # main window background
BG_ELEVATED = "#2a3340"  # cards / panels
BG_INPUT = "#36404f"     # entries / spinboxes
FG = "#e6ecf2"           # primary text
FG_MUTED = "#9aa6b8"     # secondary text / labels
ACCENT = "#4a90e2"       # primary action / focus
ACCENT_HOVER = "#5fa3ee"
ACCENT_PRESSED = "#3978c4"
SUCCESS = "#3ec19a"
WARNING = "#e8a838"
DANGER = "#e85c5c"
BORDER = "#3a4555"

STATUS_IDLE = FG_MUTED
STATUS_RUNNING = WARNING
STATUS_OK = SUCCESS
STATUS_ERROR = DANGER


# --- Fonts ----------------------------------------------------------------
def _pick_family(*candidates: str) -> str:
    available = set(tkfont.families())
    for c in candidates:
        if c in available:
            return c
    return "TkDefaultFont"


def configure_fonts(root: tk.Tk) -> dict:
    """Pick a clean sans family and return named font handles."""
    family = _pick_family("Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", "Arial")
    mono = _pick_family("Consolas", "JetBrains Mono", "Menlo", "Courier New")

    fonts = {
        "h1": tkfont.Font(root=root, family=family, size=18, weight="bold"),
        "h2": tkfont.Font(root=root, family=family, size=13, weight="bold"),
        "body": tkfont.Font(root=root, family=family, size=10),
        "body_bold": tkfont.Font(root=root, family=family, size=10, weight="bold"),
        "small": tkfont.Font(root=root, family=family, size=9),
        "mono": tkfont.Font(root=root, family=mono, size=10),
    }
    # Also override Tk's defaults so untyped widgets pick up the family
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=family, size=10)
        except tk.TclError:
            pass
    try:
        tkfont.nametofont("TkFixedFont").configure(family=mono, size=10)
    except tk.TclError:
        pass
    return fonts


# --- Style ----------------------------------------------------------------
def apply_theme(root: tk.Tk) -> dict:
    """Apply the QRL theme to the given root. Returns the fonts dict."""
    fonts = configure_fonts(root)

    root.configure(bg=BG)

    style = ttk.Style(root)
    # 'clam' allows full color control on Windows; default 'vista' theme
    # ignores most ttk style overrides.
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", background=BG, foreground=FG, fieldbackground=BG_INPUT,
                    bordercolor=BORDER, lightcolor=BG, darkcolor=BG,
                    troughcolor=BG_ELEVATED, focuscolor=ACCENT)

    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=BG_ELEVATED, relief="flat", borderwidth=0)
    style.configure("TLabel", background=BG, foreground=FG, font=fonts["body"])
    style.configure("Card.TLabel", background=BG_ELEVATED, foreground=FG)
    style.configure("Muted.TLabel", background=BG, foreground=FG_MUTED, font=fonts["small"])
    style.configure("CardMuted.TLabel", background=BG_ELEVATED, foreground=FG_MUTED, font=fonts["small"])
    style.configure("H1.TLabel", background=BG, foreground=FG, font=fonts["h1"])
    style.configure("H2.TLabel", background=BG, foreground=FG, font=fonts["h2"])
    style.configure("CardH2.TLabel", background=BG_ELEVATED, foreground=FG, font=fonts["h2"])

    # Status pill labels — drawn as colored text
    style.configure("StatusIdle.TLabel", background=BG, foreground=STATUS_IDLE, font=fonts["body_bold"])
    style.configure("StatusRunning.TLabel", background=BG, foreground=STATUS_RUNNING, font=fonts["body_bold"])
    style.configure("StatusOk.TLabel", background=BG, foreground=STATUS_OK, font=fonts["body_bold"])
    style.configure("StatusError.TLabel", background=BG, foreground=STATUS_ERROR, font=fonts["body_bold"])

    # Buttons
    style.configure("TButton", background=BG_ELEVATED, foreground=FG,
                    bordercolor=BORDER, padding=(12, 6), font=fonts["body"], borderwidth=1)
    style.map("TButton",
              background=[("active", BG_INPUT), ("pressed", BG_INPUT)],
              bordercolor=[("focus", ACCENT)])

    style.configure("Primary.TButton", background=ACCENT, foreground="#ffffff",
                    bordercolor=ACCENT, padding=(16, 8), font=fonts["body_bold"])
    style.map("Primary.TButton",
              background=[("active", ACCENT_HOVER), ("pressed", ACCENT_PRESSED), ("disabled", BG_ELEVATED)],
              foreground=[("disabled", FG_MUTED)])

    style.configure("Danger.TButton", background=DANGER, foreground="#ffffff",
                    bordercolor=DANGER, padding=(12, 6), font=fonts["body_bold"])
    style.map("Danger.TButton",
              background=[("active", "#ef7373"), ("pressed", "#c44a4a"), ("disabled", BG_ELEVATED)],
              foreground=[("disabled", FG_MUTED)])

    style.configure("Chip.TButton", background=BG_ELEVATED, foreground=FG,
                    bordercolor=BORDER, padding=(10, 4), font=fonts["small"])
    style.map("Chip.TButton",
              background=[("active", BG_INPUT)])
    style.configure("ChipActive.TButton", background=ACCENT, foreground="#ffffff",
                    bordercolor=ACCENT, padding=(10, 4), font=fonts["small"])

    # Entries / spinboxes / combos
    style.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG,
                    bordercolor=BORDER, insertcolor=FG, padding=4)
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure("TSpinbox", fieldbackground=BG_INPUT, foreground=FG,
                    bordercolor=BORDER, arrowcolor=FG, padding=2)
    style.map("TSpinbox",
              bordercolor=[("focus", ACCENT)],
              fieldbackground=[("readonly", BG_INPUT)])
    style.configure("TCombobox", fieldbackground=BG_INPUT, foreground=FG,
                    bordercolor=BORDER, arrowcolor=FG, padding=4,
                    selectbackground=ACCENT, selectforeground="#ffffff")
    style.map("TCombobox",
              fieldbackground=[("readonly", BG_INPUT)],
              foreground=[("readonly", FG)],
              bordercolor=[("focus", ACCENT)])

    # Checkbutton
    style.configure("TCheckbutton", background=BG, foreground=FG,
                    indicatorbackground=BG_INPUT, indicatorforeground=ACCENT,
                    focuscolor=BG, padding=4)
    style.map("TCheckbutton",
              background=[("active", BG)],
              indicatorbackground=[("selected", ACCENT)])
    style.configure("Card.TCheckbutton", background=BG_ELEVATED, foreground=FG,
                    indicatorbackground=BG_INPUT, focuscolor=BG_ELEVATED, padding=4)

    # Notebook (tabs)
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG_ELEVATED, foreground=FG_MUTED,
                    padding=(16, 8), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", BG)],
              foreground=[("selected", FG)],
              expand=[("selected", [1, 1, 1, 0])])

    # Progressbar
    style.configure("Horizontal.TProgressbar", background=ACCENT,
                    troughcolor=BG_ELEVATED, bordercolor=BG_ELEVATED,
                    lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)

    # Scale (slider)
    style.configure("Horizontal.TScale", background=BG, troughcolor=BG_ELEVATED)

    # Scrollbar
    style.configure("Vertical.TScrollbar", background=BG_ELEVATED,
                    troughcolor=BG, bordercolor=BG, arrowcolor=FG_MUTED,
                    lightcolor=BG_ELEVATED, darkcolor=BG_ELEVATED)

    # PanedWindow sash
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=6, gripcount=0, background=BG_ELEVATED)

    # Separator
    style.configure("TSeparator", background=BORDER)

    # LabelFrame (used in some legacy code paths)
    style.configure("TLabelframe", background=BG_ELEVATED, foreground=FG,
                    bordercolor=BORDER, padding=10, borderwidth=1, relief="solid")
    style.configure("TLabelframe.Label", background=BG_ELEVATED, foreground=FG, font=fonts["body_bold"])

    return fonts


# --- Convenience widgets ---------------------------------------------------
def card(parent: tk.Misc, padding: int = 14, **kwargs) -> ttk.Frame:
    """A styled panel with elevated background and inner padding."""
    frame = ttk.Frame(parent, style="Card.TFrame", padding=padding, **kwargs)
    return frame


def section_heading(parent: tk.Misc, text: str, on_card: bool = False) -> ttk.Label:
    return ttk.Label(parent, text=text, style="CardH2.TLabel" if on_card else "H2.TLabel")


def hsep(parent: tk.Misc) -> ttk.Separator:
    return ttk.Separator(parent, orient=tk.HORIZONTAL)


def status_pill(parent: tk.Misc) -> ttk.Label:
    """Status indicator. Update via set_status()."""
    label = ttk.Label(parent, text="● Idle", style="StatusIdle.TLabel")
    return label


def set_status(label: ttk.Label, kind: str, text: str) -> None:
    """kind in {'idle','running','ok','error'}."""
    style = {
        "idle": "StatusIdle.TLabel",
        "running": "StatusRunning.TLabel",
        "ok": "StatusOk.TLabel",
        "error": "StatusError.TLabel",
    }.get(kind, "StatusIdle.TLabel")
    label.configure(text=f"● {text}", style=style)


# Re-export for convenience
__all__ = [
    "BG", "BG_ELEVATED", "BG_INPUT", "FG", "FG_MUTED",
    "ACCENT", "ACCENT_HOVER", "SUCCESS", "WARNING", "DANGER", "BORDER",
    "apply_theme", "configure_fonts",
    "card", "section_heading", "hsep", "status_pill", "set_status",
]
