"""Anti-bot tier info for all registered sites."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browsermind_core.registry.site_registry import SITE_REGISTRY

TIER_LABELS = ["none", "basic_js", "bot_mgmt", "cf_waf", "captcha"]

print()
print(f"  {'Site Key':<22} {'Category':<24} Tier")
print("  " + "-" * 60)
for key, e in sorted(SITE_REGISTRY.items()):
    tier = getattr(e, "anti_bot_tier", 0)
    label = TIER_LABELS[tier] if tier < len(TIER_LABELS) else str(tier)
    marker = " !!!" if tier >= 3 else (" !!" if tier >= 2 else "")
    print(f"  {key:<22} {e.category:<24} {tier} ({label}){marker}")
print()
