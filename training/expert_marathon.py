"""
BrowserMind — Authenticated Expert Marathon
============================================
5-hour continuous expert demonstration using saved session state.
Runs complex tasks across Google, LinkedIn, Reddit, GitHub, YouTube, etc.
Every step is recorded as Golden training data (S_GOLD_MARATHON_*).

Run after auth_hub.py has saved a session:
    python training/expert_marathon.py
"""
import asyncio
import argparse
import sys
import os
import time
import json
import re
import random
from pathlib import Path

# Authenticated runs should never persist raw typed payloads.
os.environ.setdefault("BROWSERMIND_STRICT_PRIVACY", "1")

# Force UTF-8 output for Windows console
sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.getcwd())
from playwright.async_api import async_playwright
from training.graph_builder import build_graph_from_page_pruned
from training.session_manager import get_session_path, save_session_state
from training.web_taxonomy import WEB_LAYERS
from collect_massive import SessionRecorder, _execute_action

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SESSIONS_DIR = Path("training/massive_sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

ACTION_MAP = {
    "navigate": 0, "click": 1, "type": 2, "scroll": 3,
    "wait": 4, "extract": 5, "go_back": 6, "done": 7
}

# ─────────────────────────────────────────────────────────
#  Expert Marathon Task List
#  (goal, start_url, steps)
#  steps = list of (action, selector_hint, value)
# ─────────────────────────────────────────────────────────
MARATHON_TASKS = [
    # ── GOOGLE ───────────────────────────────────────────
    {
        "goal": "Search for 'BrowserMind AI agent 2024' on Google and extract top 5 results",
        "url":  "https://www.google.com",
        "sid":  "S_GOLD_MARATHON_GOOGLE_SEARCH",
    },
    {
        "goal": "Navigate to Google News and extract top 10 headlines",
        "url":  "https://news.google.com",
        "sid":  "S_GOLD_MARATHON_GOOGLE_NEWS",
    },
    {
        "goal": "Open Gmail and navigate to Inbox then extract the first 5 email subjects",
        "url":  "https://mail.google.com",
        "sid":  "S_GOLD_MARATHON_GMAIL_INBOX",
    },
    {
        "goal": "Open Gmail compose window and write a draft email",
        "url":  "https://mail.google.com",
        "sid":  "S_GOLD_MARATHON_GMAIL_COMPOSE",
    },
    {
        "goal": "Navigate to Google Drive and extract recent file names",
        "url":  "https://drive.google.com",
        "sid":  "S_GOLD_MARATHON_GDRIVE",
    },
    {
        "goal": "Search Google Scholar for 'large language models 2024' and extract paper titles",
        "url":  "https://scholar.google.com",
        "sid":  "S_GOLD_MARATHON_SCHOLAR",
    },
    # ── YOUTUBE ──────────────────────────────────────────
    {
        "goal": "Navigate to YouTube trending page and extract top 10 video titles",
        "url":  "https://www.youtube.com/feed/trending",
        "sid":  "S_GOLD_MARATHON_YT_TRENDING",
    },
    {
        "goal": "Search YouTube for 'machine learning tutorial 2024' and extract first 5 video titles",
        "url":  "https://www.youtube.com",
        "sid":  "S_GOLD_MARATHON_YT_SEARCH",
    },
    # ── REDDIT ───────────────────────────────────────────
    {
        "goal": "Navigate to r/MachineLearning and extract top 10 post titles and scores",
        "url":  "https://www.reddit.com/r/MachineLearning",
        "sid":  "S_GOLD_MARATHON_REDDIT_ML",
    },
    {
        "goal": "Navigate to r/programming and scroll to find 5 posts with over 1000 upvotes",
        "url":  "https://www.reddit.com/r/programming",
        "sid":  "S_GOLD_MARATHON_REDDIT_PROG",
    },
    {
        "goal": "Search Reddit for 'AI agent automation' and extract first 5 results",
        "url":  "https://www.reddit.com/search/?q=AI+agent+automation",
        "sid":  "S_GOLD_MARATHON_REDDIT_SEARCH",
    },
    # ── GITHUB ───────────────────────────────────────────
    {
        "goal": "Navigate to GitHub trending repositories and extract top 10 repo names and stars",
        "url":  "https://github.com/trending",
        "sid":  "S_GOLD_MARATHON_GITHUB_TRENDING",
    },
    {
        "goal": "Search GitHub for 'browser agent python' and extract top 5 repository names",
        "url":  "https://github.com/search?q=browser+agent+python&type=repositories",
        "sid":  "S_GOLD_MARATHON_GITHUB_SEARCH",
    },
    {
        "goal": "Navigate to GitHub notifications and extract notification titles",
        "url":  "https://github.com/notifications",
        "sid":  "S_GOLD_MARATHON_GITHUB_NOTIF",
    },
    # ── LINKEDIN ─────────────────────────────────────────
    {
        "goal": "Navigate to LinkedIn feed and extract top 5 post headlines",
        "url":  "https://www.linkedin.com/feed",
        "sid":  "S_GOLD_MARATHON_LINKEDIN_FEED",
    },
    {
        "goal": "Search LinkedIn jobs for 'AI Engineer' and extract top 5 job titles and companies",
        "url":  "https://www.linkedin.com/jobs/search/?keywords=AI+Engineer",
        "sid":  "S_GOLD_MARATHON_LINKEDIN_JOBS",
    },
    {
        "goal": "Navigate to LinkedIn my network page and extract connection recommendations",
        "url":  "https://www.linkedin.com/mynetwork",
        "sid":  "S_GOLD_MARATHON_LINKEDIN_NETWORK",
    },
    # ── TWITTER / X ──────────────────────────────────────
    {
        "goal": "Navigate to X (Twitter) and extract trending topics from the right sidebar",
        "url":  "https://x.com/explore",
        "sid":  "S_GOLD_MARATHON_TWITTER_TRENDS",
    },
    {
        "goal": "Search X for 'AI agents 2024' and extract first 5 tweet texts",
        "url":  "https://x.com/search?q=AI+agents+2024&f=live",
        "sid":  "S_GOLD_MARATHON_TWITTER_SEARCH",
    },
    # ── ARXIV ────────────────────────────────────────────
    {
        "goal": "Search arXiv for 'vision language agents' and extract titles and authors of 5 papers",
        "url":  "https://arxiv.org/search/?query=vision+language+agents&searchtype=all",
        "sid":  "S_GOLD_MARATHON_ARXIV_VLA",
    },
    {
        "goal": "Navigate to arXiv cs.AI recent submissions and extract top 10 paper titles",
        "url":  "https://arxiv.org/list/cs.AI/recent",
        "sid":  "S_GOLD_MARATHON_ARXIV_AI",
    },
    # ── E-COMMERCE ───────────────────────────────────────
    {
        "goal": "Navigate to Amazon Best Sellers Electronics and extract top 5 product names and prices",
        "url":  "https://www.amazon.com/best-sellers-electronics/zgbs/electronics",
        "sid":  "S_GOLD_MARATHON_AMAZON_ELECTRONICS",
    },
    {
        "goal": "Search Amazon for 'mechanical keyboard' and extract top 5 results with prices",
        "url":  "https://www.amazon.com/s?k=mechanical+keyboard",
        "sid":  "S_GOLD_MARATHON_AMAZON_SEARCH",
    },
    # ── DEVELOPER TOOLS ─────────────────────────────────
    {
        "goal": "Navigate to Hacker News and extract top 10 story titles and point counts",
        "url":  "https://news.ycombinator.com",
        "sid":  "S_GOLD_MARATHON_HN",
    },
    {
        "goal": "Navigate to Stack Overflow questions and extract top 5 question titles and vote counts",
        "url":  "https://stackoverflow.com/questions?sort=votes",
        "sid":  "S_GOLD_MARATHON_SO",
    },
    {
        "goal": "Navigate to Hugging Face models and extract top 10 most downloaded model names",
        "url":  "https://huggingface.co/models?sort=downloads",
        "sid":  "S_GOLD_MARATHON_HF_MODELS",
    },
    # ── NEWS ────────────────────────────────────────────
    {
        "goal": "Navigate to BBC News and extract all article headlines on the front page",
        "url":  "https://www.bbc.com/news",
        "sid":  "S_GOLD_MARATHON_BBC",
    },
    {
        "goal": "Navigate to TechCrunch and extract all article headlines",
        "url":  "https://techcrunch.com",
        "sid":  "S_GOLD_MARATHON_TECHCRUNCH",
    },
    {
        "goal": "Navigate to Al Jazeera Arabic and extract top news headlines",
        "url":  "https://www.aljazeera.net",
        "sid":  "S_GOLD_MARATHON_ALJAZEERA_AR",
    },
    # ── WIKIPEDIA ───────────────────────────────────────
    {
        "goal": "Search Wikipedia for 'Transformer neural network' and extract all section headings",
        "url":  "https://en.wikipedia.org/wiki/Transformer_(machine_learning_model)",
        "sid":  "S_GOLD_MARATHON_WIKI_TRANSFORMER",
    },
]


_QUERY_BANK = [
    "AI automation",
    "machine learning",
    "browser agent",
    "deep learning",
    "python",
    "startup trends",
    "productivity",
    "cloud workflows",
    "web scraping",
    "prompt engineering",
]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def _build_goal(site_name: str, capability: str, query: str) -> str:
    if capability == "search":
        return f"Search {site_name} for '{query}' and extract top visible results"
    if capability == "scroll":
        return f"Scroll {site_name} and extract visible content blocks"
    if capability == "extract":
        return f"Extract key visible headlines and items from {site_name}"
    if capability == "like":
        return f"Like one visible post on {site_name}"
    if capability == "comment":
        return f"Comment on one visible post on {site_name} with text 'Great insights, thanks for sharing.'"
    if capability == "share":
        return f"Share or repost one visible post on {site_name}"
    if capability == "post":
        return f"Create a new post on {site_name} with text 'BrowserMind training post about {query}.'"
    if capability == "follow":
        return f"Follow or subscribe to one relevant account on {site_name}"
    return f"Explore {site_name} and extract useful visible information"


def build_social_world_tasks(
    include_sensitive: bool = False,
    layer_filter: set[str] | None = None,
) -> list[dict]:
    """Build taxonomy-driven web tasks using layer target counts."""
    tasks: list[dict] = []

    for layer in WEB_LAYERS:
        lid = str(layer.get("id", ""))
        if layer_filter and lid not in layer_filter:
            continue
        if bool(layer.get("sensitive", False)) and not include_sensitive:
            continue

        sites = layer.get("sites", []) or []
        caps = layer.get("capabilities", []) or ["extract"]
        target_count = max(1, int(layer.get("target_count", len(sites) or 1)))
        if not sites:
            continue

        for i in range(target_count):
            site = sites[i % len(sites)]
            site_name = str(site.get("name", "website"))
            site_url = str(site.get("url", "")).strip()
            if not site_url:
                continue
            capability = str(caps[i % len(caps)])
            query = _QUERY_BANK[i % len(_QUERY_BANK)]
            goal = _build_goal(site_name, capability, query)
            sid = f"S_GOLD_WORLD_{_slug(lid)}_{_slug(site_name)}_{capability.upper()}_{i+1:03d}"
            tasks.append({
                "goal": goal,
                "url": site_url,
                "sid": sid,
                "layer": lid,
            })

    return tasks


class ExpertMarathonRunner:
    def __init__(self, auth_state_path: Path = None, tasks=None, save_auth_state: bool = False):
        self.auth_state_path = auth_state_path
        self.tasks = tasks or MARATHON_TASKS
        self.save_auth_state = bool(save_auth_state)
        self.sessions_completed = 0
        self.sessions_failed = 0
        self.total = len(self.tasks)

    async def _stealth_context(self, pw):
        """Launch real Chrome with persistent profile."""
        PROFILE_DIR = r"C:\Users\mg\.browsermind\chrome_profile"
        
        ctx_args = {
            "headless": False,
            "executable_path": CHROME_PATH,
            "user_data_dir": PROFILE_DIR,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--start-maximized",
            ],
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
        }
        
        context = await pw.chromium.launch_persistent_context(**ctx_args)

        # Remove webdriver fingerprint
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        # Apply stealth to all pages
        try:
            from playwright_stealth import stealth_async
            context.on("page", lambda p: asyncio.ensure_future(stealth_async(p)))
        except ImportError:
            pass

        return None, context

    async def run_task(self, task: dict, context) -> bool:
        """Run a single marathon expert task and save session."""
        goal = task["goal"]
        url = task["url"]
        sid = task["sid"]

        print(f"\n{'─'*60}")
        print(f"[TASK] {goal[:70]}")
        print(f"[URL ] {url}")

        recorder = SessionRecorder(goal, SESSIONS_DIR)
        page = await context.new_page()
        step = 1

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # ── Do 6–10 autonomous expert reasoning steps ──
            for i in range(8):
                try:
                    graph = await build_graph_from_page_pruned(page, max_nodes=80)
                except Exception:
                    break

                nodes = graph.get("nodes", [])
                if not nodes:
                    break

                # Expert logic: decide what to do based on goal keywords
                action_type, element_idx, value = await self._expert_decide(
                    page, nodes, goal, step, i
                )

                expert_action = {
                    "type": action_type,
                    "action_id": ACTION_MAP.get(action_type, 1),
                    "element_idx": element_idx,
                    "value": value,
                }
                if isinstance(element_idx, int) and 0 <= element_idx < len(nodes):
                    expert_action["target_text"] = str(nodes[element_idx].get("name", ""))
                recorder.record(graph, expert_action, page.url, step, success=True)
                print(f"  Step {step}: {action_type:10} idx={element_idx} val={str(value)[:40]!r}")

                if action_type == "done":
                    break

                try:
                    await _execute_action(page, expert_action, nodes)
                except Exception as e:
                    print(f"  [WARN] Action failed: {e}")

                await asyncio.sleep(2)
                step += 1

            # Final done action
            graph = await build_graph_from_page_pruned(page, max_nodes=80)
            recorder.record(graph, {"type": "done", "action_id": 7, "element_idx": None, "value": ""}, page.url, step, success=True)

            if recorder.is_trainable():
                path = recorder.save(sid)
                print(f"  [SAVED] {path}")
                self.sessions_completed += 1
                return True
            else:
                print(f"  [SKIP] Session too short to be trainable.")
                self.sessions_failed += 1
                return False

        except Exception as e:
            print(f"  [ERROR] {e}")
            self.sessions_failed += 1
            return False
        finally:
            await page.close()

    async def _expert_decide(self, page, nodes, goal: str, step: int, iteration: int):
        """
        Expert reasoning engine: decides best action based on goal + page state.
        Uses keyword matching and node role analysis to emulate expert behavior.
        """
        goal_lower = goal.lower()

        def _name(n: dict) -> str:
            return str(n.get("name", "") or "").strip()

        def _by_roles(*roles: str) -> list[dict]:
            role_set = set(roles)
            return [n for n in nodes if str(n.get("role", "")) in role_set]

        def _find(cands: list[dict], keywords: tuple[str, ...]) -> dict | None:
            for kw in keywords:
                for c in cands:
                    if kw in _name(c).lower():
                        return c
            return None

        textboxes = _by_roles("textbox", "combobox")
        buttons = _by_roles("button", "menuitem", "tab")
        links = _by_roles("link")
        headings = _by_roles("heading")
        interactive = [n for n in nodes if str(n.get("role", "")) in {"button", "link", "menuitem", "tab", "checkbox", "radio"}]

        def _idx_or_none(node: dict | None) -> int | None:
            return int(node["idx"]) if isinstance(node, dict) and "idx" in node else None

        quoted = re.findall(r"['\"]([^'\"]+)['\"]", goal)
        quoted_text = quoted[0].strip() if quoted else ""

        search_query = quoted_text or "ai automation"
        comment_match = re.search(r"comment[^'\"]*['\"]([^'\"]+)['\"]", goal, re.IGNORECASE)
        post_match = re.search(r"post[^'\"]*['\"]([^'\"]+)['\"]", goal, re.IGNORECASE)
        comment_text = (comment_match.group(1).strip() if comment_match else "Great post. Thanks for sharing.")
        post_text = (post_match.group(1).strip() if post_match else "BrowserMind social interaction training post.")

        is_search = any(w in goal_lower for w in ("search", "find", "look up", "query"))
        is_scroll = "scroll" in goal_lower
        is_extract = any(w in goal_lower for w in ("extract", "headline", "title", "visible posts", "results"))
        is_like = any(w in goal_lower for w in ("like", "react", "upvote", "favorite", "heart", "star", "clap"))
        is_comment = any(w in goal_lower for w in ("comment", "reply"))
        is_share = any(w in goal_lower for w in ("share", "repost", "retweet", "boost"))
        is_post = any(w in goal_lower for w in ("create a new post", "create post", "write post", "publish", "tweet", "post on"))
        is_follow = any(w in goal_lower for w in ("follow", "subscribe", "connect"))

        if is_post:
            compose_keywords = ("create post", "compose", "post", "tweet", "write", "new post", "what's on your mind")
            publish_keywords = ("post", "publish", "share", "tweet", "send")
            if iteration == 0:
                node = _find(interactive, compose_keywords)
                return "click", _idx_or_none(node), ""
            if iteration == 1:
                field = _find(textboxes, ("what's on your mind", "post", "tweet", "compose", "write", "message"))
                if field is None and textboxes:
                    field = textboxes[0]
                return "type", _idx_or_none(field), post_text
            if iteration == 2:
                node = _find(interactive, publish_keywords)
                return "click", _idx_or_none(node), ""
            return "done", None, ""

        if is_comment:
            comment_keywords = ("comment", "reply", "respond")
            submit_keywords = ("post", "reply", "send", "comment")
            if iteration == 0:
                node = _find(interactive, comment_keywords)
                return "click", _idx_or_none(node), ""
            if iteration == 1:
                field = _find(textboxes, ("comment", "reply", "write a comment", "add a comment", "message"))
                if field is None and textboxes:
                    field = textboxes[0]
                return "type", _idx_or_none(field), comment_text
            if iteration == 2:
                node = _find(interactive, submit_keywords)
                return "click", _idx_or_none(node), ""
            return "done", None, ""

        if is_share:
            share_keywords = ("share", "repost", "retweet", "boost", "send")
            if iteration == 0:
                node = _find(interactive, share_keywords)
                return "click", _idx_or_none(node), ""
            if iteration == 1:
                confirm = _find(interactive, ("share", "post", "repost", "retweet", "send"))
                return "click", _idx_or_none(confirm), ""
            return "done", None, ""

        if is_like:
            like_node = _find(interactive, ("like", "react", "upvote", "favorite", "heart", "star", "clap"))
            if iteration == 0:
                return "click", _idx_or_none(like_node), ""
            return "done", None, ""

        if is_follow:
            follow_node = _find(interactive, ("follow", "subscribe", "connect", "watch"))
            if iteration == 0:
                return "click", _idx_or_none(follow_node), ""
            return "done", None, ""

        if is_search:
            if iteration == 0:
                search_field = _find(textboxes, ("search", "find", "query"))
                if search_field is None and textboxes:
                    search_field = textboxes[0]
                return "type", _idx_or_none(search_field), search_query
            if iteration == 1:
                submit = _find(interactive, ("search", "go", "submit", "find"))
                if submit:
                    return "click", _idx_or_none(submit), ""
                return "scroll", None, "down"
            if is_extract and iteration in (2, 3):
                node = headings[0] if headings else (links[0] if links else None)
                return "extract", _idx_or_none(node), ""
            if iteration < 5:
                return "scroll", None, "down"
            return "done", None, ""

        if is_extract:
            if iteration in (0, 2, 4):
                return "scroll", None, "down"
            node = headings[0] if headings else (links[0] if links else None)
            if node:
                return "extract", _idx_or_none(node), ""

        goal_words = set(goal_lower.split())
        for ln in links:
            link_words = set(_name(ln).lower().split())
            if len(goal_words & link_words) >= 2:
                return "click", _idx_or_none(ln), ""

        if is_scroll and iteration < 6:
            return "scroll", None, "down"
        if iteration < 5:
            return "scroll", None, "down"
        return "done", None, ""

    async def run_all(self):
        """Run the full marathon."""
        print(f"\n{'='*60}")
        print(f"  BrowserMind Expert Marathon — {self.total} tasks")
        print(f"  Save auth state: {self.save_auth_state}")
        print(f"{'='*60}\n")

        auth_path = get_session_path()
        if not auth_path:
            print("[WARN] No saved session found. Running without authentication.")

        async with async_playwright() as pw:
            browser, context = await self._stealth_context(pw)
            batch_size = 5

            for i, task in enumerate(self.tasks):
                print(f"\n[{i+1}/{self.total}] Starting task...")
                await self.run_task(task, context)

                # Save updated session state periodically
                if self.save_auth_state and (i + 1) % batch_size == 0:
                    try:
                        await save_session_state(context)
                    except Exception:
                        pass
                    print(f"\n  [CHECKPOINT] {self.sessions_completed} sessions saved so far.")

                    # Fine-tune immediately on fresh golden data
                    print(f"  [FINE-TUNE] Running BC epoch on latest golden data...")
                    import subprocess, sys as _sys
                    subprocess.Popen(
                        [_sys.executable, "train_bc.py",
                         "--data", "training/massive_sessions",
                         "--epochs", "2", "--lr", "5e-4"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )

            if self.save_auth_state:
                await save_session_state(context)
            if browser:
                await browser.close()
            else:
                await context.close()

        print(f"\n{'='*60}")
        print(f"  MARATHON COMPLETE")
        print(f"  Sessions completed : {self.sessions_completed}")
        print(f"  Sessions failed    : {self.sessions_failed}")
        print(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run authenticated expert marathon data collection")
    parser.add_argument("--social-only", action="store_true", help="Run only social-platform tasks")
    parser.add_argument("--all-websites", action="store_true", help="Run taxonomy-driven multi-layer global web coverage")
    parser.add_argument("--include-sensitive", action="store_true", help="Include sensitive high-traffic layers")
    parser.add_argument("--shuffle-tasks", action="store_true", help="Shuffle task order before optional truncation")
    parser.add_argument("--seed", type=int, default=42, help="Seed for task shuffling")
    parser.add_argument("--max-tasks", type=int, default=0, help="Optional cap on number of tasks to run")
    parser.add_argument("--save-auth-state", action="store_true", help="Persist cookies/local storage auth state to disk")
    args = parser.parse_args()

    tasks = MARATHON_TASKS
    if args.all_websites:
        tasks = build_social_world_tasks(include_sensitive=args.include_sensitive)
    elif args.social_only:
        tasks = build_social_world_tasks(
            include_sensitive=args.include_sensitive,
            layer_filter={"social_attention", "video_streaming_media"},
        )

    if args.shuffle_tasks:
        rng = random.Random(int(args.seed))
        rng.shuffle(tasks)

    if args.max_tasks > 0:
        tasks = tasks[: args.max_tasks]

    runner = ExpertMarathonRunner(
        auth_state_path=get_session_path(),
        tasks=tasks,
        save_auth_state=args.save_auth_state,
    )
    asyncio.run(runner.run_all())
