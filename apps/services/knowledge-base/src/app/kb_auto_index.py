from __future__ import annotations

from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from .parsing import parse_text_content
from .runtime import BLOB_ROOT, KBChunkingSettings, load_chunking_settings


AUTO_INDEX_INBOX_DIR = "knowledge_base/inbox"
AUTO_INDEX_ALLOWED_EXTENSIONS = {".md", ".markdown", ".txt"}
AUTO_INDEX_MAX_FILES = 20
AUTO_INDEX_MAX_FILE_BYTES = 300_000
AUTO_INDEX_MAX_TOTAL_CHARS = 300_000
AUTO_INDEX_MAX_SECTION_SUMMARY_ITEMS = 20


def build_knowledge_auto_index_preview_payload() -> dict[str, Any]:
    chunking_settings = load_chunking_settings()
    chunking_summary = chunking_settings.summary()
    inbox = fixed_auto_index_inbox_path()
    if not inbox.exists():
        return {
            "dry_run": True,
            "source": "fixed_inbox",
            "inbox": _safe_inbox_ref(inbox),
            "exists": False,
            "document_count": 0,
            "skipped_count": 0,
            "chunk_count": 0,
            "char_count": 0,
            "chunking": chunking_summary,
            "documents": [],
            "skipped": [],
            "limits": _limits_payload(),
        }
    if not inbox.is_dir():
        return {
            "dry_run": True,
            "source": "fixed_inbox",
            "inbox": _safe_inbox_ref(inbox),
            "exists": False,
            "document_count": 0,
            "skipped_count": 1,
            "chunk_count": 0,
            "char_count": 0,
            "chunking": chunking_summary,
            "documents": [],
            "skipped": [{"file_name": _safe_leaf_name(inbox.name, fallback="inbox"), "reason": "inbox_not_directory"}],
            "limits": _limits_payload(),
        }

    documents: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    total_chars = 0
    for path in sorted(inbox.iterdir(), key=lambda item: item.name.lower()):
        if path.is_symlink():
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="item"), "reason": "symlink_ignored"})
            continue
        if path.is_dir():
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="directory"), "reason": "directory_ignored"})
            continue
        if not path.is_file():
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="item"), "reason": "not_file"})
            continue
        if path.suffix.lower() not in AUTO_INDEX_ALLOWED_EXTENSIONS:
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="file"), "reason": "unsupported_extension"})
            continue
        if len(documents) >= AUTO_INDEX_MAX_FILES:
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="file"), "reason": "too_many_files"})
            continue

        size_bytes = int(path.stat().st_size)
        if size_bytes > AUTO_INDEX_MAX_FILE_BYTES:
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="file"), "reason": "file_too_large"})
            continue
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="file"), "reason": "utf8_decode_failed"})
            continue
        except OSError:
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="file"), "reason": "read_failed"})
            continue
        if not content.strip():
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="file"), "reason": "empty_content"})
            continue
        if total_chars + len(content) > AUTO_INDEX_MAX_TOTAL_CHARS:
            skipped.append({"file_name": _safe_leaf_name(path.name, fallback="file"), "reason": "total_content_too_large"})
            continue

        documents.append(
            _build_document_preview(
                path,
                content=content,
                size_bytes=size_bytes,
                chunking_settings=chunking_settings,
            )
        )
        total_chars += len(content)

    return {
        "dry_run": True,
        "source": "fixed_inbox",
        "inbox": _safe_inbox_ref(inbox),
        "exists": True,
        "document_count": len(documents),
        "skipped_count": len(skipped),
        "chunk_count": sum(int(item["chunk_count"]) for item in documents),
        "char_count": total_chars,
        "chunking": chunking_summary,
        "documents": documents,
        "skipped": skipped,
        "limits": _limits_payload(),
    }


def fixed_auto_index_inbox_path() -> Path:
    return (BLOB_ROOT / AUTO_INDEX_INBOX_DIR).resolve()


def _build_document_preview(
    path: Path,
    *,
    content: str,
    size_bytes: int,
    chunking_settings: KBChunkingSettings | None = None,
) -> dict[str, Any]:
    chunking_settings = chunking_settings or load_chunking_settings()
    parsed = parse_text_content(content, **chunking_settings.as_kwargs())
    chunks_by_section = Counter(int(chunk.section_index) for chunk in parsed.chunks)
    sections = [
        {
            "section_index": int(section.section_index),
            "char_start": int(section.char_start),
            "char_end": int(section.char_end),
            "char_count": max(int(section.char_end) - int(section.char_start), 0),
            "chunk_count": int(chunks_by_section.get(int(section.section_index), 0)),
        }
        for section in parsed.sections[:AUTO_INDEX_MAX_SECTION_SUMMARY_ITEMS]
    ]
    file_name = _safe_leaf_name(path.name, fallback="document.txt")
    return {
        "doc_id": path.stem[:160],
        "file_name": file_name,
        "file_type": path.suffix.lower().lstrip("."),
        "size_bytes": size_bytes,
        "content_chars": len(content),
        "section_count": len(parsed.sections),
        "chunk_count": len(parsed.chunks),
        "sections": sections,
        "truncated_sections": max(len(parsed.sections) - len(sections), 0),
    }


def _safe_inbox_ref(path: Path) -> str:
    try:
        parts = path.parts
        if len(parts) >= 2:
            return str(PurePosixPath(parts[-2], parts[-1]))
    except Exception:
        pass
    return _safe_leaf_name(path.name, fallback="inbox")


def _safe_leaf_name(raw: Any, *, fallback: str) -> str:
    cleaned = str(raw or "").strip().replace("\\", "/")
    leaf = PurePosixPath(cleaned).name.strip()
    if not leaf or leaf in {".", ".."}:
        leaf = fallback
    return leaf[:160]


def _limits_payload() -> dict[str, Any]:
    return {
        "max_files": AUTO_INDEX_MAX_FILES,
        "max_file_bytes": AUTO_INDEX_MAX_FILE_BYTES,
        "max_total_chars": AUTO_INDEX_MAX_TOTAL_CHARS,
        "allowed_extensions": sorted(AUTO_INDEX_ALLOWED_EXTENSIONS),
    }
