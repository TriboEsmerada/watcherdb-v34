"""
Strip UTF-8 BOM (byte order mark) from Python source files before PyArmor.

PyArmor's obfuscator is sensitive to files saved as UTF-8-with-BOM: the
obfuscated output compiles but raises SyntaxError at runtime when the BOM
remains on the first line. This was observed historically in V5 (see
pyarmor.bug.log) and is cheap to prevent.

This script walks the project tree, detects BOM on .py files, and rewrites
them as UTF-8 without BOM. It is idempotent.

Invoked automatically by deploy/build.py before the PyArmor phase.
"""

from __future__ import annotations

import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"

# Directories to scan (relative to project root)
SCAN_DIRS = [
    "api",
    "watcherdb",
    "services",
    "modules",
    "collectors",
    "scripts",
    "tools",
    "alembic",
]

# Extra root-level files
SCAN_FILES = [
    "watcherdb_main.py",
    "watcherdb_intelligence.py",
]

# Directories to skip when walking (even if inside SCAN_DIRS)
SKIP = {"__pycache__", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache"}


def strip_bom(path: Path) -> bool:
    """Return True if the file had a BOM and was rewritten."""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if not data.startswith(BOM):
        return False
    path.write_bytes(data[len(BOM):])
    return True


def iter_py_files(root: Path):
    for name in SCAN_FILES:
        p = root / name
        if p.is_file() and p.suffix == ".py":
            yield p
    for d in SCAN_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if any(part in SKIP for part in p.parts):
                continue
            yield p


def main(root: Path | None = None) -> int:
    project_root = root or Path(__file__).resolve().parent.parent
    fixed = 0
    scanned = 0
    for py in iter_py_files(project_root):
        scanned += 1
        if strip_bom(py):
            fixed += 1
            rel = py.relative_to(project_root)
            print(f"  [BOM] stripped: {rel}")
    print(f"sanitize_bom: scanned {scanned} files, fixed {fixed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
