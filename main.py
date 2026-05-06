#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - main.py application launcher
-Launches the Intricate node-based UI application for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import sys
import signal
import argparse
import ctypes
import logging
from pathlib import Path

__version__ = "0.6.0"
__era__     = "The Housekeeping before paradise arrives Era"

__version_history__ = [
    "0.1.0 - The Fluff Era",
    "0.0.2 - The Era where we fixed the typo in the version counter",
    "0.0.3 - The Interlinking Era",
    'There is also one named Two, its not a descendant of One or something, it\'s its name "Two"',
    "0.0.5 - The Breath of Air Era",
    '0.0.4 - Is missing - is its actual name, not that it is missing, its named "0.0.4 - Is Missing", and came after 0.0.5',
    "0.1.0 - The Dawn of a new Era of Mankind",
    "0.2.0 - The Prestige Era",
    "0.3.0 - The Expressive Era",
    "0.5.0 - The Other Era, Not the untold one.",
    "0.6.0 - The Housekeeping before paradise arrives Era",
]

# Reconfigure stdout/stderr to UTF-8 so emoji in log lines don't crash on
# Windows consoles that default to cp1252 (e.g. plain cmd.exe or PowerShell).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from shared_braincell.logger import setup_logger, set_log_level, TRACE
import shared_braincell.settings as settings
from shared_braincell.settings import appName, orgName
from pretty_widgets.utils.settings import init_watcher  # Qt live-reload watcher
from shared_braincell import is_singleton

_INSTANCE_START_PORT = int(settings.get("intricate", "instance_port", default=47321))


_SESSION_FILE_EXTS = {".intricate", ".json", ".jsonl"}


# ── Windows file association (HKCU, per-user, no admin required) ────────────
# Registers ".intricate" with Windows Explorer so double-clicking a session
# file launches (or hands off to) this Intricate install. Uses HKEY_CURRENT_USER
# exclusively — no touching HKLM, no elevation prompts, no machine-wide state.
# Idempotent: if the keys already match the expected values, _ensure_file_association
# is a no-op with no writes and no log entries.

_REGISTRY_PROG_ID = "Intricate.Session"
_REGISTRY_DESCRIPTION = "Intricate Session File"


def _expected_association_command() -> str:
    """The expected HKCU shell\\open\\command value for this Intricate install."""
    main_py = str(Path(__file__).resolve())
    return f'"{sys.executable}" "{main_py}" "%1"'


def _expected_association_icon() -> str:
    """The expected DefaultIcon value for the file association."""
    return str(Path(__file__).resolve().parent / "icons" / "intricate.ico")


