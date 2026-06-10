"""Stage 1 live verification -- does field_registry_rescue actually fire?

The user's success criterion for Stage 1 is *not* "tests pass." It is:

  A real replay produces at least one observable field_registry_rescue
  resolution on a genuine ambiguity case.

This script reproduces the exact AMBIGUOUS_IDENTITY case observed in the
ledger -- 12 buttons named "Toggle flyout", one per form section, with the
relevant section labeled "Country / Region" -- and runs the real
TargetResolver against it.

Success: resolver returns ResolutionResult with resolved_by ==
"field_registry_rescue" and points at the button inside the
"Country / Region" section.

Failure: any other outcome. If the resolver raises AmbiguousIdentityError
or picks the wrong button, Stage 1 has not achieved its goal and we stop
to root-cause rather than proceed to Stage 2.

This script writes its raw output to reports/stage1_verification/.
"""
from __future__ import annotations

import asyncio
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from browsermind_core.runtime.target_resolver import (
    AmbiguousIdentityError,
    TargetResolutionError,
    TargetResolver,
)

REPORT_DIR = Path("reports/stage1_verification")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# Synthetic Greenhouse-style application form with 12 react-select dropdowns.
# Each dropdown renders as a styled button labeled "Toggle flyout" (this is
# the exact accessible name observed in the failing ledger records).
# Each lives inside a labeled section. The "correct" target is the one in
# the section whose visible label says "Country / Region".
SYNTHETIC_PAGE = """
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Synthetic Greenhouse Form</title></head>
<body>
  <h1>Apply for Software Engineer</h1>
  <form>
    <section>
      <label>First Name</label>
      <input name="first_name" />
    </section>
    <section>
      <label>Last Name</label>
      <input name="last_name" />
    </section>
    <section>
      <label>Email</label>
      <input type="email" name="email" />
    </section>
    <section>
      <label>Phone</label>
      <input name="phone" />
    </section>

    <!-- 12 react-select-style dropdowns, each rendered as a button named
         "Toggle flyout". The Country / Region one is the disambiguation
         target. -->
    <section>
      <label>School</label>
      <div class="select__control"><button data-id="school" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Degree</label>
      <div class="select__control"><button data-id="degree" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Discipline</label>
      <div class="select__control"><button data-id="discipline" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Start Year</label>
      <div class="select__control"><button data-id="start-year" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>End Year</label>
      <div class="select__control"><button data-id="end-year" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Country / Region</label>
      <div class="select__control"><button data-id="country" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Gender</label>
      <div class="select__control"><button data-id="gender" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Race / Ethnicity</label>
      <div class="select__control"><button data-id="race" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Veteran Status</label>
      <div class="select__control"><button data-id="veteran" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Disability Status</label>
      <div class="select__control"><button data-id="disability" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>Work Authorization</label>
      <div class="select__control"><button data-id="work-auth" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
    <section>
      <label>How did you hear about us?</label>
      <div class="select__control"><button data-id="referral" aria-label="Toggle flyout">Toggle flyout</button></div>
    </section>
  </form>
</body>
</html>
"""


