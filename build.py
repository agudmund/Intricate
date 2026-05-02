#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - build.py build automation
-OneDir build with shared runtime junction for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import PyInstaller.__main__
import shutil
import os
import datetime
import subprocess
import hashlib
import json
from pathlib import Path
from send2trash import send2trash

# --- Configuration ---
appName      = "Intricate"
entryPoint   = "main.py"
iconsFolder  = "icons"
docsFolder   = str(Path("Documents") / "Build")

# Shared runtime — built by _runtime/build_runtime.py
_RUNTIME_DIR = Path(os.environ.get(
    "SingleSharedBraincell_Runtime",
    Path(__file__).parent.parent / "_runtime"
))

# Modules that live in the shared runtime — excluded from per-app builds
_SHARED_EXCLUDES = [
    "PySide6", "shiboken6", "pretty_widgets",
    "tomli_w", "send2trash", "requests",
    "certifi", "urllib3", "charset_normalizer", "idna",
]


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


class BuildManager:
    """Utility to handle build rotations, documentation, and forensic hashing."""

    exeName = f"{appName}.exe"
    prevExe = f"{appName}_previous.exe"
    archExe = f"{appName}_archive.exe"

    docName = "Build Version.md"
    prevDoc = "Build Version Previous.md"
    archDoc = "Build Version Archive.md"

    @classmethod
    def getFileHash(cls, filePath: Path) -> str:
        if not filePath.exists():
            return "n/a (new build)"
        sha256Hash = hashlib.sha256()
        with open(filePath, "rb") as f:
            for byteBlock in iter(lambda: f.read(4096), b""):
                sha256Hash.update(byteBlock)
        return sha256Hash.hexdigest()[:16]

    @classmethod
    def rotateAndArchive(cls, root: Path):
        archiveDir = root / "archive"
        ensure_dir(archiveDir)
        docsDir = root / docsFolder
        ensure_dir(docsDir)

        currentExeFile = root / cls.exeName
        oldHash = cls.getFileHash(currentExeFile)

        rotationSummary = []
        trashLog = []

        # 1. Rotate Binaries
        prevExeFile = archiveDir / cls.prevExe
        archExeFile = archiveDir / cls.archExe

        if archExeFile.exists():
            send2trash(str(archExeFile))
            trashLog.append(f"archive/{cls.archExe}")

        if prevExeFile.exists():
            prevExeFile.rename(archExeFile)
            rotationSummary.append(f"archive/{cls.prevExe} -> archive/{cls.archExe}")

        if currentExeFile.exists():
            try:
                currentExeFile.rename(prevExeFile)
                rotationSummary.append(f"{cls.exeName} -> archive/{cls.prevExe}")
            except PermissionError:
                print(f"FAILED: {cls.exeName} is locked. Close Intricate first!")
                return None, [], []

        # 2. Rotate Documentation
        currentDocFile = docsDir / cls.docName
        prevDocFile    = docsDir / cls.prevDoc
        archDocFile    = docsDir / cls.archDoc

        if archDocFile.exists():
            send2trash(str(archDocFile))
            trashLog.append(f"{docsFolder}/{cls.archDoc}")

        if prevDocFile.exists():
            prevDocFile.rename(archDocFile)
            rotationSummary.append(f"{docsFolder}/{cls.prevDoc} -> {docsFolder}/{cls.archDoc}")

        if currentDocFile.exists():
            currentDocFile.rename(prevDocFile)
            rotationSummary.append(f"{docsFolder}/{cls.docName} -> {docsFolder}/{cls.prevDoc}")

        return oldHash, rotationSummary, trashLog

    @classmethod
    def updateVersionMarkdown(cls, root: Path, newHash: str) -> str:
        timestamp = datetime.datetime.now().strftime("%Y.%m.%d - %H:%M")
        content = (
            f"# Build Version\n\n"
            f"**Timestamp:** `{timestamp}`\n"
            f"**Signature:** `{newHash}`\n"
            f"**Status:** `Stable Daily Build`\n"
        )
        docsPath = root / docsFolder
        with open(docsPath / cls.docName, "w", encoding="utf-8") as f:
            f.write(content)
        return timestamp

    @classmethod
    def finalizeAndCleanup(cls, root: Path, trashLog: list) -> str:
        """Move the thin exe from dist/ to project root and create the runtime junction."""
        distFolder  = root / "dist"
        buildFolder = root / "build"
        # In --onedir mode the exe is inside dist/<appName>/
        onedirFolder = distFolder / appName
        newExePath   = onedirFolder / cls.exeName

        newHash = "unknown"
        if newExePath.exists():
            newHash = cls.getFileHash(newExePath)
            dest = root / cls.exeName
            if dest.exists():
                send2trash(str(dest))
                trashLog.append(f"Root/{cls.exeName} (replaced)")
            shutil.move(str(newExePath), str(dest))
            print(f"\nPromoted {cls.exeName} to project root.")

        # Create _internal junction → shared runtime
        internal = root / "_internal"
        if internal.exists():
            # Always use rmdir first — handles junctions without deleting target.
            # Falls back to rmtree for real directories.
            result = subprocess.run(["cmd", "/c", "rmdir", str(internal)],
                                    capture_output=True)
            if internal.exists():
                shutil.rmtree(internal)
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(internal), str(_RUNTIME_DIR)],
            check=True, capture_output=True,
        )
        print(f"Junction: _internal -> {_RUNTIME_DIR}")

        for folder in [buildFolder, distFolder]:
            if folder.exists():
                try:
                    send2trash(str(folder))
                    trashLog.append(f"{folder.name}/")
                except Exception:
                    pass

        return newHash


