#!/usr/bin/env python3
"""Optional SMTP mailer for account verification / password reset.

When SMTP is not configured, callers should still return tokens in JSON (dev mode).
Env (preferred) or dict config:

  MINGMIRROR_SMTP_HOST / smtp.host
  MINGMIRROR_SMTP_PORT (default 587)
  MINGMIRROR_SMTP_USER
  MINGMIRROR_SMTP_PASSWORD
  MINGMIRROR_SMTP_FROM
  MINGMIRROR_SMTP_TLS (default true)
  MINGMIRROR_PUBLIC_BASE_URL  (e.g. https://mingmirror.example)
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Dict, Optional

from utils.logger import setup_logger

logger = setup_logger("Mailer")


@dataclass
class MailConfig:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    from_addr: str = ""
    use_tls: bool = True
    public_base_url: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.host and self.from_addr)

    @classmethod
    def from_env_and_dict(cls, cfg: Optional[Dict[str, Any]] = None) -> "MailConfig":
        cfg = cfg or {}
        smtp = cfg.get("smtp") if isinstance(cfg.get("smtp"), dict) else {}
        ming = cfg if "smtp" in (cfg or {}) else (cfg.get("mingmirror") or {})
        if isinstance(ming, dict) and isinstance(ming.get("smtp"), dict):
            smtp = {**smtp, **ming["smtp"]}

        def _g(*keys: str, default: str = "") -> str:
            for k in keys:
                v = os.environ.get(k)
                if v:
                    return str(v).strip()
            return default

        host = _g("MINGMIRROR_SMTP_HOST", "SMTP_HOST") or str(smtp.get("host") or "")
        port_s = _g("MINGMIRROR_SMTP_PORT", "SMTP_PORT") or str(smtp.get("port") or "587")
        user = _g("MINGMIRROR_SMTP_USER", "SMTP_USER") or str(smtp.get("user") or "")
        password = _g("MINGMIRROR_SMTP_PASSWORD", "SMTP_PASSWORD") or str(
            smtp.get("password") or ""
        )
        from_addr = (
            _g("MINGMIRROR_SMTP_FROM", "SMTP_FROM")
            or str(smtp.get("from") or smtp.get("from_addr") or user or "")
        )
        tls_raw = _g("MINGMIRROR_SMTP_TLS", "SMTP_TLS") or str(smtp.get("tls", "true"))
        use_tls = str(tls_raw).lower() not in ("0", "false", "no", "off")
        base = _g("MINGMIRROR_PUBLIC_BASE_URL") or str(
            smtp.get("public_base_url") or (ming.get("public_base_url") if isinstance(ming, dict) else "") or ""
        )
        try:
            port = int(port_s)
        except ValueError:
            port = 587
        return cls(
            host=host.strip(),
            port=port,
            user=user.strip(),
            password=password,
            from_addr=from_addr.strip(),
            use_tls=use_tls,
            public_base_url=base.rstrip("/"),
        )


class Mailer:
    def __init__(self, config: Optional[MailConfig] = None) -> None:
        self.config = config or MailConfig()

    @property
    def enabled(self) -> bool:
        return self.config.configured

    def send(self, to: str, subject: str, body_text: str) -> bool:
        if not self.enabled:
            logger.info("SMTP not configured; skip send to %s subject=%s", to, subject)
            return False
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.config.from_addr
        msg["To"] = to
        msg.set_content(body_text)
        try:
            if self.config.use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(self.config.host, self.config.port, timeout=20) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                    if self.config.user:
                        smtp.login(self.config.user, self.config.password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(self.config.host, self.config.port, timeout=20) as smtp:
                    if self.config.user:
                        smtp.login(self.config.user, self.config.password)
                    smtp.send_message(msg)
            logger.info("Mail sent to %s subject=%s", to, subject)
            return True
        except Exception as exc:  # pragma: no cover - network
            logger.warning("Mail send failed to %s: %s", to, exc)
            return False

    def send_verify_email(self, to: str, token: str) -> bool:
        base = self.config.public_base_url
        link = f"{base}/app/account?verify={token}" if base else ""
        body = (
            "命镜 · 邮箱验证\n\n"
            f"验证令牌：\n{token}\n\n"
        )
        if link:
            body += f"或打开：\n{link}\n\n"
        body += "若非本人操作请忽略。令牌 48 小时内有效。\n"
        return self.send(to, "命镜 · 验证您的邮箱", body)

    def send_reset_password(self, to: str, token: str) -> bool:
        base = self.config.public_base_url
        link = f"{base}/app/account?reset={token}" if base else ""
        body = (
            "命镜 · 重置密码\n\n"
            f"重置令牌：\n{token}\n\n"
        )
        if link:
            body += f"或打开：\n{link}\n\n"
        body += "若非本人操作请忽略。令牌 2 小时内有效。\n"
        return self.send(to, "命镜 · 重置密码", body)
