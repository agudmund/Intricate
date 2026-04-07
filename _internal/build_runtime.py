#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Single Shared Braincell - Shared Runtime Builder
-Builds the common runtime folder that all apps in the family share via directory junctions
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import PyInstaller.__main__

_ROOT = Path(__file__).parent.absolute()


def _get_versions() -> dict:
    """Collect installed versions of shared dependencies."""
    versions = {"python": sys.version.split()[0]}
    for pkg in ("PySide6", "pretty_widgets", "tomli_w", "send2trash", "shiboken6"):
        try:
            mod = __import__(pkg)
            versions[pkg] = getattr(mod, "__version__", "unknown")
        except ImportError:
            versions[pkg] = "NOT INSTALLED"
    # requests is optional (only Notepad needs it)
    try:
        import requests
        versions["requests"] = requests.__version__
    except ImportError:
        versions["requests"] = "not installed (optional)"
    return versions


def _hash_folder(folder: Path) -> str:
    """Quick SHA-256 summary of all files in a folder."""
    h = hashlib.sha256()
    for f in sorted(folder.rglob("*")):
        if f.is_file():
            h.update(str(f.relative_to(folder)).encode())
            h.update(f.stat().st_size.to_bytes(8, "little"))
    return h.hexdigest()[:16]


def build_runtime():
    print(f"\n{'=' * 60}")
    print(f"  Single Shared Braincell — Runtime Builder")
    print(f"{'=' * 60}\n")

    # ── Version check ────────────────────────────────────────────────────
    versions = _get_versions()
    print("Dependency versions:")
    for pkg, ver in versions.items():
        status = "OK" if "NOT INSTALLED" not in ver else "MISSING"
        print(f"  {pkg}: {ver}  [{status}]")
    print()

    missing = [k for k, v in versions.items() if "NOT INSTALLED" in v]
    if missing:
        print(f"FATAL: Missing dependencies: {', '.join(missing)}")
        print("Install them first, then re-run this script.")
        return

    # ── Generate collector script ────────────────────────────────────────
    collector = _ROOT / "_collector.py"
    collector.write_text(
        "# Auto-generated — imports all shared deps so PyInstaller collects them\n"
        "import PySide6.QtCore\n"
        "import PySide6.QtGui\n"
        "import PySide6.QtWidgets\n"
        "try:\n"
        "    import PySide6.QtMultimedia\n"
        "except ImportError:\n"
        "    pass\n"
        "try:\n"
        "    import PySide6.QtMultimediaWidgets\n"
        "except ImportError:\n"
        "    pass\n"
        "import shiboken6\n"
        "import pretty_widgets\n"
        "import pretty_widgets.graphics.Theme\n"
        "import pretty_widgets.utils.settings\n"
        "import pretty_widgets.utils.logger\n"
        "import tomli_w\n"
        "import send2trash\n"
        "try:\n"
        "    import requests\n"
        "except ImportError:\n"
        "    pass\n",
        encoding="utf-8",
    )

    # ── Run PyInstaller ──────────────────────────────────────────────────
    print("Building shared runtime via PyInstaller --onedir ...")
    args = [
        str(collector),
        "--name=_runtime_collector",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=PySide6.QtMultimedia",
        "--hidden-import=PySide6.QtMultimediaWidgets",
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=PySide6.QtNetwork",
        "--hidden-import=shiboken6",
        "--hidden-import=pretty_widgets",
        "--hidden-import=pretty_widgets.graphics.Theme",
        "--hidden-import=pretty_widgets.utils.settings",
        "--hidden-import=pretty_widgets.utils.logger",
        "--hidden-import=pretty_widgets.PrettyButton",
        "--hidden-import=pretty_widgets.PrettyLabel",
        "--hidden-import=pretty_widgets.PrettyMenu",
        "--hidden-import=pretty_widgets.PrettyCombo",
        "--hidden-import=pretty_widgets.PrettySlider",
        "--hidden-import=pretty_widgets.PrettyCheckbox",
        "--hidden-import=pretty_widgets.PrettyEdit",
        "--hidden-import=tomli_w",
        "--hidden-import=send2trash",
        f"--distpath={_ROOT / 'dist'}",
        f"--workpath={_ROOT / 'build'}",
        f"--specpath={_ROOT}",
    ]
    PyInstaller.__main__.run(args)

    # ── Promote _internal contents to _runtime root ──────────────────────
    internal = _ROOT / "dist" / "_runtime_collector" / "_internal"
    if not internal.exists():
        print(f"FATAL: Expected {internal} not found after PyInstaller.")
        return

    print("\nPromoting runtime contents ...")
    # Remove old runtime files (keep build_runtime.py and manifest.json)
    preserve = {"build_runtime.py", "manifest.json", "dist", "build",
                "_collector.py", "_runtime_collector.spec"}
    for item in _ROOT.iterdir():
        if item.name in preserve or item.name.startswith("."):
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    # Move everything from _internal up to _runtime root
    for item in internal.iterdir():
        dest = _ROOT / item.name
        shutil.move(str(item), str(dest))

    # ── Cleanup ──────────────────────────────────────────────────────────
    for cleanup in [_ROOT / "dist", _ROOT / "build",
                    collector, _ROOT / "_runtime_collector.spec"]:
        if cleanup.is_dir():
            shutil.rmtree(cleanup, ignore_errors=True)
        elif cleanup.is_file():
            cleanup.unlink(missing_ok=True)

    # Also remove the collector exe that ended up in dist
    collector_exe = _ROOT / "_runtime_collector.exe"
    if collector_exe.exists():
        collector_exe.unlink()

    # ── Write manifest ───────────────────────────────────────────────────
    runtime_hash = _hash_folder(_ROOT)
    manifest = {
        "built": datetime.datetime.now().isoformat(timespec="seconds"),
        "hash": runtime_hash,
        **versions,
    }
    (_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print(f"\n{'=' * 60}")
    print(f"  Runtime built successfully")
    print(f"  Location: {_ROOT}")
    print(f"  Hash:     {runtime_hash}")
    print(f"  Manifest: {_ROOT / 'manifest.json'}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    build_runtime()