def buildApp():
    projectRoot = Path(__file__).parent.absolute()
    print(f"\nStarting build for {appName} (onedir + shared runtime)...")

    # ── Validate shared runtime ──────────────────────────────────────────
    if not (_RUNTIME_DIR / "PySide6").is_dir():
        print(f"\nShared runtime not found at {_RUNTIME_DIR}")
        print("Run _runtime/build_runtime.py first.")
        return

    manifest_path = _RUNTIME_DIR / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(f"Shared runtime: {manifest.get('hash', '?')} "
              f"(PySide6 {manifest.get('PySide6', '?')}, "
              f"pretty_widgets {manifest.get('pretty_widgets', '?')})")

    # ── Archive ──────────────────────────────────────────────────────────
    previousSignature, rotationLogs, trashLog = BuildManager.rotateAndArchive(projectRoot)
    if previousSignature is None:
        return

    # ── Build Args ───────────────────────────────────────────────────────
    appIcon = projectRoot / iconsFolder / "intricate.ico"
    args = [
        entryPoint,
        f"--name={appName}",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        f"--icon={appIcon}",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=PySide6.QtMultimedia",
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=PySide6.QtNetwork",
        "--hidden-import=pretty_widgets",
        "--hidden-import=pretty_widgets.graphics.Theme",
        "--hidden-import=pretty_widgets.utils.settings",
        "--hidden-import=shared_braincell",
        "--hidden-import=shared_braincell.logger",
        "--hidden-import=intricate_log",
        "--exclude-module=pygame",
    ]

    # ── PyInstaller Execution ────────────────────────────────────────────
    print(f"Building {appName}.exe via PyInstaller --onedir ...")
    PyInstaller.__main__.run(args)

    # ── Finalize & Versioning ────────────────────────────────────────────
    newSignature = BuildManager.finalizeAndCleanup(projectRoot, trashLog)
    buildTime    = BuildManager.updateVersionMarkdown(projectRoot, newSignature)

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"BUILD SUMMARY - {buildTime}")
    print(f"{'=' * 60}")

    for log in rotationLogs:
        print(f"  {log}")

    if trashLog:
        for item in trashLog:
            print(f"  Recycled: {item}")

    print(f"\n  Previous signature: [{previousSignature}]")
    print(f"  Fresh signature:    [{newSignature}]")

    finalExe = projectRoot / f"{appName}.exe"
    if finalExe.exists():
        os.utime(str(finalExe))
        subprocess.run(["ie4uinit.exe", "-show"], capture_output=True)
        print(f"\n  Launching {appName}.exe...")
        subprocess.Popen([str(finalExe)])
        print(f"  Check logs for sparkle [{newSignature}]")

    print(f"\n{'=' * 60}")
    print(f"Build complete. Stay cozy!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    buildApp()
