from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Any, Protocol

from .db import to_json
from .gateway_runtime import gateway_db


class HandoffQueueBackend(Protocol):
    def claim_next(self, *, tenant_id: str, skill_group: str, operator_id: str) -> dict[str, Any] | None:
        """为坐席原子认领下一条待接管会话。"""


def _handoff_payload(row: dict[str, Any]) -> dict[str, Any]:
    return dict((dict(row.get("scope_json") or {}).get("handoff") or {}))


def _normalize_skill_group(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _priority_value(row: dict[str, Any]) -> float:
    raw = _handoff_payload(row).get("priority", 0)
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _requested_at_value(row: dict[str, Any]) -> str:
    handoff = _handoff_payload(row)
    return str(handoff.get("requested_at") or row.get("created_at") or row.get("updated_at") or "")


def _stable_session_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or "")


def _candidate_sort_key(row: dict[str, Any]) -> tuple[float, str, str]:
    return (-_priority_value(row), _requested_at_value(row), _stable_session_id(row))


def serialize_handoff_session(row: dict[str, Any]) -> dict[str, Any]:
    scope = dict(row.get("scope_json") or {})
    return {
        "id": str(row.get("id") or ""),
        "session_id": str(row.get("id") or ""),
        "user_id": str(row.get("user_id") or ""),
        "title": str(row.get("title") or ""),
        "scope": scope,
        "handoff": dict(scope.get("handoff") or {}),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


class LocalSessionHandoffQueueBackend:
    """基于 chat_sessions.scope_json 的本地进程内安全接管队列。"""

    def __init__(self, *, db: Any | None = None, lock: RLock | None = None) -> None:
        self._db = db or gateway_db
        self._lock = lock or RLock()

    def claim_next(self, *, tenant_id: str, skill_group: str, operator_id: str) -> dict[str, Any] | None:
        normalized_tenant_id = str(tenant_id or "").strip()
        normalized_skill_group = _normalize_skill_group(skill_group)
        normalized_operator_id = str(operator_id or "").strip()
        if not normalized_tenant_id or not normalized_skill_group or not normalized_operator_id:
            return None

        with self._lock:
            with self._db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT *
                        FROM chat_sessions
                        WHERE COALESCE(scope_json #>> '{handoff,status}', '') = 'pending'
                          AND COALESCE(scope_json #>> '{handoff,tenant_id}', '') = %s
                        """,
                        (normalized_tenant_id,),
                    )
                    rows = cur.fetchall()

                    candidates = [
                        row
                        for row in rows
                        if _normalize_skill_group(str(_handoff_payload(row).get("skill_group") or "")) == normalized_skill_group
                    ]
                    for candidate in sorted(candidates, key=_candidate_sort_key):
                        claimed = self._claim_candidate(
                            cur,
                            candidate=candidate,
                            tenant_id=normalized_tenant_id,
                            skill_group=normalized_skill_group,
                            operator_id=normalized_operator_id,
                        )
                        if claimed is not None:
                            conn.commit()
                            return serialize_handoff_session(claimed)
                conn.commit()
        return None

    def _claim_candidate(
        self,
        cur: Any,
        *,
        candidate: dict[str, Any],
        tenant_id: str,
        skill_group: str,
        operator_id: str,
    ) -> dict[str, Any] | None:
        scope = dict(candidate.get("scope_json") or {})
        handoff = dict(scope.get("handoff") or {})
        handoff.update(
            {
                "status": "claimed",
                "tenant_id": tenant_id,
                "skill_group": skill_group,
                "claimed_by": operator_id,
                "claimed_at": datetime.now(timezone.utc).isoformat(),
                "claim_backend": "local_session_scope",
            }
        )
        scope["handoff"] = handoff
        cur.execute(
            """
            UPDATE chat_sessions
            SET scope_json = %s::jsonb,
                updated_at = NOW()
            WHERE id = %s
              AND COALESCE(scope_json #>> '{handoff,status}', '') = 'pending'
              AND COALESCE(scope_json #>> '{handoff,tenant_id}', '') = %s
              AND trim(both '_' from lower(replace(COALESCE(scope_json #>> '{handoff,skill_group}', ''), ' ', '_'))) = %s
            RETURNING *
            """,
            (to_json(scope), str(candidate.get("id") or ""), tenant_id, skill_group),
        )
        return cur.fetchone()


local_handoff_queue = LocalSessionHandoffQueueBackend()
