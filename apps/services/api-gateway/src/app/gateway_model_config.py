from __future__ import annotations

import base64
import hashlib
import os
from typing import Any
from uuid import UUID, uuid4

from shared.api_errors import raise_api_error

from .gateway_runtime import gateway_db, logger


DEFAULT_COLUMNS = {
    "chat": "is_default_chat",
    "embedding": "is_default_embedding",
    "interview": "is_default_interview",
    "scoring": "is_default_scoring",
}

MODEL_STAGE_DEFINITIONS = [
    {
        "key": "query_intent",
        "name": "用户问题意图识别",
        "description": "判断语义、精确匹配、表格和图谱检索路径。",
        "order": 10,
        "builtin": False,
        "allowed_provider_types": [],
    },
    {
        "key": "query_rewrite",
        "name": "查询改写与 Multi-Query",
        "description": "扩展检索表达并生成 focus query。当前默认使用内置规则。",
        "order": 20,
        "builtin": True,
        "allowed_provider_types": [],
    },
    {
        "key": "embedding",
        "name": "向量化",
        "description": "为知识库文档和用户问题生成向量。",
        "order": 30,
        "builtin": False,
        "allowed_provider_types": [],
    },
    {
        "key": "hybrid_retrieval",
        "name": "混合召回",
        "description": "结构、全文、向量和精确词并行召回，系统内置。",
        "order": 40,
        "builtin": True,
        "allowed_provider_types": [],
    },
    {
        "key": "rerank",
        "name": "Cross-Encoder 精排",
        "description": "对混合召回候选进行外部精排；未配置时使用启发式排序。",
        "order": 50,
        "builtin": False,
        "allowed_provider_types": ["cross-encoder", "external-cross-encoder"],
    },
    {
        "key": "jev_intent",
        "name": "JEV 意图识别",
        "description": "用 JEV 判断用户问题的检索路由，失败时回退规则分类。",
        "order": 60,
        "builtin": False,
        "allowed_provider_types": ["jev"],
    },
    {
        "key": "jev_rerank",
        "name": "JEV Context 精排与门控",
        "description": "对精排后的证据进行相关性判断，过滤低相关 Context。",
        "order": 70,
        "builtin": False,
        "allowed_provider_types": ["jev"],
    },
    {
        "key": "generation",
        "name": "答案生成",
        "description": "基于证据生成最终回答、引用和安全结果。",
        "order": 80,
        "builtin": False,
        "allowed_provider_types": [],
    },
    {
        "key": "interview_scoring",
        "name": "面试评分",
        "description": "生成面试评价、维度分数和改进建议。",
        "order": 90,
        "builtin": False,
        "allowed_provider_types": [],
    },
]
MODEL_STAGE_DEFINITION_BY_KEY = {item["key"]: item for item in MODEL_STAGE_DEFINITIONS}


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
    extra = dict(row.get("extra_json") or {})
    available_models = extra.get("available_models")
    if not isinstance(available_models, list):
        available_models = []
    normalized_models = []
    for item in available_models:
        if isinstance(item, str) and item.strip():
            normalized_models.append({"id": item.strip(), "object": "model", "owned_by": "", "created": None})
        elif isinstance(item, dict) and str(item.get("id") or "").strip():
            normalized_models.append({
                "id": str(item.get("id") or "").strip(),
                "object": str(item.get("object") or "model"),
                "owned_by": str(item.get("owned_by") or ""),
                "created": item.get("created"),
            })
    legacy_model = str(row.get("model_name") or "").strip()
    if legacy_model and not any(item["id"] == legacy_model for item in normalized_models):
        normalized_models.insert(0, {"id": legacy_model, "object": "model", "owned_by": "", "created": None})
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
        "available_models": normalized_models,
        "extra": extra,
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
            cur.execute("UPDATE model_stage_bindings SET config_id = NULL, updated_at = NOW() WHERE config_id = %s", (config_id,))
        conn.commit()


def _runtime_model_config(row: dict[str, Any]) -> dict[str, Any]:
    extra = dict(row.get("extra_json") or {})
    return {
        "config_id": str(row.get("id") or ""),
        "name": str(row.get("name") or ""),
        "provider_type": str(row.get("provider_type") or ""),
        "base_url": str(row.get("base_url") or "").rstrip("/"),
        "api_key": decrypt_api_key(str(row.get("api_key_ciphertext") or "")),
        "model_name": str(row.get("stage_model_name") or row.get("model_name") or ""),
        "embedding_model": str(row.get("embedding_model") or ""),
        "temperature": float(row.get("temperature") or 0.0),
        "max_tokens": int(row.get("max_tokens") or 0),
        "timeout_seconds": float(row.get("timeout_seconds") or 0.0),
        "request_format": str(extra.get("request_format") or "chat_completions"),
        "extra": extra,
    }


def list_enabled_model_configs() -> list[dict[str, Any]]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM model_provider_configs WHERE enabled = TRUE ORDER BY updated_at DESC, created_at DESC")
            return [serialize_model_config(row) for row in cur.fetchall()]


