from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
from typing import Any

from .parsing import parse_text_content
from .runtime import load_chunking_settings


MAX_KNOWLEDGE_BATCH_DOCUMENTS = 20
MAX_KNOWLEDGE_BATCH_CONTENT_CHARS = 300_000
MAX_SAFE_NAME_CHARS = 160
MAX_SECTION_SUMMARY_ITEMS = 20
FORBIDDEN_DOCUMENT_FIELDS = {
    "chunk_text",
    "chunk_texts",
    "chunks",
    "content_path",
    "embedding",
    "embeddings",
    "path",
    "source_file",
    "source_path",
    "storage_path",
}
CHUNKING_SETTINGS = load_chunking_settings()


class KnowledgeBatchPayloadError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def parse_knowledge_document_payload(raw: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise KnowledgeBatchPayloadError("knowledge_batch_document_invalid", "documents items must be objects")

    forbidden = sorted(FORBIDDEN_DOCUMENT_FIELDS & set(raw.keys()))
    if forbidden:
        raise KnowledgeBatchPayloadError(
            "knowledge_batch_field_not_allowed",
            f"documents[{index}] contains forbidden fields: {', '.join(forbidden)}",
        )

    content = raw.get("content")
    if not isinstance(content, str) or not content.strip():
        raise KnowledgeBatchPayloadError("knowledge_batch_content_required", f"documents[{index}].content must not be blank")

    fallback_id = f"document-{index + 1}"
    doc_id = _safe_leaf_name(raw.get("doc_id") or raw.get("document_id") or fallback_id, fallback=fallback_id)
    file_name = _safe_leaf_name(raw.get("file_name") or raw.get("name") or doc_id, fallback=f"{doc_id}.txt")

    return {
        "doc_id": doc_id[:MAX_SAFE_NAME_CHARS],
        "file_name": file_name,
        "content": content,
    }


def parse_knowledge_batch_payload(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        raise KnowledgeBatchPayloadError("knowledge_batch_payload_invalid", "request body must be an object")
    documents = raw.get("documents")
    if not isinstance(documents, list) or not documents:
        raise KnowledgeBatchPayloadError("knowledge_batch_documents_required", "documents must contain at least one item")
    if len(documents) > MAX_KNOWLEDGE_BATCH_DOCUMENTS:
        raise KnowledgeBatchPayloadError(
            "knowledge_batch_too_many_documents",
            f"documents must contain no more than {MAX_KNOWLEDGE_BATCH_DOCUMENTS} items",
        )

    parsed = [parse_knowledge_document_payload(item, index=index) for index, item in enumerate(documents)]
    total_content_chars = sum(len(item["content"]) for item in parsed)
    if total_content_chars > MAX_KNOWLEDGE_BATCH_CONTENT_CHARS:
        raise KnowledgeBatchPayloadError(
            "knowledge_batch_content_too_large",
            f"documents content must contain no more than {MAX_KNOWLEDGE_BATCH_CONTENT_CHARS} characters in total",
        )
    return parsed


def build_knowledge_dry_run_payload(document: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_text_content(str(document["content"]), **CHUNKING_SETTINGS.as_kwargs())
    chunks_by_section = Counter(int(chunk.section_index) for chunk in parsed.chunks)
    section_summaries = [
        {
            "section_index": int(section.section_index),
            "char_start": int(section.char_start),
            "char_end": int(section.char_end),
            "char_count": max(int(section.char_end) - int(section.char_start), 0),
            "chunk_count": int(chunks_by_section.get(int(section.section_index), 0)),
        }
        for section in parsed.sections[:MAX_SECTION_SUMMARY_ITEMS]
    ]

    return {
        "doc_id": str(document["doc_id"]),
        "file_name": str(document["file_name"]),
        "content_chars": len(str(document["content"])),
        "section_count": len(parsed.sections),
        "chunk_count": len(parsed.chunks),
        "sections": section_summaries,
        "truncated_sections": max(len(parsed.sections) - len(section_summaries), 0),
    }


def build_knowledge_batch_dry_run_payload(raw: Any) -> dict[str, Any]:
    documents = parse_knowledge_batch_payload(raw)
    document_summaries = [build_knowledge_dry_run_payload(document) for document in documents]
    return {
        "dry_run": True,
        "document_count": len(document_summaries),
        "total_content_chars": sum(int(item["content_chars"]) for item in document_summaries),
        "total_sections": sum(int(item["section_count"]) for item in document_summaries),
        "total_chunks": sum(int(item["chunk_count"]) for item in document_summaries),
        "documents": document_summaries,
        "limits": {
            "max_documents": MAX_KNOWLEDGE_BATCH_DOCUMENTS,
            "max_content_chars": MAX_KNOWLEDGE_BATCH_CONTENT_CHARS,
        },
    }


def _safe_leaf_name(raw: Any, *, fallback: str) -> str:
    cleaned = str(raw or "").strip().replace("\\", "/")
    leaf = PurePosixPath(cleaned).name.strip()
    if not leaf or leaf in {".", ".."}:
        leaf = fallback
    return leaf[:MAX_SAFE_NAME_CHARS]
