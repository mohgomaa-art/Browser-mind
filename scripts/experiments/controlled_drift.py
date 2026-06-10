#!/usr/bin/env python3
"""
Experiment 2: Controlled Drift Matrix (BrowserMind Survivability Curve)

Applies a severity-ordered matrix of UI drifts and measures the
BrowserMind resolution rate at each severity level.

Severity levels (ascending difficulty):
  0  None (Baseline)
  1  Single Label Change
  2  Single Placeholder Change
  3  DOM Nesting (structural wrapper)
  4  Label + DOM (compound)
  5  Semantic Rename (synonym replacement)
  6  Semantic Replacement (different concept entirely)

The output drift_matrix.json is structured as a Survivability Curve:
read it in order of severity to see where BrowserMind's resolution degrades.
"""
import argparse
import subprocess
import threading
import time
import os
import json
import http.server
import socketserver
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# HTML variants — ordered by semantic drift severity
# ---------------------------------------------------------------------------

HTML_BASELINE = """<!DOCTYPE html>
<html>
<head><title>Mock Login</title></head>
<body>
    <div class="login-container" id="login-box-123">
        <h2>Sign In</h2>
        <form action="/submit" method="post">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" placeholder="Enter username">

            <label for="password">Password</label>
            <input type="password" id="password" name="password" placeholder="Enter password">

            <button type="submit" id="submit-btn" class="btn-primary">Login</button>
        </form>
    </div>
</body>
</html>
"""

