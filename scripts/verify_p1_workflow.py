#!/usr/bin/env python3
"""Verify P1 full workflow chain after pilot (fresh KernelSession = restart)."""
from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from browsermind_core.console.session import DEFAULT_STORE, KernelSession


def main() -> int:
    store = DEFAULT_STORE
    s = KernelSession(store)
    errors = []

    n_ledger = s.ledger_repo.count()
    n_outcome = s.outcome_repo.count()
    if n_ledger < 20:
        errors.append(f"ledger count {n_ledger} < 20")
    if n_outcome < 1:
        errors.append(f"outcome count {n_outcome} < 1")

    outcomes = s.outcome_repo.tail(5)
    last_ok = any(o.success and o.outcome_type == "login_succeeded" for o in outcomes)
    if not last_ok:
        errors.append("no recent login_succeeded outcome")

    tpls = s.workflow_store.list_templates()
    insts = s.workflow_store.list_instances()
    if not tpls:
        errors.append("no workflow templates in store")
    if not insts:
        errors.append("no workflow instances in store")

    exec_idx = s._load_index("execution")
    if not exec_idx:
        errors.append("no executions in index")

  # Rehydrate latest execution
    best_exc = None
    best_eid = None
    best_ledger_n = 0
    for _key, entry in exec_idx.items():
        eid = UUID(entry["id"])
        exc = s.execution_engine.rehydrate_execution(eid)
        if not exc:
            continue
        n_ent = len(s.ledger_repo.get_by_entity(eid))
        if exc.status == "succeeded" and n_ent >= best_ledger_n:
            best_exc = exc
            best_eid = eid
            best_ledger_n = n_ent

    if not best_exc:
        errors.append("no succeeded execution found in store")
    else:
        eid = best_eid
        exc = best_exc
        if exc.context and exc.context.template_id is None:
            errors.append("execution context missing template_id")
        if best_ledger_n < 3:
            errors.append(f"only {best_ledger_n} ledger entries for best execution")

    print("=== P1 Workflow Verification ===")
    print(f"  store:      {store}")
    print(f"  ledger:     {n_ledger}")
    print(f"  outcomes:   {n_outcome}")
    print(f"  templates:  {len(tpls)}")
    print(f"  instances:  {len(insts)}")
    print(f"  executions: {len(exec_idx)}")
    if best_exc and best_eid:
        print(f"  best exec:   {str(best_eid)[:8]}... status={best_exc.status} ledger={best_ledger_n}")

    if errors:
        print("\n[FAIL]")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n[OK] Full P1 workflow chain verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
