"""Experiment C -- template-scan generalization probe.

Discriminates H3e (template-specific recording artifact) from
H3a/H3b/H3c/H3d (runtime-context-dependence is broad).

Design: 6 stratified templates x 2 personas = 12 replays.

The two personas reproduce Investigation A's discriminating
contrast:
  Pass 1: persona='replay_agent'  -- vault has no row under this name.
                                    Predicted: vault-typed bindings
                                    fail with RESOURCE_MISSING.
  Pass 2: persona='pilot'         -- vault has populated saucedemo
                                    entries. Predicted: vault-typed
                                    bindings resolve (subject to
                                    template-side state).

The 6 templates span:
  T1 -- exp_saucedemo_checkout (bba7836a, 17 steps, 1 vault binding)
        the known-failing case from Stage 3 / Investigation A
  T2 -- exp_saucedemo_checkout_t1 (a10e2489, 17 steps, 1 vault binding)
        sibling variant -- same family, different ID
  T3 -- exp_demoqa_form (b51a4631, 6 steps, 0 vault bindings)
        CONTROL: no vault binding -> should not exhibit
        RESOURCE_MISSING under either pass
  T4 -- exp_aria_login (b4c2d440, 6 steps, 1 vault binding)
        different environment (aria_internet) -- tests cross-env
        generalization
  T5 -- exp_aria_login_t1 (23641698, 6 steps, 1 vault binding)
        sibling of T4 -- same env, different ID
  T6 -- hf_login_b (198382b4, 11 steps, 1 vault binding)
        third environment (huggingface) -- broadens the cross-env
        sample

Telemetry captured per run:
  - exit code
  - duration
  - failed_binding_key (from the workflow_instance OutcomeRecord
    written by replay_engine.py -- Investigation A telemetry)
  - resolved_steps / total_steps
  - evidence string

No code beyond this probe. No template modifications. No vault
modifications. No persona modifications.

Per directive: experiment-only, no architecture, no fixes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path("reports/experiment_c")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES = [
    {"slot": "T1", "name": "exp_saucedemo_checkout",    "env": "saucedemo",     "expected_vault_keys": ["password"], "note": "known-failing (Stage 3/IA)"},
    {"slot": "T2", "name": "exp_saucedemo_checkout_t1", "env": "saucedemo",     "expected_vault_keys": ["password"], "note": "sibling variant, same family"},
    {"slot": "T3", "name": "exp_demoqa_form",           "env": "demoqa",        "expected_vault_keys": [],           "note": "CONTROL -- no vault binding"},
    {"slot": "T4", "name": "exp_aria_login",            "env": "aria_internet", "expected_vault_keys": ["password"], "note": "different env"},
    {"slot": "T5", "name": "exp_aria_login_t1",         "env": "aria_internet", "expected_vault_keys": ["password"], "note": "sibling of T4"},
    {"slot": "T6", "name": "hf_login_b",                "env": "huggingface",   "expected_vault_keys": ["password"], "note": "third env"},
]

PERSONAS = [
    {"label": "P1", "name": "replay_agent", "note": "vault: NO row under this name"},
    {"label": "P2", "name": "pilot",        "note": "vault: populated saucedemo password (12 chars)"},
]


def fetch_latest_record_for(template_name: str, persona_name: str) -> dict | None:
    """Read most-recent workflow_instance OutcomeRecord matching template+persona."""
    ledger = Path.home() / ".browsermind" / "outcome_ledger"
    if not ledger.exists():
        return None
    # Need persona ID -> look up by name
    pdir = Path.home() / ".browsermind" / "persona"
    pid_prefix = ""
    for p in pdir.glob("*.json"):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            d = blob.get("_data", blob)
            if d.get("name") == persona_name:
                pid_prefix = str(d.get("id", ""))[:8]
                break
        except Exception:
            continue

    candidates = []
    for p in ledger.glob("*.json"):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            d = blob.get("_data", blob)
        except Exception:
            continue
        if d.get("scope") != "workflow_instance":
            continue
        if d.get("outcome_type") != "replay_run":
            continue
        if d.get("metrics", {}).get("template_name") != template_name:
            continue
        # Persona match by ID prefix (if available)
        if pid_prefix and not str(d.get("persona_id", "")).startswith(pid_prefix):
            continue
        candidates.append(d)
    candidates.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return candidates[0] if candidates else None


def run_one(template: str, env: str, persona: str) -> dict:
    cmd = [sys.executable, "bm.py", "replay", "start", template,
           "--env", env, "--persona", persona, "--headless", "--skip-failures"]
    t0 = time.time()
    started_at = datetime.utcnow().isoformat() + "Z"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        dt = time.time() - t0
        return {
            "started_at": started_at,
            "template": template,
            "env": env,
            "persona": persona,
            "duration_s": round(dt, 2),
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "").splitlines()[-15:],
            "stderr_tail": (proc.stderr or "").splitlines()[-5:],
        }
    except subprocess.TimeoutExpired:
        return {
            "started_at": started_at, "template": template, "env": env, "persona": persona,
            "duration_s": round(time.time() - t0, 2),
            "exit_code": -1,
            "stdout_tail": ["<TIMEOUT after 180s>"], "stderr_tail": [],
        }
    except Exception as e:
        return {
            "started_at": started_at, "template": template, "env": env, "persona": persona,
            "duration_s": round(time.time() - t0, 2),
            "exit_code": -2,
            "stdout_tail": [f"<EXCEPTION: {type(e).__name__}: {e}>"], "stderr_tail": [],
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    started = datetime.utcnow().isoformat() + "Z"
    print("=" * 70)
    print(f"EXPERIMENT C -- Template-scan generalization probe ({started})")
    print("=" * 70)
    print(f"  Templates ({len(TEMPLATES)}):")
    for t in TEMPLATES:
        keys = t["expected_vault_keys"] or "[]"
        print(f"    {t['slot']} {t['name']:<32} env={t['env']:<14} vault={keys}  -- {t['note']}")
    print(f"\n  Personas ({len(PERSONAS)}):")
    for p in PERSONAS:
        print(f"    {p['label']} {p['name']:<14} -- {p['note']}")
    print(f"\n  Total runs: {len(TEMPLATES) * len(PERSONAS)}")
    print("=" * 70)

    if args.dry_run:
        print("[dry-run]")
        return 0

    runs = []
    cell_count = 0
    for tpl in TEMPLATES:
        for persona in PERSONAS:
            cell_count += 1
            cell_id = f"{tpl['slot']}-{persona['label']}"
            print(f"\n[{cell_id}] {tpl['name']} x {persona['name']}  ({cell_count}/{len(TEMPLATES)*len(PERSONAS)})", flush=True)
            result = run_one(tpl["name"], tpl["env"], persona["name"])
            # Pull the fresh ledger record
            ledger = fetch_latest_record_for(tpl["name"], persona["name"])
            metrics = (ledger or {}).get("metrics") or {}
            result.update({
                "cell_id": cell_id,
                "template_slot": tpl["slot"],
                "persona_label": persona["label"],
                "expected_vault_keys": tpl["expected_vault_keys"],
                "ledger_status": metrics.get("status"),
                "ledger_resolved_steps": metrics.get("resolved_steps"),
                "ledger_total_steps": metrics.get("total_steps"),
                "ledger_failed_binding_key": metrics.get("failed_binding_key"),
                "ledger_evidence": (ledger or {}).get("evidence"),
                "ledger_cascade_workflow_class": metrics.get("cascade_workflow_class"),
            })
            runs.append(result)

            # Console-friendly status
            status_line = (
                f"exit={result['exit_code']:>3}  "
                f"dur={result['duration_s']:>5.1f}s  "
                f"status={result['ledger_status']!r:<13}  "
                f"resolved={result['ledger_resolved_steps']}/{result['ledger_total_steps']}  "
                f"failed_binding={result['ledger_failed_binding_key']!r}"
            )
            print(f"  -> {status_line}")

    finished = datetime.utcnow().isoformat() + "Z"
    out = REPORT_DIR / f"runs_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
    out.write_text(json.dumps({
        "started_at": started,
        "finished_at": finished,
        "templates": TEMPLATES,
        "personas": PERSONAS,
        "runs": runs,
    }, indent=2, default=str), encoding="utf-8")

    # Brief matrix summary
    print("\n" + "=" * 70)
    print(f"COMPLETE  ({finished})")
    print("=" * 70)
    print(f"\n{'':<5} {' '.join(p['label'] + '(' + p['name'][:10] + ')' for p in PERSONAS)}")
    for tpl in TEMPLATES:
        row = [tpl["slot"]]
        for persona in PERSONAS:
            cell = next((r for r in runs if r["template_slot"] == tpl["slot"] and r["persona_label"] == persona["label"]), None)
            if cell is None:
                row.append("?")
                continue
            status = cell.get("ledger_status") or f"exit{cell['exit_code']}"
            fbk = cell.get("ledger_failed_binding_key")
            cell_str = f"{status[:8]}"
            if fbk:
                cell_str += f"/{fbk[:8]}"
            row.append(cell_str.ljust(15))
        print("  " + " ".join(row) + f"  ({tpl['name']})")
    print(f"\nRaw runs: {out}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
