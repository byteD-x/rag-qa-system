from __future__ import annotations

import re
from datetime import datetime
from typing import Any


_VERSION_NUMBER_RE = re.compile(r"(?:^|[\s_\-.])v(?:ersion)?\s*(\d{1,5})(?:$|[\s_\-.])", re.IGNORECASE)
_YEAR_QUARTER_RE = re.compile(r"(20\d{2})[\s_\-.]?(q[1-4])", re.IGNORECASE)
_YEAR_MONTH_RE = re.compile(r"(20\d{2})[\s_\-.]?(0[1-9]|1[0-2])")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_STOP_TOKENS = {
    "draft",
    "active",
    "archived",
    "history",
    "archive",
    "current",
    "latest",
    "final",
    "copy",
    "doc",
    "pdf",
    "txt",
    "docx",
    "png",
    "jpg",
    "jpeg",
}


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_for_match(*values: Any) -> str:
    merged = " ".join(_safe_text(value).lower() for value in values if _safe_text(value))
    merged = _YEAR_QUARTER_RE.sub(" ", merged)
    merged = _YEAR_MONTH_RE.sub(" ", merged)
    merged = _VERSION_NUMBER_RE.sub(" ", merged)
    merged = _NON_ALNUM_RE.sub(" ", merged)
    tokens = [token for token in merged.split() if token and token not in _STOP_TOKENS]
    return " ".join(tokens)


def _extract_version_number(*values: Any) -> int | None:
    for value in values:
        match = _VERSION_NUMBER_RE.search(_safe_text(value))
        if match:
            return int(match.group(1))
    return None


def _extract_period_label(*values: Any) -> str:
    for value in values:
        candidate = _safe_text(value)
        if not candidate:
            continue
        quarter = _YEAR_QUARTER_RE.search(candidate)
        if quarter:
            return f"{quarter.group(1)}-{quarter.group(2).upper()}"
        year_month = _YEAR_MONTH_RE.search(candidate)
        if year_month:
            return f"{year_month.group(1)}-{year_month.group(2)}"
    return ""


def _pick_title(candidate: dict[str, Any]) -> str:
    metadata = dict(candidate.get("source_metadata") or {})
    return (
        _safe_text(candidate.get("title"))
        or _safe_text(metadata.get("page_title"))
        or _safe_text(candidate.get("relative_path"))
        or _safe_text(candidate.get("file_name"))
    )


def build_version_assist(
    *,
    candidate: dict[str, Any],
    existing_documents: list[dict[str, Any]],
    explicit_version_family_key: str = "",
    explicit_version_label: str = "",
    explicit_supersedes_document_id: str = "",
) -> dict[str, Any]:
    explicit_family = _safe_text(explicit_version_family_key)
    explicit_label = _safe_text(explicit_version_label)
    explicit_supersedes = _safe_text(explicit_supersedes_document_id)
    if explicit_family and explicit_label:
        return {}

    candidate_title = _pick_title(candidate)
    candidate_file_name = _safe_text(candidate.get("file_name"))
    candidate_source_uri = _safe_text(candidate.get("source_uri"))
    candidate_relative_path = _safe_text(candidate.get("relative_path"))
    candidate_updated_at = candidate.get("source_updated_at")
    candidate_version_number = _extract_version_number(candidate_file_name, candidate_relative_path, candidate_title)
    candidate_period_label = _extract_period_label(candidate_file_name, candidate_relative_path, candidate_title)
    candidate_norm = _normalize_for_match(candidate_title, candidate_file_name, candidate_relative_path)

    if explicit_supersedes:
        matched = next((item for item in existing_documents if _safe_text(item.get("id")) == explicit_supersedes), None)
        if matched is not None:
            next_number = candidate_version_number or (int(matched.get("version_number") or 1) + 1)
            return {
                "suggested_version_family_key": _safe_text(matched.get("version_family_key") or matched.get("id")),
                "suggested_version_label": explicit_label or (candidate_period_label or f"v{next_number}"),
                "suggested_supersedes_document_id": explicit_supersedes,
                "confidence": 0.99,
                "reasons": ["explicit_supersedes_document_id"],
                "matched_document_id": explicit_supersedes,
                "auto_apply": True,
            }

    scored: list[tuple[float, dict[str, Any], list[str]]] = []
    for document in existing_documents:
        document_id = _safe_text(document.get("id"))
        if not document_id:
            continue
        doc_title = _safe_text(document.get("file_name"))
        doc_source_uri = _safe_text(document.get("source_uri"))
        doc_metadata = dict(document.get("source_metadata_json") or {})
        doc_relative_path = _safe_text(doc_metadata.get("relative_path"))
        doc_norm = _normalize_for_match(doc_title, doc_relative_path)
        if not doc_norm or not candidate_norm:
            continue
        score = 0.0
        reasons: list[str] = []
        if doc_source_uri and candidate_source_uri and doc_source_uri == candidate_source_uri:
            score += 1.3
            reasons.append("same_source_uri")
        if doc_relative_path and candidate_relative_path and doc_relative_path.lower() == candidate_relative_path.lower():
            score += 1.1
            reasons.append("same_relative_path")
        if doc_norm == candidate_norm:
            score += 0.95
            reasons.append("normalized_title_match")
        elif candidate_norm in doc_norm or doc_norm in candidate_norm:
            score += 0.55
            reasons.append("partial_title_match")
        doc_version_number = int(document.get("version_number") or 0)
        if candidate_version_number is not None and doc_version_number and candidate_version_number == doc_version_number + 1:
            score += 0.45
            reasons.append("version_sequence_match")
        doc_updated_at = document.get("source_updated_at") or document.get("updated_at")
        if isinstance(candidate_updated_at, datetime) and isinstance(doc_updated_at, datetime) and candidate_updated_at >= doc_updated_at:
            score += 0.15
            reasons.append("updated_after_candidate")
        if score > 0:
            scored.append((score, document, reasons))

    if not scored:
        return {}

    scored.sort(key=lambda item: (item[0], int(item[1].get("version_number") or 0), _safe_text(item[1].get("updated_at"))), reverse=True)
    score, matched, reasons = scored[0]
    matched_document_id = _safe_text(matched.get("id"))
    matched_version_number = int(matched.get("version_number") or 1)
    next_number = candidate_version_number or (matched_version_number + 1)
    suggested_label = explicit_label or (candidate_period_label or f"v{next_number}")
    confidence = 0.0
    if score >= 2.1:
        confidence = 0.94
    elif score >= 1.6:
        confidence = 0.84
    elif score >= 1.1:
        confidence = 0.72
    else:
        confidence = 0.58
    auto_apply = confidence >= 0.94 and "version_sequence_match" in reasons and bool(_safe_text(matched.get("version_family_key") or matched_document_id))
    return {
        "suggested_version_family_key": _safe_text(matched.get("version_family_key") or matched_document_id),
        "suggested_version_label": suggested_label,
        "suggested_supersedes_document_id": matched_document_id,
        "confidence": confidence,
        "reasons": reasons,
        "matched_document_id": matched_document_id,
        "auto_apply": auto_apply,
    }


__all__ = ["build_version_assist"]
