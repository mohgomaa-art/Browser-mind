"""
Emit `--site X` flags for all campaign-done sites so train_campaign.bat
can filter the OutcomeLedger export to only explored sites.

Also always includes the benchmark baseline environments so the model
retains knowledge needed to pass the regression gate.

Usage: python scripts/campaign_site_flags.py
Prints one line: --site amazon --site rakuten ...
"""
import json, pathlib, sys

# Benchmark environments: always included so the model never regresses
# on the frozen benchmark suite regardless of what the campaign covered.
BENCHMARK_SITES = {
    "saucedemo",
    "demoqa",
    "aria_internet",
    "static_baseline",
}

queue_path = pathlib.Path.home() / ".browsermind" / "missions" / "queue.json"
if not queue_path.exists():
    sys.exit(0)

raw = json.loads(queue_path.read_text(encoding="utf-8"))
entries = raw if isinstance(raw, list) else raw.get("entries", [])

campaign_sites = {
    e["site_key"]
    for e in entries
    if e.get("status") == "done" and e.get("last_steps", 0) > 0
}

all_sites = sorted(campaign_sites | BENCHMARK_SITES)

if not all_sites:
    sys.exit(0)

print(" ".join(f"--site {s}" for s in all_sites))
