"""多轮对话状态与长期记忆服务。

记忆与知识库证据分开管理：记忆描述用户、任务和历史决定，知识库证据仍然是回答事实的主依据。
本模块使用 PostgreSQL 做可解释的混合检索，后续可在不改变调用契约的情况下替换为向量索引。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .db import to_json
from .gateway_runtime import gateway_db, logger


_TEMPORAL_RE = re.compile(r"(当前|现在|目前|最新|之前|以后|上周|本周|今天|昨天|明天|\d{4}[-年/]\d{1,2})")
_REFERENCE_RE = re.compile(r"^(那|这个|这个问题|上面|上一条|刚才|它|他们|继续|还有|然后|再说)")
_PREFERENCE_RE = re.compile(r"(?:我|用户)(?:比较|更|喜欢|偏好|习惯)(?P<object>[^，。；;\n]{1,80})")
_ROLE_RE = re.compile(r"(?:我|用户)(?:是|负责|在)(?P<object>[^，。；;\n]{1,80})")
_DECISION_RE = re.compile(r"(?:决定|确定|采用|选择|改为|使用)(?P<object>[^，。；;\n]{1,100})")
_TASK_RE = re.compile(r"(?:需要|要|正在|继续|完成|处理)(?P<object>[^，。；;\n]{2,100})")
_CONFIRMED_DECISION_RE = re.compile(r"(?:已确认|已决定|最终采用|我们采用|可以按|确认使用)(?P<object>[^，。；;\n]{2,100})")


@dataclass(frozen=True)
class MemoryHit:
    id: str
    memory_type: str
    subject: str
    predicate: str
    object: str
    summary: str
    confidence: float
    importance: float
    score: float
    scope_type: str
    valid_to: str = ""
    status: str = "active"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_type": self.memory_type,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "summary": self.summary,
            "confidence": self.confidence,
            "importance": self.importance,
            "score": self.score,
            "scope_type": self.scope_type,
            "valid_to": self.valid_to,
            "status": self.status,
        }


def contextualize_question(question: str, history: list[dict[str, Any]], summary: str = "") -> str:
    """把代词式追问规范化为可独立检索的问题，只提取摘要主题避免污染检索词。"""
    cleaned = str(question or "").strip()
    if not cleaned:
        return cleaned
    previous_users = [str(item.get("content") or item.get("question") or "").strip() for item in history if str(item.get("role") or "") == "user"]
    previous_users = [item for item in previous_users if item]
    if _REFERENCE_RE.search(cleaned) and previous_users:
        cleaned = f"{previous_users[-1]}\n当前追问：{cleaned}"
    if summary and len(cleaned) < 80 and not _TEMPORAL_RE.search(cleaned):
        topic_terms = _summary_topic_terms(summary)
        if topic_terms:
            return f"{topic_terms}\n当前问题：{cleaned}"
    return cleaned


def _summary_topic_terms(summary: str) -> str:
    chunks = [item.strip() for item in str(summary or "").splitlines() if item.strip()][-3:]
    terms: list[str] = []
    for chunk in chunks:
        terms.extend(re.findall(r"[A-Za-z0-9_./:-]{2,}|[\u4e00-\u9fff]{2,8}", chunk))
    return " ".join(dict.fromkeys(terms)[-12:])


def load_conversation_context(session_id: str, user_id: str) -> dict[str, Any]:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT conversation_summary, conversation_state_json, summary_version, summary_updated_at FROM chat_sessions WHERE id = %s AND user_id = %s",
                (session_id, user_id),
            )
            row = cur.fetchone() or {}
    return {
        "summary": str(row.get("conversation_summary") or ""),
        "state": dict(row.get("conversation_state_json") or {}),
        "summary_version": int(row.get("summary_version") or 1),
        "summary_updated_at": row.get("summary_updated_at"),
    }


def _memory_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "").strip()
        for key in ("memory_type", "subject", "predicate", "object", "summary", "evidence_quote")
    ).strip()


def _tokenize(text: str) -> set[str]:
    return {item for item in re.findall(r"[\w一-龥][\w一-龥.-]{1,}", text.lower()) if len(item) > 1}


def search_memories(*, user_id: str, query: str, session_id: str = "", limit: int = 6) -> list[dict[str, Any]]:
    query_terms = _tokenize(query)
    patterns = [f"%{term}%" for term in sorted(query_terms)[:8]] or ["%"]
    now = datetime.now(timezone.utc)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM agent_memory_entries
                WHERE user_id = %s
                  AND is_active = TRUE
                  AND status = 'active'
                  AND (expires_at IS NULL OR expires_at > NOW())
                  AND (valid_from IS NULL OR valid_from <= NOW())
                  AND (valid_to IS NULL OR valid_to >= NOW())
                  AND (scope_type <> 'session' OR scope_id = %s)
                  AND (subject ILIKE ANY(%s) OR predicate ILIKE ANY(%s) OR object ILIKE ANY(%s) OR summary ILIKE ANY(%s))
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (user_id, session_id, patterns, patterns, patterns, patterns, max(limit * 4, 12)),
            )
            rows = cur.fetchall()
    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        text = _memory_text(row)
        overlap = len(query_terms.intersection(_tokenize(text))) / max(len(query_terms), 1)
        exact = 0.25 if query.strip() and query.strip().lower() in text.lower() else 0.0
        recency = 0.1 if str(row.get("updated_at") or "")[:10] == now.date().isoformat() else 0.0
        temporal = 0.1 if _TEMPORAL_RE.search(query) and row.get("valid_to") else 0.0
        score = overlap * 0.55 + float(row.get("confidence") or 0.0) * 0.2 + float(row.get("importance") or 0.5) * 0.15 + exact + recency + temporal
        ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked:
        ids = [str(row.get("id")) for _score, row in ranked[:limit]]
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE agent_memory_entries SET access_count = access_count + 1, last_accessed_at = NOW() WHERE id = ANY(%s::uuid[]) AND user_id = %s",
                    (ids, user_id),
                )
            conn.commit()
    output: list[dict[str, Any]] = []
    for score, row in ranked[:limit]:
        output.append(
            MemoryHit(
                id=str(row.get("id") or ""),
                memory_type=str(row.get("memory_type") or "fact"),
                subject=str(row.get("subject") or ""),
                predicate=str(row.get("predicate") or ""),
                object=str(row.get("object") or ""),
                summary=str(row.get("summary") or ""),
                confidence=float(row.get("confidence") or 0.0),
                importance=float(row.get("importance") or 0.5),
                score=round(score, 6),
                scope_type=str(row.get("scope_type") or "user"),
                valid_to=str(row.get("valid_to") or ""),
                status=str(row.get("status") or "active"),
            ).as_dict()
        )
    return output


def memory_prompt_block(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = ["用户记忆（仅用于个性化和理解上下文，不可替代知识库证据）："]
    for index, item in enumerate(memories, start=1):
        statement = str(item.get("summary") or "").strip() or " ".join(
            str(item.get(key) or "").strip() for key in ("subject", "predicate", "object")
        ).strip()
        if statement:
            lines.append(f"- M{index}: {statement}")
    return "\n".join(lines)


def _extract_candidates(question: str, answer: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for pattern, memory_type, predicate in (
        (_PREFERENCE_RE, "preference", "偏好"),
        (_ROLE_RE, "fact", "身份或职责"),
        (_DECISION_RE, "decision", "决定"),
        (_TASK_RE, "task", "任务"),
    ):
        match = pattern.search(str(question or ""))
        if not match:
            continue
        value = str(match.group("object") or "").strip(" ，。；;\n")
        if len(value) < 2:
            continue
        candidates.append({"memory_type": memory_type, "subject": "用户", "predicate": predicate, "object": value, "summary": f"用户{predicate}：{value}"})
    answer_match = _CONFIRMED_DECISION_RE.search(str(answer or ""))
    if answer_match:
        value = str(answer_match.group("object") or "").strip(" ，。；;\n")
        if len(value) >= 2:
            candidates.append({"memory_type": "decision", "subject": "用户", "predicate": "已确认决定", "object": value, "summary": f"用户已确认决定：{value}"})
    return candidates


def _candidate_entity_keys(candidate: dict[str, Any]) -> list[str]:
    text = f"{candidate.get('subject') or ''} {candidate.get('object') or ''}"
    terms = re.findall(r"[A-Za-z][A-Za-z0-9_.:/-]{1,}|[\u4e00-\u9fff]{2,8}", text)
    return list(dict.fromkeys(terms))[:8]


def _candidate_temporal_fields(candidate: dict[str, Any], question: str) -> dict[str, datetime | None]:
    text = f"{question} {candidate.get('object') or ''}"
    now = datetime.now(timezone.utc)
    fields: dict[str, datetime | None] = {"valid_from": None, "valid_to": None, "expires_at": None}
    if re.search(r"(以后|之后|当前|现在|目前|最新|本周|今天)", text):
        fields["valid_from"] = now
    if re.search(r"(之前|上周|昨天|历史)", text):
        fields["valid_to"] = now
    if candidate.get("memory_type") == "task" and re.search(r"(今天|本周|正在|继续)", text):
        fields["expires_at"] = now + timedelta(days=30)
    return fields


def extract_and_store_memories(*, user_id: str, session_id: str, question: str, answer: str, message_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """执行低成本、可解释的记忆抽取；后续可由 LLM extractor 替换候选生成。"""
    candidates = _extract_candidates(question, answer)
    stored: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate["object"] = str(candidate.get("object") or "").strip()[:240]
        candidate["summary"] = str(candidate.get("summary") or "").strip()[:320]
        entity_keys = _candidate_entity_keys(candidate)
        temporal = _candidate_temporal_fields(candidate, question)
        with gateway_db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM agent_memory_entries
                    WHERE user_id = %s AND subject = %s AND predicate = %s AND is_active = TRUE AND status = 'active'
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (user_id, candidate["subject"], candidate["predicate"]),
                )
                existing = cur.fetchone()
                same_object = bool(existing and str(existing.get("object") or "").strip() == candidate["object"])
                supersedes_id = ""
                if existing and not same_object:
                    supersedes_id = str(existing.get("id") or "")
                    cur.execute(
                        "UPDATE agent_memory_entries SET status = 'superseded', is_active = FALSE, updated_at = NOW() WHERE id = %s",
                        (existing["id"],),
                    )
                    existing = None
                if existing:
                    cur.execute(
                        """
                        UPDATE agent_memory_entries
                        SET confidence = LEAST(confidence + 0.03, 1.0),
                            importance = LEAST(importance + 0.02, 1.0),
                            summary = %s,
                            evidence_quote = %s,
                            source_message_ids_json = %s::jsonb,
                            entity_keys_json = %s::jsonb,
                            valid_from = COALESCE(%s, valid_from),
                            valid_to = COALESCE(%s, valid_to),
                            expires_at = COALESCE(%s, expires_at),
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (candidate["summary"], question[:500], to_json(message_ids or []), to_json(entity_keys), temporal["valid_from"], temporal["valid_to"], temporal["expires_at"], existing["id"]),
                    )
                    row = cur.fetchone()
                else:
                    memory_id = str(uuid4())
                    cur.execute(
                        """
                        INSERT INTO agent_memory_entries (id, user_id, memory_type, subject, predicate, object, summary, confidence, importance, source_session_id, source_message_ids_json, entity_keys_json, scope_type, scope_id, evidence_quote, valid_from, valid_to, expires_at, supersedes_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, 'user', %s, %s, %s, %s, %s, NULLIF(%s, '')::uuid)
                        RETURNING *
                        """,
                        (memory_id, user_id, candidate["memory_type"], candidate["subject"], candidate["predicate"], candidate["object"], candidate["summary"], 0.72, 0.5, session_id, to_json(message_ids or []), to_json(entity_keys), user_id, question[:500], temporal["valid_from"], temporal["valid_to"], temporal["expires_at"], supersedes_id),
                    )
                    row = cur.fetchone()
            conn.commit()
        stored.append({"id": str(row.get("id") or ""), "memory_type": str(row.get("memory_type") or ""), "summary": str(row.get("summary") or "")})
    return stored


