"""Compare AX trees of github.com vs github.com/login to understand semantic signals."""
import asyncio, json, sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page

async def main():
    urls = [
        "https://github.com",
        "https://github.com/login",
        "https://www.google.com",
        "https://duckduckgo.com",
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        for url in urls:
            try:
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                
                ax = await build_graph_from_page(page)
                nodes = ax.get("nodes", [])
                
                print(f"\n{'='*80}")
                print(f"URL: {url}")
                print(f"{'='*80}")
                
                # Collect semantic signals
                names_lower = []
                has_password = False
                for n in nodes:
                    name = n.get("name", "").lower()
                    role = n.get("role", "")
                    names_lower.append(name)
                    
                    # Check for password fields
                    if "password" in name or "passwd" in name:
                        has_password = True
                
                all_names = " | ".join(n.get("name","") for n in nodes if n.get("name","").strip())
                
                # Semantic keyword scan
                login_kw = ["sign in", "log in", "login", "password", "username"]
                signup_kw = ["sign up", "create account", "register", "join", "confirm password"]
                search_kw = ["search", "find", "query", "lookup"]
                newsletter_kw = ["subscribe", "newsletter", "updates", "notify me"]
                landing_kw = ["get started", "learn more", "try for free", "start free", "pricing"]
                
                def scan(keywords):
                    return [kw for kw in keywords if kw in " ".join(names_lower)]
                
                print(f"\nTotal nodes: {len(nodes)}")
                print(f"Has password field: {has_password}")
                print(f"\nLogin signals:      {scan(login_kw)}")
                print(f"Signup signals:     {scan(signup_kw)}")
                print(f"Search signals:     {scan(search_kw)}")
                print(f"Newsletter signals: {scan(newsletter_kw)}")
                print(f"Landing signals:    {scan(landing_kw)}")
                
                # Show interactive nodes only
                print(f"\nInteractive elements:")
                for n in nodes:
                    role = n.get("role", "")
                    if role in ("textbox", "button", "searchbox", "combobox", "checkbox", "radio"):
                        print(f"  [{role:>10s}] {n.get('name','')[:70]}")
                        
                await page.close()
            except Exception as e:
                print(f"\n[ERROR] {url}: {e}")
                
        await browser.close()

asyncio.run(main())
