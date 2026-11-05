"""Light or dark look, following the operating system's setting at start-up.

Windows and Linux use the Sun Valley ttk theme (sv-ttk); macOS keeps its native look,
which already follows the system. Plain Tk widgets (Text, Canvas) are not themed by ttk,
so callers colour them from the returned palette.
"""

import sys
import tkinter as tk
from tkinter import ttk

PALETTES = {
    "light": {"muted": "#5f5f5f", "warn": "#b45309", "text_bg": "#f3f3f3", "text_fg": "#1c1c1c"},
    "dark": {"muted": "#a8a8a8", "warn": "#f5a524", "text_bg": "#232323", "text_fg": "#e4e4e4"},
}


def system_mode() -> str:
    try:
        import darkdetect

        return "dark" if (darkdetect.theme() or "").lower() == "dark" else "light"
    except Exception:
        return "light"


def _dark_title_bar(root: tk.Tk):
    """Windows 10 1809+/11: ask the window manager for a dark title bar."""
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, and its pre-20H1 number
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def apply(root: tk.Tk) -> dict:
    """Theme the window like the system and return the palette for non-ttk widgets."""
    mode = system_mode()
    palette = dict(PALETTES[mode])
    style = ttk.Style(root)
    if sys.platform == "darwin":
        palette["bg"] = str(style.lookup("TFrame", "background") or root.cget("background"))
        return palette
    try:
        import sv_ttk

        sv_ttk.set_theme(mode)
        # sv-ttk sets the base colours (frames, labels, window) on <<ThemeChanged>>, which a
        # window that is not on screen yet never receives: run its handler directly.
        root.tk.call("configure_colors")
    except Exception:
        mode = "light"
        palette = dict(PALETTES["light"])
        style.theme_use("vista" if "vista" in style.theme_names() else "clam")
    if sys.platform == "win32" and mode == "dark":
        _dark_title_bar(root)
    palette["bg"] = str(style.lookup("TFrame", "background") or root.cget("background"))
    return palette
