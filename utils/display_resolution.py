#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate - utils/display_resolution.py fivefold display-resolution validation
-Five independent sources cross-check the physical resolution for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import ctypes
import ctypes.wintypes as wt
import winreg
from dataclasses import dataclass, field

from pretty_widgets.utils.logger import setup_logger

logger = setup_logger("display_resolution")


# ─────────────────────────────────────────────────────────────────────────────
# WIN32 SCAFFOLDING
# ─────────────────────────────────────────────────────────────────────────────

user32  = ctypes.WinDLL("user32",  use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

ENUM_CURRENT_SETTINGS = -1

# Taskbar query
ABM_GETTASKBARPOS = 0x00000005


class _APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize",           wt.DWORD),
        ("hWnd",             ctypes.c_void_p),
        ("uCallbackMessage", wt.UINT),
        ("uEdge",            wt.UINT),
        ("rc",               wt.RECT),
        ("lParam",           wt.LPARAM),
    ]


shell32.SHAppBarMessage.restype  = ctypes.c_void_p
shell32.SHAppBarMessage.argtypes = [wt.DWORD, ctypes.POINTER(_APPBARDATA)]

user32.GetShellWindow.restype  = ctypes.c_void_p
user32.GetShellWindow.argtypes = []

user32.GetWindowRect.restype  = wt.BOOL
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.RECT)]


class _DEVMODEW(ctypes.Structure):
    """Minimum viable DEVMODEW — fields up to dmDisplayFrequency.

    Natural alignment handled by ctypes. dmSize must be set to sizeof(this)
    before calling EnumDisplaySettings; Windows fills in up to that many
    bytes and ignores the rest.
    """
    _fields_ = [
        ("dmDeviceName",         wt.WCHAR * 32),
        ("dmSpecVersion",        wt.WORD),
        ("dmDriverVersion",      wt.WORD),
        ("dmSize",               wt.WORD),
        ("dmDriverExtra",        wt.WORD),
        ("dmFields",             wt.DWORD),
        # Union for display contexts — POINTL + two DWORDs = 16 bytes
        ("dmPositionX",          ctypes.c_long),
        ("dmPositionY",          ctypes.c_long),
        ("dmDisplayOrientation", wt.DWORD),
        ("dmDisplayFixedOutput", wt.DWORD),
        ("dmColor",              ctypes.c_short),
        ("dmDuplex",             ctypes.c_short),
        ("dmYResolution",        ctypes.c_short),
        ("dmTTOption",           ctypes.c_short),
        ("dmCollate",            ctypes.c_short),
        ("dmFormName",           wt.WCHAR * 32),
        ("dmLogPixels",          wt.WORD),
        ("dmBitsPerPel",         wt.DWORD),
        ("dmPelsWidth",          wt.DWORD),
        ("dmPelsHeight",         wt.DWORD),
        ("dmDisplayFlags",       wt.DWORD),
        ("dmDisplayFrequency",   wt.DWORD),
    ]


user32.EnumDisplaySettingsW.restype  = wt.BOOL
user32.EnumDisplaySettingsW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.POINTER(_DEVMODEW)]


# ─────────────────────────────────────────────────────────────────────────────
# FIVE INDEPENDENT READERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_edid_preferred_timing(blob: bytes) -> tuple[int, int] | None:
    """Extract (h_active, v_active) from Detailed Timing Descriptor 1 of
    an EDID block. DTD1 lives at bytes 54-71 of the 128-byte base block.

    Layout within DTD1 (bytes are offsets within DTD1, not absolute):
        DTD1[2]           — H active pixels, low 8 bits    (abs 56)
        DTD1[4] high nib  — H active pixels, high 4 bits   (abs 58)
        DTD1[5]           — V active lines,  low 8 bits    (abs 59)
        DTD1[7] high nib  — V active lines,  high 4 bits   (abs 61)
    """
    if len(blob) < 72:
        return None
    try:
        h_active = ((blob[58] & 0xF0) << 4) | blob[56]
        v_active = ((blob[61] & 0xF0) << 4) | blob[59]
        if h_active <= 0 or v_active <= 0:
            return None
        return (h_active, v_active)
    except Exception:
        return None


