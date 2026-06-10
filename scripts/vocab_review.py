"""BrowserMind Vocabulary Review — propose and confirm new vocab items.

Loads the FallbackLedger, runs VocabInductor, displays pending proposals,
and lets you review each one interactively.

Usage:
    python scripts/vocab_review.py              # interactive review
    python scripts/vocab_review.py --stats      # show ledger + proposal stats
    python scripts/vocab_review.py --induct     # run induction only, save proposals
    python scripts/vocab_review.py --threshold 0.4 --min-sites 2 --min-freq 5

Controls (interactive mode):
    c  — confirm proposal (adds pattern to vocab_extensions.json)
    r  — reject proposal
    s  — skip (decide later)
    q  — quit

No external dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browsermind_core.representation.fallback_ledger import FallbackLedger
from browsermind_core.representation.vocab_inductor import (
    VocabProposalStore,
    cluster_fallbacks,
    propose_vocab_expansions,
)
from browsermind_core.representation.primitive_normalizer import load_vocab_extensions


# ── Terminal helpers ───────────────────────────────────────────────────────────

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"

def _green(t):  return _c(t, "32")
def _red(t):    return _c(t, "31")
def _yellow(t): return _c(t, "33")
def _cyan(t):   return _c(t, "36")
def _bold(t):   return _c(t, "1")
def _dim(t):    return _c(t, "2")


def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def _key() -> str:
    if os.name == "nt":
        import msvcrt
        return msvcrt.getwch().lower()
    else:
        import tty, termios, sys
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setraw(fd)
        ch = sys.stdin.read(1).lower()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch


# ── Stats display ──────────────────────────────────────────────────────────────

def show_stats(ledger: FallbackLedger, store: VocabProposalStore) -> None:
    print()
    print(_bold("═" * 60))
    print(_bold("  BrowserMind Vocabulary Review — Stats"))
    print(_bold("═" * 60))

    s = ledger.stats()
    print(f"\n  {_bold('FallbackLedger')}")
    print(f"    Unique fragments    : {s['unique_fragments']}")
    print(f"    Total observations  : {s['total_observations']}")
    print(f"    Multi-site fragments: {s['multi_site_fragments']}")
    if s.get("top_fragments"):
        print(f"\n    Top fragments:")
        for f in s["top_fragments"]:
            print(f"      {f['freq']:3}x  ({f['sites']} sites)  {f['fragment']}")

    ps = store.stats()
    print(f"\n  {_bold('VocabProposalStore')}")
    print(f"    Total proposals     : {ps['total']}")
    for status, cnt in ps.get("by_status", {}).items():
        colour = (_green if status in ("CONFIRMED", "INTEGRATED")
                  else _red if status == "REJECTED"
                  else _yellow)
        print(f"    {colour(status):<22}: {cnt}")

    # Runtime extensions loaded
    ext_path = Path.home() / ".browsermind" / "vocab_extensions.json"
    if ext_path.exists():
        try:
            exts = json.loads(ext_path.read_text())
            print(f"\n  {_bold('Runtime extensions')} (vocab_extensions.json)")
            print(f"    Loaded patterns     : {len(exts)}")
            for ex in exts[:5]:
                print(f"      {_cyan(ex.get('l0_name','?'))}  → {ex.get('l1_name','?')}")
                print(f"        patterns: {', '.join(ex.get('patterns',[])[:3])}")
        except Exception:
            pass

    print()


# ── Interactive review ─────────────────────────────────────────────────────────

def review_proposal(proposal, idx: int, total: int) -> str:
    _clear()
    print(_bold("═" * 64))
    print(_bold(f"  Vocabulary Review  [{idx}/{total}]"))
    print(_bold("═" * 64))
    print()

    status_c = _yellow("PROPOSED")
    print(f"  Status      : {status_c}")
    print(f"  Proposal ID : {_dim(proposal.proposal_id)}")
    print()

    print(f"  Proposed name : {_bold(_cyan(proposal.proposed_name))}")
    print(f"  L1 category   : {proposal.l1_category}")
    print(f"  Sites seen    : {len(proposal.cluster_sites)}  "
          f"({', '.join(proposal.cluster_sites[:5])})")
    print(f"  Total freq    : {proposal.total_frequency}")
    print()

    print(f"  {_bold('Cluster members')} ({len(proposal.cluster_members)}):")
    for m in proposal.cluster_members[:8]:
        print(f"    • {m}")
    if len(proposal.cluster_members) > 8:
        print(f"    ... and {len(proposal.cluster_members) - 8} more")
    print()

    if proposal.example_names:
        print(f"  {_bold('Example raw target names')}:")
        for ex in proposal.example_names[:6]:
            print(f"    \"{ex}\"")
    print()

    print(f"  {_bold('Name patterns')} (will be added to runtime normalizer):")
    for pat in proposal.name_patterns[:6]:
        print(f"    → if '{pat}' in target_name → {proposal.proposed_name}")
    print()

    print(_bold("─" * 64))
    print(f"  {_green('c')} confirm  |  {_red('r')} reject  |  {_yellow('s')} skip  |  q quit")
    print()

    key = _key()
    return key


def run_interactive(store: VocabProposalStore) -> None:
    pending = store.pending()
    if not pending:
        print(_yellow("  No pending proposals. Run with --induct first."))
        return

    confirmed_names = []
    rejected_count  = 0
    skipped_count   = 0

    for i, proposal in enumerate(pending, start=1):
        key = review_proposal(proposal, i, len(pending))

        if key == "c":
            store.confirm(proposal.proposal_id)
            confirmed_names.append(proposal.proposed_name)
            print(f"\n  {_green('✓')} Confirmed: {_bold(proposal.proposed_name)}")
        elif key == "r":
            reason = input("  Rejection reason (Enter to skip): ").strip()
            store.reject(proposal.proposal_id, reason)
            rejected_count += 1
            print(f"  {_red('✗')} Rejected.")
        elif key == "q":
            print(f"\n  Exiting review. Reviewed {i - 1}/{len(pending)} proposals.")
            break
        else:
            skipped_count += 1
            print(f"  {_yellow('→')} Skipped.")

    print()
    print(_bold("═" * 50))
    print(f"  Confirmed : {len(confirmed_names)}")
    if confirmed_names:
        for name in confirmed_names:
            print(f"    + {_green(name)}")
    print(f"  Rejected  : {rejected_count}")
    print(f"  Skipped   : {skipped_count}")
    print()
    if confirmed_names:
        ext_path = store._ep
        print(f"  Extensions written to: {ext_path}")
        print(f"  Run load_vocab_extensions() to activate in this process.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="BrowserMind Vocabulary Review — cluster fallbacks and propose vocab"
    )
    parser.add_argument("--stats",     action="store_true", help="Show stats only")
    parser.add_argument("--induct",    action="store_true", help="Run induction only, save proposals")
    parser.add_argument("--threshold", type=float, default=0.35,
                        help="Similarity threshold for clustering (default 0.35)")
    parser.add_argument("--min-sites", type=int, default=2,
                        help="Min distinct sites for a proposal (default 2)")
    parser.add_argument("--min-freq",  type=int, default=5,
                        help="Min total frequency for a proposal (default 5)")
    parser.add_argument("--ledger",    type=str, default=None,
                        help="Path to fallback_ledger.json (default ~/.browsermind/)")
    args = parser.parse_args()

    ledger = FallbackLedger(path=args.ledger)
    store  = VocabProposalStore()

    if args.stats:
        show_stats(ledger, store)
        return

    # Always run induction to find new proposals
    entries = ledger.all()
    if not entries:
        print(_yellow("  FallbackLedger is empty. Run exploration with a ledger-wired normalizer first."))
        print(_dim("  Example:"))
        print(_dim("    from browsermind_core.representation.fallback_ledger import FallbackLedger"))
        print(_dim("    from browsermind_core.representation.primitive_normalizer import PrimitiveNormalizer"))
        print(_dim("    ledger = FallbackLedger()"))
        print(_dim("    norm = PrimitiveNormalizer(logger=ledger.as_logger(site_key='github'))"))
        print()
        return

    print(f"  Ledger: {len(entries)} unique fragments, "
          f"{sum(e.frequency for e in entries.values())} total observations")
    print(f"  Clustering with threshold={args.threshold} ...")

    clusters  = cluster_fallbacks(entries, similarity_threshold=args.threshold)
    proposals = propose_vocab_expansions(
        clusters,
        min_sites=args.min_sites,
        min_freq=args.min_freq,
    )

    # Only save NEW proposals (don't overwrite existing decisions)
    existing_ids = {p.proposal_id for p in store.all()}
    new_proposals = [p for p in proposals if p.proposal_id not in existing_ids]
    if new_proposals:
        store.save_many(new_proposals)
        print(f"  Saved {len(new_proposals)} new proposals. "
              f"({len(proposals) - len(new_proposals)} already existed)")
    else:
        print(f"  {len(proposals)} proposals found, all already saved.")

    print(f"  {len(store.pending())} pending proposals.\n")

    if args.induct:
        show_stats(ledger, store)
        return

    # Interactive review
    run_interactive(store)

    # Reload extensions so this process benefits immediately
    n = load_vocab_extensions()
    if n:
        print(f"\n  Loaded {n} runtime extension(s) into PrimitiveNormalizer.")


if __name__ == "__main__":
    main()
