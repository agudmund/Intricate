#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - utils/OSClickMonitor.py OSClickMonitor class
-OS-level global mouse hook. Knows what the mouse is clicking, unconditionally for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import ctypes
import ctypes.wintypes as wt
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint


# ─────────────────────────────────────────────────────────────────────────────
# WIN32 SETUP
# ─────────────────────────────────────────────────────────────────────────────
#
# Platform-guarded: ctypes.WinDLL and ctypes.WINFUNCTYPE are Windows-only.
# On non-Windows hosts the module imports cleanly with stubs; the OSClickMonitor
# class's install() turns into a no-op (logged once) so the HealthNode that
# owns it never observes a "click monitor missing" failure mode — there's
# simply no global mouse hook on a Linux/macOS host, which is the correct
# behaviour anyway since WH_MOUSE_LL is a Win32 hook and has no portable
# equivalent we'd want here.

WH_MOUSE_LL    = 14
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207

if sys.platform == "win32":
    user32   = ctypes.WinDLL("user32",   use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Explicit argtypes and restype for every user32 call that touches pointer-sized
    # values. Without these, ctypes defaults to c_int (32-bit) for all arguments,
    # which silently truncates 64-bit pointers on 64-bit Windows — exactly the
    # overflow we are fixing. Declared once at module load, applies to all calls.
    user32.SetWindowsHookExW.restype  = ctypes.c_void_p
    user32.SetWindowsHookExW.argtypes = [
        ctypes.c_int,       # idHook
        ctypes.c_void_p,    # lpfn   — HOOKPROC function pointer
        ctypes.c_void_p,    # hMod
        wt.DWORD,           # dwThreadId
    ]

    user32.CallNextHookEx.restype  = ctypes.c_long
    user32.CallNextHookEx.argtypes = [
        ctypes.c_void_p,    # hhk    — hook handle (pointer-sized)
        ctypes.c_int,       # nCode
        wt.WPARAM,          # wParam
        ctypes.c_void_p,    # lParam — pointer to MSLLHOOKSTRUCT (pointer-sized)
    ]

    user32.UnhookWindowsHookEx.restype  = wt.BOOL
    user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

    user32.WindowFromPoint.restype  = ctypes.c_void_p
    user32.WindowFromPoint.argtypes = [wt.POINT]

    user32.GetWindowThreadProcessId.restype  = wt.DWORD
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]


    # HOOKPROC signature for WH_MOUSE_LL on 64-bit Windows.
    # lParam MUST be c_void_p — it carries a pointer to MSLLHOOKSTRUCT.
    # Using LPARAM (c_long, 32-bit) overflows on 64-bit and breaks CallNextHookEx.
    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_long,      # return
        ctypes.c_int,       # nCode
        wt.WPARAM,          # wParam  — message identifier (WM_LBUTTONDOWN etc.)
        ctypes.c_void_p,    # lParam  — pointer to MSLLHOOKSTRUCT (64-bit safe)
    )
else:
    user32   = None
    kernel32 = None
    HOOKPROC = None


class MSLLHOOKSTRUCT(ctypes.Structure):
    """
    Low-level mouse hook data.
    https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-msllhookstruct
    """
    _fields_ = [
        ("pt",          wt.POINT),
        ("mouseData",   wt.DWORD),
        ("flags",       wt.DWORD),
        ("time",        wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wt.ULONG)),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# MONITOR
# ─────────────────────────────────────────────────────────────────────────────

