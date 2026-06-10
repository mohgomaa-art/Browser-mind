"""
forensic_demoqa.py

Inspect every field on demoqa.com/text-box and produce a per-step failure
classification table. We check:

  1. What accessible name does Playwright resolve?
  2. Is there a <label> nearby that a human can see?
  3. Is that label properly bound (for= / aria-labelledby / nesting)?
  4. What is the resulting failure category?

Output: a table printed to stdout and written to
  reports/forensic/demoqa_step_table.md
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

FIELDS = [
    # (step, id, human description)
    (2, "userName",        "Full Name textbox"),
    (3, "userEmail",       "Email textbox"),
    (4, "currentAddress",  "Current Address textarea"),
    (5, "permanentAddress","Permanent Address textarea"),
    (6, "submit",          "Submit button"),
]

async def inspect_field(page, field_id: str):
    el = page.locator(f"#{field_id}")
    try:
        await el.wait_for(state="attached", timeout=5000)
    except Exception:
        return {"error": "element not found"}

    tag       = await el.evaluate("el => el.tagName.toLowerCase()")
    el_type   = await el.evaluate("el => el.type || ''")
    aria_label = await el.evaluate("el => el.getAttribute('aria-label') || ''")
    aria_lb    = await el.evaluate("el => el.getAttribute('aria-labelledby') || ''")
    placeholder= await el.evaluate("el => el.getAttribute('placeholder') || ''")
    el_id      = await el.evaluate("el => el.id || ''")

    # Labels whose for= points to this id
    formal_labels = await page.evaluate(
        """([id]) => {
            const els = document.querySelectorAll(`label[for="${id}"]`);
            return Array.from(els).map(l => l.innerText.trim());
        }""",
        [el_id],
    )

    # Labels that wrap this element
    wrapped_labels = await el.evaluate(
        "el => { const p = el.closest('label'); return p ? p.innerText.trim() : ''; }"
    )

    # Nearby sibling/cousin labels (same row wrapper)
    nearby_labels = await page.evaluate(
        """([id]) => {
            const el = document.getElementById(id);
            if (!el) return [];
            const row = el.closest('.row') || el.parentElement;
            if (!row) return [];
            const labels = row.querySelectorAll('label');
            return Array.from(labels).map(l => l.innerText.trim());
        }""",
        [el_id],
    )

    # What role does the recorder extract?
    def infer_role(tag, el_type):
        if tag == "button" or (tag == "input" and el_type in ("button", "submit", "reset")):
            return "button"
        if tag in ("input", "textarea") and el_type not in ("checkbox", "radio", "hidden"):
            return "textbox"
        return tag

    role = infer_role(tag, el_type)

    # Accessible name priority (matches updated recorder)
    if aria_label:
        accessible_name = aria_label
    elif formal_labels:
        accessible_name = formal_labels[0]
    elif wrapped_labels:
        accessible_name = wrapped_labels
    elif placeholder:
        accessible_name = placeholder
    else:
        accessible_name = ""

    # Classify
    human_label_visible = bool(nearby_labels and any(nearby_labels))
    label_bound = bool(formal_labels or wrapped_labels or aria_label or aria_lb)

    if accessible_name:
        category = "RESOLVED"
    elif human_label_visible and not label_bound:
        category = "ORPHANED_LABEL"
    else:
        category = "EMPTY_SEMANTICS"

    return {
        "tag": tag,
        "type": el_type,
        "role": role,
        "aria_label": aria_label,
        "aria_labelledby": aria_lb,
        "placeholder": placeholder,
        "formal_labels": formal_labels,
        "wrapped_label": wrapped_labels,
        "nearby_labels": nearby_labels,
        "accessible_name_resolved": accessible_name,
        "human_label_visible": human_label_visible,
        "label_bound": label_bound,
        "category": category,
    }


async def main():
    out_dir = Path("reports/forensic")
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://demoqa.com/text-box")
        await page.wait_for_load_state("networkidle")

        rows = []
        for step, field_id, description in FIELDS:
            result = await inspect_field(page, field_id)
            rows.append({
                "step": step,
                "field_id": f"#{field_id}",
                "description": description,
                **result,
            })

        await browser.close()

    # -- Print table ------------------------------------------------------------
    col_w = [6, 22, 16, 16, 20, 16]
    headers = ["Step", "Description", "Accessible Name", "Human Label", "Label Bound?", "Category"]
    sep = "  ".join("-" * w for w in col_w)
    hdr = "  ".join(h.ljust(w) for h, w in zip(headers, col_w))

    lines = ["", "# DemoQA Step Forensics", "", hdr, sep]
    for r in rows:
        an = (r.get("accessible_name_resolved") or "")[:15]
        hl = (", ".join(r.get("nearby_labels") or []) or "")[:15]
        lb = "YES" if r.get("label_bound") else "NO"
        cat = r.get("category", "?")
        row_line = "  ".join([
            str(r["step"]).ljust(col_w[0]),
            r["description"][:21].ljust(col_w[1]),
            an.ljust(col_w[2]),
            hl.ljust(col_w[3]),
            lb.ljust(col_w[4]),
            cat.ljust(col_w[5]),
        ])
        lines.append(row_line)

    lines.append("")
    table_text = "\n".join(lines)
    print(table_text)

    # -- Write markdown ---------------------------------------------------------
    md_lines = [
        "# DemoQA Forensic Step Table",
        "",
        "| Step | Field | Description | Accessible Name | Human Label Visible | Label Bound? | Category |",
        "|------|-------|-------------|-----------------|---------------------|--------------|----------|",
    ]
    for r in rows:
        an   = r.get("accessible_name_resolved") or "--"
        hl   = ", ".join(r.get("nearby_labels") or []) or "--"
        lb   = "[OK] YES" if r.get("label_bound") else "[X] NO"
        cat  = r.get("category", "?")
        md_lines.append(
            f"| {r['step']} | `{r['field_id']}` | {r['description']} "
            f"| `{an}` | {hl} | {lb} | **{cat}** |"
        )

    # Key
    md_lines += [
        "",
        "## Key",
        "- **RESOLVED** -- BrowserMind can locate this element semantically during replay",
        "- **ORPHANED_LABEL** -- Human-visible label exists; website broke the binding (no `for=`, no nesting, no `aria-labelledby`). Environmental failure.",
        "- **EMPTY_SEMANTICS** -- No usable semantic identifier of any kind.",
        "",
        "## Raw Data",
        "```json",
        json.dumps(rows, indent=2),
        "```",
    ]

    md_path = out_dir / "demoqa_step_table.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\nReport written to: {md_path}")


asyncio.run(main())
