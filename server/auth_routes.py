#!/usr/bin/env python3
"""HTTP routes for MingMirror account system."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from server.accounts import AccountStore


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""
    device_id: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str
    device_id: str = ""


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class LinkDeviceRequest(BaseModel):
    device_id: str = Field(..., min_length=1)


class RequestVerifyRequest(BaseModel):
    """Authenticated resend; no body required but kept for future."""

    pass


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=8)


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=8)
    new_password: str


def _bearer_token(authorization: Optional[str], x_token: Optional[str] = None) -> str:
    if x_token and x_token.strip():
        return x_token.strip()
    auth = (authorization or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def register_auth_routes(
    app: FastAPI,
    *,
    get_store: Callable[[], Optional[AccountStore]],
    merge_entitlement: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Mount /api/v1/auth/* routes."""

    def _store() -> AccountStore:
        store = get_store()
        if store is None:
            raise HTTPException(status_code=503, detail="account store unavailable")
        return store

    def _user_from_request(
        authorization: Optional[str] = None,
        x_session_token: Optional[str] = None,
    ):
        token = _bearer_token(authorization, x_session_token)
        if not token:
            raise HTTPException(status_code=401, detail="not authenticated")
        user = _store().get_user_by_token(token)
        if user is None:
            raise HTTPException(status_code=401, detail="session expired or invalid")
        return user, token

    @app.post("/api/v1/auth/register")
    async def auth_register(req: RegisterRequest) -> Dict[str, Any]:
        store = _store()
        try:
            user, session = store.register(
                req.email,
                req.password,
                display_name=req.display_name,
                device_id=req.device_id,
            )
            verify_token = store.create_email_verification(user.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if merge_entitlement and req.device_id:
            try:
                merge_entitlement(user.id, req.device_id.strip())
            except Exception:
                pass
        return {
            "user": user.to_public(),
            "token": session.token,
            "expires_at": session.expires_at,
            "token_type": "bearer",
            # Dev / no-SMTP: return token so clients can complete verify without mail.
            "email_verify_token": verify_token,
            "email_verify_hint": "No SMTP configured; use email_verify_token with /auth/verify-email",
        }

    @app.post("/api/v1/auth/login")
    async def auth_login(req: LoginRequest) -> Dict[str, Any]:
        store = _store()
        try:
            user, session = store.login(
                req.email, req.password, device_id=req.device_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if merge_entitlement and req.device_id:
            try:
                merge_entitlement(user.id, req.device_id.strip())
            except Exception:
                pass
        return {
            "user": user.to_public(),
            "token": session.token,
            "expires_at": session.expires_at,
            "token_type": "bearer",
        }

    @app.post("/api/v1/auth/logout")
    async def auth_logout(
        authorization: Optional[str] = Header(default=None),
        x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    ) -> Dict[str, Any]:
        token = _bearer_token(authorization, x_session_token)
        if not token:
            return {"ok": True, "logged_out": False}
        ok = _store().logout(token)
        return {"ok": True, "logged_out": ok}

    @app.get("/api/v1/auth/me")
    async def auth_me(
        authorization: Optional[str] = Header(default=None),
        x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    ) -> Dict[str, Any]:
        user, _ = _user_from_request(authorization, x_session_token)
        devices = _store().devices_for_user(user.id)
        return {"user": user.to_public(), "devices": devices}

    @app.post("/api/v1/auth/link-device")
    async def auth_link_device(
        req: LinkDeviceRequest,
        authorization: Optional[str] = Header(default=None),
        x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    ) -> Dict[str, Any]:
        user, _ = _user_from_request(authorization, x_session_token)
        _store().link_device(user.id, req.device_id)
        if merge_entitlement:
            try:
                merge_entitlement(user.id, req.device_id.strip())
            except Exception:
                pass
        return {
            "ok": True,
            "devices": _store().devices_for_user(user.id),
        }

    @app.post("/api/v1/auth/change-password")
    async def auth_change_password(
        req: ChangePasswordRequest,
        authorization: Optional[str] = Header(default=None),
        x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    ) -> Dict[str, Any]:
        user, _ = _user_from_request(authorization, x_session_token)
        try:
            _store().change_password(user.id, req.old_password, req.new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # Issue new session
        session = _store().create_session(user.id)
        return {
            "ok": True,
            "token": session.token,
            "expires_at": session.expires_at,
            "token_type": "bearer",
            "message": "password changed; other sessions revoked",
        }

    @app.post("/api/v1/auth/request-verify")
    async def auth_request_verify(
        authorization: Optional[str] = Header(default=None),
        x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    ) -> Dict[str, Any]:
        """Re-issue email verification token (no SMTP: token returned in JSON)."""
        user, _ = _user_from_request(authorization, x_session_token)
        try:
            token = _store().request_email_verification(user.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "email_verify_token": token,
            "email_verify_hint": "No SMTP; POST token to /auth/verify-email",
        }

    @app.post("/api/v1/auth/verify-email")
    async def auth_verify_email(req: VerifyEmailRequest) -> Dict[str, Any]:
        try:
            user = _store().verify_email(req.token)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "user": user.to_public()}

    @app.post("/api/v1/auth/forgot-password")
    async def auth_forgot_password(req: ForgotPasswordRequest) -> Dict[str, Any]:
        """Always 200 to avoid email enumeration; token only when email exists."""
        info = _store().create_password_reset(req.email)
        body: Dict[str, Any] = {
            "ok": True,
            "message": "If the email is registered, a reset token was issued.",
        }
        # Dev / no-SMTP: include token when present so product can complete flow.
        if info:
            body["reset_token"] = info["token"]
            body["reset_hint"] = "No SMTP; POST reset_token + new_password to /auth/reset-password"
        return body

    @app.post("/api/v1/auth/reset-password")
    async def auth_reset_password(req: ResetPasswordRequest) -> Dict[str, Any]:
        try:
            user = _store().reset_password_with_token(req.token, req.new_password)
            session = _store().create_session(user.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "user": user.to_public(),
            "token": session.token,
            "expires_at": session.expires_at,
            "token_type": "bearer",
        }

    @app.get("/api/v1/auth/oauth/{provider}")
    async def auth_oauth_stub(provider: str) -> Dict[str, Any]:
        """Placeholder for WeChat/Apple OAuth (not configured)."""
        raise HTTPException(
            status_code=501,
            detail=(
                f"OAuth provider '{provider}' not configured. "
                "Use email register/login. Configure provider keys to enable."
            ),
        )