def _walk_display_enum_for_edid(value_name: str) -> tuple[int, int] | None:
    """Walk HKLM\\SYSTEM\\CurrentControlSet\\Enum\\DISPLAY looking for a
    Device Parameters key with the named value (EDID or EDID_OVERRIDE).
    Returns the first valid preferred timing we can parse, or None.

    Windows tree shape:
        Enum\\DISPLAY\\{MonitorHwID}\\{InstanceID}\\Device Parameters\\{value}
    """
    try:
        root = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Enum\DISPLAY",
        )
    except OSError:
        return None

    try:
        i = 0
        while True:
            try:
                hwid = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                hwid_key = winreg.OpenKey(root, hwid)
            except OSError:
                continue
            try:
                j = 0
                while True:
                    try:
                        inst = winreg.EnumKey(hwid_key, j)
                    except OSError:
                        break
                    j += 1
                    try:
                        params = winreg.OpenKey(hwid_key,
                                                rf"{inst}\Device Parameters")
                    except OSError:
                        continue
                    try:
                        try:
                            blob, _ = winreg.QueryValueEx(params, value_name)
                        except OSError:
                            continue
                        resolution = _parse_edid_preferred_timing(blob)
                        if resolution is not None:
                            return resolution
                    finally:
                        winreg.CloseKey(params)
            finally:
                winreg.CloseKey(hwid_key)
    finally:
        winreg.CloseKey(root)
    return None


def _read_cru_edid_override() -> tuple[int, int] | None:
    """Layer 1 — CRU's EDID_OVERRIDE blob. Preferred timing tells us the
    resolution CRU is asking Windows to offer as the monitor's native."""
    return _walk_display_enum_for_edid("EDID_OVERRIDE")


def _read_raw_edid() -> tuple[int, int] | None:
    """Layer 3 — raw EDID without CRU override. The monitor's own opinion
    of its native resolution, as read over DDC at boot."""
    return _walk_display_enum_for_edid("EDID")


def _read_registry_current() -> tuple[int, int] | None:
    """Layer 2 — the driver's persisted DefaultSettings resolution for the
    active video adapter. Found by dereferencing the DEVICEMAP pointer,
    which names the winning adapter's registry subkey.

    Path example (post-dereference):
        SYSTEM\\CurrentControlSet\\Control\\Video\\{GUID}\\0000
    """
    try:
        devicemap = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\VIDEO",
        )
    except OSError:
        return None
    try:
        try:
            adapter_path, _ = winreg.QueryValueEx(devicemap, r"\Device\Video0")
        except OSError:
            return None
    finally:
        winreg.CloseKey(devicemap)

    # Adapter path is of the form: \Registry\Machine\System\...
    # Strip the \Registry\Machine\ prefix to get a winreg-usable path.
    prefix = r"\Registry\Machine\\"
    if not adapter_path.startswith(prefix):
        prefix = r"\Registry\Machine\\".replace("\\\\", "\\")
    subkey = adapter_path[len(r"\Registry\Machine\\") - 1 :] \
             if adapter_path.startswith(r"\Registry\Machine\\") else \
             adapter_path.removeprefix(r"\Registry\Machine\\").removeprefix(r"\Registry\Machine\\")
    # Robust prefix strip — handle single- and double-backslash variants
    for p in (r"\Registry\Machine\\", r"\Registry\Machine\\"):
        if adapter_path.startswith(p):
            subkey = adapter_path[len(p) :]
            break
    else:
        # One last try — find the first 'SYSTEM' and key from there
        idx = adapter_path.upper().find("SYSTEM\\")
        if idx < 0:
            return None
        subkey = adapter_path[idx:]

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey)
    except OSError:
        return None
    try:
        try:
            x, _ = winreg.QueryValueEx(key, "DefaultSettings.XResolution")
            y, _ = winreg.QueryValueEx(key, "DefaultSettings.YResolution")
        except OSError:
            return None
        if x > 0 and y > 0:
            return (int(x), int(y))
        return None
    finally:
        winreg.CloseKey(key)


