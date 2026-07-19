#!/usr/bin/env python3
"""截图验证获客落地页(Dashboard 无命盘态 → Landing)。

前置:后端 :8000(fetchDemoCharts 需要)+ vite :5173。
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://localhost:5174/app"
OUT = Path("screenshots")
OUT.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 1000})

        # 清 localStorage,确保无命盘 → Landing 渲染
        await page.goto(f"{BASE}/", wait_until="domcontentloaded")
        await page.evaluate("localStorage.removeItem('mingmirror_active_chart_v1')")
        await page.goto(f"{BASE}/", wait_until="domcontentloaded")

        # 等 Landing hero 出现
        await page.wait_for_selector("text=命运数字孪生", timeout=15000)
        await asyncio.sleep(1.5)  # 等动画 + demo 卡加载

        await page.screenshot(path=str(OUT / "landing_full.png"), full_page=True)
        print("saved screenshots/landing_full.png")

        # 截近景:免费样例命书区
        try:
            await page.locator("text=免费样例命书").first.scroll_into_view_if_needed(timeout=5000)
            await asyncio.sleep(0.6)
            await page.screenshot(path=str(OUT / "landing_samples.png"))
            print("saved screenshots/landing_samples.png")
        except Exception as e:
            print("scroll samples skip:", e)

        # 点第一个 demo 卡 → 进命书(验证钩子)
        try:
            await page.locator("text=看一份样例命书").first.click(timeout=5000)
            await asyncio.sleep(2.0)
            await page.screenshot(path=str(OUT / "landing_after_demo.png"), full_page=False)
            print("saved screenshots/landing_after_demo.png")
        except Exception as e:
            print("demo click skip:", e)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
