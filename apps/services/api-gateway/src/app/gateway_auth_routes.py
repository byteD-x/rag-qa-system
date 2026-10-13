from __future__ import annotations

import os
import smtplib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from shared.auth import CurrentUser, authenticate_local_user, create_access_token, serialize_user

from .gateway_audit_support import write_gateway_audit_event
from .auth_store import authenticate_user, create_user, deliver_password_reset, request_password_reset, reset_password
from .gateway_schemas import LoginRequest, PasswordResetConfirmRequest, PasswordResetRequest, RegisterRequest


router = APIRouter()


@router.post("/api/v1/auth/login")
async def login(payload: LoginRequest, request: Request) -> JSONResponse:
    user = authenticate_user(payload.email, payload.password) or authenticate_local_user(payload.email, payload.password)
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


@router.post("/api/v1/auth/register")
async def register(payload: RegisterRequest, request: Request) -> JSONResponse:
    try:
        user = create_user(email=payload.email, password=payload.password, department=payload.department)
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录或找回密码") from exc
        raise
    token = create_access_token(user)
    write_gateway_audit_event(action="auth.register", outcome="success", request=request, user=user, resource_type="auth_user", resource_id=user.user_id)
    return JSONResponse({"access_token": token, "token_type": "bearer", "user": serialize_user(user)}, status_code=201)


@router.post("/api/v1/auth/password-reset/request")
async def password_reset_request(payload: PasswordResetRequest, request: Request) -> dict[str, object]:
    token = request_password_reset(payload.email)
    response: dict[str, object] = {"accepted": True, "message": "如果邮箱存在，重置链接已生成，请检查邮箱。"}
    if token:
        runtime = os.getenv("APP_ENV", "development").strip().lower()
        if runtime in {"dev", "development", "local", "test"}:
            response["reset_token"] = token
        else:
            try:
                deliver_password_reset(email=payload.email, token=token)
            except (OSError, ValueError, RuntimeError, smtplib.SMTPException) as exc:
                raise HTTPException(status_code=503, detail="密码重置邮件服务未配置，请联系管理员") from exc
    write_gateway_audit_event(action="auth.password_reset.request", outcome="accepted", request=request, actor_email=payload.email, resource_type="auth_password_reset")
    return response


@router.post("/api/v1/auth/password-reset/confirm")
async def password_reset_confirm(payload: PasswordResetConfirmRequest, request: Request) -> dict[str, object]:
    user = reset_password(payload.token, payload.password)
    if user is None:
        raise HTTPException(status_code=400, detail="重置链接无效或已过期，请重新申请")
    write_gateway_audit_event(action="auth.password_reset.confirm", outcome="success", request=request, user=user, resource_type="auth_user", resource_id=user.user_id)
    return {"reset": True, "message": "密码已更新，请使用新密码登录。"}


@router.get("/api/v1/auth/me")
async def me(user: CurrentUser) -> dict[str, object]:
    return serialize_user(user)
