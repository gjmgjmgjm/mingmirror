#!/usr/bin/env python3
"""HTTP routes for MingMirror account system."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional  # noqa: F401 — Any used by get_mailer

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


class DeleteAccountRequest(BaseModel):
    """Hard-delete: confirm must be DELETE; password required for email accounts.

    OAuth-only users (synthetic @oauth.local) may omit password when session is valid.
    """

    password: str = ""
    confirm: str = Field(default="DELETE", description='Must be the literal "DELETE"')


class OAuthCallbackRequest(BaseModel):
    code: str = Field(..., min_length=1)
    state: str = ""
    device_id: str = ""


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
    get_mailer: Optional[Callable[[], Any]] = None,
) -> None:
    """Mount /api/v1/auth/* routes."""

    def _store() -> AccountStore:
        store = get_store()
        if store is None:
            raise HTTPException(status_code=503, detail="account store unavailable")
        return store

    def _mailer():
        if get_mailer is None:
            return None
        try:
            return get_mailer()
        except Exception:
            return None

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
        mailed = False
        mailer = _mailer()
        if mailer is not None and getattr(mailer, "enabled", False):
            mailed = bool(mailer.send_verify_email(user.email, verify_token))
        body: Dict[str, Any] = {
            "user": user.to_public(),
            "token": session.token,
            "expires_at": session.expires_at,
            "token_type": "bearer",
            "email_sent": mailed,
        }
        # Always return token when SMTP off or send failed (dev / resilience).
        if not mailed:
            body["email_verify_token"] = verify_token
            body["email_verify_hint"] = (
                "No SMTP or send failed; use email_verify_token with /auth/verify-email"
            )
        return body

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
        """Re-issue email verification token; SMTP when configured."""
        user, _ = _user_from_request(authorization, x_session_token)
        try:
            token = _store().request_email_verification(user.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        mailed = False
        mailer = _mailer()
        if mailer is not None and getattr(mailer, "enabled", False):
            mailed = bool(mailer.send_verify_email(user.email, token))
        body: Dict[str, Any] = {"ok": True, "email_sent": mailed}
        if not mailed:
            body["email_verify_token"] = token
            body["email_verify_hint"] = "No SMTP; POST token to /auth/verify-email"
        return body

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
            "email_sent": False,
        }
        if info:
            mailed = False
            mailer = _mailer()
            if mailer is not None and getattr(mailer, "enabled", False):
                mailed = bool(mailer.send_reset_password(info["email"], info["token"]))
            body["email_sent"] = mailed
            # Dev / send-fail: include token so product can complete flow.
            if not mailed:
                body["reset_token"] = info["token"]
                body["reset_hint"] = (
                    "No SMTP; POST reset_token + new_password to /auth/reset-password"
                )
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

    @app.get("/api/v1/auth/export-data")
    async def auth_export_data(
        authorization: Optional[str] = Header(default=None),
        x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    ) -> Dict[str, Any]:
        """Export account-owned personal data (no password hashes / full tokens)."""
        user, _ = _user_from_request(authorization, x_session_token)
        data = _store().export_user_data(user.id)
        return {"ok": True, "data": data}

    @app.post("/api/v1/auth/delete-account")
    async def auth_delete_account(
        req: DeleteAccountRequest,
        authorization: Optional[str] = Header(default=None),
        x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    ) -> Dict[str, Any]:
        """Permanently delete account. Requires password + confirm=DELETE."""
        if (req.confirm or "").strip() != "DELETE":
            raise HTTPException(
                status_code=400,
                detail='confirm must be the literal string "DELETE"',
            )
        user, _ = _user_from_request(authorization, x_session_token)
        pw = (req.password or "").strip()
        oauth_only = (user.email or "").endswith("@oauth.local")
        if not pw and not oauth_only:
            raise HTTPException(
                status_code=400,
                detail="password required to delete email accounts",
            )
        try:
            _store().delete_user(user.id, password=pw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "deleted": True, "user_id": user.id}

    @app.get("/api/v1/auth/oauth/{provider}")
    async def auth_oauth_authorize(
        provider: str,
        state: str = "",
    ) -> Dict[str, Any]:
        """Return OAuth authorize URL (WeChat / Apple). Secrets via env."""
        from server.oauth import OAuthConfig, build_authorize_url

        try:
            info = build_authorize_url(
                provider, state=state, cfg=OAuthConfig.from_env()
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            **info,
            "hint": (
                None
                if info.get("ready")
                else "Provider keys not set; authorize_url is a scaffold. "
                "Set MINGMIRROR_WECHAT_OAUTH_* / MINGMIRROR_APPLE_* and "
                "MINGMIRROR_PUBLIC_BASE_URL."
            ),
        }

    @app.get("/api/v1/auth/oauth/{provider}/callback")
    @app.post("/api/v1/auth/oauth/{provider}/callback")
    async def auth_oauth_callback(
        provider: str,
        request: Request,
        code: str = "",
        state: str = "",
        device_id: str = "",
    ) -> Dict[str, Any]:
        """OAuth redirect callback: exchange code → session.

        Production needs real token exchange. With MINGMIRROR_OAUTH_STUB=1
        a deterministic stub identity is issued for local tests.
        """
        from server.oauth import exchange_code_stub

        # Accept code from query (GET) or JSON/form (POST)
        if not code and request.method.upper() == "POST":
            ctype = (request.headers.get("content-type") or "").lower()
            if "json" in ctype:
                try:
                    body = await request.json()
                    if isinstance(body, dict):
                        code = str(body.get("code") or "")
                        state = state or str(body.get("state") or "")
                        device_id = device_id or str(body.get("device_id") or "")
                except Exception:
                    pass
            else:
                try:
                    form = await request.form()
                    code = str(form.get("code") or "")
                    state = state or str(form.get("state") or "")
                    device_id = device_id or str(form.get("device_id") or "")
                except Exception:
                    pass

        if not code:
            raise HTTPException(status_code=400, detail="code required")

        try:
            profile = exchange_code_stub(provider, code)
        except ValueError as exc:
            msg = str(exc)
            status = 501 if "not configured" in msg or "not implemented" in msg else 400
            raise HTTPException(status_code=status, detail=msg) from exc

        store = _store()
        try:
            user, session = store.upsert_oauth_identity(
                provider=str(profile.get("provider") or provider),
                provider_user_id=str(profile.get("provider_user_id") or ""),
                email=str(profile.get("email") or ""),
                display_name=str(profile.get("display_name") or ""),
                device_id=device_id or "",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if merge_entitlement and device_id:
            try:
                merge_entitlement(user.id, device_id.strip())
            except Exception:
                pass

        return {
            "ok": True,
            "user": user.to_public(),
            "token": session.token,
            "expires_at": session.expires_at,
            "token_type": "bearer",
            "provider": profile.get("provider") or provider,
            "state": state,
            "stub": True,  # real exchange will set False when implemented
        }

    @app.post("/api/v1/auth/oauth/{provider}/exchange")
    async def auth_oauth_exchange(
        provider: str,
        req: OAuthCallbackRequest,
    ) -> Dict[str, Any]:
        """SPA-friendly code exchange (same as callback, JSON body)."""
        from server.oauth import exchange_code_stub

        try:
            profile = exchange_code_stub(provider, req.code)
        except ValueError as exc:
            msg = str(exc)
            status = 501 if "not configured" in msg or "not implemented" in msg else 400
            raise HTTPException(status_code=status, detail=msg) from exc

        store = _store()
        try:
            user, session = store.upsert_oauth_identity(
                provider=str(profile.get("provider") or provider),
                provider_user_id=str(profile.get("provider_user_id") or ""),
                email=str(profile.get("email") or ""),
                display_name=str(profile.get("display_name") or ""),
                device_id=req.device_id or "",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if merge_entitlement and req.device_id:
            try:
                merge_entitlement(user.id, req.device_id.strip())
            except Exception:
                pass

        return {
            "ok": True,
            "user": user.to_public(),
            "token": session.token,
            "expires_at": session.expires_at,
            "token_type": "bearer",
            "provider": profile.get("provider") or provider,
            "state": req.state,
        }