def load_active_stage_configs() -> dict[str, dict[str, Any]]:
    try:
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT b.stage_key, b.model_name AS stage_model_name, c.*
                    FROM model_stage_bindings b
                    JOIN model_provider_configs c ON c.id = b.config_id AND c.enabled = TRUE
                    """
                )
                return {str(row["stage_key"]): _runtime_model_config(row) for row in cur.fetchall()}
    except Exception:
        # Migrations are applied lazily; preserve environment-only deployments.
        return {}


def get_model_stages() -> dict[str, Any]:
    configs = list_enabled_model_configs()
    bindings = load_active_stage_configs()
    stages: list[dict[str, Any]] = []
    for definition in MODEL_STAGE_DEFINITIONS:
        stage_key = str(definition["key"])
        active = bindings.get(stage_key)
        active_config_id = str(active.get("config_id") or "") if active else ""
        active_model_name = str(active.get("model_name") or "") if active else ""
        stages.append({
            **definition,
            "config_id": active_config_id,
            "model_name": active_model_name,
            "config": next((item for item in configs if item["id"] == active_config_id), None),
        })
    return {"stages": stages, "available_configs": configs}


def update_model_stages(*, bindings: dict[str, str | dict[str, Any] | None], user_id: str) -> dict[str, Any]:
    unknown = sorted(set(bindings) - set(MODEL_STAGE_DEFINITION_BY_KEY))
    if unknown:
        raise_api_error(400, "unsupported_model_stage", f"unsupported model stage: {unknown[0]}")
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            for stage_key, raw_binding in bindings.items():
                definition = MODEL_STAGE_DEFINITION_BY_KEY[stage_key]
                if isinstance(raw_binding, dict):
                    config_id = str(raw_binding.get("config_id") or "").strip() or None
                    model_name = str(raw_binding.get("model_name") or "").strip()
                else:
                    config_id = str(raw_binding).strip() if raw_binding else None
                    model_name = ""
                if definition["builtin"] and config_id:
                    raise_api_error(400, "builtin_model_stage", f"model stage is built-in: {stage_key}")
                if config_id:
                    try:
                        UUID(str(config_id))
                    except ValueError:
                        raise_api_error(400, "invalid_model_provider_config_id", "model provider configuration ID is invalid")
                    cur.execute("SELECT * FROM model_provider_configs WHERE id = %s AND enabled = TRUE", (config_id,))
                    row = cur.fetchone()
                    if row is None:
                        raise_api_error(400, "model_provider_config_unavailable", "only enabled model provider configurations can be bound")
                    allowed = list(definition["allowed_provider_types"])
                    provider_type = str(row.get("provider_type") or "").lower()
                    if allowed and provider_type not in allowed:
                        raise_api_error(400, "model_provider_type_not_allowed", f"provider type {provider_type} cannot be bound to {stage_key}")
                    available_models = dict(row.get("extra_json") or {}).get("available_models") or []
                    known_models = {
                        str(item.get("id") or "").strip() if isinstance(item, dict) else str(item).strip()
                        for item in available_models
                    }
                    legacy_model = str(row.get("model_name") or "").strip()
                    if legacy_model:
                        known_models.add(legacy_model)
                    if not model_name:
                        model_name = legacy_model
                    if not model_name or model_name not in known_models:
                        raise_api_error(400, "model_not_available", "model must be selected from the provider model catalog")
                cur.execute(
                    """
                    INSERT INTO model_stage_bindings(stage_key, config_id, model_name, updated_by, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (stage_key) DO UPDATE SET config_id = EXCLUDED.config_id, model_name = EXCLUDED.model_name, updated_by = EXCLUDED.updated_by, updated_at = NOW()
                    """,
                    (stage_key, config_id, model_name, user_id),
                )
        conn.commit()
    return get_model_stages()


def load_active_model_config(*, purpose: str = "chat") -> dict[str, Any] | None:
    stage_key = {"chat": "generation", "scoring": "interview_scoring", "interview": "interview_scoring", "embedding": "embedding"}.get(purpose)
    column = DEFAULT_COLUMNS.get(purpose, DEFAULT_COLUMNS["chat"])
    try:
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                if stage_key:
                    cur.execute(
                        """
                        SELECT b.model_name AS stage_model_name, c.* FROM model_stage_bindings b
                        JOIN model_provider_configs c ON c.id = b.config_id AND c.enabled = TRUE
                        WHERE b.stage_key = %s LIMIT 1
                        """,
                        (stage_key,),
                    )
                    row = cur.fetchone()
                    if row is not None:
                        selected_model = str(row.get("stage_model_name") or "").strip()
                        return {
                            **row,
                            "model_name": selected_model or str(row.get("model_name") or ""),
                            "api_key": decrypt_api_key(str(row.get("api_key_ciphertext") or "")),
                        }
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
