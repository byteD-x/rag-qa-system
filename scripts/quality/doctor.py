#!/usr/bin/env python
"""Lightweight local environment doctor for first-run diagnostics."""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PORTS = (5173, 8080, 8300, 5432, 6333, 9000)
REQUIRED_COMMANDS = ("python", "node", "npm", "make")
OPTIONAL_COMMANDS = ("docker",)
REQUIRED_FILES = (".env.example", "README.md", "docker-compose.yml", "apps/web/package.json")
RECOMMENDED_ENV_KEYS = ("JWT_SECRET", "ADMIN_EMAIL", "ADMIN_PASSWORD", "LLM_API_KEY")


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def _status_for_command(name: str, required: bool = True) -> CheckResult:
    if shutil.which(name):
        return CheckResult(name=f"command:{name}", status="ok", detail="available")
    level = "error" if required else "warn"
    if name == "docker" and not required:
        return CheckResult(
            name=f"command:{name}",
            status=level,
            detail="not found; run `make demo-offline` for offline evidence before full Docker stack checks",
        )
    return CheckResult(name=f"command:{name}", status=level, detail="not found")


def _status_for_file(relative_path: str, required: bool = True) -> CheckResult:
    path = REPO_ROOT / relative_path
    if path.exists():
        return CheckResult(name=f"file:{relative_path}", status="ok", detail="present")
    level = "error" if required else "warn"
    return CheckResult(name=f"file:{relative_path}", status=level, detail="missing")


def _status_for_port(port: int) -> CheckResult:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.2)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
    finally:
        sock.close()
    if result == 0:
        return CheckResult(name=f"port:{port}", status="warn", detail="in use")
    return CheckResult(name=f"port:{port}", status="ok", detail="free")


def _parse_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if key:
            keys.add(key)
    return keys


def _status_for_env_file() -> list[CheckResult]:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return [
            CheckResult(
                name="env:.env",
                status="warn",
                detail="missing; copy .env.example to .env before running the full stack",
            )
        ]

    keys = _parse_env_keys(env_path)
    results = [CheckResult(name="env:.env", status="ok", detail="present")]
    missing = [key for key in RECOMMENDED_ENV_KEYS if key not in keys]
    if missing:
        results.append(
            CheckResult(
                name="env:recommended_keys",
                status="warn",
                detail="missing keys: " + ", ".join(missing),
            )
        )
    else:
        results.append(CheckResult(name="env:recommended_keys", status="ok", detail="present"))
    return results


def build_report() -> dict[str, Any]:
    results = [
        _status_for_command(name, required=True) for name in REQUIRED_COMMANDS
    ] + [
        _status_for_command(name, required=False) for name in OPTIONAL_COMMANDS
    ] + [
        _status_for_file(path, required=True) for path in REQUIRED_FILES
    ] + [
        *_status_for_env_file()
    ] + [
        _status_for_port(port) for port in DEFAULT_PORTS
    ]

    errors = [item for item in results if item.status == "error"]
    warnings = [item for item in results if item.status == "warn"]

    return {
        "repo_root": str(REPO_ROOT),
        "status": "failed" if errors else "passed_with_warnings" if warnings else "passed",
        "errors": [asdict(item) for item in errors],
        "warnings": [asdict(item) for item in warnings],
        "checks": [asdict(item) for item in results],
    }


def write_human_report(report: dict[str, Any]) -> None:
    print("Doctor report")
    print(f"Status: {report['status']}")
    print(f"Repo root: {report['repo_root']}")
    print("")
    for item in report["checks"]:
        print(f"- {item['name']}: {item['status']} ({item['detail']})")
    if report["warnings"]:
        print("")
        print("Warnings:")
        for item in report["warnings"]:
            print(f"- {item['name']}: {item['detail']}")
    if report["errors"]:
        print("")
        print("Errors:")
        for item in report["errors"]:
            print(f"- {item['name']}: {item['detail']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human readable text.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero for warnings as well as errors.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        write_human_report(report)
    if report["errors"]:
        return 1
    if args.strict and report["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
