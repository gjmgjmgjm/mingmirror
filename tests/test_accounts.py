"""Account system: register / login / session / device link."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from server.accounts import (
    AccountStore,
    hash_password,
    validate_email,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("secret-pass-99")
    assert verify_password("secret-pass-99", h)
    assert not verify_password("wrong", h)


def test_validate_email():
    assert validate_email("A@B.COM") == "a@b.com"
    with pytest.raises(ValueError):
        validate_email("not-an-email")


def test_register_login_session(tmp_path: Path):
    store = AccountStore(tmp_path / "acc.db")
    user, sess = store.register(
        "user@example.com",
        "password12",
        display_name="测主",
        device_id="dev-1",
    )
    assert user.email == "user@example.com"
    assert sess.token
    me = store.get_user_by_token(sess.token)
    assert me is not None
    assert me.id == user.id
    assert "dev-1" in store.devices_for_user(user.id)

    user2, sess2 = store.login(
        "user@example.com", "password12", device_id="dev-2"
    )
    assert user2.id == user.id
    assert sess2.token != sess.token
    assert "dev-2" in store.devices_for_user(user.id)

    with pytest.raises(ValueError):
        store.login("user@example.com", "bad-password")

    with pytest.raises(ValueError):
        store.register("user@example.com", "password12")

    store.logout(sess.token)
    assert store.get_user_by_token(sess.token) is None
    store.close()


def test_change_password_revokes_sessions(tmp_path: Path):
    store = AccountStore(tmp_path / "acc2.db")
    user, sess = store.register("b@c.d", "password12")
    store.change_password(user.id, "password12", "newpass999")
    assert store.get_user_by_token(sess.token) is None
    _, sess_new = store.login("b@c.d", "newpass999")
    assert store.get_user_by_token(sess_new.token) is not None
    store.close()


def test_entitlement_merge(tmp_path: Path):
    from tools.destiny.product_store import ProductStore

    ps = ProductStore(tmp_path / "prod.db")
    ps.add_credits("anon-dev", 3)
    ps.activate_pro("anon-dev", days=7)
    merged = ps.merge_device_into_user("user:abc", "anon-dev")
    d = merged.to_dict()
    assert d["plan"] == "pro"
    assert d["package_credits"] >= 3
    # device zeroed
    assert ps.get_entitlement("anon-dev").package_credits == 0
