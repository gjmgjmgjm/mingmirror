#!/usr/bin/env python3
"""Payment adapters: normalize WeChat / Alipay / Stripe / demo webhooks.

Canonical order fields:
  provider, external_id, device_id (or scope_key), product, amount_cents,
  currency, status, days, credits, raw

Checkout returns either:
  - demo: immediate fulfillment (existing ProductStore.checkout)
  - wechat/alipay/stripe: pending order + checkout_url / prepay payload
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _g(*keys: str, default: str = "") -> str:
    for k in keys:
        v = os.environ.get(k)
        if v:
            return str(v).strip()
    return default


@dataclass
class PaymentConfig:
    """Gateway credentials (env-first)."""

    wechat_mch_id: str = ""
    wechat_api_v3_key: str = ""
    wechat_app_id: str = ""
    alipay_app_id: str = ""
    alipay_public_key: str = ""
    stripe_webhook_secret: str = ""
    public_base_url: str = ""

    @classmethod
    def from_env(cls) -> "PaymentConfig":
        return cls(
            wechat_mch_id=_g("MINGMIRROR_WECHAT_MCH_ID", "WECHAT_MCH_ID"),
            wechat_api_v3_key=_g("MINGMIRROR_WECHAT_API_V3_KEY", "WECHAT_API_V3_KEY"),
            wechat_app_id=_g("MINGMIRROR_WECHAT_APP_ID", "WECHAT_APP_ID"),
            alipay_app_id=_g("MINGMIRROR_ALIPAY_APP_ID", "ALIPAY_APP_ID"),
            alipay_public_key=_g("MINGMIRROR_ALIPAY_PUBLIC_KEY", "ALIPAY_PUBLIC_KEY"),
            stripe_webhook_secret=_g(
                "MINGMIRROR_STRIPE_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET"
            ),
            public_base_url=_g("MINGMIRROR_PUBLIC_BASE_URL").rstrip("/"),
        )

    def provider_ready(self, provider: str) -> bool:
        p = (provider or "").lower()
        if p == "demo":
            return True
        if p in ("wechat", "wechatpay", "wx"):
            return bool(self.wechat_mch_id and self.wechat_api_v3_key)
        if p in ("alipay", "ali"):
            return bool(self.alipay_app_id)
        if p == "stripe":
            return bool(self.stripe_webhook_secret)
        return False


def normalize_product(sku: str) -> str:
    s = (sku or "package").strip().lower()
    aliases = {
        "pro_month": "pro",
        "subscription_pro": "pro",
        "mingmirror_pro": "pro",
        "package_1": "package",
        "mingmirror_package": "package",
        "credit": "package",
    }
    return aliases.get(s, s)


def normalize_webhook_payload(
    provider: str, body: Dict[str, Any], *, headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Map provider-specific JSON into canonical webhook fields."""
    provider = (provider or "demo").strip().lower()
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    raw = body or {}

    if provider in ("wechat", "wechatpay", "wx"):
        # Accept both resource-decrypted shape and simplified test shape.
        resource = raw.get("resource") if isinstance(raw.get("resource"), dict) else raw
        out_trade = (
            resource.get("out_trade_no")
            or resource.get("external_id")
            or raw.get("out_trade_no")
            or ""
        )
        trade_state = (
            resource.get("trade_state")
            or resource.get("status")
            or raw.get("event_type")
            or ""
        )
        status = "succeeded" if str(trade_state).upper() in (
            "SUCCESS",
            "SUCCEEDED",
            "PAID",
            "TRANSACTION.SUCCESS",
        ) or str(trade_state).lower() in ("succeeded", "success", "paid") else str(
            trade_state or "pending"
        ).lower()
        amount = 0
        amt = resource.get("amount") if isinstance(resource.get("amount"), dict) else {}
        try:
            amount = int(amt.get("total") or resource.get("amount_cents") or 0)
        except (TypeError, ValueError):
            amount = 0
        attach = resource.get("attach") or raw.get("attach") or ""
        # attach may be JSON: {"device_id":"...","product":"pro"}
        device_id, product = "", "package"
        if isinstance(attach, str) and attach.strip().startswith("{"):
            try:
                att = json.loads(attach)
                device_id = str(att.get("device_id") or att.get("scope_key") or "")
                product = str(att.get("product") or "package")
            except json.JSONDecodeError:
                device_id = attach
        else:
            device_id = str(
                resource.get("device_id")
                or raw.get("device_id")
                or attach
                or ""
            )
            product = str(resource.get("product") or raw.get("product") or "package")
        return {
            "provider": "wechat",
            "external_id": str(out_trade),
            "device_id": device_id,
            "product": normalize_product(product),
            "amount_cents": amount,
            "currency": "CNY",
            "status": status,
            "days": int(raw.get("days") or resource.get("days") or 30),
            "credits": int(raw.get("credits") or resource.get("credits") or 1),
            "raw": raw,
        }

    if provider in ("alipay", "ali"):
        out_trade = str(
            raw.get("out_trade_no") or raw.get("external_id") or raw.get("trade_no") or ""
        )
        trade_status = str(raw.get("trade_status") or raw.get("status") or "")
        status = "succeeded" if trade_status.upper() in (
            "TRADE_SUCCESS",
            "TRADE_FINISHED",
            "SUCCESS",
            "SUCCEEDED",
            "PAID",
        ) or trade_status.lower() in ("succeeded", "success", "paid") else trade_status.lower() or "pending"
        try:
            # Alipay total_amount is yuan string
            yuan = float(raw.get("total_amount") or raw.get("amount") or 0)
            amount = int(round(yuan * 100))
        except (TypeError, ValueError):
            amount = int(raw.get("amount_cents") or 0)
        passback = str(raw.get("passback_params") or raw.get("body") or "")
        device_id = str(raw.get("device_id") or "")
        product = str(raw.get("product") or "package")
        if passback.startswith("{"):
            try:
                pb = json.loads(passback)
                device_id = device_id or str(pb.get("device_id") or "")
                product = str(pb.get("product") or product)
            except json.JSONDecodeError:
                pass
        return {
            "provider": "alipay",
            "external_id": out_trade,
            "device_id": device_id,
            "product": normalize_product(product),
            "amount_cents": amount,
            "currency": "CNY",
            "status": status,
            "days": int(raw.get("days") or 30),
            "credits": int(raw.get("credits") or 1),
            "raw": raw,
        }

    if provider == "stripe":
        # Stripe Checkout session completed event
        obj = raw.get("data", {}).get("object") if isinstance(raw.get("data"), dict) else raw
        if not isinstance(obj, dict):
            obj = raw
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        status_raw = str(obj.get("payment_status") or obj.get("status") or raw.get("type") or "")
        status = "succeeded" if "paid" in status_raw or "complete" in status_raw or status_raw == "checkout.session.completed" else status_raw
        if raw.get("type") == "checkout.session.completed":
            status = "succeeded"
        try:
            amount = int(obj.get("amount_total") or obj.get("amount_cents") or 0)
        except (TypeError, ValueError):
            amount = 0
        return {
            "provider": "stripe",
            "external_id": str(obj.get("id") or obj.get("external_id") or raw.get("id") or ""),
            "device_id": str(meta.get("device_id") or obj.get("client_reference_id") or obj.get("device_id") or ""),
            "product": normalize_product(str(meta.get("product") or obj.get("product") or "package")),
            "amount_cents": amount,
            "currency": str(obj.get("currency") or "usd").upper(),
            "status": status,
            "days": int(meta.get("days") or 30),
            "credits": int(meta.get("credits") or 1),
            "raw": raw,
        }

    # demo / generic already-canonical
    return {
        "provider": provider or "demo",
        "external_id": str(raw.get("external_id") or raw.get("out_trade_no") or ""),
        "device_id": str(raw.get("device_id") or raw.get("scope_key") or ""),
        "product": normalize_product(str(raw.get("product") or "package")),
        "amount_cents": int(raw.get("amount_cents") or 0),
        "currency": str(raw.get("currency") or "CNY"),
        "status": str(raw.get("status") or "succeeded"),
        "days": int(raw.get("days") or 30),
        "credits": int(raw.get("credits") or 1),
        "raw": raw,
    }


