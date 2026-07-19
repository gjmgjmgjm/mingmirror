#!/usr/bin/env python3
"""OAuth providers (WeChat / Apple) — authorization URL + code exchange skeleton.

When client secrets are missing, authorize URL is still generated for docs/tests;
token exchange returns 501-style error for real HTTP handlers to map.
"""
from __future__ import annotations

import os
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _g(*keys: str, default: str = "") -> str:
    for k in keys:
        v = os.environ.get(k)
        if v:
            return str(v).strip()
    return default


@dataclass
class OAuthConfig:
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    public_base_url: str = ""

    @classmethod
    def from_env(cls) -> "OAuthConfig":
        return cls(
            wechat_app_id=_g("MINGMIRROR_WECHAT_OAUTH_APP_ID", "WECHAT_OAUTH_APP_ID"),
            wechat_app_secret=_g(
                "MINGMIRROR_WECHAT_OAUTH_SECRET", "WECHAT_OAUTH_SECRET"
            ),
            apple_client_id=_g("MINGMIRROR_APPLE_CLIENT_ID", "APPLE_CLIENT_ID"),
            apple_team_id=_g("MINGMIRROR_APPLE_TEAM_ID", "APPLE_TEAM_ID"),
            apple_key_id=_g("MINGMIRROR_APPLE_KEY_ID", "APPLE_KEY_ID"),
            public_base_url=_g("MINGMIRROR_PUBLIC_BASE_URL").rstrip("/"),
        )

    def ready(self, provider: str) -> bool:
        p = (provider or "").lower()
        if p in ("wechat", "wx"):
            return bool(self.wechat_app_id and self.wechat_app_secret)
        if p == "apple":
            return bool(self.apple_client_id)
        return False


def build_authorize_url(
    provider: str,
    *,
    state: str = "",
    cfg: Optional[OAuthConfig] = None,
) -> Dict[str, Any]:
    cfg = cfg or OAuthConfig.from_env()
    provider = (provider or "").strip().lower()
    state = state or secrets.token_urlsafe(16)
    base = cfg.public_base_url
    redirect = f"{base}/api/v1/auth/oauth/{provider}/callback" if base else ""

    if provider in ("wechat", "wx"):
        # WeChat Open Platform website QR login
        q = urllib.parse.urlencode(
            {
                "appid": cfg.wechat_app_id or "YOUR_APPID",
                "redirect_uri": redirect or "https://example.com/callback",
                "response_type": "code",
                "scope": "snsapi_login",
                "state": state,
            }
        )
        url = f"https://open.weixin.qq.com/connect/qrconnect?{q}#wechat_redirect"
        return {
            "provider": "wechat",
            "authorize_url": url,
            "state": state,
            "ready": cfg.ready("wechat"),
            "redirect_uri": redirect,
        }

    if provider == "apple":
        q = urllib.parse.urlencode(
            {
                "client_id": cfg.apple_client_id or "YOUR_SERVICE_ID",
                "redirect_uri": redirect or "https://example.com/callback",
                "response_type": "code id_token",
                "response_mode": "form_post",
                "scope": "name email",
                "state": state,
            }
        )
        url = f"https://appleid.apple.com/auth/authorize?{q}"
        return {
            "provider": "apple",
            "authorize_url": url,
            "state": state,
            "ready": cfg.ready("apple"),
            "redirect_uri": redirect,
        }

    raise ValueError(f"unsupported oauth provider: {provider}")


def exchange_code_stub(
    provider: str,
    code: str,
    *,
    cfg: Optional[OAuthConfig] = None,
) -> Dict[str, Any]:
    """Exchange authorization code for profile.

    Production: HTTP call to WeChat/Apple token endpoints.
    Without secrets: raise ValueError so route returns 501.
    """
    cfg = cfg or OAuthConfig.from_env()
    provider = (provider or "").strip().lower()
    code = (code or "").strip()
    if not code:
        raise ValueError("code required")

    stub = _g("MINGMIRROR_OAUTH_STUB") in ("1", "true", "yes")

    if provider in ("wechat", "wx"):
        # Stub identity for integration tests when MINGMIRROR_OAUTH_STUB=1
        if stub:
            return {
                "provider": "wechat",
                "provider_user_id": f"wx_stub_{code[:12]}",
                "email": "",
                "display_name": "微信用户",
            }
        if not cfg.ready("wechat"):
            raise ValueError("wechat oauth not configured")
        raise ValueError(
            "wechat token exchange not implemented in this build; "
            "set MINGMIRROR_OAUTH_STUB=1 for local stub or implement access_token API"
        )

    if provider == "apple":
        if stub:
            return {
                "provider": "apple",
                "provider_user_id": f"apple_stub_{code[:12]}",
                "email": f"apple_{code[:8]}@privaterelay.appleid.com",
                "display_name": "Apple User",
            }
        if not cfg.ready("apple"):
            raise ValueError("apple oauth not configured")
        raise ValueError(
            "apple token exchange not implemented in this build; "
            "set MINGMIRROR_OAUTH_STUB=1 for local stub"
        )

    raise ValueError(f"unsupported oauth provider: {provider}")