async def run_verification() -> dict:
    """Return a result dict with all observed facts. Never raises."""
    result = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "synthetic_page": "12 Toggle-flyout buttons, one in 'Country / Region' section",
        "step_under_test": None,
        "outcome": None,
        "resolver_strategy": None,
        "resolved_target_data_id": None,
        "error": None,
        "evidence": [],
    }

    # Step that the compiler would have produced for the failing case:
    # action=click, target_role=button, target_name='Toggle flyout',
    # with field_id='country' written at step level.
    step = {
        "seq": 10,
        "action_type": "click",
        "target_role": "button",
        "target_name": "Toggle flyout",
        "target_selector": "",
        "field_id": "country",
        "field_kind": "single_select",
        "descriptor": {
            "role": "button",
            "accessible_name": "Toggle flyout",
            "container_label": "",  # empty -- this is the recorder gap
            "dom_path": "div > div > div > button",
            "capability_hint": "generic_button",
            "list_size": 12,
        },
    }
    result["step_under_test"] = step

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(SYNTHETIC_PAGE)

            resolver = TargetResolver(
                page, env_key="synthetic_verification", persona_id="stage1_probe"
            )

            try:
                res = await resolver.resolve(
                    target_role=step["target_role"],
                    target_name=step["target_name"],
                    target_selector=step["target_selector"],
                    descriptor=step["descriptor"],
                    enable_recovery=True,
                    step=step,
                )
                result["outcome"] = res.mode
                result["resolver_strategy"] = res.resolved_by
                result["recovered_by"] = res.recovered_by
                result["candidate_count"] = res.candidate_count

                # If we got a locator, identify which one it pointed at.
                if res.locator is not None:
                    try:
                        data_id = await res.locator.get_attribute("data-id")
                        result["resolved_target_data_id"] = data_id
                    except Exception as e:
                        result["resolved_target_data_id"] = f"<probe failed: {e}>"

            except AmbiguousIdentityError as e:
                result["outcome"] = "AMBIGUOUS_IDENTITY"
                result["error"] = str(e)
                result["candidate_count"] = getattr(e, "candidate_count", None)
            except TargetResolutionError as e:
                result["outcome"] = "TARGET_NOT_FOUND"
                result["error"] = str(e)
            except Exception as e:
                result["outcome"] = "UNEXPECTED_ERROR"
                result["error"] = f"{type(e).__name__}: {e}"
                result["traceback"] = traceback.format_exc()
        finally:
            await browser.close()

    return result


def evaluate(result: dict) -> dict:
    """Apply the user's success criterion. Pure function."""
    verdict = {
        "stage1_passes": False,
        "reason": "",
        "details": [],
    }
    if result["resolver_strategy"] == "field_registry_rescue":
        if result["resolved_target_data_id"] == "country":
            verdict["stage1_passes"] = True
            verdict["reason"] = (
                "field_registry_rescue fired AND pointed at the correct "
                "(Country / Region) button among 12 ambiguous candidates."
            )
        else:
            verdict["stage1_passes"] = False
            verdict["reason"] = (
                f"field_registry_rescue fired, but pointed at the wrong "
                f"button (data-id={result['resolved_target_data_id']!r}, "
                "expected 'country'). The strategy is reachable but its "
                "label-proximity walk is selecting the wrong candidate."
            )
    elif result["outcome"] == "AMBIGUOUS_IDENTITY":
        verdict["stage1_passes"] = False
        verdict["reason"] = (
            "AmbiguousIdentityError still raised. Defect A is not actually "
            "fixed -- field_registry_rescue was bypassed."
        )
    elif result["outcome"] == "TARGET_NOT_FOUND":
        verdict["stage1_passes"] = False
        verdict["reason"] = (
            "TargetResolutionError raised. Resolver didn't see any matching "
            "candidate at all -- this is a Playwright/page-rendering issue "
            "in the synthetic fixture, not a Stage 1 outcome."
        )
    else:
        verdict["stage1_passes"] = False
        verdict["reason"] = (
            f"Resolver returned strategy={result['resolver_strategy']!r}, "
            f"outcome={result['outcome']!r}. Field Ontology did not win the "
            "ambiguity case. Either a different strategy resolved it first "
            "(unlikely given identical role+name), or the rescue failed "
            "silently."
        )
    return verdict


async def main() -> int:
    result = await run_verification()
    verdict = evaluate(result)

    out_path = REPORT_DIR / f"verification_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
    out_path.write_text(
        json.dumps({"result": result, "verdict": verdict}, indent=2, default=str),
        encoding="utf-8",
    )

    print("=" * 70)
    print("STAGE 1 LIVE VERIFICATION")
    print("=" * 70)
    print(f"Resolver strategy:    {result['resolver_strategy']!r}")
    print(f"Outcome:              {result['outcome']!r}")
    print(f"Target data-id:       {result['resolved_target_data_id']!r}")
    print(f"Candidate count:      {result.get('candidate_count')!r}")
    print(f"Error:                {result.get('error')!r}")
    print()
    print(f"VERDICT:              {'PASS' if verdict['stage1_passes'] else 'FAIL'}")
    print(f"Reason:               {verdict['reason']}")
    print()
    print(f"Full report:          {out_path}")
    print("=" * 70)

    return 0 if verdict["stage1_passes"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
