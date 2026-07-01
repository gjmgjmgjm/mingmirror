"""自动获取抖音 Cookie（无需按 Enter，等待固定时间后自动保存）"""
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from utils.cookie_utils import parse_cookie_header, sanitize_cookies

DEFAULT_URL = "https://www.douyin.com/"
WAIT_SECONDS = 90
REQUIRED_KEYS = {"msToken", "ttwid", "odin_tt", "passport_csrf_token"}
SUGGESTED_KEYS = REQUIRED_KEYS | {"sid_guard", "sessionid", "sid_tt"}
DEFAULT_AUXILIARY_KEYS = {
    "_waftokenid",
    "s_v_web_id",
    "__ac_nonce",
    "__ac_signature",
    "UIFID",
    "UIFID_TEMP",
    "d_ticket",
    "x-web-secsdk-uid",
    "__security_server_data_status",
}
DEFAULT_AUXILIARY_PREFIXES = (
    "__security_mc_",
    "bd_ticket_guard_",
    "_bd_ticket_crypt_",
)


def extract_ms_token_from_text(text: str):
    import re
    from urllib.parse import unquote

    if not text:
        return None
    patterns = [
        r"(?:^|[;,&\s\"'])msToken=([^;,&\s\"']+)",
        r'"msToken"\s*:\s*"([^"]+)"',
        r"'msToken'\s*:\s*'([^']+)'",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            token = (match.group(1) or "").strip()
            if token:
                return unquote(token)
    return None


async def capture_cookies(url: str, output: Path, config_path: Path):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        observed_cookie_headers = []
        observed_mstokens = []

        def _on_request(request):
            try:
                headers = request.headers or {}
                cookie_header = headers.get("cookie")
                if cookie_header:
                    observed_cookie_headers.append(cookie_header)
                url = request.url or ""
                query = parse_qs(urlparse(url).query)
                if "msToken" in query and query["msToken"]:
                    observed_mstokens.append((query["msToken"][0] or "").strip())
                token = extract_ms_token_from_text(url)
                if token:
                    observed_mstokens.append(token)
            except Exception:
                pass

        page.on("request", _on_request)

        print(f"[INFO] 浏览器已启动，请在 {WAIT_SECONDS} 秒内登录抖音")
        print("[INFO] 登录成功后保持页面打开，程序会自动保存 Cookie")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=300_000)
        except Exception as exc:
            print(f"[WARN] 页面加载异常: {exc}")

        # 等待用户登录
        for i in range(WAIT_SECONDS, 0, -1):
            if i % 10 == 0:
                print(f"[INFO] 还剩 {i} 秒，请完成登录...")
            await asyncio.sleep(1)

        storage = await context.storage_state()
        cookies = {
            cookie["name"]: cookie["value"]
            for cookie in storage["cookies"]
            if cookie["domain"].endswith("douyin.com")
        }
        cookies = sanitize_cookies(cookies)

        # 尝试从多处提取 msToken
        ms_token = None
        for token in reversed(observed_mstokens):
            token = (token or "").strip()
            if token:
                ms_token = token
                break
        if not ms_token:
            for header in reversed(observed_cookie_headers):
                parsed = parse_cookie_header(header)
                token = (parsed.get("msToken") or "").strip()
                if token:
                    ms_token = token
                    break
                extra = extract_ms_token_from_text(header)
                if extra:
                    ms_token = extra
                    break
        if not ms_token:
            try:
                doc_cookie = await page.evaluate("() => document.cookie || ''")
                parsed = parse_cookie_header(doc_cookie)
                ms_token = (parsed.get("msToken") or "").strip() or None
            except Exception:
                pass

        if ms_token and not cookies.get("msToken"):
            cookies["msToken"] = ms_token
            print("[INFO] 已从其他来源提取 msToken")

        await context.close()
        await browser.close()

    picked = filter_cookies(cookies)
    picked = sanitize_cookies(picked)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(picked, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] 已保存 {len(picked)} 个 Cookie 到 {output.resolve()}")

    missing = REQUIRED_KEYS - picked.keys()
    if missing:
        print(f"[WARN] 缺少关键 Cookie: {', '.join(sorted(missing))}")
        print("[WARN] 请重新运行并确保登录成功")
    else:
        print("[INFO] 所有关键 Cookie 已获取")

    if config_path.exists():
        update_config(config_path, picked)

    return 0 if not missing else 1


def filter_cookies(cookies):
    cookies = sanitize_cookies(cookies)
    picked = {}
    for key, value in cookies.items():
        if key in SUGGESTED_KEYS or key in DEFAULT_AUXILIARY_KEYS:
            picked[key] = value
            continue
        if any(key.startswith(prefix) for prefix in DEFAULT_AUXILIARY_PREFIXES):
            picked[key] = value
    if not picked:
        return cookies
    return picked


def update_config(config_path: Path, cookies):
    existing = {}
    if config_path.exists():
        existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    existing["cookies"] = cookies
    config_path.write_text(yaml.safe_dump(existing, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"[INFO] 已更新配置文件: {config_path.resolve()}")


if __name__ == "__main__":
    output = Path("config/cookies.json")
    config = Path("config.yml")
    exit_code = asyncio.run(capture_cookies(DEFAULT_URL, output, config))
    sys.exit(exit_code)
