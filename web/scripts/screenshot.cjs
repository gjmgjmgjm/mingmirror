const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  });

  try {
    await page.goto('http://localhost:5173/app/', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2500);

    // Inspect hero section
    const hero = await page.locator('h1').filter({ hasText: '生成你的命运数字孪生' }).first();
    if (await hero.isVisible().catch(() => false)) {
      const box = await hero.boundingBox();
      const styles = await hero.evaluate((el) => {
        const computed = window.getComputedStyle(el);
        return {
          opacity: computed.opacity,
          display: computed.display,
          visibility: computed.visibility,
          color: computed.color,
          transform: computed.transform,
        };
      });
      console.log('Hero found:', box, styles);
    } else {
      console.log('Hero NOT visible');
      const html = await page.content();
      console.log('Contains 生成你的命运数字孪生:', html.includes('生成你的命运数字孪生'));
    }

    // Full page
    await page.screenshot({ path: 'scripts/dashboard-full.png', fullPage: true });

    // Focus on the form card top area
    const formCard = await page.locator('form').first();
    if (await formCard.isVisible().catch(() => false)) {
      await formCard.screenshot({ path: 'scripts/dashboard-form-top.png' });
    }

    console.log('Screenshots saved to web/scripts/');
  } catch (err) {
    console.error('Screenshot failed:', err.message);
    await page.screenshot({ path: 'scripts/dashboard-error.png' });
  } finally {
    await browser.close();
  }
})();
