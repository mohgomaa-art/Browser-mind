import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('https://demoqa.com/text-box')
        
        # We wait for the #permanentAddress to appear
        el = page.locator('#permanentAddress')
        await el.wait_for(state="attached")
        
        # Let's get the outer HTML of its parent or grandparent to see the label structure
        parent = page.locator('#permanentAddress').locator('xpath=..')
        grandparent = page.locator('#permanentAddress').locator('xpath=../..')
        
        print("--- PARENT HTML ---")
        print(await parent.evaluate("el => el.outerHTML"))
        
        print("\n--- GRANDPARENT HTML ---")
        print(await grandparent.evaluate("el => el.outerHTML"))
        
        # Let's also ask Playwright what it thinks the label is
        labels = await el.evaluate("el => el.labels ? Array.from(el.labels).map(l => l.outerHTML) : []")
        print(f"\n--- ATTACHED LABELS ---")
        print(labels)
        
        await browser.close()

asyncio.run(main())
