#!/usr/bin/env python3
"""生成 og-cover.png(1200x630 品牌海报)供社交分享预览。

用 playwright set_content + screenshot,避免额外渲染依赖。字幅走系统中文衬线回退。
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("web/public/og-cover.png")

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
* { margin:0; padding:0; box-sizing:border-box; }
html,body { width:1200px; height:630px; }
body {
  font-family: "Noto Serif SC","Songti SC","SimSun","Microsoft YaHei",serif;
  background:
    radial-gradient(circle at 80% 20%, rgba(201,162,39,0.18), transparent 55%),
    radial-gradient(circle at 15% 85%, rgba(197,61,47,0.14), transparent 55%),
    linear-gradient(135deg, #f4f1ea 0%, #e8e3d8 100%);
  color: #2c2824;
  display:flex; flex-direction:column; align-items:center; justify-content:center;
  position:relative; overflow:hidden;
}
.ring { position:absolute; border-radius:9999px; opacity:0.4; }
.r1 { top:-60px; right:-60px; width:260px; height:260px; border:2px solid rgba(197,61,47,0.35); }
.r2 { bottom:-50px; left:-50px; width:200px; height:200px; border:2px solid rgba(201,162,39,0.35); }
.seal {
  width:132px; height:132px; border:5px solid #c53d2f; border-radius:18px;
  display:flex; align-items:center; justify-content:center;
  font-size:74px; font-weight:700; color:#c53d2f; letter-spacing:6px;
  background: rgba(255,255,255,0.5); margin-bottom:34px;
  font-family: "Zhi Mang Xing","Noto Serif SC","Songti SC","SimSun",serif;
}
h1 { font-size:64px; font-weight:700; letter-spacing:2px; color:#2c2824; margin-bottom:18px; }
.sub { font-size:30px; color:#7a746a; letter-spacing:3px; margin-bottom:30px; }
.tags { display:flex; gap:14px; }
.tags span {
  font-size:22px; color:#5a8f7b; background:rgba(90,143,123,0.12);
  padding:8px 20px; border-radius:9999px;
}
.brand { position:absolute; bottom:30px; right:40px; font-size:20px; color:#a89e8a; letter-spacing:2px; }
</style></head><body>
  <div class="ring r1"></div>
  <div class="ring r2"></div>
  <div class="seal">命镜</div>
  <h1>生成你的命运数字孪生</h1>
  <div class="sub">可计算 · 可验证 · 可交互</div>
  <div class="tags"><span>排盘 100%</span><span>用神 90%</span><span>结构层可复核</span></div>
  <div class="brand">MingMirror</div>
</body></html>"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        await page.set_content(HTML, wait_until="domcontentloaded")
        await asyncio.sleep(0.6)
        await page.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        print("saved", OUT)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
