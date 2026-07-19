#!/usr/bin/env python3
"""验证 ShareCard:进报告页点「分享命盘」→ 捕获生成的海报 PNG。

前置:后端 :8000 + vite :5174。
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://localhost:5174/app"
BAZI = "乙卯 戊寅 庚子 丙子"
OUT = Path("screenshots")
OUT.mkdir(exist_ok=True)

CHART = json.dumps({
    "id": "demo-share-verify", "bazi": BAZI, "gender": "male",
    "birth_date": "", "birth_time": "", "calendar_type": "solar",
    "label": "分享验证", "created_at": 1, "updated_at": 1,
}, ensure_ascii=False)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
        await page.add_init_script(
            f"localStorage.setItem('mingmirror_active_chart_v1', {json.dumps(CHART)})"
        )
        await page.goto(f"{BASE}/chart/report", wait_until="domcontentloaded")
        await page.wait_for_selector("text=神煞", timeout=30000)
        await asyncio.sleep(1.2)

        btn = page.locator("button:has-text('分享命盘')")
        print("found 分享命盘 button:", await btn.count())
        async with page.expect_download(timeout=30000) as di:
            await btn.first.click()
        dl = await di.value
        out = OUT / "share_poster.png"
        await dl.save_as(str(out))
        print("saved", out, out.stat().st_size, "bytes")

        # 看 hint 文案
        hint = await page.locator("text=海报已生成").count()
        print("success hint shown:", hint > 0)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
