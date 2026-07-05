#!/usr/bin/env python3
"""Take screenshots of the Dashboard page for visual review."""

from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    output_dir = Path("screenshots")
    output_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # 1. Initial dashboard
        page.goto("http://localhost:5173/")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(output_dir / "01_dashboard_initial.png"), full_page=True)

        # 2. Scroll to form
        page.evaluate("window.scrollTo(0, 400)")
        page.wait_for_timeout(500)
        page.screenshot(path=str(output_dir / "02_form_focus.png"), full_page=False)

        # 3. Scroll time wheels into view for a close-up
        page.evaluate("window.scrollTo(0, 700)")
        page.wait_for_timeout(500)
        page.screenshot(path=str(output_dir / "03_time_wheels.png"), full_page=False)

        # 4. Generate chart using the pre-filled default date/time
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        page.click("button:has-text('生成命盘')")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(output_dir / "04_chart_result.png"), full_page=True)

        browser.close()
        print(f"Screenshots saved to {output_dir.absolute()}")


if __name__ == "__main__":
    main()
