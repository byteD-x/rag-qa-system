from __future__ import annotations

import codecs
from pathlib import Path


def detect_text_encoding_from_bytes(sample: bytes) -> str:
    if not sample:
        return "utf-8"
    if sample.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if sample.startswith(codecs.BOM_UTF16_LE) or sample.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"

    null_ratio = sample.count(b"\x00") / float(len(sample))
    if null_ratio >= 0.2:
        try:
            sample.decode("utf-16")
            return "utf-16"
        except UnicodeError:
            pass

    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            sample.decode(encoding)
            return encoding
        except UnicodeError:
            continue
    return "utf-8"


def detect_text_encoding(path: Path) -> str:
    with path.open("rb") as handle:
        sample = handle.read(65536)
    return detect_text_encoding_from_bytes(sample)


def read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    encoding = detect_text_encoding_from_bytes(raw[:65536])
    return raw.decode(encoding, errors="replace")
