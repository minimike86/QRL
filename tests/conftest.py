"""Pytest session fixtures.

Provides a single Tk root shared across the whole test session. Tk on
Windows can't reliably destroy and recreate `tk.Tk()` instances within
one process, so all GUI tests reuse this root via Toplevel windows.
"""

import tkinter as tk

import pytest


_session_root = None


def _can_open_display() -> bool:
    try:
        root = tk.Tk()
    except tk.TclError:
        return False
    root.destroy()
    return True


@pytest.fixture(scope="session")
def tk_root():
    """A session-scoped Tk root. Skips the test if no display is available."""
    global _session_root
    if not _can_open_display():
        pytest.skip("No display available for tk.Tk()")
    if _session_root is None:
        _session_root = tk.Tk()
        _session_root.withdraw()
    yield _session_root
    # Don't destroy at session end — interpreter teardown handles it, and
    # destroying here can crash on Windows.


def get_session_root():
    """Module-level accessor for unittest-style tests that can't take fixtures."""
    global _session_root
    if not _can_open_display():
        return None
    if _session_root is None:
        _session_root = tk.Tk()
        _session_root.withdraw()
    return _session_root
