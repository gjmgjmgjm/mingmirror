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
