#!/usr/bin/env python3
"""Screenshot the YearlyChart page to verify DaYun timeline."""
import asyncio

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:5173"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto(f"{BASE_URL}/")
        await page.wait_for_selector("button:has-text('手动输入八字')", timeout=10000)

        # Switch to manual bazi input
        await page.click("button:has-text('手动输入八字')")
        await page.fill("#manualBazi", "癸未 己未 甲申 壬申")

        # Select gender
        await page.click("button:has-text('男')")
        await asyncio.sleep(0.2)

        # Submit form (client-side navigation keeps ChartContext)
        await page.click("button:has-text('生成命盘')")
        await page.wait_for_selector("a[href='/chart']", timeout=15000)
        await page.click("a[href='/chart']")
        await page.wait_for_selector("text=基础分析", timeout=15000)

        # Switch to yearly tab and generate analysis
        await page.click("a[href='/chart/yearly']")
        await page.wait_for_selector("text=大运时间轴", timeout=15000)
        await page.click("button:has-text('生成流年精排')")
        await page.wait_for_selector("text=2026年", timeout=90000)
        await asyncio.sleep(1)

        await page.screenshot(path="screenshots/yearly_dayun.png", full_page=True)
        print("saved screenshots/yearly_dayun.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
