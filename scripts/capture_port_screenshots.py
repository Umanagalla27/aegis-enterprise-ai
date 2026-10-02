import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "media"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

async def capture_screenshots():
    print(f"[*] Saving screenshots to: {OUTPUT_DIR}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 1. Port 8000 - Aegis Dashboard & Tabs
        print("[1/4] Capturing Port 8000 (Aegis Web Control Center)...")
        await page.goto("http://localhost:8000", wait_until="networkidle")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUTPUT_DIR / "port_8000_aegis_dashboard.png"), full_page=False)

        # Full page view
        await page.screenshot(path=str(OUTPUT_DIR / "port_8000_aegis_fullpage.png"), full_page=True)

        # 2. Port 9091 - Prometheus UI
        print("[2/4] Capturing Port 9091 (Prometheus Metrics UI)...")
        try:
            await page.goto("http://localhost:9091/graph?g0.expr=aegis_http_requests_total&g0.tab=1&g0.stacked=0&g0.show_exemplars=0&g0.range_input=1h", wait_until="networkidle")
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUTPUT_DIR / "port_9091_prometheus.png"), full_page=False)
        except Exception as e:
            print(f"Error on 9091: {e}")

        # 3. Port 3001 - Grafana UI
        print("[3/4] Capturing Port 3001 (Grafana UI)...")
        try:
            await page.goto("http://localhost:3001", wait_until="networkidle")
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUTPUT_DIR / "port_3001_grafana.png"), full_page=False)
        except Exception as e:
            print(f"Error on 3001: {e}")

        # 4. Port 5000 - MLflow UI
        print("[4/4] Capturing Port 5000 (MLflow UI)...")
        try:
            await page.goto("http://localhost:5000", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            await page.screenshot(path=str(OUTPUT_DIR / "port_5000_mlflow.png"), full_page=False)
        except Exception as e:
            print(f"Error on 5000: {e}")

        await browser.close()
    print("[+] All screenshots captured successfully!")

if __name__ == "__main__":
    asyncio.run(capture_screenshots())