DRIFT_MATRIX = [
    {
        "drift_type": "none",
        "drift_category": "baseline",
        "severity_level": 0,
        "description": "No changes — identical to baseline",
        "html": HTML_BASELINE,
    },
    {
        "drift_type": "single_label_change",
        "drift_category": "label_change",
        "severity_level": 1,
        "description": "Label text changed, IDs and structure intact",
        "html": """<!DOCTYPE html>
<html><body><form action="/submit" method="post">
    <label for="username">Email Address</label>
    <input type="text" id="username" name="username" placeholder="Enter username">
    <label for="password">Password</label>
    <input type="password" id="password" name="password" placeholder="Enter password">
    <button type="submit" id="submit-btn">Login</button>
</form></body></html>""",
    },
    {
        "drift_type": "single_placeholder_change",
        "drift_category": "placeholder_change",
        "severity_level": 2,
        "description": "Placeholder text changed, labels and IDs intact",
        "html": """<!DOCTYPE html>
<html><body><form action="/submit" method="post">
    <label for="username">Username</label>
    <input type="text" id="username" name="username" placeholder="Email address">
    <label for="password">Password</label>
    <input type="password" id="password" name="password" placeholder="Passcode">
    <button type="submit" id="submit-btn">Login</button>
</form></body></html>""",
    },
    {
        "drift_type": "single_dom_nesting",
        "drift_category": "dom_structural",
        "severity_level": 3,
        "description": "Extra wrapper divs inserted, labels and IDs intact",
        "html": """<!DOCTYPE html>
<html><body><form action="/submit" method="post">
    <div class="field-wrap">
        <label for="username">Username</label>
        <span><input type="text" id="username" name="username" placeholder="Enter username"></span>
    </div>
    <div class="field-wrap">
        <label for="password">Password</label>
        <span><input type="password" id="password" name="password" placeholder="Enter password"></span>
    </div>
    <button type="submit" id="submit-btn">Login</button>
</form></body></html>""",
    },
    {
        "drift_type": "compound_label_and_nesting",
        "drift_category": "compound",
        "severity_level": 4,
        "description": "Label text changed + DOM nesting added simultaneously",
        "html": """<!DOCTYPE html>
<html><body><form action="/submit" method="post">
    <div class="outer">
        <label for="user_email">Email Address</label>
        <input type="text" id="user_email" name="user_email" placeholder="Enter username">
        <span>
            <label for="pwd">Passcode</label>
            <input type="password" id="pwd" name="pwd" placeholder="Enter passcode">
        </span>
        <button type="submit" id="submit-btn-new">Sign In</button>
    </div>
</form></body></html>""",
    },
    {
        "drift_type": "semantic_rename",
        "drift_category": "semantic_rename",
        "severity_level": 5,
        "description": "Synonym replacement: 'Password'→'Secret', 'Login'→'Enter', placeholder changed",
        "html": """<!DOCTYPE html>
<html><body><form action="/submit" method="post">
    <label for="user_id">User ID</label>
    <input type="text" id="user_id" name="user_id" placeholder="Your user ID">
    <label for="secret">Secret</label>
    <input type="password" id="secret" name="secret" placeholder="Your secret">
    <button type="submit" id="enter-btn">Enter</button>
</form></body></html>""",
    },
    {
        "drift_type": "semantic_replacement",
        "drift_category": "semantic_replacement",
        "severity_level": 6,
        "description": "Complete semantic replacement — all signals different concept (search form instead of login)",
        "html": """<!DOCTYPE html>
<html><body>
    <div class="search-wrapper">
        <h2>Find Resources</h2>
        <form action="/search" method="get">
            <label for="query">Search Query</label>
            <input type="search" id="query" name="query" placeholder="What are you looking for?">
            <label for="category">Category</label>
            <select id="category" name="category">
                <option value="all">All</option>
            </select>
            <button type="submit" id="search-btn">Search</button>
        </form>
    </div>
</body></html>""",
    },
]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def start_server(port, directory):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        def log_message(self, format, *args):
            pass

    httpd = socketserver.TCPServer(("", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.daemon = True
    thread.start()
    return httpd


def get_latest_report(site_key: str) -> dict:
    reports_dir = ROOT_DIR / "reports" / "replay_experiments"
    if not reports_dir.exists():
        return {}
    dirs = [d for d in reports_dir.iterdir() if d.is_dir()]
    if not dirs:
        return {}
    latest_dir = sorted(dirs, key=lambda d: d.name)[-1]
    for file in latest_dir.glob(f"{site_key}_*.json"):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Controlled Drift Matrix — Survivability Curve")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    workdir = ROOT_DIR / "scratch" / "controlled_drift"
    workdir.mkdir(parents=True, exist_ok=True)
    index_file = workdir / "index.html"

    out_dir = ROOT_DIR / "reports" / "survivability" / "drift"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "drift_matrix.json"

    print(f"Starting mock server on port {args.port}...")
    httpd = start_server(args.port, workdir)
    time.sleep(1)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # 1. Record Baseline Once
    print("\n--- Recording Baseline ---")
    index_file.write_text(HTML_BASELINE, encoding="utf-8")
    subprocess.run(["python", "scripts/auto_record.py", "run", "--site", "controlled_drift"],
                   env=env, cwd=ROOT_DIR)

    results = []

    # 2. Iterate Severity Levels
    for drift in DRIFT_MATRIX:
        severity = drift["severity_level"]
        drift_type = drift["drift_type"]
        print(f"\n--- Severity {severity}: {drift_type} ---")
        print(f"    {drift['description']}")

        index_file.write_text(drift["html"], encoding="utf-8")
        subprocess.run(["python", "scripts/run_replay_experiments.py", "replay", "--site", "controlled_drift"],
                       env=env, cwd=ROOT_DIR)

        report = get_latest_report("controlled_drift")

        resolution_rate = report.get("resolution_rate", 0.0) if report else 0.0
        replay_success  = report.get("replay_success", False) if report else False

        # Extract state_inference
        state_inference = (report.get("state_inference") or {}) if report else {}
        state_match = state_inference.get("match", False)

        # Extract Representation Ledger from per-step attribution
        representation_counts: dict = {}
        false_recovery_count = 0
        for step in (report.get("step_outcomes") or []):
            resolved_by = step.get("resolved_by")
            if resolved_by:
                representation_counts[resolved_by] = representation_counts.get(resolved_by, 0) + 1
            # False recovery = recovered but goal not achieved
            if step.get("recovered_by") and not state_match:
                false_recovery_count += 1

        results.append({
            "severity_level": severity,
            "drift_type": drift_type,
            "drift_category": drift["drift_category"],
            "description": drift["description"],
            "resolution_rate": resolution_rate,
            "state_match": state_match,
            "workflow_success": replay_success and state_match,
            "representation_breakdown": representation_counts,
            "false_recovery_count": false_recovery_count,
        })

        status = "SURVIVED" if replay_success and state_match else "FAILED"
        print(f"    → {status} | resolution={resolution_rate:.1%}")

    httpd.shutdown()

    # Sort by severity before writing
    results.sort(key=lambda x: x["severity_level"])

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*50}")
    print(f"Survivability Curve written → {out_file}")
    print(f"{'='*50}")
    print(f"{'Severity':<10} {'Drift Type':<30} {'Resolution':<12} {'Success'}")
    print("-" * 65)
    for r in results:
        print(f"{r['severity_level']:<10} {r['drift_type']:<30} {r['resolution_rate']:<12.1%} {r['workflow_success']}")


if __name__ == "__main__":
    main()
