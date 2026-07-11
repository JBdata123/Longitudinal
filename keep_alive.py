"""
Visits the deployed Streamlit app with a real headless browser (a plain
HTTP request isn't enough - Streamlit needs an actual page load to wake up
or to reset its "last active" clock) and clicks the "Yes, get this app
back up!" button if the app has gone to sleep.

Run automatically on a schedule via .github/workflows/keep-alive.yml -
no need to run this yourself.
"""
import asyncio
import os
import sys
from playwright.async_api import async_playwright

# Set this to your real deployed app URL (or override via env var STREAMLIT_URL)
STREAMLIT_URL = os.environ.get("STREAMLIT_URL", "https://mdjdfnfovkdojedd.streamlit.app/")


async def visit(url: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        await page.wait_for_timeout(5000)

        wake_btn = page.get_by_role("button", name="Yes, get this app back up!")
        if await wake_btn.count() > 0:
            await wake_btn.click()
            await page.wait_for_timeout(60_000)  # give it time to actually spin up
            await browser.close()
            return "WOKE UP (was sleeping)"

        await browser.close()
        return "OK (already awake)"


def main():
    if "YOUR-APP-NAME" in STREAMLIT_URL:
        print("Set STREAMLIT_URL (env var or edit this file) to your real app URL.")
        sys.exit(1)
    result = asyncio.run(visit(STREAMLIT_URL))
    print(f"{STREAMLIT_URL} -> {result}")


if __name__ == "__main__":
    main()