def _read_enum_display() -> tuple[int, int] | None:
    """Layer 4 — live current settings from the display driver via Win32
    EnumDisplaySettings(ENUM_CURRENT_SETTINGS). Same source as the
    registry, but queried at runtime — never stale."""
    dm = _DEVMODEW()
    dm.dmSize = ctypes.sizeof(_DEVMODEW)
    ok = user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    if not ok:
        return None
    if dm.dmPelsWidth <= 0 or dm.dmPelsHeight <= 0:
        return None
    return (int(dm.dmPelsWidth), int(dm.dmPelsHeight))


def _read_progman_rect() -> tuple[int, int] | None:
    """Layer 5 — the shell desktop window (Progman) as reported by Win32.
    This is what actually paints the desktop wallpaper behind everything,
    so its rect is ground-truth 'what the desktop is drawn at' on the
    primary monitor."""
    hwnd = user32.GetShellWindow()
    if not hwnd:
        return None
    rect = wt.RECT()
    if not user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
        return None
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None
    return (w, h)


# ─────────────────────────────────────────────────────────────────────────────
# CONSENSUS
# ─────────────────────────────────────────────────────────────────────────────

_READERS = {
    "cru_edid_override": _read_cru_edid_override,
    "registry_current":  _read_registry_current,
    "raw_edid":          _read_raw_edid,
    "enum_display":      _read_enum_display,
    "progman_rect":      _read_progman_rect,
}


@dataclass
class ResolutionReading:
    sources: dict[str, tuple[int, int] | None] = field(default_factory=dict)
    consensus_value: tuple[int, int] | None = None   # set iff all five agree

    @property
    def agreed(self) -> bool:
        return self.consensus_value is not None

    def summary(self) -> str:
        return ", ".join(
            f"{name}={'/'.join(map(str, v)) if v else 'None'}"
            for name, v in self.sources.items()
        )


def all_layers() -> dict[str, tuple[int, int] | None]:
    """Return a fresh reading from each of the five sources. Never raises;
    readers that fail return None."""
    out: dict[str, tuple[int, int] | None] = {}
    for name, fn in _READERS.items():
        try:
            out[name] = fn()
        except Exception:
            logger.exception("[display] reader %s raised — treating as None", name)
            out[name] = None
    return out


def consensus() -> tuple[int, int] | None:
    """All five readers must return a non-None value AND all five must
    match, else return None. Strict by design — a single disagreement
    means we stop trusting the number and let the caller fall back."""
    readings = all_layers()
    values = list(readings.values())
    if any(v is None for v in values):
        return None
    first = values[0]
    if all(v == first for v in values):
        return first
    return None


def authoritative_resolution() -> ResolutionReading:
    """Consensus-or-None wrapped in a reading record — on mismatch the
    record carries the per-layer values so the caller (or a log line)
    can show exactly which source diverged."""
    sources = all_layers()
    reading = ResolutionReading(sources=sources)
    values = list(sources.values())
    if all(v is not None for v in values):
        first = values[0]
        if all(v == first for v in values):
            reading.consensus_value = first
    return reading


def taskbar_height_on_bottom_of(monitor_top: int, monitor_bottom: int,
                                monitor_left: int, monitor_right: int) -> int:
    """Return the taskbar's height in pixels if it's docked to the bottom
    edge of the given monitor rect, else 0. Auto-hide taskbars return 0
    — they don't reserve space.

    Implementation uses SHAppBarMessage(ABM_GETTASKBARPOS), which gives
    the taskbar's absolute position directly — independent of whatever
    the work-area reservation looks like."""
    data = _APPBARDATA()
    data.cbSize = ctypes.sizeof(_APPBARDATA)
    result = shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(data))
    if not result:
        return 0
    tb_top, tb_bottom = data.rc.top, data.rc.bottom
    tb_left, tb_right = data.rc.left, data.rc.right
    # On same monitor (horizontal overlap) and docked at bottom
    horizontally_on_monitor = (
        tb_left < monitor_right and tb_right > monitor_left
    )
    docked_at_bottom = abs(tb_bottom - monitor_bottom) <= 2
    if horizontally_on_monitor and docked_at_bottom:
        return max(0, tb_bottom - tb_top)
    return 0
