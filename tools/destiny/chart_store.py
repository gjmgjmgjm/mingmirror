#!/usr/bin/env python3
"""Persistent chart (命盘) store — product identity layer.

Each chart has a stable UUID independent of the bazi string, so events,
calibration, and exports survive birth-time tweaks and multi-device use.

``chart_id`` in event APIs may be either:
- a UUID stored here, or
- a legacy bazi string (still accepted for backward compatibility).
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def is_chart_uuid(value: str) -> bool:
    return bool(value and _UUID_RE.match(value.strip()))


@dataclass
class ChartRecord:
    id: str
    bazi: str
    gender: str = "male"
    birth_date: str = ""
    birth_time: str = ""
    calendar_type: str = "solar"
    location: Optional[Dict[str, Any]] = None
    label: str = ""
    # Anonymous device isolation (browser localStorage id). Empty = legacy/public.
    device_id: str = ""
    # Logged-in account owner (MingMirror user id). Empty = device-only.
    user_id: str = ""
    created_at: int = 0
    updated_at: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def create(
        cls,
        bazi: str,
        gender: str = "male",
        birth_date: str = "",
        birth_time: str = "",
        calendar_type: str = "solar",
        location: Optional[Dict[str, Any]] = None,
        label: str = "",
        chart_id: Optional[str] = None,
        device_id: str = "",
        user_id: str = "",
    ) -> "ChartRecord":
        now = int(time.time())
        bazi = (bazi or "").strip()
        if not bazi:
            raise ValueError("bazi is required")
        return cls(
            id=chart_id or str(uuid.uuid4()),
            bazi=bazi,
            gender=(gender or "male").strip() or "male",
            birth_date=(birth_date or "").strip(),
            birth_time=(birth_time or "").strip(),
            calendar_type=(calendar_type or "solar").strip() or "solar",
            location=location,
            label=(label or "").strip() or bazi,
            device_id=(device_id or "").strip(),
            user_id=(user_id or "").strip(),
            created_at=now,
            updated_at=now,
        )


class ChartStore:
    """SQLite-backed chart registry (sync API, same style as SqliteEventStore)."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chart (
                id TEXT PRIMARY KEY,
                bazi TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT 'male',
                birth_date TEXT NOT NULL DEFAULT '',
                birth_time TEXT NOT NULL DEFAULT '',
                calendar_type TEXT NOT NULL DEFAULT 'solar',
                location_json TEXT,
                label TEXT NOT NULL DEFAULT '',
                device_id TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chart_bazi ON chart(bazi);
            CREATE INDEX IF NOT EXISTS idx_chart_updated ON chart(updated_at);
            CREATE INDEX IF NOT EXISTS idx_chart_device ON chart(device_id);
            CREATE INDEX IF NOT EXISTS idx_chart_user ON chart(user_id);
            """
        )
        # Incremental migration for DBs created before device_id / user_id.
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(chart)").fetchall()
        }
        if "device_id" not in cols:
            self._conn.execute(
                "ALTER TABLE chart ADD COLUMN device_id TEXT NOT NULL DEFAULT ''"
            )
        if "user_id" not in cols:
            self._conn.execute(
                "ALTER TABLE chart ADD COLUMN user_id TEXT NOT NULL DEFAULT ''"
            )
        self._conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> ChartRecord:
        loc = None
        raw = row["location_json"]
        if raw:
            try:
                loc = json.loads(raw)
            except json.JSONDecodeError:
                loc = None
        keys = row.keys()
        return ChartRecord(
            id=row["id"],
            bazi=row["bazi"],
            gender=row["gender"] or "male",
            birth_date=row["birth_date"] or "",
            birth_time=row["birth_time"] or "",
            calendar_type=row["calendar_type"] or "solar",
            location=loc,
            label=row["label"] or row["bazi"],
            device_id=(row["device_id"] if "device_id" in keys else "") or "",
            user_id=(row["user_id"] if "user_id" in keys else "") or "",
            created_at=int(row["created_at"] or 0),
            updated_at=int(row["updated_at"] or 0),
        )

    def save(self, chart: ChartRecord) -> ChartRecord:
        chart.updated_at = int(time.time())
        if not chart.created_at:
            chart.created_at = chart.updated_at
        self._conn.execute(
            """
            INSERT INTO chart
            (id, bazi, gender, birth_date, birth_time, calendar_type,
             location_json, label, device_id, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                bazi=excluded.bazi,
                gender=excluded.gender,
                birth_date=excluded.birth_date,
                birth_time=excluded.birth_time,
                calendar_type=excluded.calendar_type,
                location_json=excluded.location_json,
                label=excluded.label,
                device_id=excluded.device_id,
                user_id=excluded.user_id,
                updated_at=excluded.updated_at
            """,
            (
                chart.id,
                chart.bazi,
                chart.gender,
                chart.birth_date,
                chart.birth_time,
                chart.calendar_type,
                json.dumps(chart.location, ensure_ascii=False)
                if chart.location
                else None,
                chart.label or chart.bazi,
                chart.device_id or "",
                chart.user_id or "",
                chart.created_at,
                chart.updated_at,
            ),
        )
        self._conn.commit()
        return chart

    def get(self, chart_id: str) -> Optional[ChartRecord]:
        cur = self._conn.execute(
            "SELECT * FROM chart WHERE id = ?", (chart_id.strip(),)
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def get_by_bazi(
        self,
        bazi: str,
        *,
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[ChartRecord]:
        """Most recently updated chart with this exact bazi string.

        Prefer ``user_id`` scope when set (cross-device), else ``device_id``.
        """
        bazi = bazi.strip()
        uid = (user_id or "").strip()
        did = (device_id or "").strip()
        if uid:
            cur = self._conn.execute(
                """
                SELECT * FROM chart WHERE bazi = ? AND user_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (bazi, uid),
            )
        elif did:
            cur = self._conn.execute(
                """
                SELECT * FROM chart WHERE bazi = ? AND device_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (bazi, did),
            )
        else:
            cur = self._conn.execute(
                """
                SELECT * FROM chart WHERE bazi = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (bazi,),
            )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def list(
        self,
        limit: int = 50,
        *,
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[ChartRecord]:
        limit = max(1, min(int(limit or 50), 200))
        uid = (user_id or "").strip()
        did = (device_id or "").strip()
        if uid:
            cur = self._conn.execute(
                """
                SELECT * FROM chart WHERE user_id = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (uid, limit),
            )
        elif did:
            cur = self._conn.execute(
                """
                SELECT * FROM chart WHERE device_id = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (did, limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM chart ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        return [self._row_to_record(r) for r in cur.fetchall()]

    def claim_device_charts(self, user_id: str, device_id: str) -> int:
        """Attach all charts of device_id to user_id (cross-device ownership)."""
        uid = (user_id or "").strip()
        did = (device_id or "").strip()
        if not uid or not did:
            return 0
        cur = self._conn.execute(
            """
            UPDATE chart SET user_id = ?, updated_at = ?
            WHERE device_id = ? AND (user_id = '' OR user_id IS NULL)
            """,
            (uid, int(time.time()), did),
        )
        self._conn.commit()
        return int(cur.rowcount or 0)

    def assert_device_access(
        self,
        chart_id: str,
        device_id: str,
        *,
        allow_legacy_empty: bool = True,
        user_id: str = "",
    ) -> ChartRecord:
        """Raise PermissionError if device/user may not access this chart UUID."""
        rec = self.get(chart_id)
        if rec is None:
            raise KeyError("chart not found")
        uid = (user_id or "").strip()
        owner_user = (rec.user_id or "").strip()
        if uid and owner_user and uid == owner_user:
            return rec
        did = (device_id or "").strip()
        owner = (rec.device_id or "").strip()
        if not owner and not owner_user:
            if allow_legacy_empty:
                return rec
            raise PermissionError("chart has no device owner")
        if owner and did and did == owner:
            return rec
        if owner_user and uid and uid == owner_user:
            return rec
        if not owner and not owner_user and allow_legacy_empty:
            return rec
        raise PermissionError("chart not owned by this device/user")

    def delete(self, chart_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM chart WHERE id = ?", (chart_id.strip(),)
        )
        self._conn.commit()
        return bool(cur.rowcount and cur.rowcount > 0)

    def resolve_bazi(self, chart_id_or_bazi: str) -> str:
        """Resolve path param to bazi string (UUID → lookup, else passthrough)."""
        key = (chart_id_or_bazi or "").strip()
        if not key:
            return ""
        if is_chart_uuid(key):
            rec = self.get(key)
            return rec.bazi if rec else ""
        return key

    def resolve_chart_id(self, chart_id_or_bazi: str) -> str:
        """Prefer UUID when known; for legacy bazi return bazi string."""
        key = (chart_id_or_bazi or "").strip()
        if not key:
            return ""
        if is_chart_uuid(key):
            return key if self.get(key) else ""
        return key

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]
