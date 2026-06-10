"""Investigation A -- single-template cross-dyad replay.

Runs `exp_saucedemo_checkout` (template id bba7836a, 17 steps,
binding seq=3 / type=vault / key='password') against three runtime
contexts:

  C1 -- original failing context: persona name='replay_agent'.
       Vault has NO entry under that name. Expected: RESOURCE_MISSING
       on key='password' (reproduce Stage 3).
  C2 -- known-populated vault: persona name='pilot'.
       persona_vault['pilot'].secrets.saucedemo.password exists.
       Outcome determines whether the failure is template-only (fails
       here too) or template-plus-context (succeeds here).
  C3 -- independent populated vault: persona name='validator'.
       persona_vault['validator'].secrets.saucedemo.password exists.
       Independent confirmation of C2 -- rules out single-context
       quirks.

Three observations. Each writes a workflow_instance OutcomeRecord.
With the per-binding-key telemetry added to the runtime, the
`metrics.failed_binding_key` field will be populated on any
RESOURCE_MISSING result.

This script does not propose fixes. It does not modify templates.
It does not modify the resolver. It does not modify vaults
(vault state is read as-is from each persona).

The output is purely observational. Interpretation lives in
INVESTIGATION_A_RESULTS.md.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path("reports/investigation_a")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATE = "exp_saucedemo_checkout"  # Will pick the 17-step bba7836a variant -- CLI resolves by name
ENV = "saucedemo"

# The three contexts. Each is a (persona_name, justification) pair.
# Vault state for each was inventoried before the experiment was
# designed; it is NOT mutated by this script.
CONTEXTS = [
    ("replay_agent", "C1: original Stage 3 context (vault: no entry under this name)"),
    ("pilot",        "C2: known-populated vault (saucedemo.password present, 12 chars)"),
    ("Job",          "C3: independent populated vault (saucedemo.password present, 105 chars)"),
]


def run_one(persona: str, context_id: str, justification: str) -> dict:
    """Execute one replay and capture observable outcome.

    The runtime now forwards report.missing_resource into
    metrics.failed_binding_key on the workflow_instance OutcomeRecord
    (Investigation A telemetry). The CLI's stdout still shows the
    surface-level result; the deeper evidence lives in the new
    ledger record.
    """
    cmd = [sys.executable, "bm.py", "replay", "start", TEMPLATE,
           "--env", ENV, "--persona", persona, "--headless", "--skip-failures"]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        dt = time.time() - t0
        result = {
            "context_id": context_id,
            "persona": persona,
            "justification": justification,
            "started_at": datetime.utcfromtimestamp(t0).isoformat() + "Z",
            "duration_s": round(dt, 2),
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "").splitlines()[-30:],
            "stderr_tail": (proc.stderr or "").splitlines()[-10:],
        }
    except subprocess.TimeoutExpired:
        result = {
            "context_id": context_id, "persona": persona,
            "justification": justification,
            "started_at": datetime.utcfromtimestamp(t0).isoformat() + "Z",
            "duration_s": round(time.time() - t0, 2),
            "exit_code": -1,
            "stdout_tail": ["<TIMEOUT after 120s>"], "stderr_tail": [],
        }
    return result


def fetch_latest_workflow_instance_record(persona_substring: str) -> dict | None:
    """Read the most-recent OutcomeRecord for a given persona (matched
    by ID prefix) on this template. Returns the inner _data dict
    with the failed_binding_key telemetry if present."""
    ledger = Path.home() / ".browsermind" / "outcome_ledger"
    candidates = []
    for p in ledger.glob("*.json"):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            d = blob.get("_data", blob)
            if d.get("scope") != "workflow_instance":
                continue
            if d.get("outcome_type") != "replay_run":
                continue
            if str(d.get("persona_id", "")).startswith(persona_substring):
                if d.get("metrics", {}).get("template_name") == TEMPLATE:
                    candidates.append(d)
        except Exception:
            continue
    candidates.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return candidates[0] if candidates else None


def persona_id_for(persona_name: str) -> str:
    """Resolve persona name -> id prefix by reading persona index."""
    pdir = Path.home() / ".browsermind" / "persona"
    for p in pdir.glob("*.json"):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            d = blob.get("_data", blob)
            if d.get("name") == persona_name:
                return str(d.get("id", ""))[:8]
        except Exception:
            continue
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    started_at = datetime.utcnow().isoformat() + "Z"
    print("=" * 70)
    print(f"INVESTIGATION A  (started {started_at})")
    print(f"Template: {TEMPLATE}  Env: {ENV}")
    print("=" * 70)
    for cid, (persona, just) in zip(("C1", "C2", "C3"), CONTEXTS):
        print(f"  {cid}: persona={persona!r}  -- {just}")
    print("=" * 70)

    if args.dry_run:
        print("[dry-run]")
        return 0

    runs = []
    for cid, (persona, just) in zip(("C1", "C2", "C3"), CONTEXTS):
        print(f"\n[{cid}] Running against persona={persona!r}...")
        result = run_one(persona, cid, just)
        # Pull the freshest matching ledger record
        pid_prefix = persona_id_for(persona)
        ledger_record = fetch_latest_workflow_instance_record(pid_prefix) if pid_prefix else None
        result["persona_id_prefix"] = pid_prefix
        result["ledger_record_metrics"] = (ledger_record or {}).get("metrics")
        result["ledger_record_evidence"] = (ledger_record or {}).get("evidence")
        runs.append(result)

        # Console summary
        status_line = next(
            (l for l in result["stdout_tail"] if "Resolution Rate" in l or "[ERR]" in l or "Replay Failed" in l),
            f"exit={result['exit_code']}"
        )
        print(f"  -> {status_line.strip()[:80]}")
        if result.get("ledger_record_metrics"):
            m = result["ledger_record_metrics"]
            print(f"  -> ledger: status={m.get('status')!r}  "
                  f"resolved={m.get('resolved_steps')}/{m.get('total_steps')}  "
                  f"failed_binding_key={m.get('failed_binding_key')!r}")

    finished_at = datetime.utcnow().isoformat() + "Z"
    out_path = REPORT_DIR / f"runs_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(
        json.dumps({
            "started_at": started_at,
            "finished_at": finished_at,
            "template": TEMPLATE,
            "env": ENV,
            "runs": runs,
        }, indent=2, default=str),
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print(f"INVESTIGATION A COMPLETE  ({finished_at})")
    print(f"Raw runs: {out_path}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
