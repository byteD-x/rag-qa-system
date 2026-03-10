from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser

from .kb_connector_sync import ConnectorSyncCandidate, execute_connector_sync


URL_CONNECTOR_TYPES = {"web_crawler", "feishu_document", "dingtalk_document"}
DEFAULT_URL_CONNECTOR_MAX_URLS = 32


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._title_chunks: list[str] = []
        self._in_title = False

    @property
    def title(self) -> str:
        return " ".join(part.strip() for part in self._title_chunks if part.strip()).strip()

    @property
    def text(self) -> str:
        lines = [part.strip() for part in self._chunks if part.strip()]
        return "\n".join(lines).strip()

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        cleaned = tag.lower()
        if cleaned == "title":
            self._in_title = False
        if cleaned in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        text = unescape(str(data or "")).strip()
        if not text:
            return
        if self._in_title:
            self._title_chunks.append(text)
        self._chunks.append(text)


def _label_for_connector(connector_type: str) -> str:
    return {
        "web_crawler": "web crawler",
        "feishu_document": "feishu",
        "dingtalk_document": "dingtalk",
    }.get(connector_type, "url")


def _normalize_urls(urls: list[str], *, max_urls: int | None = None) -> list[str]:
    normalized: list[str] = []
    limit = max_urls if max_urls is not None else DEFAULT_URL_CONNECTOR_MAX_URLS
    for raw in urls:
        candidate = str(raw or "").strip()
        if not candidate:
            continue
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise_api_error(400, "url_connector_invalid_url", "connector urls must use http or https")
        normalized.append(candidate)
    normalized = list(dict.fromkeys(normalized))
    if not normalized:
        raise_api_error(400, "url_connector_empty", "connector urls must not be empty")
    if len(normalized) > limit:
        raise_api_error(400, "url_connector_too_many_urls", f"url connector matched more than {limit} urls")
    return normalized


def _resolve_auth_headers(header_name: str, header_value_env: str) -> dict[str, str]:
    name = str(header_name or "").strip()
    env_name = str(header_value_env or "").strip()
    if not name or not env_name:
        return {}
    header_value = os.getenv(env_name, "").strip()
    if not header_value:
        raise_api_error(503, "url_connector_auth_missing", f"connector auth env is missing: {env_name}")
    return {name: header_value}


def _slugify_filename(title: str, url: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", title.strip())[:80].strip("-")
    if not base:
        parsed = urlparse(url)
        base = re.sub(r"[^a-zA-Z0-9_-]+", "-", parsed.path.strip("/") or parsed.netloc)[:80].strip("-") or "web-page"
    return f"{base}.txt"


def _build_candidate(*, url: str, response: httpx.Response, connector_type: str) -> ConnectorSyncCandidate:
    content_type = str(response.headers.get("content-type") or "").lower()
    body = response.text
    title = ""
    text_body = body.strip()
    if "html" in content_type or "<html" in body.lower():
        parser = _HTMLTextExtractor()
        parser.feed(body)
        title = parser.title
        text_body = parser.text
    if not text_body.strip():
        raise_api_error(502, "url_connector_empty_body", "url connector fetched an empty response body")
    if not title:
        title = _slugify_filename("", url).removesuffix(".txt")
    rendered = f"# {title}\n\n{text_body.strip()}\n"
    encoded = rendered.encode("utf-8")
    return ConnectorSyncCandidate(
        file_name=_slugify_filename(title, url),
        file_type="txt",
        size_bytes=len(encoded),
        content_hash=hashlib.sha256(encoded).hexdigest(),
        source_uri=url,
        source_updated_at=datetime.now(timezone.utc),
        relative_path=title,
        content_bytes=encoded,
        source_metadata={
            "title": title,
            "url": url,
            "connector_type": connector_type,
            "content_type": content_type,
        },
        content_type="text/plain; charset=utf-8",
    )


def execute_url_sync(
    *,
    base_id: str,
    connector_type: str,
    urls: list[str],
    category: str,
    delete_missing: bool,
    dry_run: bool,
    max_urls: int | None,
    user: CurrentUser,
    db: Any,
    storage: Any,
    header_name: str = "",
    header_value_env: str = "",
    client_factory: Any = None,
) -> dict[str, Any]:
    normalized_urls = _normalize_urls(urls, max_urls=max_urls)
    headers = _resolve_auth_headers(header_name, header_value_env)
    factory = client_factory or (lambda: httpx.Client(timeout=httpx.Timeout(30.0), follow_redirects=True))
    candidates: list[ConnectorSyncCandidate] = []
    with factory() as client:
        for url in normalized_urls:
            response = client.get(url, headers=headers)
            if response.status_code >= 400:
                raise_api_error(502, "url_connector_upstream_error", f"url connector fetch failed for {url}")
            candidates.append(_build_candidate(url=url, response=response, connector_type=connector_type))
    return execute_connector_sync(
        base_id=base_id,
        source_type=connector_type,
        source_label=_label_for_connector(connector_type),
        source_path=",".join(normalized_urls),
        candidates=candidates,
        delete_missing=delete_missing,
        dry_run=dry_run,
        category=category,
        user=user,
        db=db,
        storage=storage,
        storage_service=f"kb-connector-{connector_type}",
        ignored_files=[],
        extra_result={"urls": normalized_urls},
    )

