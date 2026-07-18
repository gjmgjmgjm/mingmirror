#!/usr/bin/env python3
"""截图验证神煞前端渲染(绕开表单,直接注入 ChartContext localStorage)。

前置:后端 :8000(已 proxy)+ vite :5173。
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://localhost:5173/app"
BAZI = "乙卯 戊寅 庚子 丙子"
OUT = Path("screenshots")
OUT.mkdir(exist_ok=True)

CHART = json.dumps({
    "id": "demo-shensha-verify",
    "bazi": BAZI,
    "gender": "male",
    "birth_date": "",
    "birth_time": "",
    "calendar_type": "solar",
    "label": "神煞验证",
    "created_at": 1700000000000,
    "updated_at": 1700000000000,
}, ensure_ascii=False)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 1000})

        # 先到 origin,再注入 localStorage
        await page.goto(f"{BASE}/", wait_until="domcontentloaded")
        await page.evaluate(
            "([k,v]) => localStorage.setItem(k, v)",
            ["mingmirror_active_chart_v1", CHART],
        )

        # ---- 报告页 ----
        await page.goto(f"{BASE}/chart/report", wait_until="domcontentloaded")
        await page.wait_for_selector("text=神煞", timeout=30000)
        await asyncio.sleep(1.5)
        await page.screenshot(path=str(OUT / "shensha_report.png"), full_page=True)
        print("saved screenshots/shensha_report.png")

        # 滚到神煞 section 再截一张近景
        try:
            await page.locator("text=神煞").first.scroll_into_view_if_needed(timeout=5000)
            await asyncio.sleep(0.6)
            await page.screenshot(path=str(OUT / "shensha_section.png"))
            print("saved screenshots/shensha_section.png")
        except Exception as e:
            print("scroll skip:", e)

        # ---- Calendar 页(择日日卡神煞 chips)----
        await page.goto(f"{BASE}/calendar", wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("text=首吉", timeout=45000)
            await asyncio.sleep(1.0)
        except Exception as e:
            print("calendar 首吉 wait failed:", e)
        await page.screenshot(path=str(OUT / "shensha_calendar.png"), full_page=True)
        print("saved screenshots/shensha_calendar.png")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
