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

# Reconfigure stdout/stderr to UTF-8 so emoji in log lines don't crash on
# Windows consoles that default to cp1252 (e.g. plain cmd.exe or PowerShell).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from utils.logger import setup_logger, set_log_level, TRACE
from utils.settings import appName, orgName

_INSTANCE_PORT = 47321
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
    set_log_level(args.debug, args.trace)
    if args.trace:
        logger.log(TRACE, "Trace mode active — verbose diagnostics will appear in console")
    print(f"{appName} is generally so happy that you are here. ✨")

    # Qt warnings that are known-harmless and too noisy to keep in the log
    _QT_SUPPRESSED = (
        "SamplesPerPixel",   # TIFF ExtraSamples mismatch — cosmetic, not our files
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
    logger.log(TRACE, "[boot:2] QApplication created — Qt event loop ready")

    # Raise Qt's image allocation cap — the default 256 MB is hit by any modern
    # photo or 4K screenshot.  0 = no limit; we keep a generous hard ceiling so
    # a corrupted file can't exhaust all RAM.
    from PySide6.QtGui import QImageReader
    QImageReader.setAllocationLimit(1024)   # MB — plenty for any canvas image

    logger.log(TRACE, "[boot:3] importing utils.settings")
    import utils.settings as settings
    logger.log(TRACE, "[boot:4] utils.settings imported")

    logger.log(TRACE, "[boot:5] importing graphics.Theme")
    from graphics.Theme import Theme
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

    logger.log(TRACE, "[boot:13] constructing IntricateApp window")
    logger.log(TRACE, f"[boot:13a] Theme.icon at window construction = {getattr(Theme, 'icon', 'MISSING')}")
    window = IntricateApp()
    logger.log(TRACE, "[boot:14] IntricateApp window constructed")

    window.show()
    logger.log(TRACE, "[boot:15] window shown — entering event loop")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