def update_conversation_context(*, session_id: str, user_id: str, question: str, answer: str, current_summary: str, current_state: dict[str, Any]) -> dict[str, Any]:
    """更新滚动摘要和结构化状态，避免每轮把完整历史送给模型。"""
    summary_line = f"用户：{question.strip()}\n助手：{answer.strip()[:800]}"
    summary_parts = [part for part in (current_summary.strip(), summary_line) if part]
    summary = "\n".join(summary_parts)[-4000:]
    state = dict(current_state or {})
    state["last_question"] = question.strip()[:500]
    state["last_answer"] = answer.strip()[:800]
    state["open_tasks"] = [item for item in list(state.get("open_tasks") or []) if item][:8]
    task_match = _TASK_RE.search(question)
    if task_match:
        task = str(task_match.group("object") or "").strip(" ，。；;\n")[:240]
        if task and task not in state["open_tasks"]:
            state["open_tasks"].append(task)
            state["open_tasks"] = state["open_tasks"][-8:]
    state["updated_at"] = time.time()
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_sessions
                SET conversation_summary = %s, conversation_state_json = %s::jsonb,
                    summary_version = summary_version + 1, summary_updated_at = NOW(), updated_at = NOW()
                WHERE id = %s AND user_id = %s
                RETURNING summary_version, summary_updated_at
                """,
                (summary, to_json(state), session_id, user_id),
            )
            version_row = cur.fetchone() or {}
        conn.commit()
    return {"summary": summary, "state": state, "summary_version": int(version_row.get("summary_version") or 1), "summary_updated_at": version_row.get("summary_updated_at")}


__all__ = [
    "contextualize_question",
    "extract_and_store_memories",
    "load_conversation_context",
    "memory_prompt_block",
    "search_memories",
    "update_conversation_context",
]
