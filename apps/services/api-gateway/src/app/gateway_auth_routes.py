from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from shared.auth import CurrentUser, authenticate_local_user, create_access_token, serialize_user

from .gateway_audit_support import write_gateway_audit_event
from .gateway_schemas import LoginRequest


router = APIRouter()


@router.post("/api/v1/auth/login")
async def login(payload: LoginRequest, request: Request) -> JSONResponse:
    user = authenticate_local_user(payload.email, payload.password)
    if user is None:
        write_gateway_audit_event(
            action="auth.login",
            outcome="failed",
            request=request,
            actor_email=payload.email.strip().lower(),
            resource_type="auth_session",
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = create_access_token(user)
    write_gateway_audit_event(action="auth.login", outcome="success", request=request, user=user, resource_type="auth_session")
    return JSONResponse({"access_token": token, "token_type": "bearer", "user": serialize_user(user)})


@router.get("/api/v1/auth/me")
async def me(user: CurrentUser) -> dict[str, object]:
    return serialize_user(user)
