#!/usr/bin/env python3
"""Scan every .py file in the repo for external imports.

Filters out stdlib and local modules, prints a frequency-ranked list of
external package roots — the real dependency surface of the codebase.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).parent

# Identify local modules: any top-level .py in root + any package directory
local_pkgs = set()
for f in ROOT.glob("*.py"):
    local_pkgs.add(f.stem)
for d in ROOT.iterdir():
    if d.is_dir() and (d / "__init__.py").exists():
        local_pkgs.add(d.name)
# Also treat these directory names as local (they hold local modules even
# without __init__.py in this codebase)
local_pkgs.update({
    "nodes", "graphics", "data", "widgets", "utils",
    "icons", "audio", "archive",
})

# Stdlib modules — broad but hand-curated subset
STDLIB = set("""
os sys re ast math json time datetime subprocess shutil pathlib typing collections
threading queue logging functools itertools contextlib io tempfile traceback
ctypes weakref dataclasses enum abc copy random hashlib base64 struct binascii
asyncio socket urllib http email warnings atexit signal platform inspect uuid
textwrap unicodedata sqlite3 csv configparser xml html argparse glob fnmatch
string stat errno mmap pickle zipfile tarfile gzip bz2 lzma zlib
operator array bisect heapq reprlib types builtins __future__
tkinter multiprocessing concurrent difflib gc getpass locale
tomllib tomli runpy shlex importlib pkgutil linecache dis
resource selectors select site termios fcntl curses
winreg msvcrt _thread _tkinter _winapi
""".split())

SKIP_PATH_PARTS = {".git", "__pycache__", "venv", ".venv", "Documents",
                   ".claude", "archive", "_internal", "Display Resolution",
                   "Images", "logs", "build", "dist"}

imports: dict[str, set[str]] = {}

for p in ROOT.rglob("*.py"):
    if any(part in SKIP_PATH_PARTS for part in p.parts):
        continue
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"  [skip] {p.relative_to(ROOT)}: {exc}")
        continue
    rel = str(p.relative_to(ROOT)).replace("\\", "/")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                imports.setdefault(root, set()).add(rel)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                root = node.module.split(".")[0]
                imports.setdefault(root, set()).add(rel)

external = {k: v for k, v in imports.items()
            if k not in STDLIB and k not in local_pkgs and not k.startswith("_")}

print(f"Scanned .py files under: {ROOT}")
print(f"Local modules filtered:  {len(local_pkgs)}")
print(f"External import roots:   {len(external)}")
print()
print(f"{'PACKAGE':30} {'FILES':>6}  USED IN")
print("-" * 90)
for pkg in sorted(external, key=lambda k: (-len(external[k]), k)):
    files = sorted(external[pkg])
    sample = files[0] if len(files) == 1 else f"{files[0]} + {len(files)-1} more"
    print(f"{pkg:30} {len(files):>6}  {sample}")

print()
print("=== Per-package first-occurrence context ===")
for pkg in sorted(external):
    files = sorted(external[pkg])
    print(f"\n{pkg}:")
    for f in files[:3]:
        print(f"  - {f}")
    if len(files) > 3:
        print(f"  - ... ({len(files)-3} more)")
