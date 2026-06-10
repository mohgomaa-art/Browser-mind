"""Discovery validation: measure PrimitiveNormalizer fallback rate."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browsermind_core.representation.primitive_normalizer import measure_fallback_rate

SAMPLES = [
    ("click",  "button",  "Sign in"),
    ("fill",   "textbox", "email"),
    ("click",  "button",  "Search"),
    ("click",  "button",  "Accept all cookies"),
    ("click",  "button",  "Add to cart"),
    ("click",  "button",  "Load more"),
    ("click",  "button",  "Upload file"),
    ("click",  "button",  "Follow"),
    ("click",  "button",  "Like"),
    ("hover",  "div",     "tooltip hint"),
    ("scroll", "main",    "page content"),
    ("click",  "button",  "Delete item"),
    ("click",  "button",  "Checkout"),
    ("click",  "button",  "Play video"),
    ("click",  "button",  "Star"),
]

r = measure_fallback_rate(SAMPLES)
print()
print(f"  Total samples  : {r['total']}")
print(f"  Known (vocab)  : {r['total'] - r['fallback_count']}")
print(f"  Fallback       : {r['fallback_count']}")
print(f"  Fallback rate  : {r['fallback_rate']*100:.1f}%")
print()
print("  Known intents seen:")
for intent in r["known_intents"]:
    print(f"    {intent}")
if r["fallback_examples"]:
    print()
    print("  Fallback examples:")
    for ex in r["fallback_examples"]:
        print(f"    {ex['action_type']} / {ex['target_role']} / {ex['target_name']}  ->  {ex['result']}")
print()