def build_pending_checkout(
    *,
    provider: str,
    device_id: str,
    product: str,
    amount_cents: int,
    currency: str = "CNY",
    days: int = 30,
    credits: int = 1,
    external_id: str = "",
    cfg: Optional[PaymentConfig] = None,
) -> Dict[str, Any]:
    """Create pending order descriptor for non-demo gateways.

    Real prepay APIs (WeChat JSAPI / Alipay trade.page.pay) should replace
    the placeholder ``checkout_url`` when merchant keys are live.
    """
    cfg = cfg or PaymentConfig.from_env()
    provider = (provider or "demo").strip().lower()
    product = normalize_product(product)
    ext = (external_id or "").strip() or f"{provider}_{uuid.uuid4().hex[:16]}"
    if amount_cents <= 0:
        amount_cents = 9900 if product == "pro" else 1900
    attach = json.dumps(
        {"device_id": device_id, "product": product, "days": days, "credits": credits},
        ensure_ascii=False,
    )
    base = cfg.public_base_url or ""
    notify = f"{base}/api/v1/product/payment/webhook/{provider}" if base else ""

    if provider in ("wechat", "wechatpay", "wx"):
        # Placeholder unified order — production: call WeChat Pay v3 transactions
        prepay_id = f"wx_prepay_{ext}"
        return {
            "mode": "pending",
            "provider": "wechat",
            "external_id": ext,
            "status": "pending",
            "amount_cents": amount_cents,
            "currency": currency,
            "product": product,
            "device_id": device_id,
            "days": days,
            "credits": credits,
            "checkout_url": f"{base}/app/pricing?order={ext}&provider=wechat" if base else "",
            "prepay": {
                "prepay_id": prepay_id,
                "app_id": cfg.wechat_app_id,
                "mch_id": cfg.wechat_mch_id,
                "attach": attach,
                "notify_url": notify,
                "ready": cfg.provider_ready("wechat"),
                "hint": "Configure WeChat Pay v3 and replace prepay with real JSAPI/native order",
            },
        }

    if provider in ("alipay", "ali"):
        return {
            "mode": "pending",
            "provider": "alipay",
            "external_id": ext,
            "status": "pending",
            "amount_cents": amount_cents,
            "currency": currency,
            "product": product,
            "device_id": device_id,
            "days": days,
            "credits": credits,
            "checkout_url": f"{base}/app/pricing?order={ext}&provider=alipay" if base else "",
            "prepay": {
                "app_id": cfg.alipay_app_id,
                "out_trade_no": ext,
                "total_amount": f"{amount_cents / 100:.2f}",
                "passback_params": attach,
                "notify_url": notify,
                "ready": cfg.provider_ready("alipay"),
                "hint": "Configure Alipay openapi and return form/page pay URL",
            },
        }

    if provider == "stripe":
        return {
            "mode": "pending",
            "provider": "stripe",
            "external_id": ext,
            "status": "pending",
            "amount_cents": amount_cents,
            "currency": currency.lower(),
            "product": product,
            "device_id": device_id,
            "days": days,
            "credits": credits,
            "checkout_url": f"{base}/app/pricing?order={ext}&provider=stripe" if base else "",
            "prepay": {
                "session_id": f"cs_test_{ext}",
                "metadata": {"device_id": device_id, "product": product},
                "success_url": f"{base}/app/pricing?paid=1" if base else "",
                "ready": cfg.provider_ready("stripe"),
                "hint": "Create Stripe Checkout Session server-side with secret key",
            },
        }

    # demo immediate
    return {
        "mode": "immediate",
        "provider": "demo",
        "external_id": ext,
        "status": "succeeded",
        "amount_cents": amount_cents,
        "currency": currency,
        "product": product,
        "device_id": device_id,
        "days": days,
        "credits": credits,
    }


def verify_stripe_signature(
    payload: bytes, sig_header: str, secret: str, *, tolerance: int = 300
) -> bool:
    """Minimal Stripe-compatible signature check (t=...,v1=...)."""
    if not secret or not sig_header:
        return False
    parts = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts.setdefault(k.strip(), []).append(v.strip())
    t = (parts.get("t") or [""])[0]
    v1s = parts.get("v1") or []
    if not t or not v1s:
        return False
    try:
        ts = int(t)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > tolerance:
        return False
    signed = f"{t}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, v) for v in v1s)
