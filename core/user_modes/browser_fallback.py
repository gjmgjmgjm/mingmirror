from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Dict, List, Set

from utils.logger import setup_logger

if TYPE_CHECKING:
    from core.api_client import DouyinAPIClient

try:
    from playwright.async_api import async_playwright
except Exception:  # pragma: no cover
    async_playwright = None

logger = setup_logger("BrowserFallback")

_MODE_TABS = {
    "like": "like",
    "mix": "mix",
    "music": "music",
}


async def collect_aweme_ids_via_browser(
    api_client: "DouyinAPIClient",
    sec_uid: str,
    mode: str,
    *,
    expected_count: int = 0,
    headless: bool = False,
    max_scrolls: int = 240,
    idle_rounds: int = 8,
    wait_timeout_seconds: int = 600,
) -> List[str]:
    """Collect aweme_ids from a user profile tab using Playwright.

    Falls back to DOM parsing when API responses are blocked or empty. The
    caller is responsible for fetching aweme details afterwards.
    """
    if async_playwright is None:
        logger.warning("Playwright not available, browser fallback disabled")
        return []

    tab = _MODE_TABS.get(mode, mode)
    target_url = f"{api_client.BASE_URL}/user/{sec_uid}?showTab={tab}"
    timeout_ms = max(30, int(wait_timeout_seconds)) * 1000
    ids: List[str] = []
    seen: Set[str] = set()

    logger.warning(
        "API collection failed for mode=%s, starting browser fallback: %s",
        mode,
        target_url,
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=api_client.headers.get("User-Agent", ""),
            locale="zh-CN",
            viewport={"width": 1600, "height": 900},
        )
        cookies = api_client._browser_cookie_payload()
        if cookies:
            await context.add_cookies(cookies)

        page = await context.new_page()

        try:
            try:
                await page.goto(
                    target_url, wait_until="domcontentloaded", timeout=timeout_ms
                )
            except Exception as exc:
                logger.warning("Browser goto timeout or error, continue: %s", exc)

            title = ""
            try:
                title = await page.title()
            except Exception:
                pass
            if "验证码" in title:
                if headless:
                    logger.warning(
                        "检测到验证码页面且当前为 headless 模式，无法人工验证。"
                    )
                    return []
                logger.warning("检测到验证码页面，请在浏览器中完成验证。")
                await _wait_for_manual_verification(page, wait_timeout_seconds)

            warmup_seconds = min(20, max(3, int(wait_timeout_seconds)))
            for _ in range(warmup_seconds):
                if page.is_closed():
                    break
                _merge(ids, seen, await _extract_aweme_ids_from_page(page))
                if ids:
                    break
                await page.wait_for_timeout(1000)

            stable_rounds = 0
            max_scroll_rounds = max(1, int(max_scrolls))
            idle_stop_rounds = max(1, int(idle_rounds))

            for _ in range(max_scroll_rounds):
                if page.is_closed():
                    break
                await page.mouse.wheel(0, 3800)
                await page.wait_for_timeout(1200)

                before = len(ids)
                _merge(ids, seen, await _extract_aweme_ids_from_page(page))
                if len(ids) == before:
                    stable_rounds += 1
                else:
                    stable_rounds = 0

                if expected_count > 0 and len(ids) >= expected_count:
                    break
                if expected_count <= 0 and stable_rounds >= idle_stop_rounds:
                    break
        finally:
            try:
                browser_cookies = await context.cookies(api_client.BASE_URL)
                api_client._sync_browser_cookies(browser_cookies)
            except Exception as exc:
                logger.debug("Sync browser cookies skipped: %s", exc)
            await context.close()
            await browser.close()

    if expected_count > 0:
        ids = ids[:expected_count]
    logger.warning("Browser fallback for mode=%s collected %s aweme_ids", mode, len(ids))
    return ids


async def fetch_aweme_details(
    api_client: "DouyinAPIClient",
    rate_limiter,
    aweme_ids: List[str],
) -> List[Dict[str, Any]]:
    """Fetch aweme details for a list of aweme_ids, honoring rate limiting."""
    details: List[Dict[str, Any]] = []
    for aweme_id in aweme_ids:
        await rate_limiter.acquire()
        detail = await api_client.get_video_detail(aweme_id, suppress_error=True)
        if detail and isinstance(detail, dict):
            details.append(detail)
    return details


def _merge(ids: List[str], seen: Set[str], new_ids: List[str]) -> None:
    for aweme_id in new_ids:
        if aweme_id and aweme_id not in seen:
            seen.add(aweme_id)
            ids.append(aweme_id)


async def _extract_aweme_ids_from_page(page) -> List[str]:
    script = """
    () => {
      const result = [];
      const seen = new Set();
      const push = (id) => {
        if (!id || seen.has(id)) return;
        seen.add(id);
        result.push(id);
      };
      const collectFrom = (text, pattern) => {
        if (!text) return;
        let match;
        while ((match = pattern.exec(text)) !== null) {
          push(match[1]);
        }
      };
      const links = document.querySelectorAll("a[href]");
      for (const node of links) {
        const href = node.getAttribute("href") || "";
        collectFrom(href, /\\/video\\/(\\d{15,20})/g);
        collectFrom(href, /\\/note\\/(\\d{15,20})/g);
      }
      const html = document.documentElement ? document.documentElement.innerHTML : "";
      collectFrom(html, /"aweme_id":"(\\d{15,20})"/g);
      collectFrom(html, /"group_id":"(\\d{15,20})"/g);
      return result;
    }
    """
    try:
        data = await page.evaluate(script)
        if isinstance(data, list):
            return [str(x) for x in data if x]
    except Exception as exc:
        logger.debug("Extract aweme_id from page failed: %s", exc)
    return []


async def _wait_for_manual_verification(page, wait_timeout_seconds: int) -> None:
    deadline = asyncio.get_running_loop().time() + max(30, int(wait_timeout_seconds))
    while asyncio.get_running_loop().time() < deadline:
        if page.is_closed():
            logger.warning("Browser page closed while waiting manual verification")
            return
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        if "验证码" not in title:
            logger.warning("验证码页面已退出，继续采集。")
            return
        await page.wait_for_timeout(1000)
    logger.warning("等待手动验证超时（%ss），继续按当前页面状态采集。", wait_timeout_seconds)
