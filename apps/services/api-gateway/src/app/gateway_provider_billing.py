from __future__ import annotations

from typing import Any
from uuid import uuid4

from .db import to_json
from .gateway_runtime import gateway_db


def import_provider_billing_records(
    records: list[dict[str, Any]],
    *,
    imported_by_user_id: str,
) -> dict[str, Any]:
    normalized_records = [_normalize_record(item, imported_by_user_id=imported_by_user_id) for item in records]
    persisted_ids: list[str] = []
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            for record in normalized_records:
                cur.execute(
                    """
                    INSERT INTO provider_billing_records (
                        id, external_id, tenant_id, user_id, provider, model, route_key,
                        prompt_key, currency, billed_cost_cents, input_tokens, output_tokens,
                        billed_at, metadata_json, imported_by_user_id
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        COALESCE(NULLIF(%s, '')::timestamptz, NOW()), %s::jsonb, %s
                    )
                    ON CONFLICT (provider, external_id) WHERE external_id <> ''
                    DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        user_id = EXCLUDED.user_id,
                        model = EXCLUDED.model,
                        route_key = EXCLUDED.route_key,
                        prompt_key = EXCLUDED.prompt_key,
                        currency = EXCLUDED.currency,
                        billed_cost_cents = EXCLUDED.billed_cost_cents,
                        input_tokens = EXCLUDED.input_tokens,
                        output_tokens = EXCLUDED.output_tokens,
                        billed_at = EXCLUDED.billed_at,
                        metadata_json = EXCLUDED.metadata_json,
                        imported_by_user_id = EXCLUDED.imported_by_user_id,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        record["id"],
                        record["external_id"],
                        record["tenant_id"],
                        record["user_id"],
                        record["provider"],
                        record["model"],
                        record["route_key"],
                        record["prompt_key"],
                        record["currency"],
                        record["billed_cost_cents"],
                        record["input_tokens"],
                        record["output_tokens"],
                        record["billed_at"],
                        to_json(record["metadata"]),
                        imported_by_user_id,
                    ),
                )
                row = cur.fetchone() or {}
                persisted_ids.append(str(row.get("id") or record["id"]))
        conn.commit()
    return {
        "imported": len(normalized_records),
        "record_ids": persisted_ids,
    }


def _normalize_record(raw: dict[str, Any], *, imported_by_user_id: str) -> dict[str, Any]:
    provider = str(raw.get("provider") or "").strip()
    if not provider:
        raise ValueError("provider is required")
    return {
        "id": str(raw.get("id") or "").strip() or str(uuid4()),
        "external_id": str(raw.get("external_id") or "").strip(),
        "tenant_id": str(raw.get("tenant_id") or "").strip(),
        "user_id": str(raw.get("user_id") or "").strip() or imported_by_user_id,
        "provider": provider,
        "model": str(raw.get("model") or "").strip(),
        "route_key": str(raw.get("route_key") or "").strip(),
        "prompt_key": str(raw.get("prompt_key") or "").strip(),
        "currency": (str(raw.get("currency") or "CNY").strip().upper() or "CNY")[:16],
        "billed_cost_cents": max(int(raw.get("billed_cost_cents") or 0), 0),
        "input_tokens": max(int(raw.get("input_tokens") or 0), 0),
        "output_tokens": max(int(raw.get("output_tokens") or 0), 0),
        "billed_at": str(raw.get("billed_at") or "").strip(),
        "metadata": dict(raw.get("metadata") or {}),
    }
