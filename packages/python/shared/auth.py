from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status

DEFAULT_JWT_SECRET = "change-me-in-env"
DEFAULT_ADMIN_EMAIL = "admin@local"
DEFAULT_MEMBER_EMAIL = "member@local"
DEFAULT_LOCAL_PASSWORD = "ChangeMe123!"
LOCAL_RUNTIME_NAMES = {"dev", "development", "local", "test"}
ROLE_VERSION = 1

ROLE_ALIASES = {
    "admin": "platform_admin",
    "member": "kb_editor",
}
ROLE_PERMISSIONS = {
    "platform_admin": (
        "kb.read",
        "kb.write",
        "kb.manage",
        "chat.use",
        "audit.read",
    ),
    "kb_admin": (
        "kb.read",
        "kb.write",
        "kb.manage",
        "chat.use",
    ),
    "kb_editor": (
        "kb.read",
        "kb.write",
        "chat.use",
    ),
    "kb_viewer": (
        "kb.read",
        "chat.use",
    ),
    "audit_viewer": (
        "audit.read",
    ),
}


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str
    role: str
    permissions: tuple[str, ...] = ()
    role_version: int = ROLE_VERSION


def normalize_role(role: str) -> str:
    cleaned = str(role or "").strip().lower() or "kb_editor"
    canonical = ROLE_ALIASES.get(cleaned, cleaned)
    if canonical not in ROLE_PERMISSIONS:
        return "kb_editor"
    return canonical


def permissions_for_role(role: str) -> tuple[str, ...]:
    return tuple(ROLE_PERMISSIONS[normalize_role(role)])


def has_permission(user: AuthUser, permission: str) -> bool:
    required = str(permission or "").strip().lower()
    return bool(required) and required in {item.lower() for item in user.permissions}


def has_any_permission(user: AuthUser, permissions: list[str] | tuple[str, ...]) -> bool:
    return any(has_permission(user, item) for item in permissions)


def serialize_user(user: AuthUser) -> dict[str, Any]:
    return {
        "id": user.user_id,
        "email": user.email,
        "role": user.role,
        "permissions": list(user.permissions),
        "role_version": user.role_version,
    }


def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET", DEFAULT_JWT_SECRET).strip() or DEFAULT_JWT_SECRET


def _runtime_mode() -> str:
    for name in ("APP_ENV", "ENVIRONMENT", "RUNTIME_ENV"):
        raw = os.getenv(name)
        if raw and raw.strip():
            return raw.strip().lower()
    return "development"


def _is_local_runtime() -> bool:
    return _runtime_mode() in LOCAL_RUNTIME_NAMES


def _jwt_ttl_minutes() -> int:
    raw = os.getenv("AUTH_TOKEN_TTL_MINUTES", "720").strip()
    try:
        return max(int(raw), 5)
    except ValueError:
        return 720


def build_local_users() -> dict[str, dict[str, str]]:
    return {
        (os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip() or DEFAULT_ADMIN_EMAIL).lower(): {
            "password": os.getenv("ADMIN_PASSWORD", DEFAULT_LOCAL_PASSWORD).strip() or DEFAULT_LOCAL_PASSWORD,
            "role": "platform_admin",
            "user_id": os.getenv("ADMIN_USER_ID", "11111111-1111-1111-1111-111111111111").strip()
            or "11111111-1111-1111-1111-111111111111",
        },
        (os.getenv("MEMBER_EMAIL", DEFAULT_MEMBER_EMAIL).strip() or DEFAULT_MEMBER_EMAIL).lower(): {
            "password": os.getenv("MEMBER_PASSWORD", DEFAULT_LOCAL_PASSWORD).strip() or DEFAULT_LOCAL_PASSWORD,
            "role": "kb_editor",
            "user_id": os.getenv("MEMBER_USER_ID", "22222222-2222-2222-2222-222222222222").strip()
            or "22222222-2222-2222-2222-222222222222",
        },
    }


def auth_configuration_warnings() -> list[str]:
    """Return human-readable warnings for insecure local auth defaults.

    Output:
    - list[str]: warnings describing insecure defaults still in effect.
    Failure mode:
    - never raises; callers may surface warnings or treat them as fatal via
      `ensure_auth_configuration_ready()`.
    """
    warnings: list[str] = []
    if _jwt_secret() == DEFAULT_JWT_SECRET:
        warnings.append("JWT_SECRET is using the default placeholder value")

    users = build_local_users()
    admin = users.get((os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip() or DEFAULT_ADMIN_EMAIL).lower())
    member = users.get((os.getenv("MEMBER_EMAIL", DEFAULT_MEMBER_EMAIL).strip() or DEFAULT_MEMBER_EMAIL).lower())
    if admin and admin["password"] == DEFAULT_LOCAL_PASSWORD:
        warnings.append("ADMIN_PASSWORD is using the default local password")
    if member and member["password"] == DEFAULT_LOCAL_PASSWORD:
        warnings.append("MEMBER_PASSWORD is using the default local password")
    return warnings


def ensure_auth_configuration_ready() -> list[str]:
    """Validate auth settings for the current runtime mode.

    Output:
    - list[str]: warnings about insecure defaults.
    Failure mode:
    - raises RuntimeError when non-local runtimes still rely on default
      secrets or passwords.
    """
    warnings = auth_configuration_warnings()
    if warnings and not _is_local_runtime():
        raise RuntimeError(
            "insecure auth configuration is not allowed outside local development: "
            + "; ".join(warnings)
        )
    return warnings


def authenticate_local_user(email: str, password: str) -> AuthUser | None:
    users = build_local_users()
    candidate = users.get(email.strip().lower())
    if candidate is None or candidate["password"] != password:
        return None
    role = normalize_role(candidate["role"])
    return AuthUser(
        user_id=candidate["user_id"],
        email=email.strip().lower(),
        role=role,
        permissions=permissions_for_role(role),
        role_version=ROLE_VERSION,
    )


def create_access_token(user: AuthUser) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user.user_id,
        "email": user.email,
        "role": user.role,
        "permissions": list(user.permissions),
        "role_version": int(user.role_version or ROLE_VERSION),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=_jwt_ttl_minutes())).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_access_token(token: str) -> AuthUser:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token",
        ) from exc

    user_id = str(payload.get("sub", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    role = normalize_role(str(payload.get("role", "")).strip().lower() or "kb_editor")
    permissions_raw = payload.get("permissions")
    if isinstance(permissions_raw, list):
        permissions = tuple(
            str(item).strip().lower()
            for item in permissions_raw
            if str(item).strip()
        )
    else:
        permissions = permissions_for_role(role)
    role_version_raw = payload.get("role_version", ROLE_VERSION)
    try:
        role_version = int(role_version_raw)
    except (TypeError, ValueError):
        role_version = ROLE_VERSION
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token payload",
        )
    return AuthUser(
        user_id=user_id,
        email=email,
        role=role,
        permissions=tuple(dict.fromkeys(permissions or permissions_for_role(role))),
        role_version=role_version,
    )


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
        )
    prefix = "bearer "
    if not authorization.lower().startswith(prefix):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authorization scheme",
        )
    token = authorization[len(prefix) :].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    return token


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    return decode_access_token(_extract_bearer_token(authorization))


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
