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
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chart_bazi ON chart(bazi);
            CREATE INDEX IF NOT EXISTS idx_chart_updated ON chart(updated_at);
            """
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
        return ChartRecord(
            id=row["id"],
            bazi=row["bazi"],
            gender=row["gender"] or "male",
            birth_date=row["birth_date"] or "",
            birth_time=row["birth_time"] or "",
            calendar_type=row["calendar_type"] or "solar",
            location=loc,
            label=row["label"] or row["bazi"],
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
             location_json, label, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                bazi=excluded.bazi,
                gender=excluded.gender,
                birth_date=excluded.birth_date,
                birth_time=excluded.birth_time,
                calendar_type=excluded.calendar_type,
                location_json=excluded.location_json,
                label=excluded.label,
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

    def get_by_bazi(self, bazi: str) -> Optional[ChartRecord]:
        """Most recently updated chart with this exact bazi string."""
        cur = self._conn.execute(
            """
            SELECT * FROM chart WHERE bazi = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (bazi.strip(),),
        )
        row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def list(self, limit: int = 50) -> List[ChartRecord]:
        limit = max(1, min(int(limit or 50), 200))
        cur = self._conn.execute(
            "SELECT * FROM chart ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_record(r) for r in cur.fetchall()]

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
