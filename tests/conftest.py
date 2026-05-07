"""Pytest session fixtures.

Provides a single Tk root shared across the whole test session. Tk on
Windows can't reliably destroy and recreate `tk.Tk()` instances within
one process, so all GUI tests reuse this root via Toplevel windows.
"""

import tkinter as tk

import pytest


_session_root = None
_display_ok = None  # cached probe result — see note below


def _can_open_display() -> bool:
    """Check if Tk can open a display. Result is cached after the first call.

    Windows can't reliably create/destroy multiple `tk.Tk()` instances in one
    process — the second `Tk()` after a `destroy()` often fails with cryptic
    Tcl init errors. Probing on every call would cause test classes to skip
    after the first module that touched Tk."""
    global _display_ok, _session_root
    if _display_ok is not None:
        return _display_ok
    try:
        # Reuse this root as the session root instead of creating + destroying
        # a probe — that's what the second `tk.Tk()` would fail at.
        _session_root = tk.Tk()
        _session_root.withdraw()
        _display_ok = True
    except tk.TclError:
        _display_ok = False
    return _display_ok


@pytest.fixture(scope="session")
def tk_root():
    """A session-scoped Tk root. Skips the test if no display is available."""
    if not _can_open_display():
        pytest.skip("No display available for tk.Tk()")
    yield _session_root
    # Don't destroy at session end — interpreter teardown handles it, and
    # destroying here can crash on Windows.


def get_session_root():
    """Module-level accessor for unittest-style tests that can't take fixtures."""
    if not _can_open_display():
        return None
    return _session_root