class OSClickMonitor:
    """
    Global OS-level mouse click monitor using WH_MOUSE_LL.

    Installs a low-level Windows mouse hook that fires on every mouse button
    press system-wide — inside our window, inside other apps, on the desktop,
    everywhere. Reports exactly what the OS received the click on.

    Threading contract:
        Must be installed from the main thread. WH_MOUSE_LL fires on the
        installing thread, pumped by Qt's Win32 message loop automatically.
        No secondary threads, no synchronisation needed.

    Hook contract:
        CallNextHookEx is called unconditionally after every callback.
        We observe. We never consume. Consuming events breaks other apps.

    Click classification (priority order):
        1. Qt scene item    — a QGraphicsItem in our scene
        2. Qt widget        — our process, not a scene item
        3. External process — outside our process (shows exe name)
    """

    def __init__(self, health_node):
        self._health   = health_node
        self._hook     = None       # HHOOK — None when not installed
        self._callback = None       # HOOKPROC ref — must stay alive while hooked

    # ─────────────────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def install(self) -> None:
        """
        Install the global mouse hook. Idempotent. Main thread only.

        No-op on non-Windows hosts — WH_MOUSE_LL has no portable equivalent
        and the HealthNode that owns this monitor is content with a missing
        click stream there (the census panel just shows zeroes).
        """
        if self._hook is not None:
            return
        if HOOKPROC is None or user32 is None:
            return  # non-Windows host: nothing to hook into

        self._callback = HOOKPROC(self._hook_callback)

        self._hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            self._callback,
            None,   # hMod — NULL is correct for WH_MOUSE_LL on modern Windows
            0       # dwThreadId=0 — global, all threads
        )

        if not self._hook:
            err = ctypes.get_last_error()
            self._callback = None
            raise OSError(f"SetWindowsHookExW failed — error code {err}")

    def uninstall(self) -> None:
        """
        Remove the global mouse hook. Idempotent.
        """
        if self._hook is None:
            return
        user32.UnhookWindowsHookEx(self._hook)
        self._hook     = None
        self._callback = None

    # ─────────────────────────────────────────────────────────────────────────
    # HOOK CALLBACK
    # ─────────────────────────────────────────────────────────────────────────

    def _hook_callback(self, n_code: int, w_param: int, l_param) -> int:
        """
        Called by Windows on every low-level mouse event.

        l_param is c_void_p — cast to MSLLHOOKSTRUCT pointer to read coords.
        CallNextHookEx is always last, unconditionally.
        """
        if n_code >= 0 and w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
            try:
                # Cast the void pointer to our struct pointer and dereference
                data     = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                screen_x = data.pt.x
                screen_y = data.pt.y
                self._classify_and_report(screen_x, screen_y)
            except Exception:
                pass  # Never crash the hook chain — we are a guest here

        # UNCONDITIONAL — always pass the event through
        return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

    # ─────────────────────────────────────────────────────────────────────────
    # CLASSIFICATION
    # ─────────────────────────────────────────────────────────────────────────

    def _classify_and_report(self, screen_x: int, screen_y: int) -> None:
        """
        Classify a click at screen coordinates and write to HealthNode display.
        """
        app = QApplication.instance()
        if not app:
            return

        global_pt = QPoint(screen_x, screen_y)

        # ── 1. Check for a Qt widget at this screen position ──────────────────
        widget = app.widgetAt(global_pt)

        if widget is not None:
            scene = self._health.scene()
            if scene and scene.views():
                view = scene.views()[0]
                if widget is view.viewport():
                    # Click landed on the scene viewport — find the scene item
                    viewport_pos = view.viewport().mapFromGlobal(global_pt)
                    scene_pos    = view.mapToScene(viewport_pos)
                    items        = scene.items(scene_pos)
                    if items:
                        top        = items[0]
                        item_title = (
                            getattr(getattr(top, 'data', None), 'title', None)
                            or getattr(top, 'uuid', None)
                            or str(id(top))[:8]
                        )
                        self._health._last_clicked_type = type(top).__name__
                        self._health._last_clicked_item = item_title
                    else:
                        self._health._last_clicked_type = "canvas"
                        self._health._last_clicked_item = "— empty —"
                    return

            # Qt widget but not the scene viewport
            self._health._last_clicked_type = type(widget).__name__
            self._health._last_clicked_item = (
                widget.objectName() or widget.windowTitle() or "—"
            )
            return

        # ── 2. No Qt widget — outside our process ─────────────────────────────
        pt      = wt.POINT(screen_x, screen_y)
        hwnd    = user32.WindowFromPoint(pt)
        if hwnd:
            pid = wt.DWORD(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            self._health._last_clicked_type = "external"
            self._health._last_clicked_item = _process_name(pid.value)
        else:
            self._health._last_clicked_type = "external"
            self._health._last_clicked_item = "— desktop —"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _process_name(pid: int) -> str:
    """
    Resolve a PID to its executable name.
    Returns filename only — full path is noise in a diagnostic display.
    Degrades gracefully if access is denied.
    """
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return f"pid:{pid}"
    try:
        buf  = ctypes.create_unicode_buffer(260)
        size = wt.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.split("\\")[-1]
        return f"pid:{pid}"
    finally:
        kernel32.CloseHandle(handle)
