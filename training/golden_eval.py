"""
BrowserMind — Golden Evaluation Set (Pristine)
==============================================
A collection of 10 high-priority tasks on 'unseen' websites.
These sites are NOT in the SITE_MAP or DAGGER_TASKS.
Success on this set is the true measure of generalization.
"""

from typing import List, Tuple

GOLDEN_EVAL: List[Tuple[str, str]] = [
    # Docs with very different structure
    ("find rate limits documentation", "https://docs.anthropic.com"),
    ("find quickstart tutorial", "https://fastapi.tiangolo.com/tutorial/"),
    ("search for array methods", "https://docs.julialang.org"),

    # Product / tool UIs
    ("find pricing page", "https://www.figma.com"),
    ("navigate to templates section", "https://zapier.com"),
    ("open blog section", "https://www.notion.so"),

    # Arabic content
    ("find latest technology articles", "https://www.aljazeera.net"),
    ("search for python programming", "https://www.marefa.org"),

    # Harder forms and docs
    ("find contact form", "https://stripe.com/contact"),
    ("navigate to getting started", "https://docs.stripe.com"),
]

if __name__ == "__main__":
    print(f"Golden Evaluation Set: {len(GOLDEN_EVAL)} tasks")
    for i, (goal, url) in enumerate(GOLDEN_EVAL, 1):
        print(f"  {i:>2}. [{url:<30}] {goal}")
