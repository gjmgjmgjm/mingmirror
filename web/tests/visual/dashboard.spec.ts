import { test, expect } from "@playwright/test";

const FIXED_TIME = new Date("2026-07-08T12:00:00Z").getTime();

const routes = [
  { path: "/app/", name: "dashboard" },
  { path: "/app/chart", name: "chart" },
  { path: "/app/chart/yearly", name: "chart-yearly" },
  { path: "/app/ziwei", name: "ziwei" },
  { path: "/app/qizheng", name: "qizheng" },
  { path: "/app/cases", name: "cases" },
];

for (const route of routes) {
  test(`visual: ${route.name}`, async ({ page }) => {
    await page.addInitScript(`
      const FIXED_TIME = ${FIXED_TIME};
      Date.now = () => FIXED_TIME;
      const OriginalDate = Date;
      Date = class extends OriginalDate {
        constructor(...args) {
          super(...(args.length ? args : [FIXED_TIME]));
        }
      };
    `);
    await page.goto(route.path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    await expect(page).toHaveScreenshot(`${route.name}.png`, {
      fullPage: true,
      maxDiffPixels: 100,
    });
  });
}
