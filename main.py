#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - main.py application launcher
-Launches the Intricate node-based UI application for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import sys
import signal
import socket
import argparse
import ctypes
import logging

__version__ = "0.3.0"
__era__     = "The Expressive Era"

__version_history__ = [
    ("0.0.1", "The Fluff Era"),
    ("0.0.2", "All Glory"),
    ("0.0.3", "The Interlinking Era"),
    ("0.0.5", "The Breath of Air Era"),
    ("Two",   "Two"),
    ("0.1.0", "The Dawn of a New Era of Mankind"),
    ("0.2.0", "The Prestige Era"),
    ("0.3.0", "The Expressive Era"),
]

# Reconfigure stdout/stderr to UTF-8 so emoji in log lines don't crash on
# Windows consoles that default to cp1252 (e.g. plain cmd.exe or PowerShell).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from pretty_widgets.utils.logger import setup_logger, set_log_level, TRACE
import pretty_widgets.utils.settings as settings
from pretty_widgets.utils.settings import appName, orgName

_INSTANCE_PORT = int(settings.get("intricate", "instance_port", default=47321))
_instance_lock: socket.socket | None = None


def _acquire_instance_lock() -> bool:
    global _instance_lock
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", _INSTANCE_PORT))
        sock.listen(1)
        _instance_lock = sock   # keep alive for process lifetime
        return True
    except OSError:
        sock.close()
        return False


def main():
    if not _acquire_instance_lock():
        sys.exit(0)

    # Name the process for the Windows taskbar and Task Manager Apps view
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appName)
    ctypes.windll.kernel32.SetConsoleTitleW(appName)

    parser = argparse.ArgumentParser(description=appName)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    logger = setup_logger()

    # CLI flags override; otherwise fall back to [intricate] log_level in settings.toml
    if args.trace:
        _debug, _trace = False, True
    elif args.debug:
        _debug, _trace = True, False
    else:
        import pretty_widgets.utils.settings as _s_boot
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

    # Rotate stale crash.txt — keep it for 24 hours for forensics, then discard
    _crash_file = _root / "logs" / "crash.txt"
    if _crash_file.exists():
        import time
        age_hours = (time.time() - _crash_file.stat().st_mtime) / 3600
        if age_hours > 24:
            _crash_file.unlink(missing_ok=True)

    logger.log(TRACE, "[boot:2] QApplication created — Qt event loop ready")

    # Raise Qt's image allocation cap — the default 256 MB is hit by any modern
    # photo or 4K screenshot.  0 = no limit; we keep a generous hard ceiling so
    # a corrupted file can't exhaust all RAM.
    from PySide6.QtGui import QImageReader
    QImageReader.setAllocationLimit(1024)   # MB — plenty for any canvas image

    logger.log(TRACE, "[boot:3] importing utils.settings")
    import pretty_widgets.utils.settings as settings
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
    _watcher = settings.init_watcher()
    _watcher.changed.connect(Theme.reload)
    _watcher.changed.connect(lambda: app.activeWindow() and app.activeWindow().update())
    logger.debug(f"[boot] File watcher active on: {settings._SETTINGS_PATH}")
    logger.log(TRACE, "[boot:12] file watcher active")

    logger.log(TRACE, "[boot:12a] initialising node registry")
    from utils import registry
    _reg_watcher = registry.init_watcher()
    logger.debug(f"[boot] Node registry loaded: {len(registry.get_all_nodes())} types")

    logger.log(TRACE, "[boot:13] constructing IntricateApp window")
    logger.log(TRACE, f"[boot:13a] Theme.icon at window construction = {getattr(Theme, 'icon', 'MISSING')}")
    window = IntricateApp()
    logger.log(TRACE, "[boot:14] IntricateApp window constructed")

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
            crash_path = Path(__file__).resolve().parent / "logs" / "crash.txt"
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

    logger.log(TRACE, "[boot:15] window shown — entering event loop")

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"Starting Intricate catastrophically failed", exc_info=True)
        print(f"Intricate has entered the void: {e}", file=sys.stderr)
        sys.exit(1)
