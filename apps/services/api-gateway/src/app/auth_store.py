from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from shared.auth import AuthUser, normalize_role, permissions_for_role

from .gateway_runtime import gateway_db


RESET_TOKEN_TTL_MINUTES = 30


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180_000)
    return f"pbkdf2_sha256$180000${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def _user_from_row(row: dict[str, object]) -> AuthUser:
    role = normalize_role(str(row.get("role") or "kb_editor"))
    return AuthUser(
        user_id=str(row.get("id") or ""),
        email=str(row.get("email") or "").lower(),
        role=role,
        permissions=permissions_for_role(role),
        department=str(row.get("department") or ""),
    )


def find_user(email: str) -> tuple[AuthUser, str] | None:
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM auth_users WHERE email = %s AND is_active = TRUE", (email.strip().lower(),))
            row = cur.fetchone()
    if not row:
        return None
    return _user_from_row(row), str(row.get("password_hash") or "")


def create_user(*, email: str, password: str, role: str = "kb_editor", department: str = "") -> AuthUser:
    normalized_email = email.strip().lower()
    user = AuthUser(
        user_id=str(uuid4()),
        email=normalized_email,
        role=normalize_role(role),
        permissions=permissions_for_role(role),
        department=department.strip(),
    )
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth_users (id, email, password_hash, role, department)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
                """,
                (user.user_id, user.email, _hash_password(password), user.role, user.department),
            )
            row = cur.fetchone()
        conn.commit()
    return _user_from_row(row or {})


def authenticate_user(email: str, password: str) -> AuthUser | None:
    found = find_user(email)
    if not found:
        return None
    user, password_hash = found
    return user if _verify_password(password, password_hash) else None


def request_password_reset(email: str) -> str | None:
    found = find_user(email)
    if not found:
        return None
    user, _ = found
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE auth_password_reset_tokens SET used_at = NOW() WHERE user_id = %s AND used_at IS NULL", (user.user_id,))
            cur.execute(
                "INSERT INTO auth_password_reset_tokens (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (token_hash, user.user_id, expires_at),
            )
        conn.commit()
    return raw_token


def deliver_password_reset(*, email: str, token: str) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        raise RuntimeError("password reset email delivery is not configured")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip() or username
    app_url = os.getenv("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")
    message = EmailMessage()
    message["Subject"] = "RAG-QA 密码重置"
    message["From"] = sender
    message["To"] = email.strip().lower()
    message.set_content(f"请在 30 分钟内使用以下重置令牌：{token}\n\n打开 {app_url}/password-reset 完成密码更新。")
    with smtplib.SMTP(host, port, timeout=10) as client:
        client.starttls()
        if username:
            client.login(username, password)
        client.send_message(message)


def reset_password(token: str, password: str) -> AuthUser | None:
    token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    with gateway_db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.*
                FROM auth_password_reset_tokens t
                JOIN auth_users u ON u.id = t.user_id
                WHERE t.token_hash = %s AND t.used_at IS NULL AND t.expires_at > NOW() AND u.is_active = TRUE
                FOR UPDATE
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("UPDATE auth_users SET password_hash = %s, updated_at = NOW() WHERE id = %s", (_hash_password(password), row["id"]))
            cur.execute("UPDATE auth_password_reset_tokens SET used_at = NOW() WHERE token_hash = %s", (token_hash,))
        conn.commit()
    return _user_from_row(row)
