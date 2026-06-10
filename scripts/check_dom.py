import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('https://demoqa.com/text-box')
        
        try:
            loc = page.get_by_role("textbox", name="Full Name", exact=True)
            count = await loc.count()
            print(f"Exact count: {count}")
            
            loc2 = page.get_by_role("textbox", name="Full Name", exact=False)
            count2 = await loc2.count()
            print(f"Partial count: {count2}")
            
            # What does get_by_placeholder return?
            loc3 = page.get_by_placeholder("Full Name", exact=True)
            print(f"Placeholder exact count: {await loc3.count()}")

        except Exception as e:
            print(e)
            
        await browser.close()

asyncio.run(main())
