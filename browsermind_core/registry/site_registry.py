"""SiteRegistry — the world description for BrowserMind exploration.

Every site that BrowserMind can explore, replay on, or benchmark against is
described by a SiteEntry. The registry is the single source of truth for:

  - TransferArena (training_envs / test_envs come from here)
  - BatchRunner   (engine_factory receives site_key from here)
  - ExplorationHarness (ExplorationSpec references SiteEntry)
  - CapabilityRecord   (transfer_envs keys match SiteEntry.key)

Design
──────
SiteEntry is a dataclass. The module exposes:
  SITE_REGISTRY: Dict[str, SiteEntry]   — keyed by SiteEntry.key
  get(key)                              — lookup by key
  by_category(category)                 — all entries for one category
  by_difficulty(max_difficulty)         — filter by difficulty tier
  exploration_candidates(...)           — sorted by priority for harness
  keys()                                — all registered site keys

Categories (30 families from the taxonomy)
──────────────────────────────────────────
  social_networks, forums_communities, chat_realtime, video_platforms,
  audio_platforms, image_platforms, news_publishing, blogs_personal,
  ecommerce, marketplaces, saas_applications, productivity_systems,
  knowledge_systems, developer_platforms, package_registries,
  cloud_platforms, authentication_systems, email_systems,
  government_portals, banking_finance, crypto_platforms,
  education_platforms, job_platforms, cms_sitebuilders, search_engines,
  maps_local_discovery, travel_systems, ai_platforms,
  dashboards_admin, unknown_frontier

Difficulty tiers (1-5)
──────────────────────
  1  Static content, no auth, standard DOM
  2  Auth required or moderate interactivity
  3  Complex state, multi-step flows, infinite scroll
  4  Heavy JS/Canvas/WebGL, real-time, unusual patterns
  5  Unknown/frontier — no known capability map
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── SiteEntry ─────────────────────────────────────────────────────────────────

@dataclass
class SiteEntry:
    """One registered web environment.

    Fields
    ──────
    key                 Stable short identifier used as env_key everywhere.
    url                 Entry-point URL for exploration.
    category            One of the 30 category strings (see module docstring).
    difficulty          1-5 scale (see module docstring).
    auth_required       True if the site requires login to exercise core capabilities.
    known_capabilities  Hint strings already mapped for this site (may be empty).
    exploration_priority  0-10, higher = preferred when budgeting exploration.
                        Set higher for sites with high expected novelty or transfer value.
    exploration_budget  Soft default step budget for ExplorationSpec.
    transfer_family     TransferArena family this site belongs to.
                        Must match a key in ARENA_CONFIGS or be None.
    is_training_env     If True, included in training_envs for its transfer_family.
    is_test_env         If True, included in test_envs for its transfer_family.
    notes               Free-form annotation (not used in any logic).
    """
    key: str
    url: str
    category: str
    difficulty: int = 2
    auth_required: bool = False
    known_capabilities: List[str] = field(default_factory=list)
    exploration_priority: int = 5
    exploration_budget: int = 200
    transfer_family: Optional[str] = None
    is_training_env: bool = False
    is_test_env: bool = False
    notes: str = ""
    anti_bot_tier: int = 0  # 0=none, 1=basic_js_checks, 2=bot_management, 3=cloudflare_waf, 4=captcha_required

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "url": self.url,
            "category": self.category,
            "difficulty": self.difficulty,
            "auth_required": self.auth_required,
            "known_capabilities": list(self.known_capabilities),
            "exploration_priority": self.exploration_priority,
            "exploration_budget": self.exploration_budget,
            "transfer_family": self.transfer_family,
            "is_training_env": self.is_training_env,
            "is_test_env": self.is_test_env,
            "notes": self.notes,
            "anti_bot_tier": self.anti_bot_tier,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SiteEntry":
        d = dict(d)
        d.setdefault("difficulty", 2)
        d.setdefault("auth_required", False)
        d.setdefault("known_capabilities", [])
        d.setdefault("exploration_priority", 5)
        d.setdefault("exploration_budget", 200)
        d.setdefault("transfer_family", None)
        d.setdefault("is_training_env", False)
        d.setdefault("is_test_env", False)
        d.setdefault("notes", "")
        d.setdefault("anti_bot_tier", 0)
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


# ── Registry ──────────────────────────────────────────────────────────────────

def _r(
    key: str,
    url: str,
    category: str,
    difficulty: int = 2,
    auth_required: bool = False,
    known_capabilities: Optional[List[str]] = None,
    exploration_priority: int = 5,
    exploration_budget: int = 200,
    transfer_family: Optional[str] = None,
    is_training_env: bool = False,
    is_test_env: bool = False,
    notes: str = "",
    anti_bot_tier: int = 0,
) -> SiteEntry:
    return SiteEntry(
        key=key, url=url, category=category, difficulty=difficulty,
        auth_required=auth_required,
        known_capabilities=known_capabilities or [],
        exploration_priority=exploration_priority,
        exploration_budget=exploration_budget,
        transfer_family=transfer_family,
        is_training_env=is_training_env,
        is_test_env=is_test_env,
        notes=notes,
        anti_bot_tier=anti_bot_tier,
    )


# ── Seed data — 30 categories × representative sites ─────────────────────────
# Keys match ARENA_CONFIGS training/test env lists in transfer_arena.py

_SEED_ENTRIES: List[SiteEntry] = [

    # ── 1. Social Networks ────────────────────────────────────────────────────
    _r("facebook",    "https://www.facebook.com",    "social_networks",  difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "content_post", "social_follow"],
       transfer_family="community", is_training_env=True, exploration_priority=7, anti_bot_tier=2),
    _r("instagram",   "https://www.instagram.com",   "social_networks",  difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "media_upload", "social_follow"],
       transfer_family="community", is_test_env=True, exploration_priority=6, anti_bot_tier=2),
    _r("twitter_x",   "https://x.com",               "social_networks",  difficulty=4, auth_required=True,
       known_capabilities=["auth_login", "content_post", "search_query_input"],
       transfer_family="community", is_test_env=True, exploration_priority=8, anti_bot_tier=2),
    _r("linkedin",    "https://www.linkedin.com",    "social_networks",  difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "profile_edit", "social_follow"],
       transfer_family="community", is_test_env=True, exploration_priority=7, anti_bot_tier=2),
    _r("bluesky",     "https://bsky.app",            "social_networks",  difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "content_post"],
       transfer_family="community", is_test_env=True, exploration_priority=6),

    # ── 2. Forums & Communities ───────────────────────────────────────────────
    _r("reddit",      "https://www.reddit.com",      "forums_communities", difficulty=3, auth_required=False,
       known_capabilities=["community_post", "community_vote", "search_query_input"],
       transfer_family="community", is_training_env=True, exploration_priority=9,
       exploration_budget=300),
    _r("stackoverflow","https://stackoverflow.com",  "forums_communities", difficulty=2, auth_required=False,
       known_capabilities=["community_post", "community_vote", "search_query_input"],
       transfer_family="community", is_training_env=True, exploration_priority=7),
    _r("hackernews",  "https://news.ycombinator.com","forums_communities", difficulty=2, auth_required=False,
       known_capabilities=["community_post", "community_vote"],
       transfer_family="community", is_training_env=True, exploration_priority=6),
    _r("lemmy",       "https://lemmy.world",         "forums_communities", difficulty=2, auth_required=False,
       known_capabilities=["community_post", "community_vote"],
       transfer_family="community", is_test_env=True, exploration_priority=5),
    _r("quora",       "https://www.quora.com",       "forums_communities", difficulty=3, auth_required=False,
       known_capabilities=["community_post", "search_query_input"],
       transfer_family="community", is_test_env=True, exploration_priority=5),

    # ── 3. Chat & Real-Time ───────────────────────────────────────────────────
    _r("discord",     "https://discord.com",         "chat_realtime",    difficulty=4, auth_required=True,
       known_capabilities=["auth_login", "content_post"],
       transfer_family="community", is_test_env=True, exploration_priority=7),
    _r("slack",       "https://slack.com",           "chat_realtime",    difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "content_post"],
       exploration_priority=6),
    _r("telegram_web","https://web.telegram.org",    "chat_realtime",    difficulty=4, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=6),

    # ── 4. Video Platforms ────────────────────────────────────────────────────
    _r("youtube",     "https://www.youtube.com",     "video_platforms",  difficulty=3, auth_required=False,
       known_capabilities=["search_query_input", "media_play"],
       exploration_priority=8, exploration_budget=250),
    _r("twitch",      "https://www.twitch.tv",       "video_platforms",  difficulty=3, auth_required=False,
       known_capabilities=["search_query_input", "media_play"],
       exploration_priority=6),
    _r("vimeo",       "https://vimeo.com",           "video_platforms",  difficulty=2, auth_required=False,
       known_capabilities=["search_query_input", "media_play"],
       exploration_priority=5),

    # ── 5. Audio Platforms ────────────────────────────────────────────────────
    _r("spotify_web", "https://open.spotify.com",   "audio_platforms",  difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "search_query_input", "media_play"],
       exploration_priority=6),
    _r("soundcloud",  "https://soundcloud.com",      "audio_platforms",  difficulty=2, auth_required=False,
       known_capabilities=["search_query_input", "media_play"],
       exploration_priority=5),

    # ── 6. Image Platforms ────────────────────────────────────────────────────
    _r("pinterest",   "https://www.pinterest.com",  "image_platforms",  difficulty=3, auth_required=False,
       known_capabilities=["search_query_input", "media_upload"],
       exploration_priority=5),
    _r("flickr",      "https://www.flickr.com",     "image_platforms",  difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),
    _r("unsplash",    "https://unsplash.com",       "image_platforms",  difficulty=1, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),

    # ── 7. News & Publishing ──────────────────────────────────────────────────
    _r("bbc_news",    "https://www.bbc.com/news",   "news_publishing",  difficulty=1, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),
    _r("reuters",     "https://www.reuters.com",    "news_publishing",  difficulty=1, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),
    _r("medium",      "https://medium.com",         "news_publishing",  difficulty=2, auth_required=False,
       known_capabilities=["search_query_input", "content_post"],
       exploration_priority=5),

    # ── 8. Blogs & Personal ───────────────────────────────────────────────────
    _r("dev_to",      "https://dev.to",             "blogs_personal",   difficulty=2, auth_required=False,
       known_capabilities=["search_query_input", "community_post"],
       exploration_priority=6),
    _r("hashnode",    "https://hashnode.com",       "blogs_personal",   difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),

    # ── 9. E-Commerce ─────────────────────────────────────────────────────────
    _r("amazon",      "https://www.amazon.com",     "ecommerce",        difficulty=3, auth_required=False,
       known_capabilities=["search_query_input", "form_submit", "cart_add"],
       exploration_priority=8, exploration_budget=300),
    _r("ebay",        "https://www.ebay.com",       "ecommerce",        difficulty=3, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=6),
    _r("etsy",        "https://www.etsy.com",       "ecommerce",        difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),
    _r("aliexpress",  "https://www.aliexpress.com", "ecommerce",        difficulty=4, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5, anti_bot_tier=2),

    # ── 10. Marketplaces (Services / P2P) ─────────────────────────────────────
    _r("fiverr",      "https://www.fiverr.com",     "marketplaces",     difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),
    _r("upwork",      "https://www.upwork.com",     "marketplaces",     difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=6),
    _r("airbnb",      "https://www.airbnb.com",     "marketplaces",     difficulty=3, auth_required=False,
       known_capabilities=["search_query_input", "form_submit"],
       exploration_priority=6),

    # ── 11. SaaS Applications ─────────────────────────────────────────────────
    _r("notion",      "https://www.notion.so",      "saas_applications",difficulty=4, auth_required=True,
       known_capabilities=["auth_login", "content_post"],
       exploration_priority=7, exploration_budget=250),
    _r("canva",       "https://www.canva.com",      "saas_applications",difficulty=4, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=5),
    _r("airtable",    "https://airtable.com",       "saas_applications",difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=5),

    # ── 12. Productivity Systems ──────────────────────────────────────────────
    _r("trello",      "https://trello.com",         "productivity_systems", difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=5),
    _r("asana",       "https://asana.com",          "productivity_systems", difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=5),
    _r("linear",      "https://linear.app",         "productivity_systems", difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=6),

    # ── 13. Knowledge Systems ─────────────────────────────────────────────────
    _r("wikipedia",   "https://www.wikipedia.org",  "knowledge_systems",difficulty=1, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=6),
    _r("confluence",  "https://www.atlassian.com/software/confluence", "knowledge_systems",
       difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "content_post"],
       exploration_priority=4),

    # ── 14. Developer Platforms ───────────────────────────────────────────────
    _r("github",      "https://github.com",         "developer_platforms", difficulty=2, auth_required=True,
       known_capabilities=["auth_login", "auth_password_input", "form_submit", "search_query_input"],
       transfer_family="authentication", is_training_env=True, exploration_priority=9,
       exploration_budget=250),
    _r("gitlab",      "https://gitlab.com",         "developer_platforms", difficulty=2, auth_required=True,
       known_capabilities=["auth_login", "auth_password_input", "form_submit"],
       transfer_family="authentication", is_test_env=True, exploration_priority=8),
    _r("huggingface", "https://huggingface.co",     "developer_platforms", difficulty=2, auth_required=True,
       known_capabilities=["auth_login", "search_query_input"],
       transfer_family="authentication", is_test_env=True, exploration_priority=7),
    _r("bitbucket",   "https://bitbucket.org",      "developer_platforms", difficulty=2, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       transfer_family="authentication", is_test_env=True, exploration_priority=6),
    _r("replit",      "https://replit.com",         "developer_platforms", difficulty=3, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=6),

    # ── 15. Package Registries ────────────────────────────────────────────────
    _r("pypi",        "https://pypi.org",           "package_registries", difficulty=1, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),
    _r("npmjs",       "https://www.npmjs.com",      "package_registries", difficulty=1, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),
    _r("crates_io",   "https://crates.io",          "package_registries", difficulty=1, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),

    # ── 16. Cloud Platforms ───────────────────────────────────────────────────
    _r("cloudflare",  "https://dash.cloudflare.com","cloud_platforms",  difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=6, anti_bot_tier=3),
    _r("digitalocean","https://cloud.digitalocean.com","cloud_platforms",difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=5),
    _r("vercel",      "https://vercel.com",         "cloud_platforms",  difficulty=2, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=6),
    _r("netlify",     "https://app.netlify.com",    "cloud_platforms",  difficulty=2, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=5),

    # ── 17. Authentication Systems ────────────────────────────────────────────
    _r("saucedemo",   "https://www.saucedemo.com",  "authentication_systems", difficulty=1, auth_required=True,
       known_capabilities=["auth_login", "auth_password_input"],
       transfer_family="authentication", is_training_env=True, exploration_priority=10,
       notes="Standard login test site; low difficulty, ideal for protocol validation"),
    _r("google",      "https://accounts.google.com","authentication_systems", difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "auth_password_input", "auth_mfa_input"],
       transfer_family="authentication", is_training_env=True, exploration_priority=9),
    _r("auth0_demo",  "https://auth0.com",          "authentication_systems", difficulty=2, auth_required=True,
       known_capabilities=["auth_login", "oauth_redirect"],
       transfer_family="authentication", is_test_env=True, exploration_priority=7),

    # ── 18. Email Systems ─────────────────────────────────────────────────────
    _r("gmail",       "https://mail.google.com",    "email_systems",    difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit", "search_query_input"],
       exploration_priority=7),
    _r("protonmail",  "https://mail.proton.me",     "email_systems",    difficulty=2, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=5),

    # ── 19. Government Portals ────────────────────────────────────────────────
    _r("usa_gov",     "https://www.usa.gov",        "government_portals", difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),
    _r("gov_uk",      "https://www.gov.uk",         "government_portals", difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),

    # ── 20. Banking & Finance ─────────────────────────────────────────────────
    _r("paypal",      "https://www.paypal.com",     "banking_finance",  difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=6),
    _r("wise",        "https://wise.com",           "banking_finance",  difficulty=2, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=5),
    _r("stripe_dashboard","https://dashboard.stripe.com","banking_finance",difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=5),

    # ── 21. Crypto Platforms ──────────────────────────────────────────────────
    _r("coinbase",    "https://www.coinbase.com",   "crypto_platforms", difficulty=4, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=5, anti_bot_tier=3),
    _r("coingecko",   "https://www.coingecko.com",  "crypto_platforms", difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),
    _r("etherscan",   "https://etherscan.io",       "crypto_platforms", difficulty=3, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),

    # ── 22. Education Platforms ───────────────────────────────────────────────
    _r("coursera",    "https://www.coursera.org",   "education_platforms", difficulty=3, auth_required=False,
       known_capabilities=["search_query_input", "form_submit"],
       exploration_priority=5),
    _r("duolingo",    "https://www.duolingo.com",   "education_platforms", difficulty=3, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=5),
    _r("khanacademy", "https://www.khanacademy.org","education_platforms", difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),

    # ── 23. Job Platforms ─────────────────────────────────────────────────────
    _r("linkedin_jobs","https://www.linkedin.com/jobs","job_platforms", difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "search_query_input", "form_submit"],
       transfer_family="form_fill", is_training_env=True, exploration_priority=7),
    _r("indeed",      "https://www.indeed.com",     "job_platforms",    difficulty=2, auth_required=False,
       known_capabilities=["search_query_input", "form_submit"],
       transfer_family="form_fill", is_training_env=True, exploration_priority=6),
    _r("glassdoor",   "https://www.glassdoor.com",  "job_platforms",    difficulty=2, auth_required=False,
       known_capabilities=["search_query_input", "form_submit"],
       transfer_family="form_fill", is_test_env=True, exploration_priority=5),

    # ── 24. CMS & Site Builders ───────────────────────────────────────────────
    _r("wordpress_com","https://wordpress.com",     "cms_sitebuilders", difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "content_post", "form_submit"],
       exploration_priority=5),
    _r("webflow",     "https://webflow.com",        "cms_sitebuilders", difficulty=4, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=5),

    # ── 25. Search Engines ────────────────────────────────────────────────────
    _r("google_search","https://www.google.com",    "search_engines",   difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       transfer_family="search", is_training_env=True, exploration_priority=9),
    _r("bing",        "https://www.bing.com",       "search_engines",   difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       transfer_family="search", is_training_env=True, exploration_priority=7),
    _r("duckduckgo",  "https://duckduckgo.com",     "search_engines",   difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       transfer_family="search", is_training_env=True, exploration_priority=7),
    _r("brave_search","https://search.brave.com",   "search_engines",   difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       transfer_family="search", is_test_env=True, exploration_priority=6),
    _r("kagi",        "https://kagi.com",           "search_engines",   difficulty=2, auth_required=True,
       known_capabilities=["search_query_input"],
       transfer_family="search", is_test_env=True, exploration_priority=6),
    _r("yandex",      "https://yandex.com",         "search_engines",   difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       transfer_family="search", is_test_env=True, exploration_priority=5),

    # ── 26. Maps & Local Discovery ────────────────────────────────────────────
    _r("google_maps", "https://maps.google.com",    "maps_local_discovery", difficulty=4, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=7),
    _r("openstreetmap","https://www.openstreetmap.org","maps_local_discovery",difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),
    _r("yelp",        "https://www.yelp.com",       "maps_local_discovery", difficulty=3, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=5),

    # ── 27. Travel Systems ────────────────────────────────────────────────────
    _r("booking_com", "https://www.booking.com",    "travel_systems",   difficulty=3, auth_required=False,
       known_capabilities=["search_query_input", "form_submit"],
       exploration_priority=6),
    _r("skyscanner",  "https://www.skyscanner.com", "travel_systems",   difficulty=3, auth_required=False,
       known_capabilities=["search_query_input", "form_submit"],
       exploration_priority=5),
    _r("tripadvisor", "https://www.tripadvisor.com","travel_systems",   difficulty=2, auth_required=False,
       known_capabilities=["search_query_input"],
       exploration_priority=4),

    # ── 28. AI Platforms ──────────────────────────────────────────────────────
    _r("chatgpt",     "https://chatgpt.com",        "ai_platforms",     difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "content_post"],
       exploration_priority=7),
    _r("perplexity",  "https://www.perplexity.ai",  "ai_platforms",     difficulty=2, auth_required=False,
       known_capabilities=["search_query_input", "content_post"],
       exploration_priority=7),
    _r("huggingchat", "https://huggingface.co/chat","ai_platforms",     difficulty=2, auth_required=False,
       known_capabilities=["content_post"],
       exploration_priority=6),

    # ── 29. Dashboards & Admin Panels ─────────────────────────────────────────
    _r("grafana",     "https://grafana.com",        "dashboards_admin", difficulty=4, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=5),
    _r("metabase",    "https://www.metabase.com",   "dashboards_admin", difficulty=3, auth_required=True,
       known_capabilities=["auth_login"],
       exploration_priority=4),
    _r("supabase",    "https://supabase.com",       "dashboards_admin", difficulty=3, auth_required=True,
       known_capabilities=["auth_login", "form_submit"],
       exploration_priority=6),

    # ── 30. Unknown Frontier ──────────────────────────────────────────────────
    # These are placeholder entries for the frontier category.
    # Real frontier sites are discovered at runtime; these represent archetypes.
    _r("router_admin",   "http://192.168.1.1",      "unknown_frontier", difficulty=5, auth_required=True,
       known_capabilities=[],
       exploration_priority=10, exploration_budget=400,
       notes="Generic router admin panel; very high novelty potential"),
    _r("local_iot_device","http://10.0.0.1",        "unknown_frontier", difficulty=5, auth_required=True,
       known_capabilities=[],
       exploration_priority=10, exploration_budget=400,
       notes="Generic IoT device local web interface"),
]

# ── Build the registry dict ───────────────────────────────────────────────────

SITE_REGISTRY: Dict[str, SiteEntry] = {e.key: e for e in _SEED_ENTRIES}


# ── Public API ────────────────────────────────────────────────────────────────

def get(key: str) -> Optional[SiteEntry]:
    """Return SiteEntry for key, or None if not registered."""
    return SITE_REGISTRY.get(key)


def register(entry: SiteEntry) -> None:
    """Add or replace a SiteEntry in the registry. Call at startup for custom sites."""
    SITE_REGISTRY[entry.key] = entry


def keys() -> List[str]:
    """All registered site keys."""
    return list(SITE_REGISTRY.keys())


def by_category(category: str) -> List[SiteEntry]:
    """All entries for a given category string."""
    return [e for e in SITE_REGISTRY.values() if e.category == category]


def by_difficulty(max_difficulty: int = 5) -> List[SiteEntry]:
    """All entries with difficulty <= max_difficulty."""
    return [e for e in SITE_REGISTRY.values() if e.difficulty <= max_difficulty]


def training_envs_for_family(family: str) -> List[str]:
    """Return list of keys where is_training_env=True and transfer_family==family."""
    return [
        e.key for e in SITE_REGISTRY.values()
        if e.transfer_family == family and e.is_training_env
    ]


def test_envs_for_family(family: str) -> List[str]:
    """Return list of keys where is_test_env=True and transfer_family==family."""
    return [
        e.key for e in SITE_REGISTRY.values()
        if e.transfer_family == family and e.is_test_env
    ]


def exploration_candidates(
    max_difficulty: int = 5,
    category: Optional[str] = None,
    min_priority: int = 0,
) -> List[SiteEntry]:
    """Return sites sorted by exploration_priority descending.

    Used by ExplorationHarness to pick the next target.
    """
    entries = [
        e for e in SITE_REGISTRY.values()
        if e.difficulty <= max_difficulty
        and e.exploration_priority >= min_priority
        and (category is None or e.category == category)
    ]
    entries.sort(key=lambda e: e.exploration_priority, reverse=True)
    return entries


def all_entries() -> List[SiteEntry]:
    """All registered SiteEntry objects."""
    return list(SITE_REGISTRY.values())
