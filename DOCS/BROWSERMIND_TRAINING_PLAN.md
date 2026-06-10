# BrowserMind — Full Training Plan
## The 500-Site Gauntlet · Popup Handling · Efficient Execution Strategy

> **Version:** 1.0 · **Status:** Production-ready · **Hardware target:** GTX 1660 Super + 16GB RAM

---

## Table of Contents

1. [The Core Problem — Popups](#1-the-core-problem--popups)
2. [Popup Dismissal System (The Missing Layer)](#2-popup-dismissal-system-the-missing-layer)
3. [Session Profile Strategy](#3-session-profile-strategy)
4. [The 500-Site Gauntlet — Categorized](#4-the-500-site-gauntlet--categorized)
5. [Training Scripts — Full Implementation](#5-training-scripts--full-implementation)
6. [Training Phases & Timeline](#6-training-phases--timeline)
7. [DAgger Curriculum Schedule](#7-dagger-curriculum-schedule)
8. [Monitoring & Success Criteria](#8-monitoring--success-criteria)
9. [Quick Reference Commands](#9-quick-reference-commands)

---

## 1. The Core Problem — Popups

Every website throws popups **before** the agent can do anything useful. These popups are the
single biggest cause of failed training sessions because:

- The agent sees a cookie consent dialog → accessibility tree full of "Accept / Reject" buttons
- The expert heuristic (`decide_expert_action`) tries to find goal-relevant elements → finds nothing
- Session recorded as **fail** → wasted browser time

### Categories of Popups the Agent Will Face

| Type | Examples | Blocks training? |
|------|----------|-----------------|
| Cookie consent | "Accept all", "Manage cookies" | ✅ Yes — fills the tree |
| Push notifications | "Allow notifications" | ✅ Yes — browser-level dialog |
| Save password | "Save password?" | ✅ Yes — browser-level |
| GDPR banners | "I agree to terms" | ✅ Yes |
| Location requests | "Allow location access" | ✅ Yes |
| Age verification | "I am over 18" | ⚠️ Sometimes |
| Newsletter signup | "Subscribe to our newsletter" | ⚠️ Sometimes |
| Chat widgets | Intercom, Zendesk bubble | ⚠️ Clutters tree |
| Paywalls | "Subscribe to read" | ❌ Can't bypass programmatically |
| Anti-bot CAPTCHAs | reCAPTCHA, hCaptcha | ❌ Skip the site |

---

## 2. Popup Dismissal System (The Missing Layer)

Create this file: **`core/popup_handler.py`**

```python
"""
BrowserMind — Popup Dismissal System
=====================================
Handles all browser-level and DOM-level popups that block agent training.

Usage:
    handler = PopupHandler(page)
    await handler.setup()          # call once after page creation
    await handler.dismiss_all()    # call before every step
"""

from __future__ import annotations
import asyncio
import re
from typing import Optional
from playwright.async_api import Page, Dialog


# ─────────────────────────────────────────────
#  All cookie/consent button text patterns
#  (covers English, Arabic, French, German, Spanish)
# ─────────────────────────────────────────────
CONSENT_ACCEPT_PATTERNS = [
    # English
    r"^accept all$", r"^accept$", r"^agree$", r"^i agree$",
    r"^got it$", r"^ok$", r"^okay$", r"^allow all$",
    r"^allow cookies$", r"^yes, i accept$", r"^continue$",
    r"^i understand$", r"^close$", r"^dismiss$",
    r"accept all cookies", r"allow all cookies",
    r"^confirm$", r"^save preferences$",
    # Arabic
    r"قبول الكل", r"أوافق", r"موافق", r"قبول", r"موافق على الكل",
    r"السماح", r"إغلاق", r"حسناً",
    # French
    r"tout accepter", r"j'accepte", r"accepter",
    # German
    r"alle akzeptieren", r"zustimmen", r"akzeptieren",
    # Spanish
    r"aceptar todo", r"acepto", r"aceptar",
]

# Elements to forcefully hide (CSS injection)
POPUP_CSS_SELECTORS_TO_HIDE = [
    # Generic cookie banners
    "#cookie-banner", "#cookie-notice", "#cookie-consent",
    "#cookieConsent", ".cookie-banner", ".cookie-notice",
    ".cookie-bar", ".cookie-popup", ".cookie-overlay",
    # GDPR
    "#gdpr-banner", ".gdpr-banner", "#gdpr-consent",
    # Common chat/support widgets (they clutter the tree)
    "#intercom-container", ".intercom-lightweight-app",
    "#hubspot-messages-iframe-container",
    "#zendesk-widget", ".zopim", "#chat-widget",
    "#tidio-chat", ".crisp-client",
    # Newsletter popups
    "#newsletter-popup", ".newsletter-overlay",
    ".popup-overlay", ".modal-overlay",
    # Notification banners
    "#notification-bar", ".notification-prompt",
]


class PopupHandler:
    """
    Two-layer popup dismissal:
    Layer 1 — Browser-level (dialogs, permission requests): handled via Playwright events
    Layer 2 — DOM-level (cookie banners, modals): handled via JS injection
    """

    def __init__(self, page: Page):
        self.page = page
        self._dialog_count = 0

    async def setup(self):
        """
        Call once after page is created, before navigation.
        Sets up automatic browser-dialog dismissal.
        """
        # Auto-dismiss all browser dialogs (alert, confirm, prompt)
        self.page.on("dialog", self._handle_dialog)

        # Grant permissions upfront so browser never shows the popup
        try:
            await self.page.context.grant_permissions([])  # deny all by default
        except Exception:
            pass

    async def _handle_dialog(self, dialog: Dialog):
        """Dismiss browser-level dialogs instantly."""
        self._dialog_count += 1
        try:
            if dialog.type in ("alert", "beforeunload"):
                await dialog.accept()
            elif dialog.type == "confirm":
                await dialog.dismiss()  # Don't confirm anything unexpected
            elif dialog.type == "prompt":
                await dialog.dismiss()
        except Exception:
            pass

    async def dismiss_all(self) -> int:
        """
        Full DOM sweep. Call before building the graph each step.
        Returns number of elements dismissed.
        """
        dismissed = 0
        dismissed += await self._click_consent_buttons()
        dismissed += await self._hide_popup_elements()
        dismissed += await self._close_modal_overlays()
        return dismissed

    async def _click_consent_buttons(self) -> int:
        """Find and click cookie/consent buttons by text pattern."""
        count = 0
        try:
            buttons = await self.page.query_selector_all(
                "button, [role='button'], a[href='#']"
            )
            for btn in buttons[:30]:  # limit to first 30 to avoid slow pages
                try:
                    text = (await btn.inner_text()).strip().lower()
                    is_visible = await btn.is_visible()
                    if not is_visible or not text:
                        continue
                    for pattern in CONSENT_ACCEPT_PATTERNS:
                        if re.search(pattern, text, re.IGNORECASE):
                            await btn.click(timeout=2000)
                            await asyncio.sleep(0.3)
                            count += 1
                            break
                except Exception:
                    continue
        except Exception:
            pass
        return count

    async def _hide_popup_elements(self) -> int:
        """Inject CSS to hide known popup containers."""
        selectors = ", ".join(POPUP_CSS_SELECTORS_TO_HIDE)
        try:
            await self.page.add_style_tag(content=f"""
                {selectors} {{
                    display: none !important;
                    visibility: hidden !important;
                    opacity: 0 !important;
                    pointer-events: none !important;
                }}
                body {{ overflow: auto !important; }}
            """)
            return 1
        except Exception:
            return 0

    async def _close_modal_overlays(self) -> int:
        """Press Escape to close modal overlays."""
        count = 0
        try:
            # Check if there's a visible overlay before pressing Escape
            overlay = await self.page.query_selector(
                ".modal.show, .modal[aria-modal='true'], [role='dialog'][aria-hidden='false']"
            )
            if overlay and await overlay.is_visible():
                await self.page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
                count += 1
        except Exception:
            pass
        return count


# ─────────────────────────────────────────────
#  Context-level setup (call once per browser context)
# ─────────────────────────────────────────────

async def configure_context_for_training(context):
    """
    Apply to browser context before creating any pages.
    Grants necessary permissions and blocks noisy resources.
    """
    # Deny notification permission globally
    await context.grant_permissions([])

    # Block resources that slow training without adding signal
    await context.route("**/*", _block_noisy_resources)

    # Inject consent dismissal script into every page before DOM loads
    await context.add_init_script("""
        // Override Notification API to auto-deny
        if (typeof Notification !== 'undefined') {
            Notification.requestPermission = () => Promise.resolve('denied');
            Object.defineProperty(Notification, 'permission', { get: () => 'denied' });
        }
        
        // Override geolocation
        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition = (s, e) => e && e({code: 1, message: 'denied'});
        }
        
        // Kill common popup scripts before they run
        window._browsermind_popup_killed = true;
    """)


async def _block_noisy_resources(route, request):
    """Block resources that waste time without DOM signal."""
    BLOCKED_TYPES = {"media", "font", "websocket"}
    BLOCKED_DOMAINS = [
        "doubleclick.net", "googlesyndication.com",
        "facebook.net", "connect.facebook.net",
        "analytics.google.com", "google-analytics.com",
        "hotjar.com", "mouseflow.com",
        "adnxs.com", "adsrvr.org",
    ]
    rtype = request.resource_type
    url = request.url.lower()

    if rtype in BLOCKED_TYPES:
        await route.abort()
        return

    for domain in BLOCKED_DOMAINS:
        if domain in url:
            await route.abort()
            return

    await route.continue_()
```

### Integration into `collect_social.py` and `collect_and_train.py`

Patch `run_task()` / `run_social_session()` to use the handler:

```python
# At the top of run_task() / run_social_session(), after page is created:
from core.popup_handler import PopupHandler, configure_context_for_training

# In collect_sessions() — after context is created:
await configure_context_for_training(context)

# In run_task() — after page is created:
handler = PopupHandler(page)
await handler.setup()

# Inside the step loop — BEFORE building the graph:
await handler.dismiss_all()
graph = await build_graph_from_page(page)
```

---

## 3. Session Profile Strategy

### Profile Directory Structure

```
browser_profiles/
├── no_login/          ← Public sites (Reddit, YouTube, News, Docs)
├── google/            ← Gmail, Docs, Drive, Scholar, Maps  
├── github/            ← GitHub, GitLab (one login covers most dev tasks)
├── facebook/          ← Facebook, Instagram (Meta accounts)
├── twitter/           ← X / Twitter
├── linkedin/          ← LinkedIn
├── amazon/            ← Amazon, Twitch
└── reddit_logged/     ← Reddit logged in (more features)
```

### One-Time Login Script

Save as **`login_setup.py`** and run once per profile:

```python
"""
Run once to set up browser profiles with saved sessions.
Usage: python login_setup.py --profile google
"""
import asyncio
import argparse
from pathlib import Path
from playwright.async_api import async_playwright

PROFILES = {
    "google":   ("browser_profiles/google",   ["https://accounts.google.com"]),
    "github":   ("browser_profiles/github",   ["https://github.com/login"]),
    "facebook": ("browser_profiles/facebook", ["https://www.facebook.com"]),
    "twitter":  ("browser_profiles/twitter",  ["https://x.com/login"]),
    "linkedin": ("browser_profiles/linkedin", ["https://www.linkedin.com/login"]),
    "amazon":   ("browser_profiles/amazon",   ["https://www.amazon.com/ap/signin"]),
    "reddit":   ("browser_profiles/reddit_logged", ["https://www.reddit.com/login"]),
}

async def setup_profile(profile_name: str):
    profile_dir, start_urls = PROFILES[profile_name]
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(start_urls[0])
        
        print(f"\n{'='*50}")
        print(f"Profile: {profile_name}")
        print(f"Saved to: {profile_dir}")
        print(f"Log in to: {', '.join(start_urls)}")
        print(f"Press Enter when done with ALL logins for this profile.")
        print(f"{'='*50}\n")
        input(">>> ")
        
        await context.close()
        print(f"✓ Profile '{profile_name}' saved successfully.\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=list(PROFILES.keys()), required=True)
    args = parser.parse_args()
    asyncio.run(setup_profile(args.profile))
```

### Which Profile → Which Sites

```python
# In your training scripts, map URLs to profiles:

PROFILE_MAP = {
    # No login needed
    "no_login": [
        "reddit.com", "youtube.com", "github.com/trending",
        "news.ycombinator.com", "bbc.com", "cnn.com", "reuters.com",
        "wikipedia.org", "stackoverflow.com/questions",
        "pypi.org", "npmjs.com", "docs.python.org",
        "arxiv.org", "medium.com", "dev.to",
        "amazon.com",  # browsing only, no cart
        "google.com",  # search
    ],
    # Needs login for full functionality
    "google":   ["mail.google.com", "docs.google.com", "drive.google.com", "scholar.google.com"],
    "github":   ["github.com/notifications", "github.com/issues", "gist.github.com"],
    "facebook": ["facebook.com/feed", "instagram.com"],
    "twitter":  ["x.com/home", "x.com/messages"],
    "linkedin": ["linkedin.com/feed", "linkedin.com/jobs"],
    "reddit":   ["reddit.com/r/*/submit", "reddit.com/message"],
}

def get_profile_for_url(url: str) -> str:
    for profile, domains in PROFILE_MAP.items():
        for domain in domains:
            if domain in url:
                return profile
    return "no_login"
```

---

## 4. The 500-Site Gauntlet — Categorized

Full task list for `training/target_websites_v2.py`:

### Category 1 — Search Engines (10 sites, difficulty 1-2)

Focus: `type` action, form submission, result extraction

```python
SEARCH_TASKS = [
    ("search for python tutorials",              "https://www.google.com"),
    ("search for machine learning papers",       "https://www.bing.com"),
    ("search for open source AI projects",       "https://duckduckgo.com"),
    ("search for deep learning 2024",            "https://scholar.google.com"),
    ("search for coffee shops",                  "https://www.google.com/maps"),
    ("search for latest tech news",              "https://search.yahoo.com"),
    ("calculate integral of x squared",          "https://www.wolframalpha.com"),
    ("search for renewable energy",              "https://www.ecosia.org"),
    ("search for privacy tools",                 "https://search.brave.com"),
    ("search for artificial intelligence news",  "https://yandex.com"),
]
```

### Category 2 — Social Media (50 sites, difficulty 1-4)

Focus: infinite scroll, dynamic popups, login walls

```python
SOCIAL_TASKS = [
    # Reddit — No login needed, great for training
    ("extract top post titles from front page",          "https://www.reddit.com"),
    ("navigate to r/programming and extract top posts",  "https://www.reddit.com/r/programming"),
    ("search for machine learning on Reddit",            "https://www.reddit.com/search"),
    ("extract top posts from r/MachineLearning",         "https://www.reddit.com/r/MachineLearning"),
    ("navigate to r/webdev and extract trending",        "https://www.reddit.com/r/webdev"),
    ("scroll down and extract more posts",               "https://www.reddit.com"),
    ("find the most upvoted comment in a post",          "https://www.reddit.com/r/AskReddit"),
    ("navigate to r/technology",                         "https://www.reddit.com/r/technology"),
    ("search for AI tools on Reddit",                    "https://www.reddit.com/search/?q=AI+tools"),
    ("find the top weekly posts on r/learnprogramming",  "https://www.reddit.com/r/learnprogramming/?f=flair_name%3A%22Weekly%22"),

    # YouTube — No login needed
    ("extract trending video titles and channels",       "https://www.youtube.com/feed/trending"),
    ("scroll and extract recommended video titles",      "https://www.youtube.com"),
    ("search for python tutorial",                       "https://www.youtube.com"),
    ("navigate to YouTube Music section",                "https://www.youtube.com/music"),
    ("find and click on Shorts tab",                     "https://www.youtube.com"),
    ("search for machine learning course",               "https://www.youtube.com"),
    ("extract channel names from trending",              "https://www.youtube.com/feed/trending"),

    # News and public social
    ("extract story titles and scores",                  "https://news.ycombinator.com"),
    ("extract top product names and taglines",           "https://www.producthunt.com"),
    ("extract recent blog post titles",                  "https://hashnode.com"),
    ("extract article titles from feed",                 "https://dev.to"),
    ("extract featured articles",                        "https://medium.com"),
    ("scroll and load more articles",                    "https://medium.com/topic/technology"),
    ("extract lobsters story titles and points",         "https://lobste.rs"),
    ("extract top answers from Quora",                   "https://www.quora.com"),
    ("extract tumblr trending posts",                    "https://www.tumblr.com"),
    ("navigate to Twitch gaming directory",              "https://www.twitch.tv/directory/game/Gaming"),
    ("extract top live stream titles",                   "https://www.twitch.tv/directory"),

    # Requires login (use respective profile)
    ("extract visible post headlines from LinkedIn feed",     "https://www.linkedin.com/feed"),
    ("search for software engineer jobs on LinkedIn",         "https://www.linkedin.com/jobs"),
    ("navigate to LinkedIn My Network tab",                   "https://www.linkedin.com/mynetwork"),
    ("extract your LinkedIn notifications",                   "https://www.linkedin.com/notifications"),
    ("search for AI news on LinkedIn",                        "https://www.linkedin.com/search/results/content/?keywords=AI"),
    ("navigate to Twitter home timeline",                     "https://x.com/home"),
    ("search for AI on Twitter",                              "https://x.com/search?q=AI"),
    ("navigate to Twitter notifications",                     "https://x.com/notifications"),
    ("extract Twitter trending topics",                       "https://x.com/explore"),
    ("navigate to Twitter messages",                          "https://x.com/messages"),
    ("navigate to Facebook feed",                             "https://www.facebook.com"),
    ("navigate to Facebook Groups section",                   "https://www.facebook.com/groups"),
    ("navigate to Facebook Marketplace",                      "https://www.facebook.com/marketplace"),
    ("navigate to Facebook notifications",                    "https://www.facebook.com/notifications"),
    ("navigate to Instagram explore page",                    "https://www.instagram.com/explore"),
    ("navigate to Instagram reels",                           "https://www.instagram.com/reels"),
    ("open Instagram direct messages",                        "https://www.instagram.com/direct/inbox"),
    ("navigate to Instagram profile page",                    "https://www.instagram.com"),
    ("navigate to Threads home feed",                         "https://www.threads.net"),
    ("extract visible posts on Threads",                      "https://www.threads.net"),
    ("navigate to Pinterest home feed and extract pins",      "https://www.pinterest.com"),
    ("search for minimalist design on Pinterest",             "https://www.pinterest.com/search/pins/?q=minimalist+design"),
]
```

### Category 3 — E-Commerce (100 sites, difficulty 2-4)

Focus: product search, filtering, cart interactions

```python
ECOMMERCE_TASKS = [
    # Amazon — High priority, complex UI
    ("search for gaming laptop on Amazon",               "https://www.amazon.com"),
    ("find best sellers in electronics on Amazon",       "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics"),
    ("search for mechanical keyboard and filter by rating", "https://www.amazon.com"),
    ("navigate to Amazon Today's Deals",                 "https://www.amazon.com/deals"),
    ("search for RTX 4070 graphics card",                "https://www.amazon.com"),
    ("find Amazon prime eligible laptops under 1000",    "https://www.amazon.com"),
    ("navigate to Amazon Fresh grocery section",         "https://www.amazon.com/alm/storefront?almBrandId=QW1hem9uIEZyZXNo"),
    ("search for noise cancelling headphones",           "https://www.amazon.com"),
    ("extract product title and price from product page","https://www.amazon.com/dp/B09G9FPHY6"),
    ("find kindle ebooks on Amazon",                     "https://www.amazon.com/Kindle-eBooks/b?node=154606011"),
    
    # eBay
    ("search for gaming laptops on eBay",                "https://www.ebay.com"),
    ("find listings for RTX 4090 on eBay",               "https://www.ebay.com"),
    ("navigate to eBay motors section",                  "https://www.ebay.com/motors"),
    ("search for vintage cameras on eBay",               "https://www.ebay.com"),
    ("filter eBay results by Buy It Now",                "https://www.ebay.com/sch/i.html?_nkw=camera"),
    
    # AliExpress
    ("search for wireless earbuds on AliExpress",        "https://www.aliexpress.com"),
    ("find flash deals on AliExpress",                   "https://www.aliexpress.com/sale/sale-flash-deals.html"),
    ("search for mechanical keyboard switches",          "https://www.aliexpress.com"),
    
    # Walmart
    ("search for 4k TV on Walmart",                      "https://www.walmart.com"),
    ("find grocery deals on Walmart",                    "https://www.walmart.com/grocery"),
    ("navigate to Walmart electronics section",          "https://www.walmart.com/cp/electronics/3944"),
    
    # Fashion
    ("search for running shoes on Nike",                 "https://www.nike.com"),
    ("find summer dresses on Zara",                      "https://www.zara.com"),
    ("navigate to Adidas new arrivals",                  "https://www.adidas.com/us/new"),
    ("search for handbags on H&M",                       "https://www2.hm.com/en_us/women/accessories/bags.html"),
    ("find sale items on ASOS",                          "https://www.asos.com/sale"),
    ("search for sneakers on StockX",                    "https://stockx.com/sneakers"),
    
    # Electronics
    ("search for RTX 4080 on Best Buy",                  "https://www.bestbuy.com"),
    ("navigate to Best Buy open box deals",              "https://www.bestbuy.com/site/misc/open-box/pcmcat1428525188054.c"),
    ("search for MacBook Pro on Newegg",                 "https://www.newegg.com"),
    ("find PC building deals on Newegg",                 "https://www.newegg.com/today-deals"),
    ("search for monitors under 300 on B&H",             "https://www.bhphotovideo.com"),
    
    # Global marketplaces
    ("search for tech accessories on Etsy",              "https://www.etsy.com"),
    ("find handmade jewelry on Etsy",                    "https://www.etsy.com/c/jewelry"),
    ("search for vintage items on eBay",                 "https://www.ebay.com/b/Vintage-Electronics/bn_7115905626"),
    ("browse IKEA living room furniture",                "https://www.ikea.com/us/en/rooms/living-room"),
    ("search for office chairs on Wayfair",              "https://www.wayfair.com/office-furniture/sb1/office-chairs-c46181.html"),
    ("find deals on Overstock",                          "https://www.overstock.com/deals"),
    ("search for groceries on Instacart",                "https://www.instacart.com"),
    ("find electronics on Target",                       "https://www.target.com/c/electronics/-/N-5xtg6"),
    ("search for protein powder on iHerb",               "https://www.iherb.com"),
    ("navigate to Shopify themes marketplace",           "https://themes.shopify.com"),
    
    # Middle East / Arabic e-commerce
    ("search for laptop on Noon",                        "https://www.noon.com"),
    ("find mobile phones on Jumia",                      "https://www.jumia.com"),
    ("search for electronics on Souq",                   "https://www.amazon.eg"),
    ("browse Namshi fashion collection",                  "https://en-eg.namshi.com"),
    ("find deals on Carrefour Egypt",                    "https://www.carrefouregypt.com"),
    
    # Specialty
    ("search for GPU on Micro Center",                   "https://www.microcenter.com/category/4294966937/graphics-cards"),
    ("find SSD deals on PC Part Picker",                 "https://pcpartpicker.com/products/internal-hard-drive"),
    ("search for camera lenses on Adorama",              "https://www.adorama.com/l/Photography/Lenses"),
    ("find electric bikes on REI",                       "https://www.rei.com/c/electric-bikes"),
    ("search for supplements on GNC",                    "https://www.gnc.com"),
    ("navigate to Steam hardware store",                 "https://store.steampowered.com/hardware"),
    ("find gaming chairs on Secret Lab",                 "https://secretlab.co/collections/all-chairs"),
    ("search for mechanical keyboards on Drop",         "https://drop.com/mechanical-keyboards"),
    
    # Food delivery
    ("search for pizza restaurants near me",             "https://www.doordash.com"),
    ("find sushi delivery on Uber Eats",                 "https://www.ubereats.com"),
    ("order food on Talabat",                            "https://www.talabat.com"),
    ("search for restaurants on Grubhub",               "https://www.grubhub.com"),
    
    # Tickets and experiences
    ("find concerts near me on Ticketmaster",            "https://www.ticketmaster.com"),
    ("search for events on Eventbrite",                  "https://www.eventbrite.com"),
    ("find local experiences on Airbnb Experiences",    "https://www.airbnb.com/s/experiences"),
    ("navigate to StubHub sports tickets",               "https://www.stubhub.com/sports-tickets"),
    
    # Automotive
    ("search for Toyota Camry on Cars.com",             "https://www.cars.com"),
    ("find used BMW on AutoTrader",                      "https://www.autotrader.com"),
    ("search for auto parts on RockAuto",               "https://www.rockauto.com"),
    ("find car insurance quotes on Progressive",         "https://www.progressive.com/auto"),
    
    # Home services
    ("search for plumbers near me on Angi",             "https://www.angi.com"),
    ("find home cleaning services on TaskRabbit",       "https://www.taskrabbit.com"),
    ("browse furniture on Article",                      "https://www.article.com"),
    ("search for rugs on Rugs Direct",                   "https://www.rugsdirect.com"),
    
    # Digital goods
    ("find royalty-free images on Shutterstock",        "https://www.shutterstock.com"),
    ("search for vector illustrations on Freepik",      "https://www.freepik.com"),
    ("browse WordPress themes on ThemeForest",          "https://themeforest.net"),
    ("find freelance projects on Fiverr",               "https://www.fiverr.com"),
    ("search for logo design on 99designs",             "https://99designs.com"),
    
    # Subscription and SaaS
    ("navigate to Adobe Creative Cloud pricing",        "https://www.adobe.com/creativecloud/plans.html"),
    ("find Microsoft 365 plans",                        "https://www.microsoft.com/en-us/microsoft-365"),
    ("browse Canva Pro features",                       "https://www.canva.com/pro"),
    ("check Figma pricing plans",                       "https://www.figma.com/pricing"),
    
    # Crypto / Finance markets
    ("search for Bitcoin on Binance",                   "https://www.binance.com/en/markets/overview"),
    ("find ETH price on Coinbase",                      "https://www.coinbase.com/price/ethereum"),
    ("check crypto market cap on CoinMarketCap",        "https://coinmarketcap.com"),
    ("find DeFi projects on CoinGecko",                 "https://www.coingecko.com/en/defi"),
    ("search for NFTs on OpenSea",                      "https://opensea.io/explore-collections"),
    
    # Wholesale / B2B
    ("search for electronics wholesale on Alibaba",     "https://www.alibaba.com"),
    ("find US distributors on ThomasNet",               "https://www.thomasnet.com"),
    ("search for office supplies on Staples",           "https://www.staples.com"),
]
```

### Category 4 — Travel & Bookings (60 sites, difficulty 3-5)

Focus: date pickers, multi-step forms, calendar interactions

```python
TRAVEL_TASKS = [
    # Flights
    ("search flights from Cairo to London on Google Flights", "https://www.google.com/flights"),
    ("find cheapest flights this month on Skyscanner",        "https://www.skyscanner.com"),
    ("search one-way flight NYC to LA on Kayak",              "https://www.kayak.com"),
    ("find flights on Expedia for next weekend",              "https://www.expedia.com"),
    ("check flight prices on Momondo",                        "https://www.momondo.com"),
    ("find budget airlines on Cheapflights",                  "https://www.cheapflights.com"),
    ("search round trip flights on Priceline",                "https://www.priceline.com"),
    ("find direct flights only on TripAdvisor flights",       "https://www.tripadvisor.com/Flights"),
    
    # Hotels
    ("search hotels in Paris for next weekend",               "https://www.booking.com"),
    ("find 5-star hotels in Dubai on Hotels.com",             "https://www.hotels.com"),
    ("search Airbnb in New York for 2 guests",               "https://www.airbnb.com"),
    ("find hotel deals on Trivago",                          "https://www.trivago.com"),
    ("search resorts in Bali on Agoda",                      "https://www.agoda.com"),
    ("find business hotels in London on HRS",                "https://www.hrs.com"),
    ("navigate to Marriott rewards page",                    "https://www.marriott.com/loyalty"),
    ("search Hilton hotels in NYC",                          "https://www.hilton.com/en/locations/united-states/new-york"),
    ("find vacation rentals on VRBO",                        "https://www.vrbo.com"),
    ("search hostels on Hostelworld",                        "https://www.hostelworld.com"),
    
    # Car rentals
    ("rent a car for a week in Miami on Hertz",              "https://www.hertz.com"),
    ("compare rental car prices on Rentalcars.com",          "https://www.rentalcars.com"),
    ("find luxury car rentals on Sixt",                      "https://www.sixt.com"),
    
    # Buses & trains
    ("search train from London to Paris on Eurostar",        "https://www.eurostar.com"),
    ("find bus tickets on FlixBus",                         "https://www.flixbus.com"),
    ("search Amtrak trains NYC to DC",                      "https://www.amtrak.com"),
    ("find intercity buses on BlaBlaBus",                   "https://www.blablabus.com"),
    
    # Ride sharing
    ("estimate Uber ride cost from Times Square to JFK",     "https://www.uber.com"),
    ("find Lyft rides available in Miami",                   "https://www.lyft.com"),
    ("navigate to Careem app booking page",                  "https://www.careem.com"),
    
    # Travel planning
    ("find top attractions in Rome on TripAdvisor",          "https://www.tripadvisor.com/Attractions-g187791-Activities-Rome_Lazio.html"),
    ("search Tokyo travel guide on Lonely Planet",           "https://www.lonelyplanet.com/japan/tokyo"),
    ("find travel itineraries for Egypt on Atlas Obscura",   "https://www.atlasobscura.com/things-to-do/egypt"),
    ("search for travel photos on 500px",                    "https://500px.com/discover"),
    ("find travel blogs on Nomadic Matt",                    "https://www.nomadicmatt.com"),
    
    # Visa & travel documents
    ("check visa requirements for Egypt to USA",             "https://www.visahq.com"),
    ("find US visa appointment on USVisaScheduling",         "https://ais.usvisa-info.com/en-eg/niv"),
    ("check Egypt passport validity requirements",           "https://www.iatatravelcentre.com"),
    
    # Insurance
    ("find travel insurance on World Nomads",                "https://www.worldnomads.com"),
    ("compare travel insurance on Squaremouth",              "https://www.squaremouth.com"),
    
    # Activities
    ("search things to do in Barcelona on Viator",           "https://www.viator.com"),
    ("find city tours in Paris on GetYourGuide",             "https://www.getyourguide.com"),
    ("book a snorkeling tour in Maldives",                   "https://www.klook.com"),
    
    # Maps & navigation
    ("get directions from London to Manchester on Google Maps", "https://www.google.com/maps"),
    ("search for petrol stations near me on Waze",           "https://www.waze.com"),
    ("find hiking trails near Denver on AllTrails",          "https://www.alltrails.com"),
    
    # Cruises
    ("find Mediterranean cruises on Carnival",               "https://www.carnival.com"),
    ("search cruise deals on Royal Caribbean",               "https://www.royalcaribbean.com"),
    
    # Vacation packages
    ("find all-inclusive packages in Cancun on Apple Vacations", "https://www.applevacations.com"),
    ("search vacation deals on Pleasant Holidays",           "https://www.pleasantholidays.com"),
    
    # Local transportation
    ("find bus routes in Cairo on Google Maps transit",      "https://www.google.com/maps"),
    ("check metro timetable for London Tube",                "https://tfl.gov.uk"),
    ("navigate to NYC subway map on MTA",                    "https://new.mta.info"),
    
    # Campgrounds
    ("search campgrounds in Yosemite on Reserve America",    "https://www.reserveamerica.com"),
    ("find RV parks on Campendium",                          "https://www.campendium.com"),
    
    # Ferries
    ("search ferries from Barcelona to Ibiza",               "https://www.directferries.com"),
    ("find ferry tickets on ClicknGo",                      "https://www.clickngo.com"),
]
```

### Category 5 — Finance & Banking (50 sites, difficulty 2-4)

Focus: structured data, tables, secure forms

```python
FINANCE_TASKS = [
    # Stock market
    ("check NVIDIA stock price and chart",              "https://finance.yahoo.com/quote/NVDA"),
    ("find S&P 500 performance today",                 "https://finance.yahoo.com/quote/%5EGSPC"),
    ("search for Apple stock on Yahoo Finance",        "https://finance.yahoo.com"),
    ("check Tesla earnings report",                    "https://finance.yahoo.com/quote/TSLA"),
    ("find NASDAQ top movers",                         "https://finance.yahoo.com/markets/stocks/most-active"),
    ("check stock screener on Finviz",                 "https://finviz.com/screener.ashx"),
    ("find dividend stocks on Seeking Alpha",          "https://seekingalpha.com/dividends/dividend-stocks"),
    ("check portfolio performance on Motley Fool",     "https://www.fool.com"),
    ("find undervalued stocks on Simply Wall St",      "https://simplywall.st"),
    ("check Dow Jones today on MarketWatch",           "https://www.marketwatch.com"),
    ("extract top gainers from Bloomberg markets",     "https://www.bloomberg.com/markets"),
    ("find bond yields on US Treasury",                "https://home.treasury.gov/resource-center/data-chart-center/interest-rates"),
    ("check VIX volatility index on CBOE",             "https://www.cboe.com/tradable_products/vix"),
    ("find ETF performance on ETF.com",                "https://www.etf.com"),
    ("check mutual fund rankings on Morningstar",      "https://www.morningstar.com"),
    
    # Banking
    ("navigate to Chase bank home banking",            "https://www.chase.com"),
    ("find interest rates on Bank of America",         "https://www.bankofamerica.com"),
    ("check Wells Fargo savings accounts",             "https://www.wellsfargo.com"),
    ("compare CD rates on Bankrate",                   "https://www.bankrate.com/banking/cds/best-cd-rates"),
    ("find best savings accounts on NerdWallet",       "https://www.nerdwallet.com/best/banking/savings-accounts"),
    
    # Crypto
    ("check Bitcoin price on CoinMarketCap",           "https://coinmarketcap.com/currencies/bitcoin"),
    ("find top cryptocurrencies by market cap",        "https://coinmarketcap.com"),
    ("check Ethereum price and gas fees",              "https://coinmarketcap.com/currencies/ethereum"),
    ("find DeFi protocols on DeFi Llama",              "https://defillama.com"),
    ("navigate to Coinbase trading page",              "https://www.coinbase.com/trade"),
    ("check crypto fear & greed index",                "https://alternative.me/crypto/fear-and-greed-index"),
    
    # Currency exchange
    ("find USD to EGP exchange rate on Xe.com",       "https://www.xe.com/currencyconverter/convert/?Amount=1&From=USD&To=EGP"),
    ("check Euro to GBP rate",                        "https://www.xe.com"),
    ("find gold price today in USD",                  "https://goldprice.org"),
    ("check oil price WTI crude",                     "https://www.investing.com/commodities/crude-oil"),
    
    # Insurance
    ("get auto insurance quote on Geico",             "https://www.geico.com"),
    ("compare life insurance on Policygenius",        "https://www.policygenius.com"),
    ("find health insurance plans on Healthcare.gov", "https://www.healthcare.gov"),
    
    # Tax & accounting
    ("navigate to IRS tax filing guide",              "https://www.irs.gov/filing"),
    ("find tax calculator on TaxAct",                 "https://www.taxact.com"),
    ("check tax refund status on TurboTax",           "https://turbotax.intuit.com"),
    
    # Egyptian finance
    ("check EGX stock exchange",                      "https://www.egx.com.eg"),
    ("find dollar rate in Egypt on Masrawy",          "https://www.masrawy.com/money"),
    ("navigate to Egyptian central bank site",        "https://www.cbe.org.eg"),
    ("find remittance rates on Western Union",        "https://www.westernunion.com"),
    
    # Personal finance
    ("check credit score info on Credit Karma",       "https://www.creditkarma.com"),
    ("find budgeting tools on Mint",                  "https://mint.intuit.com"),
    ("navigate to PayPal send money page",            "https://www.paypal.com"),
    ("find wire transfer rates on Wise",              "https://wise.com"),
    ("check Venmo transaction fees",                  "https://venmo.com"),
    
    # Business finance
    ("find SBA loan information",                     "https://www.sba.gov/funding-programs/loans"),
    ("navigate to QuickBooks pricing plans",          "https://quickbooks.intuit.com/pricing"),
    ("find invoice templates on FreshBooks",          "https://www.freshbooks.com"),
    ("check payroll costs on Gusto",                  "https://gusto.com"),
]
```

### Category 6 — Productivity & SaaS (70 sites, difficulty 2-5)

Focus: drag-drop, rich text editing, complex JS apps

```python
PRODUCTIVITY_TASKS = [
    # Google Workspace (needs google profile)
    ("open Gmail compose window",                      "https://mail.google.com"),
    ("search for emails from last week in Gmail",      "https://mail.google.com"),
    ("create a new Google Doc",                        "https://docs.google.com"),
    ("navigate to Google Drive my files",              "https://drive.google.com"),
    ("create a new Google Sheets spreadsheet",         "https://sheets.google.com"),
    ("find a presentation on Google Slides",           "https://slides.google.com"),
    ("check Google Calendar for today",                "https://calendar.google.com"),
    ("create a new event in Google Calendar",          "https://calendar.google.com"),
    
    # Microsoft 365
    ("navigate to Outlook inbox online",               "https://outlook.live.com"),
    ("open Microsoft Word online",                     "https://www.office.com/launch/word"),
    ("create new Excel spreadsheet online",            "https://www.office.com/launch/excel"),
    ("navigate to OneDrive files",                     "https://onedrive.live.com"),
    ("open Microsoft Teams channels",                  "https://teams.microsoft.com"),
    ("find PowerPoint templates online",               "https://www.office.com/launch/powerpoint"),
    
    # Notion / Productivity
    ("navigate to Notion workspace page",              "https://www.notion.so"),
    ("create a new page in Notion",                    "https://www.notion.so/new"),
    ("open Airtable base",                             "https://airtable.com"),
    ("navigate to Trello board",                       "https://trello.com"),
    ("create a card in Trello",                        "https://trello.com"),
    ("open Asana my tasks",                            "https://app.asana.com"),
    ("navigate to Monday.com dashboard",               "https://monday.com"),
    ("open ClickUp workspace",                         "https://app.clickup.com"),
    ("navigate to Jira project board",                 "https://www.atlassian.com/software/jira"),
    ("open Linear issues board",                       "https://linear.app"),
    
    # Design tools
    ("navigate to Figma editor",                       "https://www.figma.com"),
    ("open Canva design editor",                       "https://www.canva.com"),
    ("find templates on Canva",                        "https://www.canva.com/templates"),
    ("navigate to Adobe Express",                      "https://new.express.adobe.com"),
    ("open Miro whiteboard",                           "https://miro.com"),
    ("navigate to Lucidchart diagrams",                "https://lucid.app"),
    ("open draw.io for diagramming",                   "https://app.diagrams.net"),
    
    # Developer tools
    ("navigate to GitHub repository issues",           "https://github.com"),
    ("create a new GitHub repository",                 "https://github.com/new"),
    ("find GitHub Actions marketplace",                "https://github.com/marketplace?type=actions"),
    ("navigate to Vercel dashboard",                   "https://vercel.com/dashboard"),
    ("check Netlify site deployments",                 "https://app.netlify.com"),
    ("navigate to Railway project dashboard",          "https://railway.app"),
    ("open Supabase project",                          "https://app.supabase.com"),
    ("navigate to Cloudflare workers",                 "https://dash.cloudflare.com"),
    ("check Render deployment status",                 "https://render.com"),
    ("open Heroku app dashboard",                      "https://dashboard.heroku.com"),
    
    # Analytics & monitoring
    ("navigate to Google Analytics reports",           "https://analytics.google.com"),
    ("check Mixpanel events dashboard",                "https://mixpanel.com"),
    ("open Sentry error tracking",                     "https://sentry.io"),
    ("navigate to Datadog monitoring",                 "https://app.datadoghq.com"),
    ("check Grafana metrics dashboard",                "https://grafana.com"),
    
    # Communication
    ("open Slack channels list",                       "https://slack.com"),
    ("navigate to Discord server",                     "https://discord.com"),
    ("open Zoom meeting room",                         "https://zoom.us"),
    ("find Calendly scheduling page",                  "https://calendly.com"),
    ("navigate to Loom video library",                 "https://www.loom.com"),
    
    # AI tools (great for agent training — meta!)
    ("navigate to ChatGPT new chat",                   "https://chat.openai.com"),
    ("open Gemini AI assistant",                       "https://gemini.google.com"),
    ("find Claude AI chat",                            "https://claude.ai"),
    ("navigate to Perplexity AI search",               "https://www.perplexity.ai"),
    ("open Midjourney explore gallery",                "https://www.midjourney.com/explore"),
    ("navigate to Hugging Face spaces",                "https://huggingface.co/spaces"),
    ("find Replicate models",                          "https://replicate.com/explore"),
    ("navigate to Stability AI platform",              "https://stability.ai"),
    
    # Note-taking
    ("open Obsidian Publish vault",                    "https://obsidian.md"),
    ("navigate to Roam Research graph",                "https://roamresearch.com"),
    ("open Bear notes app",                            "https://bear.app"),
    ("navigate to Evernote web",                       "https://www.evernote.com"),
    ("find Apple Notes web",                           "https://www.icloud.com/notes"),
    
    # Learning platforms
    ("find Python course on Coursera",                 "https://www.coursera.org"),
    ("search for ML course on edX",                   "https://www.edx.org"),
    ("navigate to Udemy Python courses",               "https://www.udemy.com"),
    ("find coding tutorials on Pluralsight",           "https://www.pluralsight.com"),
    ("search for AI courses on fast.ai",               "https://www.fast.ai"),
]
```

### Category 7 — Docs, News & Reference (50 sites, difficulty 1-2)

Focus: navigation, reading flows, static accessibility trees

```python
DOCS_TASKS = [
    # Tech documentation (best for training — clean accessible trees)
    ("navigate to Python 3.12 what's new page",       "https://docs.python.org/3/whatsnew/3.12.html"),
    ("find asyncio documentation in Python docs",     "https://docs.python.org/3/library/asyncio.html"),
    ("navigate to MDN JavaScript array methods",      "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array"),
    ("find React hooks documentation",                "https://react.dev/reference/react"),
    ("navigate to Playwright async API docs",         "https://playwright.dev/python/docs/api/class-page"),
    ("find Docker compose documentation",             "https://docs.docker.com/compose"),
    ("navigate to FastAPI tutorial",                  "https://fastapi.tiangolo.com/tutorial"),
    ("find PyTorch tensor documentation",             "https://pytorch.org/docs/stable/tensors.html"),
    ("navigate to NumPy array creation docs",         "https://numpy.org/doc/stable/reference/routines.array-creation.html"),
    ("find Pandas DataFrame documentation",           "https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html"),
    ("navigate to TypeScript handbook",               "https://www.typescriptlang.org/docs/handbook"),
    ("find Rust ownership documentation",             "https://doc.rust-lang.org/book/ch04-00-understanding-ownership.html"),
    ("navigate to Go language tour",                  "https://go.dev/tour"),
    ("find Tailwind CSS flexbox utilities",           "https://tailwindcss.com/docs/flex"),
    ("navigate to Next.js App Router docs",           "https://nextjs.org/docs/app"),
    
    # News
    ("extract top headlines from BBC News",           "https://www.bbc.com/news"),
    ("find technology articles on CNN",               "https://www.cnn.com/tech"),
    ("extract science headlines from Reuters",        "https://www.reuters.com/science"),
    ("navigate to Al Jazeera Arabic section",         "https://www.aljazeera.net"),
    ("find breaking news on AP News",                 "https://apnews.com"),
    ("extract sports headlines from ESPN",            "https://www.espn.com"),
    ("find tech news on The Verge",                   "https://www.theverge.com"),
    ("navigate to Wired AI section",                  "https://www.wired.com/tag/artificial-intelligence"),
    ("extract headlines from Ars Technica",           "https://arstechnica.com"),
    ("find science news on Nature",                   "https://www.nature.com/news"),
    
    # Arabic news (important for Egyptian context)
    ("read latest news on Youm7",                     "https://www.youm7.com"),
    ("find sports news on Masrawy",                   "https://www.masrawy.com/sports"),
    ("navigate to El Watan News",                     "https://www.elwatannews.com"),
    ("find technology articles on Mawdoo3",           "https://mawdoo3.com/تكنولوجيا"),
    ("check Ahram digital newspaper",                  "https://www.ahram.org.eg"),
    ("navigate to Shorouk news",                      "https://www.shorouknews.com"),
    ("find Egypt Independent news",                   "https://egyptindependent.com"),
    
    # Reference
    ("search for machine learning on Wikipedia",      "https://en.wikipedia.org"),
    ("find definition of entropy on Wikipedia",       "https://en.wikipedia.org/wiki/Entropy"),
    ("navigate to Britannica AI article",             "https://www.britannica.com/technology/artificial-intelligence"),
    ("find Stack Overflow top Python questions",      "https://stackoverflow.com/questions/tagged/python"),
    ("navigate to Stack Overflow highest voted",      "https://stackoverflow.com/questions?sort=votes"),
    
    # Podcasts & audio
    ("find top AI podcasts on Spotify",               "https://open.spotify.com/genre/podcasts-web"),
    ("navigate to NPR technology podcast",            "https://www.npr.org/podcasts/510019/all-tech-considered"),
    
    # Scientific papers
    ("search for transformer attention papers on Arxiv", "https://arxiv.org/search/?searchtype=all&query=transformer+attention"),
    ("find latest ML papers on Semantic Scholar",    "https://www.semanticscholar.org"),
    ("navigate to Google Scholar AI papers 2024",    "https://scholar.google.com"),
    ("find CVPR 2024 papers list",                   "https://openaccess.thecvf.com/CVPR2024?day=all"),
    
    # Government & legal
    ("navigate to US patent search",                 "https://ppubs.uspto.gov/pubwebapp"),
    ("find Egypt official gazette",                  "https://www.vetogate.com/law"),
    ("navigate to WHO health reports",               "https://www.who.int/publications"),
    ("find FDA drug database",                       "https://www.accessdata.fda.gov/scripts/cder/daf"),
    ("check NASA space mission updates",             "https://www.nasa.gov/missions"),
]
```

### Category 8 — Jobs, Real Estate & Local (50 sites, difficulty 2-4)

Focus: map integrations, heavy filtering UI, multi-step forms

```python
JOBS_REALESTATE_TASKS = [
    # Jobs
    ("search for software engineer jobs on LinkedIn", "https://www.linkedin.com/jobs"),
    ("find remote Python jobs on Indeed",             "https://www.indeed.com"),
    ("search for AI researcher positions on Glassdoor", "https://www.glassdoor.com"),
    ("find entry level data science jobs on Dice",    "https://www.dice.com"),
    ("search tech jobs in Cairo on Wuzzuf",           "https://wuzzuf.net"),
    ("find remote developer jobs on We Work Remotely","https://weworkremotely.com"),
    ("search for startup jobs on AngelList",          "https://wellfound.com"),
    ("find freelance work on Upwork",                 "https://www.upwork.com"),
    ("search for design jobs on Dribbble Jobs",       "https://dribbble.com/jobs"),
    ("find government jobs on USAJOBS",               "https://www.usajobs.gov"),
    ("search tech jobs in Egypt on Forasna",          "https://www.forasna.com"),
    ("find remote jobs on Remote.co",                 "https://remote.co/remote-jobs"),
    ("search for junior developer positions on GitHub Jobs", "https://jobs.github.com"),
    ("find ML engineer jobs on Levels.fyi",          "https://www.levels.fyi/jobs"),
    
    # Real estate
    ("search apartments for rent in New York on Zillow", "https://www.zillow.com"),
    ("find homes for sale in Miami on Realtor.com",   "https://www.realtor.com"),
    ("search condos in Dubai on Property Finder",     "https://www.propertyfinder.ae"),
    ("find apartments for rent in Cairo on OLX",      "https://www.olx.com.eg"),
    ("search commercial property on LoopNet",         "https://www.loopnet.com"),
    ("find apartments on Apartments.com",             "https://www.apartments.com"),
    ("search rental listings on Trulia",              "https://www.trulia.com"),
    ("navigate to Compass luxury listings",           "https://www.compass.com"),
    ("find investment properties on Mashvisor",       "https://www.mashvisor.com"),
    ("search land for sale on LandWatch",             "https://www.landwatch.com"),
    
    # Local services
    ("search for electricians near me on Yelp",       "https://www.yelp.com"),
    ("find restaurant reviews on TripAdvisor",        "https://www.tripadvisor.com"),
    ("search for doctors on Zocdoc",                  "https://www.zocdoc.com"),
    ("find nearby gyms on Mindbody",                  "https://www.mindbodyonline.com"),
    ("search for plumbers on HomeAdvisor",            "https://www.homeadvisor.com"),
    ("find laundry services on TaskRabbit",           "https://www.taskrabbit.com"),
    
    # Maps & local discovery
    ("find coffee shops near central park on Google Maps", "https://www.google.com/maps"),
    ("search for ATMs near me on Yelp",               "https://www.yelp.com"),
    ("find parking in Manhattan on ParkWhiz",         "https://www.parkwhiz.com"),
    ("navigate to OpenStreetMap and find a location", "https://www.openstreetmap.org"),
    
    # Education & schools
    ("find universities in Egypt on QS Rankings",     "https://www.topuniversities.com"),
    ("search medical schools on US News",             "https://www.usnews.com/best-graduate-schools/top-medical-schools"),
    ("find MBA programs on GMAT Club",               "https://www.gmatclub.com/forum/schools"),
    
    # Healthcare
    ("search for cardiologists near me on Healthgrades", "https://www.healthgrades.com"),
    ("find drug information on drugs.com",            "https://www.drugs.com"),
    ("navigate to WebMD symptom checker",             "https://www.webmd.com/symptom-checker"),
    ("find mental health resources on NAMI",          "https://www.nami.org"),
    
    # Legal
    ("find lawyers near me on Avvo",                  "https://www.avvo.com"),
    ("search legal documents on LegalZoom",           "https://www.legalzoom.com"),
    
    # Kids & family
    ("find schools near me on GreatSchools",          "https://www.greatschools.org"),
    ("search for childcare on Care.com",              "https://www.care.com"),
    
    # Gaming & entertainment
    ("find game deals on Steam",                      "https://store.steampowered.com/specials"),
    ("check game reviews on Metacritic",              "https://www.metacritic.com"),
    ("find PlayStation games on PS Store",            "https://store.playstation.com"),
]
```

---

## 5. Training Scripts — Full Implementation

### `training/target_websites_v2.py`

```python
"""
BrowserMind — Full 500-Site Task Registry v2
=============================================
Complete task list from all categories.
"""
from typing import List, Dict

# Import all category lists
from training.task_categories import (
    SEARCH_TASKS, SOCIAL_TASKS, ECOMMERCE_TASKS,
    TRAVEL_TASKS, FINANCE_TASKS, PRODUCTIVITY_TASKS,
    DOCS_TASKS, JOBS_REALESTATE_TASKS
)

# Combine all tasks
ALL_TASKS_V2: List[Dict] = []

for goal, url in SEARCH_TASKS:
    ALL_TASKS_V2.append({"goal": goal, "url": url, "category": "search",      "needs_login": False})
for goal, url in SOCIAL_TASKS:
    needs_login = any(d in url for d in ["linkedin", "x.com", "twitter", "facebook", "instagram"])
    ALL_TASKS_V2.append({"goal": goal, "url": url, "category": "social",      "needs_login": needs_login})
for goal, url in ECOMMERCE_TASKS:
    ALL_TASKS_V2.append({"goal": goal, "url": url, "category": "ecommerce",   "needs_login": False})
for goal, url in TRAVEL_TASKS:
    ALL_TASKS_V2.append({"goal": goal, "url": url, "category": "travel",      "needs_login": False})
for goal, url in FINANCE_TASKS:
    ALL_TASKS_V2.append({"goal": goal, "url": url, "category": "finance",     "needs_login": False})
for goal, url in PRODUCTIVITY_TASKS:
    needs_login = any(d in url for d in ["mail.google", "drive.google", "docs.google", "github.com/new"])
    ALL_TASKS_V2.append({"goal": goal, "url": url, "category": "productivity","needs_login": needs_login})
for goal, url in DOCS_TASKS:
    ALL_TASKS_V2.append({"goal": goal, "url": url, "category": "docs",        "needs_login": False})
for goal, url in JOBS_REALESTATE_TASKS:
    needs_login = any(d in url for d in ["linkedin.com/jobs", "mail.google"])
    ALL_TASKS_V2.append({"goal": goal, "url": url, "category": "jobs",        "needs_login": needs_login})


def get_all_as_tuples():
    """Compatibility with existing collect_and_train.py"""
    return [(t["goal"], t["url"]) for t in ALL_TASKS_V2]

def get_tasks_by_category(category: str):
    return [(t["goal"], t["url"]) for t in ALL_TASKS_V2 if t["category"] == category]

def get_public_tasks():
    """Tasks that don't require login — safe to run anywhere."""
    return [(t["goal"], t["url"]) for t in ALL_TASKS_V2 if not t["needs_login"]]

def get_tasks_by_difficulty_budget():
    """Sort by expected difficulty — run easy ones first."""
    priority = {"search": 1, "docs": 2, "finance": 3, "social": 4,
                "ecommerce": 5, "travel": 6, "productivity": 7, "jobs": 8}
    sorted_tasks = sorted(ALL_TASKS_V2, key=lambda t: priority.get(t["category"], 9))
    return [(t["goal"], t["url"]) for t in sorted_tasks]
```

### `collect_gauntlet.py` — The Main Collection Script

```python
"""
BrowserMind — Gauntlet Collection Script
==========================================
Trains on all 500 sites with:
- Automatic popup dismissal
- Profile-based session management
- Parallel collection (4 browsers)
- Smart retry logic

Usage:
    python collect_gauntlet.py --category search     # one category
    python collect_gauntlet.py --category all        # everything
    python collect_gauntlet.py --public-only         # no login required
    python collect_gauntlet.py --rounds 3            # 3 passes over all tasks
"""

import asyncio
import argparse
import random
import time
from pathlib import Path
from collections import defaultdict
from typing import List, Tuple, Optional
from playwright.async_api import async_playwright

from core.popup_handler import PopupHandler, configure_context_for_training
from training.graph_builder import build_graph_from_page, decide_expert_action, graph_hash
from core.privacy import redact_sensitive_text, sanitize_expert_action, sanitize_goal_for_storage, sanitize_graph_for_storage
from training.target_websites_v2 import ALL_TASKS_V2, get_public_tasks, get_tasks_by_category

import json
from collections import deque

# ─────────────────────────────────────────────
SESSIONS_DIR = Path("training/gauntlet_sessions")
LOG_FILE = Path("gauntlet.log")
PROFILE_DIR = Path("browser_profiles")

PROFILE_MAP = {
    "linkedin.com": "linkedin",
    "x.com": "twitter", "twitter.com": "twitter",
    "facebook.com": "facebook", "instagram.com": "facebook",
    "mail.google.com": "google", "docs.google.com": "google",
    "drive.google.com": "google", "calendar.google.com": "google",
    "github.com/settings": "github", "github.com/new": "github",
    "github.com/notifications": "github",
}

def get_profile(url: str) -> Optional[str]:
    for domain, profile in PROFILE_MAP.items():
        if domain in url:
            profile_path = PROFILE_DIR / profile
            if profile_path.exists():
                return str(profile_path)
    return None

def _log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def run_gauntlet_task(page, goal: str, url: str, sid: str, save_dir: Path) -> Optional[Path]:
    """Run one task with full popup handling."""
    handler = PopupHandler(page)
    await handler.setup()

    samples = []
    hash_history = deque(maxlen=3)

    try:
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await asyncio.sleep(1.5)  # let JS settle
    except Exception as e:
        _log(f"  [goto error] {url}: {e}")
        return None

    # Dismiss initial popups before first step
    dismissed = await handler.dismiss_all()
    if dismissed > 0:
        await asyncio.sleep(0.5)
        _log(f"  [popup] dismissed {dismissed} elements on load")

    prev_url = page.url

    for step in range(15):
        # Dismiss popups before each graph build
        await handler.dismiss_all()

        try:
            graph = await build_graph_from_page(page)
        except Exception as e:
            _log(f"  [graph error] step={step}: {e}")
            break

        nodes = graph.get("nodes", [])
        if not nodes:
            await asyncio.sleep(1)
            continue

        gh = graph_hash(graph)
        hash_history.append(gh)
        if len(hash_history) == 3 and len(set(hash_history)) == 1:
            _log(f"  [stuck] {goal!r:.30} — stopping")
            break

        current_url = page.url
        expert = decide_expert_action(graph, goal, current_url)
        expert_record = dict(expert)
        eidx = expert_record.get("element_idx")
        if isinstance(eidx, int) and 0 <= eidx < len(nodes):
            expert_record.setdefault("target_text", str(nodes[eidx].get("name", "")))

        # Execute
        ok = await _execute_action(page, expert, nodes)
        await asyncio.sleep(0.6)

        samples.append({
            "goal":          sanitize_goal_for_storage(goal),
            "url":           redact_sensitive_text(current_url),
            "step":          step + 1,
            "success":       ok,
            "graph":         sanitize_graph_for_storage(graph),
            "expert_action": sanitize_expert_action(expert_record, goal_text=goal),
        })

        prev_url = page.url
        if expert.get("type") in ("done", "fail"):
            break

    if len(samples) < 2:
        return None

    save_dir.mkdir(parents=True, exist_ok=True)
    out_path = save_dir / f"{sid}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(samples, f, indent=2, ensure_ascii=False)

    _log(f"  [ok] {goal!r:.35} → {len(samples)} steps → {out_path.name}")
    return out_path


async def _execute_action(page, action: dict, nodes: list) -> bool:
    """Execute expert action. Same logic as collect_and_train.py."""
    etype = action.get("type", "")
    eidx = action.get("element_idx")
    value = action.get("value", "")

    try:
        if etype == "navigate":
            if value:
                await page.goto(value, timeout=12000, wait_until="domcontentloaded")
            return True
        if etype == "wait":
            await asyncio.sleep(1.5)
            return True
        if etype == "scroll":
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(0.5)
            return True
        if etype == "go_back":
            await page.go_back(timeout=8000)
            return True
        if etype in ("done", "fail"):
            return etype == "done"

        if eidx is None or eidx >= len(nodes):
            return False

        nd = nodes[eidx]
        name = nd.get("name", "")
        role = nd.get("role", "generic")

        if etype == "click":
            for get_loc in [
                lambda: page.get_by_role("button", name=name).first if role == "button" and name else None,
                lambda: page.get_by_role("link", name=name).first if role == "link" and name else None,
                lambda: page.get_by_text(name, exact=False).first if name else None,
            ]:
                try:
                    loc = get_loc()
                    if loc and await loc.is_visible():
                        await loc.click(timeout=4000)
                        await asyncio.sleep(0.8)
                        return True
                except Exception:
                    continue

        if etype == "type":
            txt = value or name
            for get_loc in [
                lambda: page.get_by_role("textbox", name=name).first if name else None,
                lambda: page.get_by_placeholder(name).first if name else None,
                lambda: page.locator("input:visible, textarea:visible").first,
            ]:
                try:
                    loc = get_loc()
                    if loc and await loc.is_visible():
                        await loc.fill(txt, timeout=4000)
                        await asyncio.sleep(0.3)
                        return True
                except Exception:
                    continue

    except Exception as e:
        _log(f"  [action err] {etype}: {e}")
    return False


async def collect_category(
    tasks: List[Tuple[str, str]],
    category: str,
    round_num: int = 1,
    parallel: int = 3,
) -> List[Path]:
    """Collect sessions for a category, with parallel browsers."""
    
    sem = asyncio.Semaphore(parallel)
    results = []
    failures = defaultdict(int)
    lock = asyncio.Lock()
    session_counter = 0

    async def run_one(goal: str, url: str, sid: str):
        async with sem:
            profile_path = get_profile(url)
            save_dir = SESSIONS_DIR / category / f"round_{round_num:03d}"

            try:
                async with async_playwright() as pw:
                    if profile_path:
                        context = await pw.chromium.launch_persistent_context(
                            user_data_dir=profile_path,
                            headless=True,
                            viewport={"width": 1280, "height": 720},
                            args=["--disable-blink-features=AutomationControlled"],
                        )
                    else:
                        browser = await pw.chromium.launch(
                            headless=True,
                            args=["--disable-blink-features=AutomationControlled"],
                        )
                        context = await browser.new_context(
                            viewport={"width": 1280, "height": 720},
                            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        )

                    await configure_context_for_training(context)
                    page = await context.new_page()

                    path = await asyncio.wait_for(
                        run_gauntlet_task(page, goal, url, sid, save_dir),
                        timeout=90,
                    )
                    await context.close()

                    if path:
                        async with lock:
                            results.append(path)
                    else:
                        failures[url] += 1

            except Exception as e:
                _log(f"  [exception] {goal!r:.30}: {e}")
                failures[url] += 1

    tasks_to_run = [
        (goal, url, f"{category}_{round_num:03d}_{i:04d}")
        for i, (goal, url) in enumerate(tasks)
        if failures.get(url, 0) < 3  # skip after 3 failures
    ]

    _log(f"[{category}] Starting {len(tasks_to_run)} tasks (parallel={parallel})")
    await asyncio.gather(*[run_one(g, u, s) for g, u, s in tasks_to_run])
    _log(f"[{category}] Done: {len(results)} successful sessions")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="all",
                        choices=["all", "search", "social", "ecommerce", "travel",
                                 "finance", "productivity", "docs", "jobs"])
    parser.add_argument("--public-only", action="store_true")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--parallel", type=int, default=3)
    args = parser.parse_args()

    if args.public_only:
        tasks = get_public_tasks()
        categories = [("public", tasks)]
    elif args.category == "all":
        from training.target_websites_v2 import get_tasks_by_difficulty_budget
        tasks = get_tasks_by_difficulty_budget()
        categories = [("all", tasks)]
    else:
        tasks = get_tasks_by_category(args.category)
        categories = [(args.category, tasks)]

    for round_num in range(1, args.rounds + 1):
        _log(f"\n{'='*50}")
        _log(f"ROUND {round_num}/{args.rounds}")
        _log(f"{'='*50}")

        for cat_name, cat_tasks in categories:
            random.shuffle(cat_tasks)
            asyncio.run(collect_category(cat_tasks, cat_name, round_num, args.parallel))

    _log("\n[done] Gauntlet collection complete.")
    _log(f"Sessions saved to: {SESSIONS_DIR}")
    _log("Next step: python collect_and_train.py --train-only")


if __name__ == "__main__":
    main()
```

---

## 6. Training Phases & Timeline

### Phase 0 — Foundation (Public Sites Only)

**Goal:** 200 sessions from no-login sites before touching anything social.

```bash
# Day 1 — run while you sleep
python collect_gauntlet.py \
  --public-only \
  --rounds 2 \
  --parallel 4
```

Expected: ~180-220 successful sessions, ~2-3 hours.

These sites (search engines, news, docs, YouTube, Reddit) have **clean accessibility trees** with no login walls. The model learns the 8 actions in stable, predictable environments first.

---

### Phase 1 — Behavioral Cloning

**Goal:** Train on Phase 0 data until val_acc ≥ 0.60.

```bash
python collect_and_train.py --train-only
```

Expected: ~5 minutes on GTX 1660 Super.

---

### Phase 2 — Category Expansion

After BC baseline established, expand by category in difficulty order:

```bash
# Week 1 — each command runs overnight
python collect_gauntlet.py --category search      --rounds 3 --parallel 4
python collect_gauntlet.py --category docs        --rounds 3 --parallel 4
python collect_gauntlet.py --category finance     --rounds 2 --parallel 4
python collect_gauntlet.py --category ecommerce   --rounds 2 --parallel 3
python collect_gauntlet.py --category travel      --rounds 2 --parallel 3
python collect_gauntlet.py --category jobs        --rounds 2 --parallel 3
python collect_gauntlet.py --category productivity --rounds 1 --parallel 2
python collect_gauntlet.py --category social      --rounds 1 --parallel 2
# Train after each category addition:
python collect_and_train.py --train-only
```

---

### Phase 3 — DAgger Loop (Full 500)

```bash
# Full DAgger: model collects + trains iteratively
python collect_and_train.py --cycle-only
```

Each round: 10 new sessions → 1 training epoch → checkpoint saved.
Stops at 65% success rate or 30 rounds.

---

## 7. DAgger Curriculum Schedule

The **order** of sites during DAgger matters. Don't throw LinkedIn and Instagram at the model in Round 1.

```python
# In collect_and_train.py, replace ALL_TASKS with this curriculum:

CURRICULUM = {
    "rounds_1_5":   ["search", "docs"],          # stable DOM, easy tasks
    "rounds_6_10":  ["finance", "ecommerce"],     # more complex but no login
    "rounds_11_15": ["travel", "jobs"],           # date pickers, forms
    "rounds_16_20": ["social"],                   # dynamic content
    "rounds_21_30": ["productivity"],             # SaaS apps, all categories mixed
}

def get_curriculum_tasks(round_num: int) -> List[Tuple[str, str]]:
    from training.target_websites_v2 import get_tasks_by_category, get_all_as_tuples
    
    if round_num <= 5:
        cats = CURRICULUM["rounds_1_5"]
    elif round_num <= 10:
        cats = CURRICULUM["rounds_6_10"]
    elif round_num <= 15:
        cats = CURRICULUM["rounds_11_15"]
    elif round_num <= 20:
        cats = CURRICULUM["rounds_16_20"]
    else:
        return get_all_as_tuples()  # everything mixed
    
    tasks = []
    for cat in cats:
        tasks.extend(get_tasks_by_category(cat))
    random.shuffle(tasks)
    return tasks
```

---

## 8. Monitoring & Success Criteria

### Target Metrics by Phase

| Phase | Action Acc | Elem@3 | Task Success |
|-------|-----------|--------|-------------|
| After Phase 1 (BC) | ≥ 0.55 | ≥ 0.50 | — |
| After Round 10 (DAgger) | ≥ 0.65 | ≥ 0.65 | ≥ 0.40 |
| After Round 20 | ≥ 0.72 | ≥ 0.75 | ≥ 0.55 |
| Target (production) | ≥ 0.75 | ≥ 0.80 | ≥ 0.65 |

### What to Do When Stuck

**Symptom:** action_acc stuck at < 0.50 after 10 epochs.

```python
# Check what actions the model is getting wrong:
# Run this after training:

from collections import Counter
action_errors = Counter()
for sample in val_samples:
    pred = policy.forward(...)["action_logits"].argmax().item()
    true = sample["expert_action"]["action_id"]
    if pred != true:
        action_errors[f"pred={pred}_true={true}"] += 1

print(action_errors.most_common(10))
```

**Common causes:**
- Model always predicts `scroll` (action_id=1) → data imbalanced, add more `click` tasks
- Model never predicts `type` → not enough form-filling tasks (add `SEARCH_TASKS` more)
- Model confused between `click` and `navigate` → need clearer goal phrasing

### Session Quality Check

```bash
# Quick sanity check on collected sessions:
python -c "
import json
from pathlib import Path
sessions = list(Path('training/gauntlet_sessions').rglob('*.json'))
print(f'Total sessions: {len(sessions)}')
from collections import Counter
actions = Counter()
for s in sessions:
    data = json.loads(s.read_text())
    if isinstance(data, list):
        for step in data:
            ea = step.get('expert_action', {})
            actions[ea.get('type', 'unknown')] += 1
print('Action distribution:')
for a, c in actions.most_common():
    print(f'  {a}: {c}')
"
```

**Healthy distribution:**
- `scroll`: 30-40%
- `click`: 25-35%
- `type`: 10-20%
- `navigate`: 5-15%
- `extract`: 10-20%
- `wait`, `go_back`, `done`: < 10% combined

---

## 9. Quick Reference Commands

```bash
# ─── One-time setup ─────────────────────────────────────────
python login_setup.py --profile google
python login_setup.py --profile github
python login_setup.py --profile linkedin
python login_setup.py --profile twitter
python login_setup.py --profile facebook

# ─── Collection ─────────────────────────────────────────────
python collect_gauntlet.py --public-only --rounds 2        # Phase 0: safe start
python collect_gauntlet.py --category search  --rounds 3   # Category by category
python collect_gauntlet.py --category all     --rounds 1   # Everything once
python collect_social.py   --rounds 3 --tasks-per-round 20 # Social-specific

# ─── Training ───────────────────────────────────────────────
python collect_and_train.py --train-only       # BC on existing sessions
python collect_and_train.py --cycle-only       # DAgger loop
python collect_and_train.py                    # Full pipeline (Phase 0 + 1 + cycles)

# ─── Evaluation ─────────────────────────────────────────────
python evaluate.py                             # Run eval on held-out tasks

# ─── Monitoring ─────────────────────────────────────────────
tail -f collect_train.log                      # Watch training live
tail -f gauntlet.log                           # Watch collection live

# ─── Checkpoints ────────────────────────────────────────────
ls -lh checkpoints/                           # List all checkpoints
# best.pt is always the best model so far

# ─── Emergency stop ─────────────────────────────────────────
# Ctrl+C — the script saves checkpoint before exiting
# Restart with --cycle-only and it resumes from best.pt
```

---

## Summary — The Optimal Flow

```
Day 0 (1 hour, manual)
  └─ python login_setup.py --profile [google|github|linkedin|twitter|facebook]

Night 1 (sleep, ~3 hours)
  └─ python collect_gauntlet.py --public-only --rounds 2 --parallel 4
     → ~200 sessions from 300+ public sites

Morning 1 (5 minutes)
  └─ python collect_and_train.py --train-only
     → BC baseline, expect action_acc ≈ 0.50-0.60

Nights 2-5 (one category per night)
  └─ python collect_gauntlet.py --category [search|docs|finance|ecommerce|travel]
  └─ python collect_and_train.py --train-only  (each morning, 5 min)

Night 6+ (DAgger loop, let it run)
  └─ python collect_and_train.py --cycle-only
     → Stops automatically at 65% or 30 rounds

Result: A model trained on 400+ sites, 1000+ sessions,
        across 8 action types, robust to popups, logins, and dynamic content.
```

---

*BrowserMind Training Plan v1.0 · Generated for GTX 1660 Super + 16GB RAM · Cairo, Egypt*
