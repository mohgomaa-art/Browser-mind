"""
BrowserMind -- Phase 3.2 Gold Session Recorder (AIRTIGHT)
=======================================================
Headed persistent context recorder for human-driven demonstrations.

On each detected click/type event:
- capture AX graph + URL + cookies + DOM text before/after
- capture a minimal action/network trace
- run the verifier gate (AIRTIGHT only)
- append to training/gold/samples.json, otherwise quarantine the attempt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import async_playwright

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _base_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse

        netloc = urlparse(url).netloc.lower()
        return netloc.replace("www.", "")
    except Exception:
        return (url or "").split("://")[-1].split("/")[0].replace("www.", "").lower()


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


async def _snapshot(page) -> Dict[str, Any]:
    from training.graph_builder import build_graph_from_page, prune_graph
    from training.verification.core import stable_hash

    url = page.url
    cookies = []
    try:
        cookies = await page.context.cookies()
    except Exception:
        cookies = []

    dom_text = ""
    try:
        dom_text = await page.locator("body").inner_text(timeout=1500)
        dom_text = (dom_text or "")[:20000]
    except Exception:
        dom_text = ""

    graph = {}
    try:
        g = await build_graph_from_page(page)
        nodes, edges = prune_graph(g.get("nodes", []), g.get("edges", []))
        graph = {"nodes": nodes, "edges": edges}
    except Exception:
        graph = {"nodes": [], "edges": []}

    snapshot = {
        "url": url,
        "cookies": cookies,
        "dom_text": dom_text,
        "graph": graph,
    }
    snapshot["state_hash"] = stable_hash({"url": url, "graph": graph, "dom": dom_text[:5000]})
    return snapshot


_INJECT_RECORDER_JS = r"""
(() => {
  if (window.__bmGoldHooksInstalled) return;
  window.__bmGoldHooksInstalled = true;

  const readText = (el) => {
    try {
      const t = (el.innerText || el.value || el.getAttribute('aria-label') || el.placeholder || '').toString().trim();
      return t.slice(0, 120);
    } catch {
      return '';
    }
  };

  const selectorFor = (el) => {
    try {
      if (el.id) return '#' + el.id;
      const tag = (el.tagName || 'unknown').toLowerCase();
      const cls = (el.className || '').toString().split(/\s+/).filter(Boolean)[0];
      if (cls) return tag + '.' + cls;
      const nameAttr = el.getAttribute('name');
      if (nameAttr) return tag + '[name="' + nameAttr + '"]';
      return tag;
    } catch {
      return '';
    }
  };

  const emit = (payload) => {
    try {
      if (typeof window.__bm_gold_record === 'function') {
        window.__bm_gold_record(payload);
      }
    } catch {}
  };

  // Click: capture-phase so we see it before navigation.
  document.addEventListener('click', (ev) => {
    const el = ev.target;
    if (!el || !el.tagName) return;
    emit({
      action_type: 'click',
      target_text: readText(el),
      target_selector: selectorFor(el),
      typed_text: ''
    });
  }, true);

  // Input: fires after value changes; still useful for before/after snapshots.
  document.addEventListener('input', (ev) => {
    const el = ev.target;
    if (!el || !el.tagName) return;
    const tag = el.tagName.toLowerCase();
    if (tag !== 'input' && tag !== 'textarea' && !el.isContentEditable) return;
    let typed = '';
    try {
      typed = (el.value || el.innerText || '').toString().slice(0, 200);
    } catch {}
    emit({
      action_type: 'type',
      target_text: readText(el),
      target_selector: selectorFor(el),
      typed_text: typed
    });
  }, true);
})();
"""


def _infer_element_idx(nodes: List[Dict[str, Any]], payload: Dict[str, Any], goal: str) -> Optional[int]:
    from core.decision_engine import ElementScorer

    target_text = str(payload.get("target_text") or payload.get("target_selector") or "").strip()
    if not nodes:
        return None

    elements = []
    for nd in nodes:
        role = str(nd.get("role", "generic"))
        name = str(nd.get("name", "")).strip()
        elements.append(
            {
                "tag": "button" if role in ("button", "link", "menuitem") else ("input" if role in ("textbox", "combobox") else "div"),
                "text": name,
                "placeholder": str(nd.get("placeholder", "")),
                "id_attr": "",
                "classes": "",
                "role": role,
                "clickable": role in ("button", "link", "menuitem", "tab"),
                "visible": True,
                "x": int(nd.get("x", 0) or 0),
                "y": int(nd.get("y", 0) or 0),
                "w": int(nd.get("w", 10) or 10),
                "h": int(nd.get("h", 10) or 10),
            }
        )

    ranked = ElementScorer.rank(elements, target_text=target_text, goal=goal, top_k=1)
    if not ranked:
        return None
    return int(ranked[0].index)


def _hard_negatives(nodes: List[Dict[str, Any]], payload: Dict[str, Any], goal: str, chosen_idx: Optional[int]) -> List[Dict[str, Any]]:
    from core.decision_engine import ElementScorer

    target_text = str(payload.get("target_text") or payload.get("target_selector") or "").strip()
    elements = []
    for nd in nodes:
        role = str(nd.get("role", "generic"))
        name = str(nd.get("name", "")).strip()
        elements.append(
            {
                "tag": "button" if role in ("button", "link", "menuitem") else ("input" if role in ("textbox", "combobox") else "div"),
                "text": name,
                "placeholder": str(nd.get("placeholder", "")),
                "id_attr": "",
                "classes": "",
                "role": role,
                "clickable": role in ("button", "link", "menuitem", "tab"),
                "visible": True,
                "x": int(nd.get("x", 0) or 0),
                "y": int(nd.get("y", 0) or 0),
                "w": int(nd.get("w", 10) or 10),
                "h": int(nd.get("h", 10) or 10),
            }
        )

    ranked = ElementScorer.rank(elements, target_text=target_text, goal=goal, top_k=6)
    out = []
    for cand in ranked:
        if chosen_idx is not None and int(cand.index) == int(chosen_idx):
            continue
        el = cand.element
        out.append({"idx": int(cand.index), "score": float(cand.score), "text": str(el.get("text", ""))[:80], "role": str(el.get("role", ""))})
        if len(out) >= 3:
            break
    return out


async def _open_persistent_context(pw, args):
    profile_dir = Path(args.user_data_dir).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    launch_kwargs: Dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": False,
        "ignore_default_args": ["--enable-automation"],
        "args": ["--no-first-run", "--start-maximized"],
    }
    if args.chrome_exe:
        launch_kwargs["executable_path"] = args.chrome_exe
    else:
        launch_kwargs["channel"] = "chrome"

    context = await pw.chromium.launch_persistent_context(**launch_kwargs)
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


async def _run(args) -> None:
    from training.verification.registry import default_registry, infer_task_type
    from training.verification.core import stable_hash
    from scripts.audit_utils import domain_from_url, state_family_key

    registry = default_registry()
    samples_path = Path("training/gold/samples.json")
    quarantine_path = Path("training/gold/quarantine/rejected.jsonl")
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)

    samples: List[Dict[str, Any]] = _read_json(samples_path, default=[])
    if not isinstance(samples, list):
        samples = []

    domain = _base_domain(args.url)

    # caps
    domain_count = sum(1 for s in samples if _base_domain(str(s.get("url", ""))) == domain)
    if domain_count >= args.max_per_domain:
        print(f"[stop] domain cap reached for {domain} ({domain_count} >= {args.max_per_domain})")
        return

    async with async_playwright() as pw:
        context, page = await _open_persistent_context(pw, args)

        # Network capture (best-effort)
        recent_network: List[Dict[str, Any]] = []

        def on_request(req):
            try:
                recent_network.append({"method": req.method, "url": req.url, "ts": time.time()})
            except Exception:
                pass

        def on_response(resp):
            try:
                recent_network.append({"url": resp.url, "status": resp.status, "ts": time.time()})
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        # Recorder binding
        last_event_at = 0.0

        async def _handle_event(payload: dict) -> None:
            nonlocal last_event_at, recent_network, samples

            if not isinstance(payload, dict):
                return
            now = time.time()
            if (now - last_event_at) < 0.2:
                return
            last_event_at = now

            action_type = str(payload.get("action_type", "")).strip().lower()
            if action_type not in {"click", "type"}:
                return

            # Snapshot before/after
            before = await _snapshot(page)
            # allow UI transition
            await asyncio.sleep(args.after_wait_ms / 1000.0)
            after = await _snapshot(page)

            # Trace
            actions_trace = [
                {
                    "type": action_type,
                    "target_text": str(payload.get("target_text", ""))[:120],
                    "target_selector": str(payload.get("target_selector", ""))[:160],
                    "value": str(payload.get("typed_text", ""))[:200] if action_type == "type" else "",
                    "ts": now,
                }
            ]
            # Keep only network events close to this action
            net = [e for e in recent_network if abs(float(e.get("ts", now)) - now) < 2.5]
            trace = {"actions": actions_trace, "network": net}

            task_type = args.task_type or infer_task_type(args.goal)
            result = registry.verify(task_type, before, after, trace, goal=args.goal)
            verification = result.to_dict() if hasattr(result, "to_dict") else asdict(result)

            chosen_idx = None
            try:
                chosen_idx = _infer_element_idx(after.get("graph", {}).get("nodes", []), payload, args.goal)
            except Exception:
                chosen_idx = None

            before_url = str(before.get("url", "") or "")
            after_url = str(after.get("url", "") or "")
            before_hash = str(before.get("state_hash", "") or "")
            after_hash = str(after.get("state_hash", "") or "")

            domain = domain_from_url(args.url)
            graph_for_family = {
                "graph": after.get("graph", {}) if isinstance(after.get("graph", {}), dict) else {},
            }
            state_family = state_family_key(graph_for_family)

            evidence = {
                "process": verification.get("process_evidence", {}),
                "transition": verification.get("transition_evidence", {}),
                "outcome": verification.get("outcome_evidence", {}),
            }

            action_payload = {
                "type": action_type,
                "action_type": action_type,
                "target_element": str(payload.get("target_text", "") or payload.get("target_selector", ""))[:140],
                "target_text": str(payload.get("target_text", ""))[:120],
                "target_selector": str(payload.get("target_selector", ""))[:160],
                "typed_text": str(payload.get("typed_text", ""))[:200] if action_type == "type" else "",
                "element_idx": chosen_idx,
            }

            sample = {
                # Required Gold fields (training/gold/README.md)
                "goal": args.goal,
                "url": args.url,
                "domain": domain,
                "state_family": state_family,
                "action": action_payload,
                "target_element": action_payload.get("target_element", ""),
                "success": bool(getattr(result, "is_gold_eligible", False)),
                "goal_verified": bool(verification.get("goal_verified") is True),
                "verification": verification,
                "causality_strength": str(verification.get("causality_strength", "")),
                "evidence": evidence,
                "process_evidence": verification.get("process_evidence", {}),
                "transition_evidence": verification.get("transition_evidence", {}),
                "outcome_evidence": verification.get("outcome_evidence", {}),
                "execution_trace": trace,
                "before_state_hash": before_hash,
                "after_state_hash": after_hash,
                "before_url": before_url,
                "after_url": after_url,
                "provenance": {
                    "source": "human_gold_recording",
                    "collection_method": "scripts/record_gold_session.py",
                    "headed_persistent_context": True,
                },
                "collector_version": "phase4.2",
                "verifier_version": str(verification.get("verifier_version", "")),
                "timestamp": _now_iso(),
                "sample_hash": stable_hash(
                    {
                        "goal": args.goal,
                        "url": args.url,
                        "task_type": task_type,
                        "action": action_payload,
                        "before": {"url": before_url, "state_hash": before_hash},
                        "after": {"url": after_url, "state_hash": after_hash},
                    }
                ),
                # Additional helpful fields
                "task_type": task_type,
                "hard_negatives": _hard_negatives(after.get("graph", {}).get("nodes", []), payload, args.goal, chosen_idx),
                "graph": after.get("graph", {}),
            }

            # state family cap
            fam_count = sum(1 for s in samples if str(s.get("state_family", "")) == state_family)
            if fam_count >= args.max_per_state_family:
                sample["rejected_reason"] = f"state_family_cap({fam_count} >= {args.max_per_state_family})"
                if not args.dry_run:
                    with open(quarantine_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                print("[reject] state family cap")
                return

            # Replay gate (Phase 4.2): must be replayable and pass.
            replay_passed = False
            replay_result: Dict[str, Any] = {}
            if args.require_replay and not args.dry_run:
                try:
                    from scripts.sample_replayer import replay_sample

                    replay_result = await replay_sample(sample, headless=True, include_graph=True)
                    replay_passed = bool(replay_result.get("replay_passed") is True)
                except Exception as exc:
                    replay_result = {"error": str(exc)[:500], "replay_passed": False}
                    replay_passed = False

            sample["replay_passed"] = replay_passed if args.require_replay else None
            sample["replay"] = replay_result

            if args.require_replay and not args.dry_run and not replay_passed:
                sample["rejected_reason"] = "replay_failed"
                with open(quarantine_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                print("[reject] replay failed")
                return

            if getattr(result, "is_gold_eligible", False):
                if not args.dry_run:
                    samples.append(sample)
                    _write_json(samples_path, samples)
                print("[gold] saved (airtight)")
            else:
                if not args.dry_run:
                    with open(quarantine_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                print(f"[reject] not airtight ({sample['verification'].get('causality_strength')})")

        async def _binding(_source, payload):
            try:
                await _handle_event(payload)
            except Exception as exc:
                print(f"[gold-recorder] handler error: {exc}")

        await page.expose_binding("__bm_gold_record", _binding)
        await page.add_init_script(_INJECT_RECORDER_JS)

        print("\n" + "=" * 70)
        print("Gold recording started (close the browser window to stop).")
        print(f"Goal     : {args.goal}")
        print(f"URL      : {args.url}")
        print(f"Task type: {args.task_type or '(infer)'}")
        print(f"Profile  : {args.user_data_dir}")
        print("=" * 70 + "\n")

        await page.goto(args.url, wait_until="domcontentloaded")

        try:
            # Keep alive until user closes.
            while True:
                await asyncio.sleep(0.5)
        except Exception:
            pass
        finally:
            await context.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", type=str, required=True)
    ap.add_argument("--url", type=str, required=True)
    ap.add_argument("--task-type", type=str, default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--after-wait-ms", type=int, default=900)
    ap.add_argument("--require-replay", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--user-data-dir", type=str, default=str((Path.home() / ".browsermind" / "chrome_profile").resolve()))
    ap.add_argument("--chrome-exe", type=str, default="")
    ap.add_argument("--max-per-domain", type=int, default=100)
    ap.add_argument("--max-per-state-family", type=int, default=50)
    args = ap.parse_args()

    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

