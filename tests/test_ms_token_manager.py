from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auth.ms_token_manager import MsTokenManager


def test_gen_false_ms_token_format():
    token = MsTokenManager.gen_false_ms_token()
    assert isinstance(token, str)
    assert token.endswith("==")
    assert len(token) == 184


def test_extract_ms_token_from_headers():
    class _Headers:
        def get_all(self, key):
            if key != "Set-Cookie":
                return []
            return [
                "foo=bar; Path=/",
                "msToken=abc123; expires=Wed, 25 Feb 2026 00:00:00 GMT; Path=/",
            ]

    token = MsTokenManager._extract_ms_token_from_headers(_Headers())
    assert token == "abc123"


def test_extract_ms_token_from_aiohttp_headers():
    """The helper should also support aiohttp's ``getall`` method."""

    class _AiohttpHeaders:
        def getall(self, key):
            if key != "Set-Cookie":
                return []
            return ["msToken=aiohttp456; Path=/"]

    token = MsTokenManager._extract_ms_token_from_headers(_AiohttpHeaders())
    assert token == "aiohttp456"


def test_ensure_ms_token_prefers_existing_cookie():
    manager = MsTokenManager(user_agent="test")
    assert manager.ensure_ms_token({"msToken": "existing"}) == "existing"


@pytest.mark.asyncio
async def test_aensure_ms_token_prefers_existing_cookie():
    manager = MsTokenManager(user_agent="test")
    assert await manager.aensure_ms_token({"msToken": "existing"}) == "existing"


@pytest.mark.asyncio
async def test_aensure_ms_token_returns_false_fallback_when_conf_missing():
    manager = MsTokenManager(user_agent="test")
    with patch.object(manager, "_async_load_f2_ms_token_conf", return_value=None):
        token = await manager.aensure_ms_token({})
    assert isinstance(token, str)
    assert len(token) == 184


@pytest.mark.asyncio
async def test_aensure_ms_token_generates_real_token_when_endpoint_succeeds():
    manager = MsTokenManager(user_agent="test")
    conf = {
        "url": "https://example.com/mssdk",
        "magic": "m",
        "version": "v",
        "dataType": "d",
        "strData": "s",
        "ulr": "u",
    }
    with patch.object(manager, "_async_load_f2_ms_token_conf", return_value=conf):
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.headers = MagicMock()
        mock_resp.headers.getall = MagicMock(
            return_value=["msToken=" + "x" * 182 + "==; Path=/"]
        )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            token = await manager.aensure_ms_token({})

    assert token.endswith("==")
    assert len(token) == 184
