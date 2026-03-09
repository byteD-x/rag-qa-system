from __future__ import annotations

from fastapi import Request


def sanitize_headers(headers: Request, *, hop_by_hop_headers: set[str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.headers.items()
        if key.lower() not in hop_by_hop_headers
    }
