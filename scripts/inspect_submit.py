import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('https://demoqa.com/text-box')
        
        el = page.locator('#submit')
        await el.wait_for(state="attached")
        
        print("--- SUBMIT HTML ---")
        print(await el.evaluate("el => el.outerHTML"))
        
        print("\n--- PLAYWRIGHT ROLE & NAME ---")
        # Try to resolve it via get_by_role
        try:
            # what role is it?
            tagName = await el.evaluate("el => el.tagName")
            inputType = await el.evaluate("el => el.type")
            print(f"Tag: {tagName}, Type: {inputType}")
            
            # Let's get accessible name according to playwright
            name = await el.evaluate("el => el.innerText || el.value || ''")
            print(f"Text content: {name.strip()}")
        except Exception as e:
            print(e)
            
        await browser.close()

asyncio.run(main())
