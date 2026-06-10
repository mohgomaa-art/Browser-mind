"""Stage 3 -- Campaign execution.

Runs a reproducible replay campaign with corrected template names
(the original PHASE3_mass_replay.bat references templates that
don't exist in the current registry). Goal: produce structural
evidence, not benchmark scores.

Campaign composition:
  - saucedemo_login                   x 10   (e-commerce login smoke)
  - exp_saucedemo_checkout            x 10   (e-commerce flow)
  - exp_demoqa_form                   x 10   (forms harness)
  - greenhousev2 (synthetic verify)   x 5    (Field Ontology rescue test)
  - greenhousev2 (live attempt)       x 1    (best-effort real-world)

Total: 36 replays. Estimated runtime: 8-15 minutes (mostly
saucedemo, which is fast; greenhouse live is the only slow leg).

Each run uses --skip-failures so partial completions still produce
ledger records, which is exactly what Stage 3 wants for structural
signal. Cascade annotation is now active in replay_engine, so new
records will carry the Stage 2.1 telemetry.

The campaign DOES NOT modify itself mid-run. If a run crashes,
the loop logs it and continues. If the entire process is killed,
the records already written remain intact. Reproducibility is the
goal.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path("reports/stage3_campaign")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Plan -- explicit, declarative, reproducible.
CAMPAIGN_PLAN = [
    {"template": "saucedemo_login",       "env": "saucedemo",   "runs": 10, "headless": True,  "skip_failures": True},
    {"template": "exp_saucedemo_checkout", "env": "saucedemo",   "runs": 10, "headless": True,  "skip_failures": True},
    {"template": "exp_demoqa_form",        "env": "demoqa",      "runs": 10, "headless": True,  "skip_failures": True},
    # Synthetic Field Ontology test -- uses the same verification script
    # built in Stage 1 (proven to produce field_registry_rescue wins).
    {"synthetic_rescue": True, "runs": 5},
    # Best-effort live greenhouse replay. Likely to fail (anti-bot,
    # expired posting, etc.) but produces real-world evidence either way.
    {"template": "greenhousev2",           "env": "greenhouse",  "runs": 1,  "headless": True,  "skip_failures": True},
]


def run_replay(template: str, env: str, headless: bool, skip_failures: bool,
               persona: str = "replay_agent") -> dict:
    """Execute one `bm replay start` and capture timing + exit code.

    Never raises. Always returns a dict. Records that capture stdout/
    stderr tails for the campaign report. Caller decides what to do
    with failures (in our case: log and continue).
    """
    cmd = [sys.executable, "bm.py", "replay", "start", template,
           "--env", env, "--persona", persona]
    if headless:
        cmd.append("--headless")
    if skip_failures:
        cmd.append("--skip-failures")
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180
        )
        dt = time.time() - t0
        return {
            "type": "replay",
            "template": template, "env": env, "exit_code": proc.returncode,
            "duration_s": round(dt, 2),
            "stdout_tail": (proc.stdout or "").splitlines()[-15:],
            "stderr_tail": (proc.stderr or "").splitlines()[-5:],
        }
    except subprocess.TimeoutExpired:
        return {
            "type": "replay", "template": template, "env": env,
            "exit_code": -1, "duration_s": round(time.time() - t0, 2),
            "stdout_tail": ["<TIMEOUT after 180s>"], "stderr_tail": [],
        }
    except Exception as e:
        return {
            "type": "replay", "template": template, "env": env,
            "exit_code": -2, "duration_s": round(time.time() - t0, 2),
            "stdout_tail": [f"<EXCEPTION: {type(e).__name__}: {e}>"],
            "stderr_tail": [],
        }


def run_synthetic_rescue() -> dict:
    """Run the Stage 1 live verification -- synthetic Field Ontology test.

    This doesn't write to the OutcomeLedger (it instantiates TargetResolver
    directly, not the full replay engine), but it produces a deterministic
    PASS/FAIL on whether field_registry_rescue still works. Run multiple
    times to detect flakiness.
    """
    cmd = [sys.executable, "scripts/stage1_live_verification.py"]
    env = {"PYTHONPATH": "."}
    import os
    env_full = {**os.environ, **env}
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, env=env_full
        )
        return {
            "type": "synthetic_rescue",
            "exit_code": proc.returncode,
            "duration_s": round(time.time() - t0, 2),
            "passed": proc.returncode == 0,
            "stdout_tail": (proc.stdout or "").splitlines()[-10:],
        }
    except Exception as e:
        return {
            "type": "synthetic_rescue", "exit_code": -2,
            "duration_s": round(time.time() - t0, 2), "passed": False,
            "stdout_tail": [f"<EXCEPTION: {type(e).__name__}: {e}>"],
        }


def ensure_replay_persona():
    """Create the replay_agent persona if it doesn't exist. Idempotent.

    The persona CLI takes positional NAME + required --principal. We bind
    to an existing principal ('pilot') because Stage 3 uses an existing
    operational identity for replays -- not a fresh one.
    """
    subprocess.run(
        [sys.executable, "bm.py", "persona", "create", "replay_agent",
         "--principal", "pilot"],
        capture_output=True, text=True, timeout=30,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 3 campaign runner")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the plan without executing.")
    args = ap.parse_args()

    started_at = datetime.utcnow().isoformat() + "Z"
    print("=" * 70)
    print(f"STAGE 3 CAMPAIGN  (started {started_at})")
    print("=" * 70)
    for i, leg in enumerate(CAMPAIGN_PLAN, 1):
        if leg.get("synthetic_rescue"):
            print(f"  Leg {i}: synthetic rescue probe x {leg['runs']}")
        else:
            print(f"  Leg {i}: {leg['template']:<32} env={leg['env']:<10} x {leg['runs']}")
    print("=" * 70)

    if args.dry_run:
        print("[dry-run] not executing")
        return 0

    ensure_replay_persona()

    all_runs = []
    leg_idx = 0
    for leg in CAMPAIGN_PLAN:
        leg_idx += 1
        if leg.get("synthetic_rescue"):
            print(f"\n[Leg {leg_idx}] Synthetic Field Ontology rescue x {leg['runs']}")
            for i in range(leg["runs"]):
                print(f"  run {i+1}/{leg['runs']}", flush=True)
                result = run_synthetic_rescue()
                result["leg"] = leg_idx
                result["run_index"] = i + 1
                all_runs.append(result)
                print(f"    -> {'PASS' if result['passed'] else 'FAIL'} "
                      f"({result['duration_s']}s)")
        else:
            print(f"\n[Leg {leg_idx}] {leg['template']} x {leg['runs']}")
            for i in range(leg["runs"]):
                print(f"  run {i+1}/{leg['runs']}", flush=True)
                result = run_replay(
                    leg["template"], leg["env"],
                    leg["headless"], leg["skip_failures"],
                )
                result["leg"] = leg_idx
                result["run_index"] = i + 1
                all_runs.append(result)
                # Print just the resolver summary line, not full stdout
                summary = next(
                    (l for l in result.get("stdout_tail", [])
                     if "status=" in l or "Resolver" in l or "FAIL" in l or "PASS" in l),
                    f"exit={result['exit_code']} dur={result['duration_s']}s"
                )
                print(f"    -> {summary[:80]}")

    finished_at = datetime.utcnow().isoformat() + "Z"
    out_path = REPORT_DIR / f"campaign_runs_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(
        json.dumps({
            "started_at": started_at,
            "finished_at": finished_at,
            "plan": CAMPAIGN_PLAN,
            "runs": all_runs,
        }, indent=2, default=str),
        encoding="utf-8",
    )

    # Quick summary
    print("\n" + "=" * 70)
    print(f"CAMPAIGN COMPLETE  ({finished_at})")
    print("=" * 70)
    replays = [r for r in all_runs if r["type"] == "replay"]
    rescues = [r for r in all_runs if r["type"] == "synthetic_rescue"]
    print(f"  Replay runs:           {len(replays)}")
    print(f"  Replay successes:      {sum(1 for r in replays if r['exit_code'] == 0)}")
    print(f"  Replay failures:       {sum(1 for r in replays if r['exit_code'] != 0)}")
    print(f"  Synthetic rescue runs: {len(rescues)}")
    print(f"  Synthetic rescue pass: {sum(1 for r in rescues if r['passed'])}")
    print(f"  Raw run log:           {out_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