def _read_hkcu(path: str) -> str | None:
    """Read HKCU\\<path>'s default value; returns None if the key is missing."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as k:
            val, _type = winreg.QueryValueEx(k, "")
            return str(val) if val is not None else None
    except OSError:
        return None


def register_file_association(logger=None) -> bool:
    """Write HKCU file-association keys for .intricate → this Intricate install.

    Four keys under HKCU\\Software\\Classes\\:
      .intricate                                         → ProgID alias
      Intricate.Session                                  → friendly name
      Intricate.Session\\DefaultIcon                     → icon file
      Intricate.Session\\shell\\open\\command            → launch command

    Returns True on success, False if any key write failed. Safe to call
    repeatedly — writing the same value twice is a no-op in practice.
    """
    import winreg
    command = _expected_association_command()
    icon    = _expected_association_icon()
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.intricate") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, _REGISTRY_PROG_ID)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Intricate.Session") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, _REGISTRY_DESCRIPTION)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Intricate.Session\DefaultIcon") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, icon)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\Intricate.Session\shell\open\command") as k:
            winreg.SetValue(k, "", winreg.REG_SZ, command)
        if logger:
            logger.info("[association] registered .intricate → %s", command)
        return True
    except OSError as e:
        if logger:
            logger.warning("[association] write failed: %s", e)
        return False


def unregister_file_association(logger=None) -> int:
    """Remove HKCU .intricate association keys. Returns count of keys
    actually removed (missing keys count as 0 but don't error)."""
    import winreg
    # Delete from deepest first — DeleteKey only removes empty keys
    keys = [
        r"Software\Classes\Intricate.Session\shell\open\command",
        r"Software\Classes\Intricate.Session\shell\open",
        r"Software\Classes\Intricate.Session\shell",
        r"Software\Classes\Intricate.Session\DefaultIcon",
        r"Software\Classes\Intricate.Session",
        r"Software\Classes\.intricate",
    ]
    removed = 0
    for key_path in keys:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            removed += 1
        except FileNotFoundError:
            pass
        except OSError as e:
            if logger:
                logger.warning("[unregister] couldn't delete %s: %s", key_path, e)
    if logger:
        logger.info("[association] unregistered .intricate (%d key(s) removed)", removed)
    return removed


def _ensure_file_association(logger=None) -> None:
    """Passive startup check — only writes the registry if the current
    association is missing or points somewhere other than this install.
    Silent no-op when state is already correct (no writes, no log noise
    that might trip a registry-watching sentinel on a machine-state audit)."""
    current_progid  = _read_hkcu(r"Software\Classes\.intricate")
    current_command = _read_hkcu(r"Software\Classes\Intricate.Session\shell\open\command")
    expected_cmd    = _expected_association_command()
    if current_progid == _REGISTRY_PROG_ID and current_command == expected_cmd:
        # Already correctly registered for this install — nothing to do
        return
    # Either missing or stale (e.g. repo moved) — refresh
    if logger:
        reason = "missing" if current_progid is None else "stale (points elsewhere)"
        logger.info("[association] %s — refreshing HKCU .intricate registration", reason)
    register_file_association(logger)


def main():
    # Parse CLI first — we might be a secondary instance with file
    # arguments to forward to the primary (e.g. user double-clicked a
    # .intricate file while Intricate is already running).
    parser = argparse.ArgumentParser(description=appName)
    parser.add_argument("files", nargs="*",
                        help=".intricate/.json/.jsonl session files to import into the current scene")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--register", action="store_true",
                        help="Register .intricate file association in HKCU, then exit")
    parser.add_argument("--unregister", action="store_true",
                        help="Remove .intricate file association from HKCU, then exit")
    args = parser.parse_args()

    # Registration operations run before anything else — they don't need a
    # Qt app or logger. Write to stdout so the user sees the result.
    if args.register:
        ok = register_file_association()
        print(f"[association] {'registered' if ok else 'FAILED'}: "
              f".intricate → {_expected_association_command()}")
        sys.exit(0 if ok else 1)
    if args.unregister:
        n = unregister_file_association()
        print(f"[association] unregistered (removed {n} key(s))")
        sys.exit(0)

    # Absolutise + filter to existing session-like files
    from pathlib import Path as _P
    _session_files: list[str] = []
    for f in args.files:
        p = _P(f)
        if p.is_file() and p.suffix.lower() in _SESSION_FILE_EXTS:
            _session_files.append(str(p.resolve()))

    # Singleton guard — handshake-validated, port-range fallback, logs
    # foreign port holders for curiosity.  Returns False only if another
    # Intricate instance is already running.
    if not is_singleton("Intricate", start_port=_INSTANCE_START_PORT):
        # Secondary instance — forward file arguments to the primary so
        # they open in its currently-loaded scene, then exit quietly.
        # This is the double-click-while-already-running path: Windows
        # launches a new pythonw.exe with the file as arg, we detect the
        # primary is holding the port, and route the import request over.
        if _session_files:
            from shared_braincell import send_command
            for path in _session_files:
                send_command("Intricate",
                             {"cmd": "import", "path": path},
                             _INSTANCE_START_PORT)
        sys.exit(0)

    # Name the process for the Windows taskbar and Task Manager Apps view.
    # ctypes.windll only exists on Windows; the try/except keeps the EC2 Era
    # boot path clean on Linux hosts where there's no taskbar to label.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appName)
        ctypes.windll.kernel32.SetConsoleTitleW(appName)
    except (AttributeError, OSError):
        pass

    # Passive file-association check happens further down, after the logger
    # is live, so refresh events get captured in the log with context.

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    logger = setup_logger()

    # Now that logger is live, run the passive file-association check
    try:
        _ensure_file_association(logger)
    except Exception:
        logger.exception("[association] passive check raised — continuing without association")

    # CLI flags override; otherwise fall back to [intricate] log_level in settings.toml
    if args.trace:
        _debug, _trace = False, True
    elif args.debug:
        _debug, _trace = True, False
    else:
        import shared_braincell.settings as _s_boot
        _toml_level = str(_s_boot.get("intricate", "log_level", "info")).lower().strip()
        _trace = _toml_level == "trace"
        _debug = _toml_level == "debug"

    set_log_level(_debug, _trace)
    if _trace:
        logger.log(TRACE, "Trace mode active — verbose diagnostics will appear in console")
    _greeting = f"{appName} is generally so happy that you are here. ✨"
    print(_greeting)
    logger.info(_greeting)

    # Qt warnings that are known-harmless and too noisy to keep in the log
    _QT_SUPPRESSED = (
        "SamplesPerPixel",          # TIFF ExtraSamples mismatch — cosmetic, not our files
        "engine == 0, type: 3",     # QPixmap.save → internal QPainter on QImage before render context
        "Painter not active",       # cascade warnings from the above
    )

    def _qt_message_handler(msg_type, context, message):
        if any(s in message for s in _QT_SUPPRESSED):
            return
        level_map = {
            QtMsgType.QtDebugMsg:    logger.debug,
            QtMsgType.QtInfoMsg:     logger.info,
            QtMsgType.QtWarningMsg:  logger.warning,
            QtMsgType.QtCriticalMsg: logger.error,
            QtMsgType.QtFatalMsg:    logger.critical,
        }
        log_fn = level_map.get(msg_type, logger.warning)
        log_fn(f"[Qt] {message}  ({context.file}:{context.line})")
    qInstallMessageHandler(_qt_message_handler)

    logger.log(TRACE, "[boot:1] creating QApplication")
    app = QApplication(sys.argv)
    app.setApplicationName(appName)
    app.setOrganizationName(orgName)

    # Register the SSB family's curated .otf set into Qt's in-process font
    # database before any QFont-using widget gets constructed.  Without
    # this Chandler42 only carries whatever style variants Windows
    # registered system-wide — typically Medium + LiteOblique, missing
    # the script-italic Medium from 1843.otf — and every painter that
    # asks for setStyleName('Italic') silently falls back to upright.
    # Idempotent, never raises.
    from pretty_widgets.utils.fonts import register_app_fonts
    register_app_fonts()

    # Release the singleton lock BEFORE app.exec() returns, while the Qt
    # event loop is still alive and the interpreter is fully usable.
    # atexit runs too late: by then Py_Finalize has already begun tearing
    # down the socket's Python wrappers around the still-blocked listener
    # thread → 0xc0000005 in python313.dll. aboutToQuit fires before the
    # event loop actually exits, so the join completes in healthy state.
    def _release_singleton_early():
        try:
            from shared_braincell import release_singleton
            release_singleton(appName)
        except Exception:
            pass
    app.aboutToQuit.connect(_release_singleton_early)

    # Set the window/taskbar icon — .exe builds embed this via PyInstaller,
    # but pythonw needs it explicitly or Windows shows the default Python icon.
    from pathlib import Path
    from PySide6.QtGui import QIcon
    _app_icon = Path(__file__).resolve().parent / "icons" / "intricate.ico"
    if _app_icon.exists():
        app.setWindowIcon(QIcon(str(_app_icon)))

    # Purge stale bytecode BEFORE any project imports — ensures a crash that
    # prevented closeEvent cleanup doesn't leave poisoned .pyc files behind.
    # Uses raw shutil, not utils.helpers, to avoid loading a stale .pyc of helpers itself.
    import shutil
    _root = Path(__file__).resolve().parent
    for _pc in list(_root.rglob("__pycache__")):
        try:
            shutil.rmtree(_pc)
        except Exception:
            pass

    # Resolve the log directory once — used by crash/fault paths below so
    # forensic files sit next to the session logs (Documents/Data/Logs by
    # default, overridable via [shared] log_dir in settings.toml).
    from shared_braincell.logger import _resolve_log_dir
    _logs_dir = _resolve_log_dir()

    # Rotate stale forensic files — keep them for 24 hours for post-mortem,
    # then discard. Sweeps both crash.txt (traceback dump) and fault.txt
    # (C-level stack dump from faulthandler) in both the current log
    # directory and the legacy ./logs/ path so stale files from before the
    # 2026-04-24 relocation get cleaned up too.
    import time
    _forensic_candidates = [
        _logs_dir / "crash.txt",
        _logs_dir / "fault.txt",
        _root / "logs" / "crash.txt",
        _root / "logs" / "fault.txt",
    ]
    for _forensic in _forensic_candidates:
        if _forensic.exists():
            age_hours = (time.time() - _forensic.stat().st_mtime) / 3600
            if age_hours > 24:
                _forensic.unlink(missing_ok=True)

    logger.log(TRACE, "[boot:2] QApplication created — Qt event loop ready")

    # Raise Qt's image allocation cap — the default 256 MB is hit by any modern
    # photo or 4K screenshot.  0 = no limit; we keep a generous hard ceiling so
    # a corrupted file can't exhaust all RAM.
    from PySide6.QtGui import QImageReader
    QImageReader.setAllocationLimit(1024)   # MB — plenty for any canvas image

    logger.log(TRACE, "[boot:3] importing utils.settings")
    import shared_braincell.settings as settings
    logger.log(TRACE, "[boot:4] utils.settings imported")

    logger.log(TRACE, "[boot:5] importing graphics.Theme")
    from pretty_widgets.graphics.Theme import Theme
    logger.log(TRACE, "[boot:6] graphics.Theme imported")
    logger.log(TRACE, f"[boot:6a] Theme.icon = {Theme.__dict__.get('icon', 'NOT IN __dict__')}")
    logger.log(TRACE, f"[boot:6b] hasattr(Theme, 'icon') = {hasattr(Theme, 'icon')}")
    try:
        logger.log(TRACE, f"[boot:6c] Theme.icon via getattr = {getattr(Theme, 'icon', 'MISSING')}")
    except Exception as e:
        logger.log(TRACE, f"[boot:6c] Theme.icon getattr raised: {e}")

    logger.log(TRACE, "[boot:7] importing main_window.IntricateApp")
    from main_window import IntricateApp
    logger.log(TRACE, "[boot:8] main_window.IntricateApp imported")

    logger.log(TRACE, "[boot:9] calling Theme.reload()")
    Theme.reload()
    logger.log(TRACE, "[boot:10] Theme.reload() complete")
    logger.debug(f"[boot] TOML loaded from: {settings._SETTINGS_PATH}")

    logger.log(TRACE, "[boot:11] initialising file watcher")
    _watcher = init_watcher()
    _watcher.changed.connect(Theme.reload)
    # Window-instance-bound connections (window.update,
    # window._apply_joy_settings) wire AFTER IntricateApp construction
    # below.  Resolving the window via app.activeWindow() at fire time
    # silently no-ops when Settlers (or any sibling family-app) holds
    # focus — exactly the case during Settlers slider drags, where the
    # TOML save fires while Settlers is still the active window.
    logger.debug(f"[boot] File watcher active on: {settings._SETTINGS_PATH}")
    logger.log(TRACE, "[boot:12] file watcher active")

    logger.log(TRACE, "[boot:12a] initialising node registry")
    from utils.persistence import registry
    _reg_watcher = registry.init_watcher()
    logger.debug(f"[boot] Node registry loaded: {len(registry.get_all_nodes())} types")

    logger.log(TRACE, "[boot:12b] initialising color registry")
    from utils.persistence import color_registry
    _color_watcher = color_registry.init_watcher()
    # window.update connection lands after IntricateApp construction
    # below — same focus-independence concern as the main settings
    # watcher.  The palette itself is pulled live by ColorPicker; the
    # repaint just nudges the view to re-read tints on visible nodes.
    logger.debug(f"[boot] Color palette loaded: {len(color_registry.get_all())} colors")

    logger.log(TRACE, "[boot:12c] extracting OS-registered app icons")
    # Pulls InDesign / Photoshop / etc. icons from the Windows shell handler
    # registry so the Adobe category menu stays visually current with whatever
    # versions the user has installed. Stale-if-newer-exe check means an
    # Adobe update automatically refreshes the cached .ico on next boot.
    from utils.app_icons import ensure_app_icons
    try:
        ensure_app_icons()
    except Exception:
        logger.warning("[boot:12c] app-icon extraction raised; continuing", exc_info=True)

    logger.log(TRACE, "[boot:13] constructing IntricateApp window")
    logger.log(TRACE, f"[boot:13a] Theme.icon at window construction = {getattr(Theme, 'icon', 'MISSING')}")
    window = IntricateApp()
    logger.log(TRACE, "[boot:14] IntricateApp window constructed")

    # Watcher connections that need a concrete IntricateApp instance.
    # Bound directly to the constructed window so they fire regardless
    # of which family-app holds focus when the TOML save lands — the
    # previous app.activeWindow()-gated lambdas silently no-opped during
    # Settlers slider drags because Settlers was the active window at
    # save time.  Qt auto-disconnects on window destruction since
    # window is a QObject, so no manual teardown is needed here.
    _watcher.changed.connect(window.update)
    _watcher.changed.connect(window._apply_joy_settings)
    _color_watcher.changed.connect(window.update)

    window.show()
    # Install a global exception hook so unhandled errors inside Qt slots and
    # callbacks land in the log file instead of vanishing into stderr (which is
    # gone when running headless via pythonw or a frozen .exe).
    def _excepthook(exc_type, exc_value, exc_tb):
        if exc_type is KeyboardInterrupt:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        # Write traceback to log AND a crash file for forensics
        import traceback
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("Unhandled exception in event loop\n%s", tb_text)
        try:
            crash_path = _logs_dir / "crash.txt"
            crash_path.write_text(tb_text, encoding="utf-8")
        except Exception:
            pass
        # Flush the ring buffer so the crash lands on disk before we go down.
        try:
            import intricate_log
            intricate_log.flush()
        except Exception:
            pass
    sys.excepthook = _excepthook

    # sys.unraisablehook fires for exceptions Python couldn't propagate
    # normally — including exceptions raised in __del__, weakref callbacks,
    # and (critically for our purposes) exceptions inside Qt slots that
    # PySide6 suppresses or converts before they'd reach sys.excepthook.
    # Route them through the same crash.txt path so silent slot-exception
    # crashes leave forensic breadcrumbs instead of stale traces.
    def _unraisablehook(unraisable):
        import traceback
        tb_text = "".join(traceback.format_exception(
            unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback,
        ))
        context = f"[unraisable: {unraisable.err_msg or 'slot exception'}]"
        if unraisable.object is not None:
            try: context += f" on {unraisable.object!r}"
            except Exception: pass
        logger.critical("%s\n%s", context, tb_text)
        try:
            crash_path = _logs_dir / "crash.txt"
            crash_path.write_text(f"{context}\n\n{tb_text}", encoding="utf-8")
        except Exception:
            pass
        try:
            import intricate_log
            intricate_log.flush()
        except Exception:
            pass
    sys.unraisablehook = _unraisablehook

    # faulthandler catches Windows structured exceptions (SEGFAULT,
    # STATUS_ACCESS_VIOLATION, STATUS_STACK_BUFFER_OVERRUN) and writes a
    # C-level stack dump to a file handle before the process dies.
    # Writing to the log file gives us the faulting thread's call stack
    # even when the crash is in Qt's C++ code and no Python exception
    # fires — crucial for the class of ucrtbase/Qt6Widgets crashes that
    # don't leave a Python traceback in crash.txt.
    try:
        import faulthandler
        _fault_path = _logs_dir / "fault.txt"
        _fault_file = open(_fault_path, "w", encoding="utf-8", buffering=1)
        faulthandler.enable(file=_fault_file, all_threads=True)
        logger.log(TRACE, f"[boot:15a] faulthandler armed → {_fault_path}")
    except Exception as _fh_exc:
        logger.warning("faulthandler install failed: %s", _fh_exc)

    # Register atexit handler to flush the ring buffer on clean shutdown.
    import atexit
    def _flush_log():
        try:
            import intricate_log
            intricate_log.flush()
        except Exception:
            pass
    atexit.register(_flush_log)

    def _exit_pycache_cleanup():
        try:
            for _pc in list(_root.rglob("__pycache__")):
                shutil.rmtree(_pc, ignore_errors=True)
        except Exception:
            pass
    atexit.register(_exit_pycache_cleanup)

    # ── CLI file imports ─────────────────────────────────────────────────
    # If launched with session file arguments (either from CLI or from a
    # double-click that routed through file association), queue them for
    # import after the initial session has fully loaded. Deferred by 2s
    # so the scene is ready to receive spawned nodes.
    if _session_files:
        def _do_cli_imports():
            for path in _session_files:
                try:
                    window.import_intricate_file(path)
                except Exception:
                    logger.exception("[cli] import failed for %s", path)
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(2000, _do_cli_imports)

    # ── IPC command pump ─────────────────────────────────────────────────
    # Drains commands sent by secondary instances (e.g. when a user
    # double-clicks another .intricate file while this instance is
    # already running). Held as a window attribute so GC doesn't collect
    # it while the event loop is still running.
    from shared_braincell import drain_commands
    from PySide6.QtCore import QTimer as _QT
    window._cmd_pump_timer = _QT()
    window._cmd_pump_timer.setInterval(250)
    def _pump_commands():
        for cmd in drain_commands("Intricate"):
            op = cmd.get("cmd")
            if op == "import":
                path = cmd.get("path")
                if path:
                    try:
                        window.import_intricate_file(path)
                    except Exception:
                        logger.exception("[ipc] import failed for %s", path)
            else:
                logger.warning("[ipc] unknown command: %r", cmd)
    window._cmd_pump_timer.timeout.connect(_pump_commands)
    window._cmd_pump_timer.start()

    logger.log(TRACE, "[boot:15] window shown — entering event loop")

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Emoji suffix is the canonical visual-signal tag for CRITICAL —
        # hardcoded here because this line fires before setup_logger's
        # formatter is guaranteed to be installed (root logger fallback).
        logging.critical("Starting Intricate catastrophically failed 🥺😮😭", exc_info=True)
        print(f"Intricate has entered the void: {e}", file=sys.stderr)
        sys.exit(1)
