#!/usr/bin/env python3
"""Validate that tracked text files are UTF-8 without BOM."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".css",
    ".env",
    ".example",
    ".go",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".sql",
    ".svg",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".yaml",
    ".yml",
}
TEXT_FILENAMES = {
    ".editorconfig",
    ".gitignore",
    "Dockerfile",
    "Makefile",
}
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "agent_runs",
    "bin",
    "build",
    "coverage",
    "dist",
    "htmlcov",
    "logs",
    "node_modules",
    "vendor",
    "venv",
}


def should_check(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False

    if path.name in TEXT_FILENAMES:
        return True

    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True

    if path.name.endswith(".env.example"):
        return True

    return False


def iter_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_check(path.relative_to(root)):
            files.append(path)
    return sorted(files)


def main() -> int:
    failures: list[str] = []

    for path in iter_text_files(REPO_ROOT):
        relative = path.relative_to(REPO_ROOT)
        data = path.read_bytes()

        if data.startswith(b"\xef\xbb\xbf"):
            failures.append(f"{relative}: UTF-8 BOM is not allowed")
            continue

        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"{relative}: invalid UTF-8 at byte {exc.start}")

    if failures:
        print("Encoding check failed:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("Encoding check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
