import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "media"

async def capture_tabs():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://localhost:8000", wait_until="networkidle")

        # Tab mapping
        tabs = [
            ("tab-rag", "port_8000_tab_rag_topology.png"),
            ("tab-security", "port_8000_tab_security_guardrails.png"),
            ("tab-rca", "port_8000_tab_incident_rca.png"),
            ("tab-airflow", "port_8000_tab_airflow_pyspark.png"),
            ("tab-eval", "port_8000_tab_eval_chaos.png"),
        ]

        for tab_id, filename in tabs:
            try:
                # Click the tab button
                btn = page.locator(f"button[onclick*='{tab_id}']")
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(800)
                    await page.screenshot(path=str(OUTPUT_DIR / filename))
                    print(f"[+] Captured {filename}")
                else:
                    # Try clicking by text
                    text_map = {
                        "tab-rag": "Hybrid RAG",
                        "tab-security": "Security",
                        "tab-rca": "Incident RCA",
                        "tab-airflow": "Airflow",
                        "tab-eval": "Eval",
                    }
                    t_btn = page.get_by_text(text_map.get(tab_id, ""), exact=False)
                    if await t_btn.count() > 0:
                        await t_btn.first.click()
                        await page.wait_for_timeout(800)
                        await page.screenshot(path=str(OUTPUT_DIR / filename))
                        print(f"[+] Captured {filename} by text")
            except Exception as e:
                print(f"Error capturing {tab_id}: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_tabs())
