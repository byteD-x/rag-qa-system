from __future__ import annotations

from pathlib import Path
from typing import List

from docx import Document as DocxDocument
from pypdf import PdfReader

from worker.chunking import ParsedSegment


def parse_document(file_path: Path, file_type: str) -> List[ParsedSegment]:
    normalized = file_type.lower().strip()
    if normalized == "txt":
        return _parse_txt(file_path)
    if normalized == "pdf":
        return _parse_pdf(file_path)
    if normalized == "docx":
        return _parse_docx(file_path)
    raise ValueError(f"unsupported file_type: {file_type}")


def _parse_txt(file_path: Path) -> List[ParsedSegment]:
    raw = file_path.read_text(encoding="utf-8-sig", errors="ignore")
    if not raw.strip():
        return []
    return [ParsedSegment(text=raw, page_or_loc="text:1")]


def _parse_pdf(file_path: Path) -> List[ParsedSegment]:
    reader = PdfReader(str(file_path))
    segments: List[ParsedSegment] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            segments.append(ParsedSegment(text=text, page_or_loc=f"page:{idx}"))
    return segments


def _parse_docx(file_path: Path) -> List[ParsedSegment]:
    doc = DocxDocument(str(file_path))
    segments: List[ParsedSegment] = []
    for idx, para in enumerate(doc.paragraphs, start=1):
        text = para.text.strip()
        if text:
            segments.append(ParsedSegment(text=text, page_or_loc=f"paragraph:{idx}"))
    return segments