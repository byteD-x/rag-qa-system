#!/usr/bin/env python3
"""Validate repository text files use UTF-8 and contain no replacement characters."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".go",
    ".py",
    ".sql",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".sh",
    ".ps1",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".scss",
    ".html",
    ".xml",
    ".mod",
    ".sum",
}

TEXT_FILENAMES = {
    "dockerfile",
    "makefile",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
}



def is_text_file(path: Path) -> bool:
    name = path.name.lower()
    if name in TEXT_FILENAMES:
        return True
    if name.startswith(".env"):
        return True
    return path.suffix.lower() in TEXT_SUFFIXES



def git_tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files"], text=True)
    return [Path(line) for line in output.splitlines() if line]



def main() -> int:
    bad_encoding: list[str] = []
    bad_replacement: list[str] = []
    bad_bom: list[str] = []

    for path in git_tracked_files():
        if not path.exists() or not path.is_file() or not is_text_file(path):
            continue

        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            bad_bom.append(path.as_posix())

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            bad_encoding.append(path.as_posix())
            continue

        if "\ufffd" in text:
            bad_replacement.append(path.as_posix())

    if not (bad_encoding or bad_replacement or bad_bom):
        print("encoding check passed: all tracked text files are UTF-8 without BOM")
        return 0

    if bad_encoding:
        print("non-UTF-8 files:")
        for item in bad_encoding:
            print(f"  - {item}")

    if bad_replacement:
        print("files containing replacement character U+FFFD:")
        for item in bad_replacement:
            print(f"  - {item}")

    if bad_bom:
        print("UTF-8 BOM detected (not allowed):")
        for item in bad_bom:
            print(f"  - {item}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
