#!/usr/bin/env python3
"""Account system: users, sessions, device linking (SQLite).

Standalone of Douyin cookie auth. Used by MingMirror product for
register/login and attaching anonymous device_id → user ownership.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD = 8
_SESSION_DAYS = 30


def _now() -> int:
    return int(time.time())


def hash_password(password: str, *, salt: Optional[bytes] = None) -> str:
    """PBKDF2-HMAC-SHA256 password hash (stdlib only). Format: pbkdf2$iter$salt$hex."""
    if salt is None:
        salt = secrets.token_bytes(16)
    iters = 200_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return f"pbkdf2${iters}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_hex, hash_hex = (stored or "").split("$", 3)
        if algo != "pbkdf2":
            return False
        iters = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def validate_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not e or not _EMAIL_RE.match(e) or len(e) > 254:
        raise ValueError("invalid email")
    return e


def validate_password(password: str) -> str:
    p = password or ""
    if len(p) < _MIN_PASSWORD:
        raise ValueError(f"password must be at least {_MIN_PASSWORD} characters")
    if len(p) > 128:
        raise ValueError("password too long")
    return p


@dataclass
class UserRecord:
    id: str
    email: str
    display_name: str
    created_at: int
    updated_at: int
    is_active: bool = True

    def to_public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active,
        }


@dataclass
class SessionRecord:
    token: str
    user_id: str
    device_id: str
    expires_at: int
    created_at: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AccountStore:
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
            CREATE TABLE IF NOT EXISTS account_user (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_account_email ON account_user(email);

            CREATE TABLE IF NOT EXISTS account_session (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL DEFAULT '',
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_session_user ON account_session(user_id);
            CREATE INDEX IF NOT EXISTS idx_session_expires ON account_session(expires_at);

            CREATE TABLE IF NOT EXISTS account_device (
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                linked_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, device_id)
            );
            CREATE INDEX IF NOT EXISTS idx_device_id ON account_device(device_id);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def register(
        self,
        email: str,
        password: str,
        *,
        display_name: str = "",
        device_id: str = "",
    ) -> tuple[UserRecord, SessionRecord]:
        email = validate_email(email)
        password = validate_password(password)
        now = _now()
        uid = uuid.uuid4().hex
        name = (display_name or email.split("@")[0] or "命主").strip()[:64]
        try:
            self._conn.execute(
                """
                INSERT INTO account_user
                (id, email, password_hash, display_name, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (uid, email, hash_password(password), name, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("email already registered") from exc
        self._conn.commit()
        user = UserRecord(
            id=uid,
            email=email,
            display_name=name,
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        session = self.create_session(uid, device_id=device_id)
        if device_id:
            self.link_device(uid, device_id)
        return user, session

    def login(
        self, email: str, password: str, *, device_id: str = ""
    ) -> tuple[UserRecord, SessionRecord]:
        email = validate_email(email)
        row = self._conn.execute(
            "SELECT * FROM account_user WHERE email = ?", (email,)
        ).fetchone()
        if row is None or not row["is_active"]:
            raise ValueError("invalid email or password")
        if not verify_password(password, row["password_hash"]):
            raise ValueError("invalid email or password")
        user = self._row_user(row)
        session = self.create_session(user.id, device_id=device_id)
        if device_id:
            self.link_device(user.id, device_id)
        return user, session

    def create_session(self, user_id: str, *, device_id: str = "") -> SessionRecord:
        now = _now()
        token = secrets.token_urlsafe(32)
        expires = now + _SESSION_DAYS * 86400
        self._conn.execute(
            """
            INSERT INTO account_session (token, user_id, device_id, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token, user_id, (device_id or "")[:128], expires, now),
        )
        self._conn.commit()
        return SessionRecord(
            token=token,
            user_id=user_id,
            device_id=(device_id or "")[:128],
            expires_at=expires,
            created_at=now,
        )

    def logout(self, token: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM account_session WHERE token = ?", ((token or "").strip(),)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def logout_all(self, user_id: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM account_session WHERE user_id = ?", (user_id,)
        )
        self._conn.commit()
        return cur.rowcount

    def get_user_by_token(self, token: str) -> Optional[UserRecord]:
        token = (token or "").strip()
        if not token:
            return None
        now = _now()
        row = self._conn.execute(
            """
            SELECT u.* FROM account_session s
            JOIN account_user u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
            """,
            (token, now),
        ).fetchone()
        if row is None:
            return None
        return self._row_user(row)

    def get_user(self, user_id: str) -> Optional[UserRecord]:
        row = self._conn.execute(
            "SELECT * FROM account_user WHERE id = ?", (user_id,)
        ).fetchone()
        return self._row_user(row) if row else None

    def link_device(self, user_id: str, device_id: str) -> None:
        did = (device_id or "").strip()[:128]
        if not did:
            return
        now = _now()
        self._conn.execute(
            """
            INSERT INTO account_device (user_id, device_id, linked_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, device_id) DO UPDATE SET linked_at = excluded.linked_at
            """,
            (user_id, did, now),
        )
        self._conn.commit()

    def devices_for_user(self, user_id: str) -> List[str]:
        cur = self._conn.execute(
            "SELECT device_id FROM account_device WHERE user_id = ? ORDER BY linked_at DESC",
            (user_id,),
        )
        return [r["device_id"] for r in cur.fetchall()]

    def user_id_for_device(self, device_id: str) -> Optional[str]:
        did = (device_id or "").strip()
        if not did:
            return None
        row = self._conn.execute(
            """
            SELECT user_id FROM account_device
            WHERE device_id = ? ORDER BY linked_at DESC LIMIT 1
            """,
            (did,),
        ).fetchone()
        return row["user_id"] if row else None

    def change_password(
        self, user_id: str, old_password: str, new_password: str
    ) -> None:
        row = self._conn.execute(
            "SELECT password_hash FROM account_user WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ValueError("user not found")
        if not verify_password(old_password, row["password_hash"]):
            raise ValueError("invalid current password")
        new_password = validate_password(new_password)
        now = _now()
        self._conn.execute(
            """
            UPDATE account_user SET password_hash = ?, updated_at = ?
            WHERE id = ?
            """,
            (hash_password(new_password), now, user_id),
        )
        self._conn.commit()
        # Invalidate other sessions
        self.logout_all(user_id)

    def purge_expired_sessions(self) -> int:
        cur = self._conn.execute(
            "DELETE FROM account_session WHERE expires_at <= ?", (_now(),)
        )
        self._conn.commit()
        return cur.rowcount

    @staticmethod
    def _row_user(row: sqlite3.Row) -> UserRecord:
        return UserRecord(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"] or "",
            created_at=int(row["created_at"] or 0),
            updated_at=int(row["updated_at"] or 0),
            is_active=bool(row["is_active"]),
        )

    def entitlement_key(self, user_id: str) -> str:
        """Stable key for ProductStore entitlement rows owned by a user."""
        return f"user:{user_id}"
