import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://github.com/microsoft/playwright")
        
        # Test generic role
        try:
            candidate = page.get_by_role("generic", name="Issues", exact=False)
            count = await candidate.count()
            print(f"Count for role='generic' name='Issues': {count}")
        except Exception as e:
            print(f"Error generic: {e}")

        # Test link role (often Issues is an anchor tag)
        try:
            candidate = page.get_by_role("link", name="Issues", exact=False)
            count = await candidate.count()
            print(f"Count for role='link' name='Issues': {count}")
        except Exception as e:
            print(f"Error link: {e}")
            
        await browser.close()

asyncio.run(main())
