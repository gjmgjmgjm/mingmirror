from __future__ import annotations

from typing import Any, Dict, List

from core.user_modes.base_strategy import BaseUserModeStrategy
from core.user_modes.browser_fallback import collect_aweme_ids_via_browser, fetch_aweme_details
from utils.logger import setup_logger

logger = setup_logger("MusicUserModeStrategy")


class MusicUserModeStrategy(BaseUserModeStrategy):
    mode_name = "music"
    api_method_name = "get_user_music"

    async def collect_items(self, sec_uid: str, user_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_items = await self._collect_paged_aweme(sec_uid, user_info)
        aweme_items = [
            a for item in raw_items if (a := self._extract_aweme_from_item(item)) is not None
        ]
        if aweme_items:
            return aweme_items

        if raw_items:
            return await self._expand_metadata_items(
                raw_items,
                id_field="music_id",
                id_aliases=["musicId"],
                fetch_method_name="get_music_aweme",
            )

        logger.warning("Music API returned empty, attempting browser fallback")
        fallback_items = await self._fallback_music_items(sec_uid)
        if fallback_items:
            return fallback_items

        return []

    async def _fallback_music_items(self, sec_uid: str) -> List[Dict[str, Any]]:
        browser_cfg = self.downloader.config.get("browser_fallback", {}) or {}
        if not browser_cfg.get("enabled", True):
            return []

        aweme_ids = await collect_aweme_ids_via_browser(
            self.downloader.api_client,
            sec_uid,
            self.mode_name,
            expected_count=int(
                self.downloader.config.get("number", {}).get(self.mode_name, 0) or 0
            ),
            headless=bool(browser_cfg.get("headless", False)),
            max_scrolls=int(browser_cfg.get("max_scrolls", 240) or 240),
            idle_rounds=int(browser_cfg.get("idle_rounds", 8) or 8),
            wait_timeout_seconds=int(browser_cfg.get("wait_timeout_seconds", 600) or 600),
        )

        if not aweme_ids:
            logger.warning("Browser fallback for music returned no aweme_id")
            return []

        return await fetch_aweme_details(
            self.downloader.api_client,
            self.downloader.rate_limiter,
            aweme_ids,
        )
