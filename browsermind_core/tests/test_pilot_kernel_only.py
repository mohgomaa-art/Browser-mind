"""P1 pilot kernel path (no Playwright)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pilot_kernel_only_meets_mutation_threshold(tmp_path):
    store = str(tmp_path / "bm")
    script = ROOT / "scripts" / "run_workflow_pilot.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--kernel-only", "--store", store],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert ">=20" in proc.stdout or "Mutations:" in proc.stdout

    from browsermind_core.console.session import KernelSession

    s = KernelSession(store)
    assert s.ledger_repo.count() >= 20
    assert s.outcome_repo.count() >= 1
    assert s.outcome_repo.tail(1)[0].success is True
