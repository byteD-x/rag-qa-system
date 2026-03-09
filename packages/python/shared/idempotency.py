from __future__ import annotations

import hashlib
import json


IDEMPOTENCY_HEADER = "Idempotency-Key"


def normalize_idempotency_key(value: str, *, max_length: int = 128) -> str:
    cleaned = "".join(ch for ch in (value or "").strip() if 32 <= ord(ch) <= 126)
    return cleaned[:max_length]


def build_request_hash(request_scope: str, payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(f"{request_scope}:{canonical}".encode("utf-8")).hexdigest()
