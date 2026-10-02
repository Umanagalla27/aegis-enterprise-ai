import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "media"

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        page = await b.new_page(viewport={'width': 1440, 'height': 900})
        await page.goto('http://localhost:8000', wait_until='networkidle')

        # Click Multi-Agent & Security
        await page.locator("button:has-text('Multi-Agent & Security')").click()
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUTPUT_DIR / "port_8000_tab_multiagent_security.png"))
        print("[+] Captured tab-agent")

        # Click Localhost Service Hub & Fixes
        await page.locator("button:has-text('Localhost Service Hub')").click()
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(OUTPUT_DIR / "port_8000_tab_localhost_hub.png"))
        print("[+] Captured tab-hub")

        await b.close()

if __name__ == "__main__":
    asyncio.run(run())
