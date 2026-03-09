from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from pydantic import BaseModel

from shared.api_errors import raise_api_error
from shared.auth import CurrentUser
from shared.idempotency import IDEMPOTENCY_HEADER, build_request_hash, normalize_idempotency_key

from .db import to_json
from .gateway_runtime import GATEWAY_IDEMPOTENCY_TOTAL, gateway_db, runtime_settings


@dataclass(frozen=True)
class IdempotencyState:
    key: str = ""
    request_scope: str = ""
    request_hash: str = ""
    replay_payload: dict[str, Any] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.key)


def _normalize_idempotency_payload(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, dict):
        return {str(key): _normalize_idempotency_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_idempotency_payload(item) for item in value]
    return value


def _idempotency_conflict(message: str) -> None:
    raise_api_error(409, "idempotency_conflict", message)


def begin_gateway_idempotency(
    request: Request,
    user: CurrentUser,
    *,
    request_scope: str,
    payload: dict[str, Any],
) -> IdempotencyState:
    key = normalize_idempotency_key(request.headers.get(IDEMPOTENCY_HEADER, ""))
    if not key:
        return IdempotencyState()

    request_hash = build_request_hash(request_scope, _normalize_idempotency_payload(payload))
    ttl_hours = runtime_settings.idempotency_ttl_hours
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gateway_idempotency_keys (
                    idempotency_key, request_scope, actor_user_id, request_hash, status, expires_at
                )
                VALUES (%s, %s, %s, %s, 'processing', NOW() + (%s || ' hours')::interval)
                ON CONFLICT DO NOTHING
                RETURNING idempotency_key
                """,
                (key, request_scope, user.user_id, request_hash, ttl_hours),
            )
            inserted = cur.fetchone() is not None
            if not inserted:
                cur.execute(
                    """
                    SELECT *
                    FROM gateway_idempotency_keys
                    WHERE idempotency_key = %s
                      AND request_scope = %s
                      AND actor_user_id = %s
                    """,
                    (key, request_scope, user.user_id),
                )
                row = cur.fetchone()
                if row is None:
                    _idempotency_conflict("idempotency state could not be resolved")
                if str(row.get("request_hash") or "") != request_hash:
                    GATEWAY_IDEMPOTENCY_TOTAL.labels("conflict", request_scope).inc()
                    _idempotency_conflict("idempotency key already used with a different request payload")
                status_value = str(row.get("status") or "")
                if status_value == "succeeded":
                    GATEWAY_IDEMPOTENCY_TOTAL.labels("replay", request_scope).inc()
                    return IdempotencyState(
                        key=key,
                        request_scope=request_scope,
                        request_hash=request_hash,
                        replay_payload=dict(row.get("response_json") or {}),
                    )
                if status_value == "processing":
                    GATEWAY_IDEMPOTENCY_TOTAL.labels("in_progress", request_scope).inc()
                    _idempotency_conflict("another request with the same idempotency key is still processing")
                cur.execute(
                    """
                    UPDATE gateway_idempotency_keys
                    SET status = 'processing',
                        response_json = '{}'::jsonb,
                        resource_id = '',
                        expires_at = NOW() + (%s || ' hours')::interval,
                        updated_at = NOW()
                    WHERE idempotency_key = %s
                      AND request_scope = %s
                      AND actor_user_id = %s
                    """,
                    (ttl_hours, key, request_scope, user.user_id),
                )
                GATEWAY_IDEMPOTENCY_TOTAL.labels("retry", request_scope).inc()
            else:
                GATEWAY_IDEMPOTENCY_TOTAL.labels("miss", request_scope).inc()
        conn.commit()
    return IdempotencyState(key=key, request_scope=request_scope, request_hash=request_hash)


def complete_gateway_idempotency(
    state: IdempotencyState,
    user: CurrentUser,
    *,
    response_payload: dict[str, Any],
    resource_id: str = "",
) -> None:
    if not state.enabled:
        return
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE gateway_idempotency_keys
                SET status = 'succeeded',
                    response_json = %s::jsonb,
                    resource_id = %s,
                    updated_at = NOW()
                WHERE idempotency_key = %s
                  AND request_scope = %s
                  AND actor_user_id = %s
                """,
                (to_json(response_payload), resource_id, state.key, state.request_scope, user.user_id),
            )
        conn.commit()
    GATEWAY_IDEMPOTENCY_TOTAL.labels("success", state.request_scope).inc()


def fail_gateway_idempotency(state: IdempotencyState, user: CurrentUser, exc: Exception) -> None:
    if not state.enabled:
        return
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", str(exc))
    payload = {"status_code": int(status_code), "detail": detail if isinstance(detail, (dict, list)) else str(detail)}
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE gateway_idempotency_keys
                SET status = 'failed',
                    response_json = %s::jsonb,
                    updated_at = NOW()
                WHERE idempotency_key = %s
                  AND request_scope = %s
                  AND actor_user_id = %s
                """,
                (to_json(payload), state.key, state.request_scope, user.user_id),
            )
        conn.commit()
    GATEWAY_IDEMPOTENCY_TOTAL.labels("failed", state.request_scope).inc()
