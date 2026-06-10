"""
BrowserMind — DAgger Task Set
================================
50+ (goal, start_url) pairs for Phase 2 DAgger rollouts.
Covers: login, search, form fill, navigation, extraction.

Import with:
    from training.dagger_tasks import DAGGER_TASKS
"""

from typing import List, Tuple

# Each entry is (goal, start_url)
DAGGER_TASKS: List[Tuple[str, str]] = [

    # ── Login tasks ───────────────────────────────────────────────────────────
    ("log in to GitHub with username testuser",          "https://github.com/login"),
    # ("sign in to Reddit",                                "https://www.reddit.com/login"),
    ("login to Wikipedia account",                       "https://en.wikipedia.org/w/index.php?title=Special:UserLogin"),
    ("sign in to Stack Overflow",                        "https://stackoverflow.com/users/login"),
    ("log into HackerNews",                              "https://news.ycombinator.com/login"),

    # ── Search tasks ─────────────────────────────────────────────────────────
    ("search for python asyncio on Google",              "https://www.google.com"),
    ("search for machine learning on DuckDuckGo",        "https://duckduckgo.com"),
    ("search Wikipedia for neural networks",             "https://en.wikipedia.org"),
    ("search for PyTorch documentation",                 "https://www.google.com"),
    ("find information about transformers architecture", "https://www.google.com"),
    # ("search for climate change on Bing",                "https://www.bing.com"),
    ("look up Python tutorial on YouTube",               "https://www.youtube.com"),
    ("search for latest AI news",                        "https://www.google.com"),
    ("find reinforcement learning papers",               "https://scholar.google.com"),
    ("search for attention is all you need paper",       "https://arxiv.org"),

    # ── Navigation tasks ─────────────────────────────────────────────────────
    ("navigate to the Python official documentation",    "https://www.python.org"),
    ("go to the PyTorch getting started page",           "https://pytorch.org"),
    ("navigate to Wikipedia's article on deep learning", "https://en.wikipedia.org"),
    ("go to GitHub trending repositories",               "https://github.com"),
    ("navigate to the HuggingFace models page",          "https://huggingface.co"),
    ("go to OpenAI research page",                       "https://openai.com"),
    ("navigate to arXiv cs.AI section",                  "https://arxiv.org"),
    ("go to Stack Overflow Python questions",             "https://stackoverflow.com"),
    ("navigate to MDN web docs for JavaScript",          "https://developer.mozilla.org"),
    ("go to the Python Package Index",                   "https://pypi.org"),

    # ── Form fill tasks ───────────────────────────────────────────────────────
    ("fill in the GitHub search box with reinforcement learning", "https://github.com"),
    ("type python into the DuckDuckGo search field and submit",   "https://duckduckgo.com"),
    ("enter deep learning in the arXiv search box",               "https://arxiv.org"),
    ("search for transformer on PyPI",                            "https://pypi.org"),
    ("type machine learning in the Wikipedia search bar",         "https://en.wikipedia.org"),
    ("search for openai gym on GitHub",                           "https://github.com"),
    ("fill the YouTube search with attention mechanism video",    "https://www.youtube.com"),
    ("enter 'sentence transformers' in HuggingFace model search", "https://huggingface.co/models"),

    # ── Extraction tasks ─────────────────────────────────────────────────────
    ("extract the current Python version from the Python website", "https://www.python.org"),
    ("read the top HackerNews headline",                          "https://news.ycombinator.com"),
    ("extract the number of stars of the PyTorch GitHub repo",    "https://github.com/pytorch/pytorch"),
    # ("get the price of the top result on Amazon for laptop",      "https://www.amazon.com"),
    ("extract the current time from time.is",                     "https://time.is"),
    ("read the description of transformers library on PyPI",      "https://pypi.org/project/transformers"),
    ("extract the abstract of the first arXiv ML result",         "https://arxiv.org/list/cs.LG/recent"),

    # ── Multi-step tasks ─────────────────────────────────────────────────────
    ("go to GitHub and search for browsermind",                   "https://github.com"),
    ("navigate to Google Scholar and search transformer survey",  "https://scholar.google.com"),
    ("go to Stack Overflow and search for PyTorch CUDA error",    "https://stackoverflow.com"),
    ("find the Wikipedia page for BERT language model",           "https://en.wikipedia.org"),
    ("navigate to YouTube and search for pytorch tutorial 2024",  "https://www.youtube.com"),
    ("go to HuggingFace and find the all-MiniLM-L6-v2 model",    "https://huggingface.co"),
    ("go to arXiv and navigate to the cs.LG new submissions",     "https://arxiv.org"),
    ("navigate to PapersWithCode and look for object detection",  "https://paperswithcode.com"),
    ("go to PyPI and find the sentence-transformers package",     "https://pypi.org"),
    ("navigate to Google and search for best GPU for training",   "https://www.google.com"),
    ("find the official PyTorch documentation for nn.Module",     "https://pytorch.org"),
    ("navigate to GitHub and look at trending Python repos",      "https://github.com/trending"),
]


from training.complex_tasks import COMPLEX_DAGGER_TASKS
DAGGER_TASKS.extend(COMPLEX_DAGGER_TASKS)

if __name__ == "__main__":
    print(f"DAgger task set: {len(DAGGER_TASKS)} tasks\n")
    for i, (goal, url) in enumerate(DAGGER_TASKS, 1):
        print(f"  {i:>3}. [{url[:35]:<35}]  {goal}")
