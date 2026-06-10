"""Run a P2B Semantic Recording Session (Observation/Action/Result)."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from browsermind_core.console.session import KernelSession
from browsermind_core.recorder.demonstration_repository import DemonstrationRepository
from browsermind_core.recorder.demonstration_session import DemonstrationSession, DemonstrationStep
from browsermind_core.recorder.semantic_recorder import SemanticRecorder
from browsermind_core.runtime.environment_registry import resolve
from browsermind_core.runtime.auth_session import AuthSession


async def run_recording_session(
    store_dir: str,
    env_key: str,
    persona_name: str,
    *,
    headless: bool = False,
    start_url: Optional[str] = None,
) -> DemonstrationSession:
    
    entry = resolve(env_key)
    if not entry:
        raise ValueError(f"Unknown environment: {env_key}")

    url = start_url or entry.start_url
    
    auth_session = AuthSession(
        entry=entry,
        persona_name=persona_name,
        store_dir=Path(store_dir),
        headless=headless,
    )

    repo = DemonstrationRepository(store_dir)
    session = DemonstrationSession(
        persona_name=persona_name,
        environment_family=entry.family,
        environment_instance=entry.key,
        profile_path=str(auth_session.profile_path),
        start_url=url,
    )
    repo.set_active(session.id)
    session_ref: list[DemonstrationSession] = [session]

    def on_step(payload: dict):
        s = session_ref[0]
        s.append(
            DemonstrationStep(
                seq=0,
                action_type=payload.get("action_type", "click"), # type: ignore
                url=payload.get("url", ""),
                target_role=payload.get("target_role", ""),
                target_name=payload.get("target_name", ""),
                target_selector=payload.get("target_selector", ""),
                value=payload.get("value"),
                vault_ref=payload.get("vault_ref"),
                result_url=payload.get("result_url", ""),
                result_state=payload.get("result_state", ""),
                screenshot_hash=payload.get("screenshot_hash", ""),
                descriptor=payload.get("descriptor") or {},
                recording_evidence=payload.get("recording_evidence") or {},
                metadata=payload.get("meta") or {},
            )
        )

    recorder = SemanticRecorder(on_step)

    # Ledger: session started
    ks = KernelSession(store_dir)
    ks.event_bus.emit(
        "EntityMutated",
        {
            "entity_type": "DemonstrationSession",
            "entity_id": session.id,
            "new_value": {"status": "recording", "url": url, "family": entry.family},
            "actor": "bm_record",
        },
    )

    # Open the browser using AuthSession
    page = await auth_session.open(url)
    context = page.context

    def _console_handler(msg):
        text = msg.text
        if "[BM-DIAG]" in text:
            print(f"\n  {'='*60}")
            print(f"  [BM-DIAG] {text}")
            print(f"  {'='*60}\n")
        else:
            pass  # suppress non-diagnostic noise during recording

    def _attach_console(p):
        p.on("console", _console_handler)
        p.on("pageerror", lambda err: print(f"  [Browser Error] {err}"))

    _attach_console(page)
    # Capture console from any new pages/popups opened in this context
    context.on("page", _attach_console)

    await recorder.attach(context, page)
    await recorder.record_navigation(page, "initial_goto")

    print(f"\n  Recording  [{str(session.id)[:8]}…]")
    print(f"  Profile:  {auth_session.profile_path}")
    print(f"  URL:      {url}")
    print("\n  Interact in the browser. Press Enter here to stop.\n")
    await asyncio.get_event_loop().run_in_executor(None, input)

    await recorder.record_navigation(page, "final_url")
    await auth_session.close()

    session.complete()
    repo.save(session)
    repo.clear_active()

    ks.event_bus.emit(
        "EntityMutated",
        {
            "entity_type": "DemonstrationSession",
            "entity_id": session.id,
            "old_value": {"status": "recording"},
            "new_value": {
                "status": "completed",
                "action_count": len(session.actions),
            },
            "actor": "bm_record",
        },
    )

    return session
