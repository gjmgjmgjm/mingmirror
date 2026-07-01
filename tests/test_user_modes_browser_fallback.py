"""Tests for like/mix/music browser fallback in core/user_modes/."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.user_modes.like_strategy import LikeUserModeStrategy
from core.user_modes.mix_strategy import MixUserModeStrategy
from core.user_modes.music_strategy import MusicUserModeStrategy


def _make_aweme(aweme_id: str):
    return {
        "aweme_id": aweme_id,
        "create_time": 1700000000,
        "video": {"play_addr": {"url_list": ["https://example.com/video.mp4"]}},
    }


class _NoopRateLimiter:
    async def acquire(self):
        return


class _MockAPI:
    BASE_URL = "https://www.douyin.com"
    headers = {"User-Agent": "test-agent"}

    def __init__(self, empty: bool = False):
        self.empty = empty
        self.calls = []
        self.detail_calls = []

    async def get_user_like(self, _sec_uid, max_cursor=0, count=20):
        self.calls.append(("get_user_like", max_cursor))
        if self.empty:
            return {"items": [], "has_more": False, "max_cursor": max_cursor}
        if max_cursor > 0:
            return {"items": [], "has_more": False, "max_cursor": max_cursor}
        return {"items": [_make_aweme("like-1")], "has_more": False, "max_cursor": 0}

    async def get_user_mix(self, _sec_uid, max_cursor=0, count=20):
        self.calls.append(("get_user_mix", max_cursor))
        if self.empty:
            return {"items": [], "has_more": False, "max_cursor": max_cursor}
        return {"items": [{"aweme_id": "mix-1"}], "has_more": False, "max_cursor": 0}

    async def get_user_music(self, _sec_uid, max_cursor=0, count=20):
        self.calls.append(("get_user_music", max_cursor))
        if self.empty:
            return {"items": [], "has_more": False, "max_cursor": max_cursor}
        return {"items": [{"aweme_id": "music-1"}], "has_more": False, "max_cursor": 0}

    async def get_video_detail(self, aweme_id, suppress_error=True):
        self.detail_calls.append(aweme_id)
        return _make_aweme(aweme_id)

    def _browser_cookie_payload(self):
        return []

    def _sync_browser_cookies(self, _cookies):
        pass


def _make_downloader(api_client, browser_enabled: bool = True):
    class _Downloader:
        def __init__(self):
            self.api_client = api_client
            self.rate_limiter = _NoopRateLimiter()
            self.database = None
            self.config = type(
                "Cfg",
                (),
                {
                    "get": lambda _self, key, default=None: {
                        "number": {"like": 0, "mix": 0, "music": 0},
                        "increase": {"like": False, "mix": False, "music": False},
                        "browser_fallback": {
                            "enabled": browser_enabled,
                            "headless": False,
                            "max_scrolls": 10,
                            "idle_rounds": 2,
                            "wait_timeout_seconds": 600,
                        },
                    }.get(key, default)
                },
            )()
            self._filter_by_time = lambda items: items
            self._limit_count = lambda items, _mode: items

    return _Downloader()


def _mock_async_playwright(*, evaluate_results=None, closed=False, goto_error=None):
    """Return a MagicMock tree that mimics Playwright's async API."""
    evaluate_results = evaluate_results or [[]]
    evaluate_iter = iter(evaluate_results)

    page = MagicMock()
    page.is_closed = MagicMock(return_value=closed)
    page.title = AsyncMock(return_value="")
    page.evaluate = AsyncMock(side_effect=lambda _script: next(evaluate_iter, []))
    page.mouse.wheel = AsyncMock()
    page.wait_for_timeout = AsyncMock()

    if goto_error:
        page.goto = AsyncMock(side_effect=goto_error)
    else:
        page.goto = AsyncMock()

    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.add_cookies = AsyncMock()
    context.cookies = AsyncMock(return_value=[])
    context.close = AsyncMock()

    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()

    playwright_instance = MagicMock()
    playwright_instance.chromium.launch = AsyncMock(return_value=browser)

    async_manager = MagicMock()
    async_manager.__aenter__ = AsyncMock(return_value=playwright_instance)
    async_manager.__aexit__ = AsyncMock(return_value=False)

    mock_playwright = MagicMock()
    mock_playwright.return_value = async_manager
    return mock_playwright


class TestLikeStrategyBrowserFallback:
    def test_api_success_does_not_trigger_fallback(self):
        api = _MockAPI(empty=False)
        downloader = _make_downloader(api)
        strategy = LikeUserModeStrategy(downloader)

        with patch("core.user_modes.browser_fallback.async_playwright") as mock_pw:
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["like-1"]
        assert ("get_user_like", 0) in api.calls
        mock_pw.assert_not_called()

    def test_api_empty_triggers_fallback(self):
        api = _MockAPI(empty=True)
        downloader = _make_downloader(api)
        strategy = LikeUserModeStrategy(downloader)

        mock_pw = _mock_async_playwright(evaluate_results=[["fb-1", "fb-2"]])
        with patch("core.user_modes.browser_fallback.async_playwright", mock_pw):
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["fb-1", "fb-2"]
        assert api.detail_calls == ["fb-1", "fb-2"]

    def test_fallback_disabled_returns_empty(self):
        api = _MockAPI(empty=True)
        downloader = _make_downloader(api, browser_enabled=False)
        strategy = LikeUserModeStrategy(downloader)

        with patch("core.user_modes.browser_fallback.async_playwright") as mock_pw:
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert items == []
        mock_pw.assert_not_called()

    def test_fallback_returns_empty_when_browser_collects_nothing(self):
        api = _MockAPI(empty=True)
        downloader = _make_downloader(api)
        strategy = LikeUserModeStrategy(downloader)

        mock_pw = _mock_async_playwright(evaluate_results=[[]])
        with patch("core.user_modes.browser_fallback.async_playwright", mock_pw):
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert items == []

    def test_fallback_error_returns_empty(self):
        api = _MockAPI(empty=True)
        downloader = _make_downloader(api)
        strategy = LikeUserModeStrategy(downloader)

        mock_pw = _mock_async_playwright(goto_error=RuntimeError("browser crashed"))
        with patch("core.user_modes.browser_fallback.async_playwright", mock_pw):
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert items == []


