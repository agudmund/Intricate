#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/window_behind.py window-behind detection
-Finds the window directly behind Intricate in Z-order for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import ctypes
import ctypes.wintypes as wt
import os

from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("window_behind")

# ─────────────────────────────────────────────────────────────────────────────
# WIN32 SETUP — explicit argtypes for 64-bit pointer safety
# ─────────────────────────────────────────────────────────────────────────────

user32   = ctypes.WinDLL("user32",   use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GW_HWNDNEXT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32.GetWindow.restype  = ctypes.c_void_p
user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]

user32.IsWindowVisible.restype  = wt.BOOL
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]

user32.IsIconic.restype  = wt.BOOL
user32.IsIconic.argtypes = [ctypes.c_void_p]

user32.GetWindowTextW.restype  = ctypes.c_int
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]

user32.GetWindowTextLengthW.restype  = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]

user32.GetWindowRect.restype  = wt.BOOL
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.RECT)]

user32.GetWindowThreadProcessId.restype  = wt.DWORD
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]

kernel32.OpenProcess.restype  = ctypes.c_void_p
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]

kernel32.QueryFullProcessImageNameW.restype  = wt.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    ctypes.c_void_p, wt.DWORD, ctypes.c_wchar_p, ctypes.POINTER(wt.DWORD)
]

kernel32.CloseHandle.restype  = wt.BOOL
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def _get_exe(hwnd) -> str:
    """Resolve a window handle to its executable name."""
    pid = wt.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wt.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _get_title(hwnd) -> str:
    """Get the window title text."""
    length = user32.GetWindowTextLengthW(hwnd)
    if not length:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_rect(hwnd) -> dict:
    """Get the window geometry as a dict."""
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return {
        "x": rect.left,
        "y": rect.top,
        "width": rect.right - rect.left,
        "height": rect.bottom - rect.top,
    }


_last_exe = None

def get_window_behind(own_hwnd: int) -> dict | None:
    """Find the first visible, non-minimized window behind *own_hwnd* in Z-order.

    Returns a dict with keys: hwnd, title, exe, rect — or None if nothing found.
    """
    global _last_exe
    hwnd = user32.GetWindow(own_hwnd, GW_HWNDNEXT)
    while hwnd:
        if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            title = _get_title(hwnd)
            # Skip windows with no title (ghost shells, tool windows)
            if title:
                exe = _get_exe(hwnd)
                result = {
                    "hwnd": hwnd,
                    "title": title,
                    "exe": exe,
                    "rect": _get_rect(hwnd),
                }
                if exe != _last_exe:
                    logger.debug(f"Window behind: {exe} — \"{title}\"")
                    _last_exe = exe
                return result
        hwnd = user32.GetWindow(hwnd, GW_HWNDNEXT)
    return None
