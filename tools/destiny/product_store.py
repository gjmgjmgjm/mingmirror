#!/usr/bin/env python3
"""Product plane: funnel analytics + device-scoped entitlements (SQLite).

Designed as a thin, payment-gateway-ready layer. Demo activation uses
``MINGMIRROR_DEMO_CODE`` (default ``demo-pro``) rather than real billing.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Canonical funnel steps (frontend should reuse these names).
FUNNEL_EVENTS = (
    "page_home",
    "chart_created",
    "demo_chart_loaded",
    "report_viewed",
    "package_export",
    "package_export_blocked",
    "calibrate_run",
    "event_added",
    "council_run",
    "compatibility_run",
    "pricing_view",
    "pro_activated",
    "credit_purchased",
    "checkout_completed",
    "payment_webhook",
    "admin_grant",
)


@dataclass
class EntitlementRecord:
    device_id: str
    plan: str  # free | pro
    expires_at: int  # unix, 0 = none
    package_credits: int
    updated_at: int

    def to_dict(self) -> Dict[str, Any]:
        active_pro = self.plan == "pro" and (
            self.expires_at == 0 or self.expires_at > int(time.time())
        )
        return {
            "device_id": self.device_id,
            "plan": "pro" if active_pro else "free",
            "expires_at": self.expires_at if active_pro else 0,
            "expires_at_iso": (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.expires_at))
                if active_pro and self.expires_at
                else None
            ),
            "package_credits": 99 if active_pro else max(0, self.package_credits),
            "can_export_package": active_pro or self.package_credits > 0,
            "updated_at": self.updated_at,
        }


class ProductStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS analytics_event (
                id TEXT PRIMARY KEY,
                event TEXT NOT NULL,
                device_id TEXT NOT NULL DEFAULT '',
                chart_id TEXT NOT NULL DEFAULT '',
                props_json TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_analytics_event ON analytics_event(event);
            CREATE INDEX IF NOT EXISTS idx_analytics_created ON analytics_event(created_at);
            CREATE INDEX IF NOT EXISTS idx_analytics_device ON analytics_event(device_id);

            CREATE TABLE IF NOT EXISTS entitlement (
                device_id TEXT PRIMARY KEY,
                plan TEXT NOT NULL DEFAULT 'free',
                expires_at INTEGER NOT NULL DEFAULT 0,
                package_credits INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payment_ledger (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL DEFAULT 'demo',
                external_id TEXT NOT NULL,
                device_id TEXT NOT NULL DEFAULT '',
                product TEXT NOT NULL DEFAULT '',
                amount_cents INTEGER NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'CNY',
                status TEXT NOT NULL DEFAULT 'succeeded',
                raw_json TEXT,
                created_at INTEGER NOT NULL,
                UNIQUE(provider, external_id)
            );
            CREATE INDEX IF NOT EXISTS idx_payment_device ON payment_ledger(device_id);
            CREATE INDEX IF NOT EXISTS idx_payment_created ON payment_ledger(created_at);
            """
        )
        self._conn.commit()

    def track(
        self,
        event: str,
        *,
        device_id: str = "",
        chart_id: str = "",
        props: Optional[Dict[str, Any]] = None,
    ) -> str:
        eid = str(uuid.uuid4())
        now = int(time.time())
        self._conn.execute(
            """
            INSERT INTO analytics_event
            (id, event, device_id, chart_id, props_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                (event or "unknown")[:64],
                (device_id or "")[:128],
                (chart_id or "")[:128],
                json.dumps(props or {}, ensure_ascii=False),
                now,
            ),
        )
        self._conn.commit()
        return eid

    def funnel_summary(self, since_unix: Optional[int] = None) -> Dict[str, Any]:
        since = since_unix if since_unix is not None else int(time.time()) - 7 * 86400
        cur = self._conn.execute(
            """
            SELECT event, COUNT(*) AS n
            FROM analytics_event
            WHERE created_at >= ?
            GROUP BY event
            ORDER BY n DESC
            """,
            (since,),
        )
        counts = {row["event"]: row["n"] for row in cur.fetchall()}
        ordered = {name: int(counts.get(name, 0)) for name in FUNNEL_EVENTS}
        # conversions (rough)
        created = ordered.get("chart_created", 0) or 0
        exported = ordered.get("package_export", 0) or 0
        calibrated = ordered.get("calibrate_run", 0) or 0
        return {
            "since": since,
            "counts": ordered,
            "extra": {k: v for k, v in counts.items() if k not in ordered},
            "rates": {
                "export_per_chart": round(exported / created, 3) if created else 0.0,
                "calibrate_per_chart": round(calibrated / created, 3) if created else 0.0,
            },
        }

    def get_entitlement(self, device_id: str) -> EntitlementRecord:
        device_id = (device_id or "").strip() or "anonymous"
        cur = self._conn.execute(
            "SELECT * FROM entitlement WHERE device_id = ?", (device_id,)
        )
        row = cur.fetchone()
        if not row:
            return EntitlementRecord(
                device_id=device_id,
                plan="free",
                expires_at=0,
                package_credits=0,
                updated_at=0,
            )
        return EntitlementRecord(
            device_id=row["device_id"],
            plan=row["plan"] or "free",
            expires_at=int(row["expires_at"] or 0),
            package_credits=int(row["package_credits"] or 0),
            updated_at=int(row["updated_at"] or 0),
        )

    def save_entitlement(self, rec: EntitlementRecord) -> EntitlementRecord:
        rec.updated_at = int(time.time())
        # Downgrade expired pro
        if rec.plan == "pro" and rec.expires_at and rec.expires_at < rec.updated_at:
            rec.plan = "free"
            rec.expires_at = 0
        self._conn.execute(
            """
            INSERT INTO entitlement
            (device_id, plan, expires_at, package_credits, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                plan=excluded.plan,
                expires_at=excluded.expires_at,
                package_credits=excluded.package_credits,
                updated_at=excluded.updated_at
            """,
            (
                rec.device_id,
                rec.plan,
                rec.expires_at,
                max(0, int(rec.package_credits)),
                rec.updated_at,
            ),
        )
        self._conn.commit()
        return rec

    def activate_pro(self, device_id: str, days: int = 30) -> EntitlementRecord:
        rec = self.get_entitlement(device_id)
        rec.plan = "pro"
        rec.expires_at = int(time.time()) + max(1, days) * 86400
        rec.package_credits = max(rec.package_credits, 99)
        return self.save_entitlement(rec)

    def add_credits(self, device_id: str, n: int = 1) -> EntitlementRecord:
        rec = self.get_entitlement(device_id)
        rec.package_credits = max(0, rec.package_credits) + max(0, n)
        return self.save_entitlement(rec)

    def merge_device_into_user(self, user_key: str, device_id: str) -> EntitlementRecord:
        """Merge anonymous device entitlement into a user-scoped key.

        ``user_key`` should be like ``user:<uuid>``. Takes max credits / longer pro.
        """
        user_key = (user_key or "").strip()
        device_id = (device_id or "").strip()
        if not user_key:
            raise ValueError("user_key required")
        user_rec = self.get_entitlement(user_key)
        if not device_id or device_id == user_key:
            return user_rec
        dev = self.get_entitlement(device_id)
        now = int(time.time())
        # plan: prefer pro if either active
        user_pro = user_rec.plan == "pro" and user_rec.expires_at > now
        dev_pro = dev.plan == "pro" and dev.expires_at > now
        if user_pro or dev_pro:
            user_rec.plan = "pro"
            user_rec.expires_at = max(
                user_rec.expires_at if user_pro else 0,
                dev.expires_at if dev_pro else 0,
            )
        user_rec.package_credits = max(
            0, int(user_rec.package_credits or 0)
        ) + max(0, int(dev.package_credits or 0))
        # Zero device credits after merge to avoid double-spend (best-effort).
        if dev.package_credits:
            dev.package_credits = 0
            self.save_entitlement(dev)
        return self.save_entitlement(user_rec)

    def consume_credit(self, device_id: str) -> Dict[str, Any]:
        """Consume one package credit unless pro. Returns entitlement dict + ok."""
        rec = self.get_entitlement(device_id)
        data = rec.to_dict()
        if data["plan"] == "pro":
            return {"ok": True, "entitlement": data, "reason": "pro"}
        if rec.package_credits <= 0:
            return {"ok": False, "entitlement": data, "reason": "no_credits"}
        rec.package_credits -= 1
        data = self.save_entitlement(rec).to_dict()
        return {"ok": True, "entitlement": data, "reason": "credit"}

    def recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 200))
        cur = self._conn.execute(
            """
            SELECT id, event, device_id, chart_id, props_json, created_at
            FROM analytics_event
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = []
        for row in cur.fetchall():
            props = {}
            try:
                props = json.loads(row["props_json"] or "{}")
            except json.JSONDecodeError:
                props = {}
            rows.append(
                {
                    "id": row["id"],
                    "event": row["event"],
                    "device_id": row["device_id"],
                    "chart_id": row["chart_id"],
                    "props": props,
                    "created_at": row["created_at"],
                }
            )
        return rows

    def list_entitlements(self, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 200))
        cur = self._conn.execute(
            """
            SELECT * FROM entitlement
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        out = []
        for row in cur.fetchall():
            rec = EntitlementRecord(
                device_id=row["device_id"],
                plan=row["plan"] or "free",
                expires_at=int(row["expires_at"] or 0),
                package_credits=int(row["package_credits"] or 0),
                updated_at=int(row["updated_at"] or 0),
            )
            out.append(rec.to_dict())
        return out

    def record_payment(
        self,
        *,
        provider: str,
        external_id: str,
        device_id: str,
        product: str,
        amount_cents: int = 0,
        currency: str = "CNY",
        status: str = "succeeded",
        raw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Idempotent payment ledger row. Returns {created, payment_id, duplicate}."""
        provider = (provider or "demo").strip()[:32]
        external_id = (external_id or "").strip()[:128]
        if not external_id:
            raise ValueError("external_id required")
        now = int(time.time())
        pid = str(uuid.uuid4())
        try:
            self._conn.execute(
                """
                INSERT INTO payment_ledger
                (id, provider, external_id, device_id, product, amount_cents,
                 currency, status, raw_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid,
                    provider,
                    external_id,
                    (device_id or "")[:128],
                    (product or "")[:64],
                    int(amount_cents or 0),
                    (currency or "CNY")[:8],
                    (status or "succeeded")[:32],
                    json.dumps(raw or {}, ensure_ascii=False),
                    now,
                ),
            )
            self._conn.commit()
            return {"created": True, "payment_id": pid, "duplicate": False}
        except sqlite3.IntegrityError:
            cur = self._conn.execute(
                """
                SELECT id FROM payment_ledger
                WHERE provider = ? AND external_id = ?
                """,
                (provider, external_id),
            )
            row = cur.fetchone()
            return {
                "created": False,
                "payment_id": row["id"] if row else "",
                "duplicate": True,
            }

    def apply_payment_product(
        self,
        device_id: str,
        product: str,
        *,
        days: int = 30,
        credits: int = 1,
    ) -> EntitlementRecord:
        """Map product SKU → entitlement mutation."""
        product = (product or "").strip().lower()
        device_id = (device_id or "").strip() or "anonymous"
        if product in ("pro", "pro_month", "subscription_pro", "mingmirror_pro"):
            return self.activate_pro(device_id, days=days)
        if product in ("credit", "package", "package_1", "mingmirror_package"):
            return self.add_credits(device_id, n=max(1, credits))
        # default: one package credit
        return self.add_credits(device_id, n=max(1, credits))

    def list_payments(
        self,
        *,
        device_id: str = "",
        limit: int = 50,
        since_unix: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 50), 200))
        if device_id:
            if since_unix is not None:
                cur = self._conn.execute(
                    """
                    SELECT * FROM payment_ledger
                    WHERE device_id = ? AND created_at >= ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (device_id[:128], int(since_unix), limit),
                )
            else:
                cur = self._conn.execute(
                    """
                    SELECT * FROM payment_ledger
                    WHERE device_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (device_id[:128], limit),
                )
        elif since_unix is not None:
            cur = self._conn.execute(
                """
                SELECT * FROM payment_ledger
                WHERE created_at >= ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (int(since_unix), limit),
            )
        else:
            cur = self._conn.execute(
                """
                SELECT * FROM payment_ledger
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            )
        return [self._payment_row(row) for row in cur.fetchall()]

    def get_payment(
        self, *, provider: str, external_id: str
    ) -> Optional[Dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT * FROM payment_ledger
            WHERE provider = ? AND external_id = ?
            """,
            ((provider or "demo").strip()[:32], (external_id or "").strip()[:128]),
        )
        row = cur.fetchone()
        return self._payment_row(row) if row else None

    def payment_summary(self, since_unix: Optional[int] = None) -> Dict[str, Any]:
        since = since_unix if since_unix is not None else int(time.time()) - 7 * 86400
        cur = self._conn.execute(
            """
            SELECT COUNT(*) AS n,
                   COALESCE(SUM(amount_cents), 0) AS revenue_cents,
                   COALESCE(SUM(CASE WHEN product LIKE '%pro%' THEN 1 ELSE 0 END), 0) AS pro_orders,
                   COALESCE(SUM(CASE WHEN product NOT LIKE '%pro%' THEN 1 ELSE 0 END), 0) AS credit_orders
            FROM payment_ledger
            WHERE created_at >= ?
              AND lower(status) IN ('succeeded', 'success', 'paid', 'complete', 'completed')
            """,
            (since,),
        )
        row = cur.fetchone()
        n = int(row["n"] or 0)
        revenue = int(row["revenue_cents"] or 0)
        return {
            "since": since,
            "order_count": n,
            "revenue_cents": revenue,
            "revenue_yuan": round(revenue / 100.0, 2),
            "pro_orders": int(row["pro_orders"] or 0),
            "credit_orders": int(row["credit_orders"] or 0),
        }

    def create_pending_payment(
        self,
        *,
        provider: str,
        external_id: str,
        device_id: str,
        product: str,
        amount_cents: int = 0,
        currency: str = "CNY",
        raw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Insert pending ledger row (or return existing)."""
        return self.record_payment(
            provider=provider,
            external_id=external_id,
            device_id=device_id,
            product=product,
            amount_cents=amount_cents,
            currency=currency,
            status="pending",
            raw=raw or {},
        )

    def fulfill_pending_or_new(
        self,
        *,
        provider: str,
        external_id: str,
        device_id: str,
        product: str,
        amount_cents: int = 0,
        currency: str = "CNY",
        days: int = 30,
        credits: int = 1,
        raw: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Idempotent fulfill: record succeeded payment + apply entitlement."""
        ledger = self.record_payment(
            provider=provider,
            external_id=external_id,
            device_id=device_id,
            product=product,
            amount_cents=amount_cents,
            currency=currency,
            status="succeeded",
            raw=raw or {},
        )
        # If first insert was pending with same key, UNIQUE blocks — handle update
        if ledger.get("duplicate"):
            existing = self.get_payment(provider=provider, external_id=external_id)
            if existing and str(existing.get("status", "")).lower() in (
                "succeeded",
                "success",
                "paid",
                "complete",
                "completed",
            ):
                ent = self.get_entitlement(
                    str(existing.get("device_id") or device_id)
                ).to_dict()
                return {
                    "ok": True,
                    "duplicate": True,
                    "payment_id": ledger.get("payment_id"),
                    "entitlement": ent,
                }
            # Upgrade pending → succeeded (first real fulfill; not a duplicate)
            self._conn.execute(
                """
                UPDATE payment_ledger
                SET status = 'succeeded',
                    device_id = ?,
                    product = ?,
                    amount_cents = ?,
                    raw_json = ?
                WHERE provider = ? AND external_id = ?
                """,
                (
                    (device_id or "")[:128],
                    (product or "")[:64],
                    int(amount_cents or 0),
                    json.dumps(raw or {}, ensure_ascii=False),
                    (provider or "demo")[:32],
                    (external_id or "")[:128],
                ),
            )
            self._conn.commit()
            ent_rec = self.apply_payment_product(
                device_id, product, days=days, credits=credits
            )
            return {
                "ok": True,
                "duplicate": False,
                "payment_id": ledger.get("payment_id"),
                "entitlement": ent_rec.to_dict(),
            }
        ent_rec = self.apply_payment_product(
            device_id, product, days=days, credits=credits
        )
        return {
            "ok": True,
            "duplicate": False,
            "payment_id": ledger.get("payment_id"),
            "entitlement": ent_rec.to_dict(),
        }

    def checkout(
        self,
        *,
        device_id: str,
        product: str,
        provider: str = "demo",
        amount_cents: int = 0,
        currency: str = "CNY",
        days: int = 30,
        credits: int = 1,
        external_id: str = "",
    ) -> Dict[str, Any]:
        """Demo checkout closed loop: ledger row + apply entitlement.

        For real gateways: create pending order here, return checkout URL;
        fulfillment still goes through ``record_payment`` + ``apply_payment_product``
        in the webhook handler (idempotent).
        """
        device_id = (device_id or "").strip() or "anonymous"
        product = (product or "package").strip().lower()
        provider = (provider or "demo").strip()[:32]
        ext = (external_id or "").strip() or f"{provider}_{uuid.uuid4().hex[:16]}"
        if amount_cents <= 0:
            amount_cents = 9900 if product in (
                "pro",
                "pro_month",
                "subscription_pro",
                "mingmirror_pro",
            ) else 1900

        # Non-demo: pending order only (no entitlement until webhook)
        if provider not in ("demo", "local", "test"):
            try:
                from server.payments import build_pending_checkout

                pending = build_pending_checkout(
                    provider=provider,
                    device_id=device_id,
                    product=product,
                    amount_cents=amount_cents,
                    currency=currency,
                    days=days,
                    credits=credits,
                    external_id=ext,
                )
                self.create_pending_payment(
                    provider=pending["provider"],
                    external_id=pending["external_id"],
                    device_id=device_id,
                    product=product,
                    amount_cents=amount_cents,
                    currency=currency,
                    raw=pending,
                )
                return {
                    "ok": True,
                    "mode": "pending",
                    "provider": pending["provider"],
                    "external_id": pending["external_id"],
                    "status": "pending",
                    "amount_cents": amount_cents,
                    "currency": currency,
                    "product": product,
                    "checkout_url": pending.get("checkout_url") or "",
                    "prepay": pending.get("prepay") or {},
                    "duplicate": False,
                }
            except Exception:
                # Fall through to demo immediate if adapter import fails
                provider = "demo"

        ledger = self.record_payment(
            provider=provider,
            external_id=ext,
            device_id=device_id,
            product=product,
            amount_cents=amount_cents,
            currency=currency,
            status="succeeded",
            raw={
                "channel": "checkout",
                "days": days,
                "credits": credits,
            },
        )
        if ledger.get("duplicate"):
            ent = self.get_entitlement(device_id)
            return {
                "ok": True,
                "duplicate": True,
                "payment_id": ledger.get("payment_id"),
                "external_id": ext,
                "provider": provider,
                "product": product,
                "entitlement": ent.to_dict(),
            }

        ent = self.apply_payment_product(
            device_id, product, days=days, credits=credits
        )
        self.track(
            "checkout_completed",
            device_id=device_id,
            props={
                "provider": provider,
                "product": product,
                "external_id": ext,
                "amount_cents": amount_cents,
            },
        )
        return {
            "ok": True,
            "duplicate": False,
            "payment_id": ledger.get("payment_id"),
            "external_id": ext,
            "provider": provider,
            "product": product,
            "amount_cents": amount_cents,
            "currency": currency,
            "entitlement": ent.to_dict(),
        }

    def admin_grant(
        self,
        device_id: str,
        *,
        action: str = "pro",
        days: int = 30,
        credits: int = 1,
    ) -> EntitlementRecord:
        """Manual grant from admin board (no payment)."""
        device_id = (device_id or "").strip() or "anonymous"
        action = (action or "pro").strip().lower()
        if action == "pro":
            rec = self.activate_pro(device_id, days=max(1, days))
        elif action in ("credit", "package"):
            rec = self.add_credits(device_id, n=max(1, credits))
        else:
            raise ValueError("action must be pro or credit")
        self.track(
            "admin_grant",
            device_id=device_id,
            props={"action": action, "days": days, "credits": credits},
        )
        return rec

    @staticmethod
    def _payment_row(row: sqlite3.Row) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except json.JSONDecodeError:
            raw = {}
        return {
            "id": row["id"],
            "provider": row["provider"],
            "external_id": row["external_id"],
            "device_id": row["device_id"],
            "product": row["product"],
            "amount_cents": int(row["amount_cents"] or 0),
            "currency": row["currency"],
            "status": row["status"],
            "raw": raw,
            "created_at": int(row["created_at"] or 0),
            "created_at_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(row["created_at"] or 0))
            ),
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]