class TestMixStrategyBrowserFallback:
    def test_api_success_does_not_trigger_fallback(self):
        api = _MockAPI(empty=False)
        downloader = _make_downloader(api)
        strategy = MixUserModeStrategy(downloader)

        with patch("core.user_modes.browser_fallback.async_playwright") as mock_pw:
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["mix-1"]
        mock_pw.assert_not_called()

    def test_api_empty_triggers_fallback(self):
        api = _MockAPI(empty=True)
        downloader = _make_downloader(api)
        strategy = MixUserModeStrategy(downloader)

        mock_pw = _mock_async_playwright(evaluate_results=[["mix-fb-1"]])
        with patch("core.user_modes.browser_fallback.async_playwright", mock_pw):
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["mix-fb-1"]

    def test_metadata_items_do_not_trigger_fallback(self):
        """When API returns metadata (mix_info), strategy should expand, not use browser."""
        class _MetaAPI(_MockAPI):
            async def get_user_mix(self, _sec_uid, max_cursor=0, count=20):
                self.calls.append(("get_user_mix", max_cursor))
                return {
                    "items": [{"mix_info": {"mix_id": "mix-1"}}],
                    "has_more": False,
                    "max_cursor": 0,
                }

            async def get_mix_aweme(self, _mix_id, cursor=0, count=20):
                return {"items": [{"aweme_id": "mix-aweme-1"}], "has_more": False, "max_cursor": 0}

        api = _MetaAPI()
        downloader = _make_downloader(api)
        strategy = MixUserModeStrategy(downloader)

        with patch("core.user_modes.browser_fallback.async_playwright") as mock_pw:
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["mix-aweme-1"]
        mock_pw.assert_not_called()


class TestMusicStrategyBrowserFallback:
    def test_api_success_does_not_trigger_fallback(self):
        api = _MockAPI(empty=False)
        downloader = _make_downloader(api)
        strategy = MusicUserModeStrategy(downloader)

        with patch("core.user_modes.browser_fallback.async_playwright") as mock_pw:
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["music-1"]
        mock_pw.assert_not_called()

    def test_api_empty_triggers_fallback(self):
        api = _MockAPI(empty=True)
        downloader = _make_downloader(api)
        strategy = MusicUserModeStrategy(downloader)

        mock_pw = _mock_async_playwright(evaluate_results=[["music-fb-1", "music-fb-2"]])
        with patch("core.user_modes.browser_fallback.async_playwright", mock_pw):
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["music-fb-1", "music-fb-2"]

    def test_metadata_items_do_not_trigger_fallback(self):
        class _MetaAPI(_MockAPI):
            async def get_user_music(self, _sec_uid, max_cursor=0, count=20):
                self.calls.append(("get_user_music", max_cursor))
                return {
                    "items": [{"music_info": {"id": "music-1"}}],
                    "has_more": False,
                    "max_cursor": 0,
                }

            async def get_music_aweme(self, _music_id, cursor=0, count=20):
                return {"items": [{"aweme_id": "music-aweme-1"}], "has_more": False, "max_cursor": 0}

        api = _MetaAPI()
        downloader = _make_downloader(api)
        strategy = MusicUserModeStrategy(downloader)

        with patch("core.user_modes.browser_fallback.async_playwright") as mock_pw:
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["music-aweme-1"]
        mock_pw.assert_not_called()


class TestBrowserFallbackHelpers:
    def test_playwright_unavailable_returns_empty(self):
        api = _MockAPI(empty=True)
        downloader = _make_downloader(api)
        strategy = LikeUserModeStrategy(downloader)

        with patch("core.user_modes.browser_fallback.async_playwright", None):
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert items == []

    def test_expected_count_limits_browser_collection(self):
        api = _MockAPI(empty=True)
        downloader = _make_downloader(api)
        # Override number limit for like
        downloader.config = type(
            "Cfg",
            (),
            {
                "get": lambda _self, key, default=None: {
                    "number": {"like": 2, "mix": 0, "music": 0},
                    "increase": {"like": False, "mix": False, "music": False},
                    "browser_fallback": {
                        "enabled": True,
                        "headless": False,
                        "max_scrolls": 10,
                        "idle_rounds": 2,
                        "wait_timeout_seconds": 600,
                    },
                }.get(key, default)
            },
        )()
        strategy = LikeUserModeStrategy(downloader)

        # Provide many ids across scroll rounds; only first 2 should be fetched.
        mock_pw = _mock_async_playwright(
            evaluate_results=[["a", "b", "c", "d"], ["e", "f"]]
        )
        with patch("core.user_modes.browser_fallback.async_playwright", mock_pw):
            items = asyncio.run(strategy.collect_items("sec_uid_x", {"uid": "uid-1"}))

        assert [item["aweme_id"] for item in items] == ["a", "b"]
