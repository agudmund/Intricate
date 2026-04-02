#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - build.py build automation
-Automated 3-stage rollover and forensic hash alignment for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import PyInstaller.__main__
import shutil
import os
import datetime
import subprocess
import hashlib
from pathlib import Path
from send2trash import send2trash
from utils.helpers import ensure_dir

# --- Configuration ---
appName      = "Intricate"
entryPoint   = "main.py"
iconsFolder  = "icons"
docsFolder   = "Documents"


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
        """Generates a SHA-256 hash for a file fingerprint."""
        if not filePath.exists():
            return "n/a (new build)"
        sha256Hash = hashlib.sha256()
        with open(filePath, "rb") as f:
            for byteBlock in iter(lambda: f.read(4096), b""):
                sha256Hash.update(byteBlock)
        return sha256Hash.hexdigest()[:16]

    @classmethod
    def rotateAndArchive(cls, root: Path):
        """Moves existing builds into buffers and tracks everything for the summary."""
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
            rotationSummary.append(f"🔄 archive/{cls.prevExe} -> archive/{cls.archExe}")

        if currentExeFile.exists():
            try:
                currentExeFile.rename(prevExeFile)
                rotationSummary.append(f"🔄 {cls.exeName} -> archive/{cls.prevExe}")
            except PermissionError:
                print(f"❌ FAILED: {cls.exeName} is locked. Close Intricate first!")
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
            rotationSummary.append(f"🔄 {docsFolder}/{cls.prevDoc} -> {docsFolder}/{cls.archDoc}")

        if currentDocFile.exists():
            currentDocFile.rename(prevDocFile)
            rotationSummary.append(f"🔄 {docsFolder}/{cls.docName} -> {docsFolder}/{cls.prevDoc}")

        return oldHash, rotationSummary, trashLog

    @classmethod
    def updateVersionMarkdown(cls, root: Path, newHash: str) -> str:
        """Creates Build Version.md with timestamp and signature."""
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
        """Moves fresh EXE to root and cleans build artefacts."""
        distFolder  = root / "dist"
        buildFolder = root / "build"
        newExePath  = distFolder / cls.exeName

        newHash = "unknown"
        if newExePath.exists():
            newHash = cls.getFileHash(newExePath)
            dest = root / cls.exeName
            if dest.exists():
                send2trash(str(dest))
                trashLog.append(f"Root/{cls.exeName} (replaced)")
            shutil.move(str(newExePath), str(dest))
            print("\n" + "─" * 60)
            print(f"📍 NOTE: PyInstaller finished in 'dist/', but I have")
            print(f"   promoted the fresh {cls.exeName} to your root folder.")
            print("─" * 60)

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
    print(f"🚀 Starting build for {appName}...")

    # 1. Archive
    previousSignature, rotationLogs, trashLog = BuildManager.rotateAndArchive(projectRoot)
    if previousSignature is None:
        return

    # 2. Build Args
    args = [
        entryPoint,
        f"--name={appName}",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--exclude-module=pygame",
        f"--add-data={iconsFolder}{os.pathsep}{iconsFolder}",
    ]

    # 3. PyInstaller Execution
    print(f"🏗️ Building {appName}.exe via PyInstaller...")
    PyInstaller.__main__.run(args)

    # 4. Finalize & Versioning
    newSignature = BuildManager.finalizeAndCleanup(projectRoot, trashLog)
    buildTime    = BuildManager.updateVersionMarkdown(projectRoot, newSignature)

    # 5. Summary
    print(f"\n{'═' * 60}")
    print(f"📦 BUILD SUMMARY - {buildTime}")
    print(f"{'═' * 60}")

    if rotationLogs:
        for log in rotationLogs:
            print(log)
    else:
        print("🔄 No previous rotation history found.")

    if trashLog:
        for item in trashLog:
            print(f"♻️ Sent to Recycle Bin: {item}")
    else:
        print("♻️ Nothing to purge.")

    print(f"\n🛡️ Previous {appName}.exe Signature: [{previousSignature}]")
    print(f"🛡️ Fresh {appName}.exe Signature:    [{newSignature}]")
    print(f"{'═' * 60}")

    finalExe = projectRoot / f"{appName}.exe"
    if finalExe.exists():
        print(f"\n✨ Success! Launching {appName}.exe...")
        subprocess.Popen([str(finalExe)])
        print(f"Check your logs to see if the sparkle ✨ [{newSignature}] arrived safely.")
    else:
        print(f"\n✨ Build complete, but {appName}.exe was not found in root.")

    print("\n✨ Build Cycle Complete. Stay cozy! 🌱")


if __name__ == "__main__":
    buildApp()
