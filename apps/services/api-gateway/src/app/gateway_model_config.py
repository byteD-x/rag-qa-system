from __future__ import annotations

import base64
import hashlib
import os
from typing import Any
from uuid import uuid4

from shared.api_errors import raise_api_error

from .gateway_runtime import gateway_db, logger


DEFAULT_COLUMNS = {
    "chat": "is_default_chat",
    "embedding": "is_default_embedding",
    "interview": "is_default_interview",
    "scoring": "is_default_scoring",
}


def _fernet() -> Any:
    # Keep gateway startup compatible with deployments that have not installed
    # the optional model-configuration dependency yet. The dependency is only
    # needed when a provider secret is actually read or written.
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError("cryptography is required for model provider secret storage") from exc
    configured = os.getenv("MODEL_CONFIG_ENCRYPTION_KEY", "").strip()
    if configured:
        try:
            return Fernet(configured.encode("ascii"))
        except Exception as exc:
            raise RuntimeError("MODEL_CONFIG_ENCRYPTION_KEY must be a valid Fernet key") from exc
    # Compatibility fallback for local deployments; production deployments should
    # always provide a dedicated, rotated encryption key.
    seed = os.getenv("JWT_SECRET", "change-me-in-env").encode("utf-8")
    derived = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
    return Fernet(derived)


def encrypt_api_key(value: str) -> str:
    cleaned = str(value or "").strip()
    return _fernet().encrypt(cleaned.encode("utf-8")).decode("ascii") if cleaned else ""


