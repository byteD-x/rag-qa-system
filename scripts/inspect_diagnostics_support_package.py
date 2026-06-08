#!/usr/bin/env python3
"""Inspect a local diagnostics support package JSON file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


MAX_LOG_ITEMS = 10
SENSITIVE_KEYS = {
    "api_key": "api_key",
    "apikey": "api_key",
    "authorization": "authorization",
    "credential": "credential",
    "password": "password",
    "passwd": "password",
    "secret": "secret",
    "token": "token",
}
CHAT_KEYS = {
    "answer",
    "chat",
    "chat_history",
    "conversation",
    "messages",
    "prompt",
    "question",
    "raw_text",
}
SENSITIVE_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{18,}", re.IGNORECASE)),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9][A-Za-z0-9._-]{18,}", re.IGNORECASE)),
    ("jwt_token", re.compile(r"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)),
    ("password_assignment", re.compile(r"(?:password|passwd|pwd|secret)\s*[:=]\s*[^\s,;}]+", re.IGNORECASE)),
    ("local_user_path", re.compile(r"\b[A-Za-z]:\\Users\\[^\\\s\"']+(?:\\[^\s\"']*)?", re.IGNORECASE)),
    ("unix_home_path", re.compile(r"(?<!\w)/(?:Users|home)/[^\s\"']+(?:/[^\s\"']*)?")),
)
SANITIZE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (pattern, f"<redacted:{category}>") for category, pattern in SENSITIVE_VALUE_PATTERNS
)


def inspect_support_package(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return inspect_package(payload)


def inspect_package(payload: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return {
            "status": "invalid",
            "warnings": ["support package root must be a JSON object"],
            "manifest": {},
            "readiness": {"blocking_failures": []},
            "update": {},
            "logs": [],
            "sensitive_findings": [],
            "redaction_passed": False,
        }

    manifest = _dict_at(payload, "manifest", warnings)
    snapshot = _dict_at(payload, "snapshot", warnings)
    runtime = _dict_at(snapshot, "runtime", warnings, required=False)

    readiness_checks = _readiness_checks(snapshot, runtime, warnings)
    blocking_failures = [
        item
        for item in readiness_checks
        if item.get("status") == "failed" and item.get("blocking") is True
    ]
    update = _update_summary(snapshot, warnings)
    logs = _log_summary(snapshot, runtime, warnings, limit=MAX_LOG_ITEMS)
    findings = _sensitive_findings(payload)

    report = {
        "status": "ok",
        "warnings": warnings,
        "manifest": _manifest_summary(manifest),
        "readiness": {
            "blocking_failures": blocking_failures,
            "blocking_failure_count": len(blocking_failures),
        },
        "update": update,
        "logs": logs,
        "sensitive_findings": findings,
        "redaction_passed": not findings,
    }
    return _sanitize_report(report)


def build_text_report(report: dict[str, Any]) -> str:
    lines = ["Diagnostics Support Package Report", ""]

    manifest = dict(report.get("manifest") or {})
    if manifest:
        lines.extend(
            [
                "Manifest:",
                f"- package_id: {manifest.get('package_id') or 'n/a'}",
                f"- created_at: {manifest.get('created_at') or 'n/a'}",
                f"- source: {manifest.get('source') or 'n/a'}",
                "",
            ]
        )

    warnings = list(report.get("warnings") or [])
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    readiness = dict(report.get("readiness") or {})
    blocking_failures = list(readiness.get("blocking_failures") or [])
    lines.append(f"Readiness blocking failures: {len(blocking_failures)}")
    for item in blocking_failures:
        detail = f" - {item.get('detail')}" if item.get("detail") else ""
        lines.append(f"- {item.get('name') or item.get('path')}: failed{detail}")
    lines.append("")

    update = dict(report.get("update") or {})
    if update:
        lines.extend(
            [
                "Update:",
                f"- status: {update.get('status') or 'unknown'}",
                f"- version: {update.get('version') or 'unknown'}",
                f"- checksum: {update.get('checksum') or 'unknown'}",
                "",
            ]
        )

    logs = list(report.get("logs") or [])
    lines.append(f"Logs summary: {len(logs)} item(s)")
    for item in logs:
        source = item.get("source") or "unknown"
        level = item.get("level") or "info"
        message = item.get("message") or ""
        lines.append(f"- [{source}] {level}: {message}")
    lines.append("")

    findings = list(report.get("sensitive_findings") or [])
    lines.append(f"Redaction passed: {str(bool(report.get('redaction_passed'))).lower()}")
    if findings:
        lines.append("Sensitive findings:")
        for item in findings:
            lines.append(f"- {item.get('category')}: {item.get('path')}")

    return sanitize_text("\n".join(lines).rstrip() + "\n")


def sanitize_text(text: Any) -> str:
    safe = str(text)
    for pattern, replacement in SANITIZE_REPLACEMENTS:
        safe = pattern.sub(replacement, safe)
    return safe


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="Path to a diagnostics support package JSON file.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON report.")
    args = parser.parse_args(argv)

    try:
        report = inspect_support_package(args.package)
    except FileNotFoundError:
        parser.error(f"support package not found: {args.package}")
    except json.JSONDecodeError as exc:
        parser.error(f"invalid JSON support package: {exc}")

    if args.json:
        print(sanitize_text(json.dumps(report, ensure_ascii=False, indent=2)))
    else:
        print(build_text_report(report), end="")
    return 0


def _dict_at(source: dict[str, Any], key: str, warnings: list[str], *, required: bool = True) -> dict[str, Any]:
    value = source.get(key)
    if isinstance(value, dict):
        return value
    if required:
        warnings.append(f"missing or invalid {key}")
    return {}


def _manifest_summary(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        "package_id": sanitize_text(manifest.get("package_id") or manifest.get("id") or ""),
        "created_at": sanitize_text(manifest.get("created_at") or manifest.get("createdAt") or ""),
        "source": sanitize_text(manifest.get("source") or manifest.get("app") or ""),
    }


def _readiness_checks(snapshot: dict[str, Any], runtime: dict[str, Any], warnings: list[str]) -> list[dict[str, Any]]:
    readiness = _dict_at(runtime, "readiness", warnings, required=False)
    if not readiness:
        readiness = _dict_at(snapshot, "readiness", warnings, required=False)
    checks = readiness.get("checks")
    if checks is None:
        warnings.append("missing readiness checks")
        return []

    normalized: list[dict[str, Any]] = []
    if isinstance(checks, dict):
        for name, value in checks.items():
            item = dict(value) if isinstance(value, dict) else {"detail": value}
            normalized.append(_normalize_readiness_check(item, fallback_name=str(name), fallback_path=f"snapshot.runtime.readiness.checks.{name}"))
    elif isinstance(checks, list):
        for index, value in enumerate(checks):
            item = dict(value) if isinstance(value, dict) else {"detail": value}
            normalized.append(_normalize_readiness_check(item, fallback_name=f"check_{index}", fallback_path=f"snapshot.runtime.readiness.checks[{index}]"))
    else:
        warnings.append("readiness checks must be an object or array")
    return normalized


def _normalize_readiness_check(item: dict[str, Any], *, fallback_name: str, fallback_path: str) -> dict[str, Any]:
    status = str(item.get("status") or "").strip().lower()
    return {
        "name": sanitize_text(item.get("name") or fallback_name),
        "path": sanitize_text(item.get("path") or fallback_path),
        "status": status,
        "blocking": item.get("blocking") is True,
        "detail": sanitize_text(item.get("detail") or item.get("message") or item.get("reason") or ""),
    }


def _update_summary(snapshot: dict[str, Any], warnings: list[str]) -> dict[str, str]:
    update = _dict_at(snapshot, "update", warnings, required=False)
    if not update:
        warnings.append("missing update summary")
        return {}
    return {
        "status": sanitize_text(update.get("status") or ""),
        "version": sanitize_text(update.get("version") or update.get("current_version") or update.get("target_version") or ""),
        "checksum": sanitize_text(update.get("checksum") or update.get("sha256") or update.get("digest") or ""),
    }


def _log_summary(snapshot: dict[str, Any], runtime: dict[str, Any], warnings: list[str], *, limit: int) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    logs = snapshot.get("logs")
    diagnostics = _dict_at(_dict_at(runtime, "status", warnings, required=False), "diagnostics", warnings, required=False)

    if logs is None and not diagnostics:
        warnings.append("missing logs summary")
        return []

    _collect_log_items(logs, source="snapshot.logs", output=items, limit=limit)
    _collect_log_items(diagnostics, source="runtime.status.diagnostics", output=items, limit=limit)
    return items[:limit]


def _collect_log_items(value: Any, *, source: str, output: list[dict[str, str]], limit: int) -> None:
    if len(output) >= limit or value in (None, ""):
        return
    if isinstance(value, dict):
        if any(key in value for key in ("message", "error", "detail", "summary")):
            message = value.get("message") or value.get("error") or value.get("detail") or value.get("summary") or ""
            output.append(
                {
                    "source": sanitize_text(value.get("service") or source),
                    "level": sanitize_text(value.get("level") or value.get("severity") or "info"),
                    "message": sanitize_text(message),
                }
            )
            return
        for key, item in value.items():
            _collect_log_items(item, source=f"{source}.{key}", output=output, limit=limit)
            if len(output) >= limit:
                return
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_log_items(item, source=f"{source}[{index}]", output=output, limit=limit)
            if len(output) >= limit:
                return
    else:
        output.append({"source": source, "level": "info", "message": sanitize_text(value)})


def _sensitive_findings(payload: Any) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(category: str, path: str) -> None:
        key = (category, path)
        if key in seen:
            return
        seen.add(key)
        findings.append({"category": category, "path": sanitize_text(path)})

    def walk(value: Any, path: str, key_name: str = "") -> None:
        lowered_key = key_name.lower()
        if isinstance(value, dict):
            for key, item in value.items():
                child_path = _join_json_path(path, str(key))
                walk(item, child_path, str(key))
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]", key_name)
            return

        if _has_non_empty_value(value):
            if lowered_key in SENSITIVE_KEYS:
                add(SENSITIVE_KEYS[lowered_key], path)
            if lowered_key in CHAT_KEYS:
                add("chat_text", path)

        if isinstance(value, str):
            for category, pattern in SENSITIVE_VALUE_PATTERNS:
                if pattern.search(value):
                    add(category, path)

    walk(payload, "$")
    return findings


def _has_non_empty_value(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _join_json_path(parent: str, key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return f"{parent}.{key}"
    safe_key = sanitize_text(key).replace("\\", "\\\\").replace('"', '\\"')
    return f'{parent}["{safe_key}"]'


def _sanitize_report(value: Any) -> Any:
    if isinstance(value, dict):
        return {sanitize_text(key): _sanitize_report(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_report(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


if __name__ == "__main__":
    sys.exit(main())
