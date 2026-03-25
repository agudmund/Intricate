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
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import qInstallMessageHandler, QtMsgType
from main_window import IntricateApp
import utils.settings as settings
from graphics.Theme import Theme
from utils.logger import setup_logger, set_log_level, TRACE

APP_NAME = "Intricate"
ORG_NAME = "Single Shared Braincell"


def main():
    # ── 1. Parse command-line arguments ───────────────────────────────────────
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging to console"
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable TRACE logging — verbose path resolution, paint cycles, all of it"
    )
    args = parser.parse_args()

    # ── 2. Ctrl+C works in the terminal ───────────────────────────────────────
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # ── 3. Logger — must exist before anything else touches it ────────────────
    logger = setup_logger()
    set_log_level(args.debug, args.trace)

    if args.trace:
        logger.log(TRACE, "Trace mode active — verbose diagnostics will appear in console")

    logger.info(f"{APP_NAME} is generally so happy that you are here. ✨")

    # ── 4. Qt message handler — routes Qt internals through our logger ─────────
    # Catches Qt warnings about missing resources, bad stylesheets, etc.
    # Without this they print raw to stderr and bypass the log file entirely.
    def _qt_message_handler(msg_type, context, message):
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

    # ── 5. QApplication ───────────────────────────────────────────────────────
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    # ── STUB: Windows taskbar identity ────────────────────────────────────────
    # Makes Windows treat Intricate as its own taskbar entity with its own icon.
    # Uncomment when the app icon and build pipeline are in place.
    #
    # import ctypes
    # try:
    #     myappid = f"SingleSharedBraincell.{APP_NAME}.v1.0"
    #     ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    # except Exception:
    #     pass

    # ── STUB: App icon ────────────────────────────────────────────────────────
    # Set the application icon from the asset vault or local resources.
    # Uncomment when the app icon exists.
    #
    # from PySide6.QtGui import QIcon
    # from pathlib import Path
    # icon_path = Path(__file__).parent / "icons" / "app_icon.png"
    # if icon_path.exists():
    #     app.setWindowIcon(QIcon(str(icon_path)))

    # ── STUB: High-DPI policy ─────────────────────────────────────────────────
    # Qt 6 handles most high-DPI cases automatically. If rendering looks off
    # on a high-DPI display, enable PassThrough mode here.
    #
    # from PySide6.QtCore import Qt
    # app.setHighDpiScaleFactorRoundingPolicy(
    #     Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # ── STUB: Encoding shield ─────────────────────────────────────────────────
    # Needed for pythonw, PyInstaller bundles, and redirected streams.
    # Not needed for normal development console use.
    #
    # import io
    # if sys.stdout is not None:
    #     try:
    #         if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
    #             sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    #     except (AttributeError, io.UnsupportedOperation):
    #         pass

    # ── STUB: Build signature ─────────────────────────────────────────────────
    # Logs the build timestamp and signature on launch.
    # Useful when running multiple builds side by side.
    # Wire up when a build pipeline exists.
    #
    # _log_build_signature(logger)

    # ── 6. Settings and Theme bootstrap ───────────────────────────────────────
    # settings._reload() ran at import time above. Theme.reload() pulls the
    # initial TOML values into Theme attributes before any UI is created.
    Theme.reload()
    logger.debug(f"[boot] TOML loaded from: {settings._SETTINGS_PATH}")

    # ── 7. File watcher ────────────────────────────────────────────────────────
    # QFileSystemWatcher requires an active QApplication — must come after step 5.
    # Any write to settings.toml from The Settlers or anywhere else fires this.
    _watcher = settings.init_watcher()
    _watcher.changed.connect(Theme.reload)
    _watcher.changed.connect(lambda: app.activeWindow() and app.activeWindow().update())
    logger.debug(f"[boot] File watcher active on: {settings._SETTINGS_PATH}")

    # ── STUB: Window geometry restore ─────────────────────────────────────────
    # settings.toml already has [window] x/y/width/height.
    # Wire up after IntricateApp exposes restoreGeometry().
    #
    # geometry = settings.get("window", "geometry")
    # if geometry:
    #     window.restoreGeometry(geometry)

    # ── 8. Launch ─────────────────────────────────────────────────────────────
    window = IntricateApp()
    window.show()

    # ── STUB: Catastrophic failure dialog ─────────────────────────────────────
    # Wrap sys.exit(app.exec()) in try/except with QMessageBox for production.
    # Overkill for development — the traceback in the console is more useful.
    #
    # try:
    #     sys.exit(app.exec())
    # except Exception as e:
    #     logger.exception(f"Catastrophic failure: {e}")
    #     from PySide6.QtWidgets import QMessageBox
    #     QMessageBox.critical(None, "Something went wrong", str(e))
    #     sys.exit(1)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