def decrypt_api_key(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    try:
        from cryptography.fernet import InvalidToken

        return _fernet().decrypt(cleaned.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError):
        logger.warning("model provider api key could not be decrypted")
        return ""


def _timestamp(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def serialize_model_config(row: dict[str, Any]) -> dict[str, Any]:
    encrypted = str(row.get("api_key_ciphertext") or "")
    decrypted = decrypt_api_key(encrypted)
    return {
        "id": str(row.get("id") or ""),
        "name": str(row.get("name") or ""),
        "provider_type": str(row.get("provider_type") or ""),
        "base_url": str(row.get("base_url") or ""),
        "model_name": str(row.get("model_name") or ""),
        "embedding_model": str(row.get("embedding_model") or ""),
        "temperature": float(row.get("temperature") or 0.0),
        "max_tokens": int(row.get("max_tokens") or 0),
        "timeout_seconds": float(row.get("timeout_seconds") or 0.0),
        "proxy_url": str(row.get("proxy_url") or ""),
        "enabled": bool(row.get("enabled")),
        "default_purposes": [purpose for purpose, column in DEFAULT_COLUMNS.items() if bool(row.get(column))],
        "api_key_configured": bool(decrypted),
        "api_key_hint": f"***{decrypted[-4:]}" if decrypted else "",
        "extra": dict(row.get("extra_json") or {}),
        "created_by": str(row.get("created_by") or ""),
        "created_at": _timestamp(row.get("created_at")),
        "updated_at": _timestamp(row.get("updated_at")),
    }


def list_model_configs() -> list[dict[str, Any]]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM model_provider_configs ORDER BY created_at DESC")
            return [serialize_model_config(row) for row in cur.fetchall()]


def load_model_config(config_id: str, *, include_secret: bool = False) -> dict[str, Any]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM model_provider_configs WHERE id = %s", (config_id,))
            row = cur.fetchone()
    if row is None:
        raise_api_error(404, "model_provider_config_not_found", "model provider configuration not found")
    if include_secret:
        return {**row, "api_key": decrypt_api_key(str(row.get("api_key_ciphertext") or ""))}
    return serialize_model_config(row)


def _set_defaults(cur, *, config_id: str, purposes: list[str]) -> None:
    for column in DEFAULT_COLUMNS.values():
        cur.execute(f"UPDATE model_provider_configs SET {column} = FALSE WHERE id <> %s", (config_id,))
        cur.execute(f"UPDATE model_provider_configs SET {column} = FALSE WHERE id = %s", (config_id,))
    for purpose in purposes:
        cur.execute(f"UPDATE model_provider_configs SET {DEFAULT_COLUMNS[purpose]} = TRUE WHERE id = %s", (config_id,))


def create_model_config(*, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
    config_id = str(uuid4())
    purposes = list(payload.get("default_purposes") or [])
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_provider_configs (
                    id, name, provider_type, api_key_ciphertext, base_url, model_name,
                    embedding_model, temperature, max_tokens, timeout_seconds, proxy_url,
                    enabled, extra_json, created_by
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (name) DO NOTHING
                RETURNING *
                """,
                (
                    config_id,
                    payload["name"],
                    payload["provider_type"],
                    encrypt_api_key(payload.get("api_key", "")),
                    payload.get("base_url", ""),
                    payload.get("model_name", ""),
                    payload.get("embedding_model", ""),
                    payload.get("temperature", 0.7),
                    payload.get("max_tokens", 2048),
                    payload.get("timeout_seconds", 120),
                    payload.get("proxy_url", ""),
                    bool(payload.get("enabled", True)),
                    _json(payload.get("extra") or {}),
                    user_id,
                ),
            )
            row = cur.fetchone()
            if row is None:
                raise_api_error(409, "model_provider_config_exists", "model provider configuration name already exists")
            if purposes:
                _set_defaults(cur, config_id=config_id, purposes=purposes)
        conn.commit()
    return load_model_config(config_id)


def update_model_config(config_id: str, *, payload: dict[str, Any]) -> dict[str, Any]:
    current = load_model_config(config_id, include_secret=True)
    values = {
        "name": payload.get("name") if payload.get("name") is not None else current["name"],
        "provider_type": payload.get("provider_type") if payload.get("provider_type") is not None else current["provider_type"],
        "base_url": payload.get("base_url") if payload.get("base_url") is not None else current["base_url"],
        "model_name": payload.get("model_name") if payload.get("model_name") is not None else current["model_name"],
        "embedding_model": payload.get("embedding_model") if payload.get("embedding_model") is not None else current["embedding_model"],
        "temperature": payload.get("temperature") if payload.get("temperature") is not None else current["temperature"],
        "max_tokens": payload.get("max_tokens") if payload.get("max_tokens") is not None else current["max_tokens"],
        "timeout_seconds": payload.get("timeout_seconds") if payload.get("timeout_seconds") is not None else current["timeout_seconds"],
        "proxy_url": payload.get("proxy_url") if payload.get("proxy_url") is not None else current["proxy_url"],
        "enabled": payload.get("enabled") if payload.get("enabled") is not None else current["enabled"],
        "extra": payload.get("extra") if payload.get("extra") is not None else current.get("extra_json", {}),
    }
    api_key = payload.get("api_key") if payload.get("api_key") not in (None, "") else current.get("api_key", "")
    purposes = payload.get("default_purposes")
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE model_provider_configs
                SET name = %s, provider_type = %s, api_key_ciphertext = %s,
                    base_url = %s, model_name = %s, embedding_model = %s,
                    temperature = %s, max_tokens = %s, timeout_seconds = %s,
                    proxy_url = %s, enabled = %s, extra_json = %s::jsonb, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (values["name"], values["provider_type"], encrypt_api_key(api_key), values["base_url"], values["model_name"], values["embedding_model"], values["temperature"], values["max_tokens"], values["timeout_seconds"], values["proxy_url"], values["enabled"], _json(values["extra"]), config_id),
            )
            row = cur.fetchone()
            if row is None:
                raise_api_error(404, "model_provider_config_not_found", "model provider configuration not found")
            if purposes is not None:
                _set_defaults(cur, config_id=config_id, purposes=list(purposes))
        conn.commit()
    return load_model_config(config_id)


def disable_model_config(config_id: str) -> None:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE model_provider_configs SET enabled = FALSE, is_default_chat = FALSE, is_default_embedding = FALSE, is_default_interview = FALSE, is_default_scoring = FALSE, updated_at = NOW() WHERE id = %s", (config_id,))
            if cur.rowcount == 0:
                raise_api_error(404, "model_provider_config_not_found", "model provider configuration not found")
        conn.commit()


def load_active_model_config(*, purpose: str = "chat") -> dict[str, Any] | None:
    column = DEFAULT_COLUMNS.get(purpose, DEFAULT_COLUMNS["chat"])
    try:
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM model_provider_configs WHERE enabled = TRUE AND {column} = TRUE ORDER BY updated_at DESC LIMIT 1")
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT * FROM model_provider_configs WHERE enabled = TRUE ORDER BY updated_at DESC LIMIT 1")
                    row = cur.fetchone()
    except Exception:
        # Keep existing environment-only deployments fully compatible until the
        # gateway migration has been applied.
        return None
    if row is None:
        return None
    return {**row, "api_key": decrypt_api_key(str(row.get("api_key_ciphertext") or ""))}


def _json(value: Any) -> str:
    import json

    return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False)
