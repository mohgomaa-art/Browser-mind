"""P2B — Semantic in-page observer. Captures Observation/Action/Result."""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List

from playwright.async_api import BrowserContext, Page
from browsermind_core.recorder.capability_classifier import CapabilityClassifier

_SEMANTIC_OBSERVER_JS = """
(() => {
  if (window.__bmSemanticObserverInstalled) return;
  window.__bmSemanticObserverInstalled = true;

  const getAXRole = (el) => {
    try {
      if (!el || !el.tagName) return '';
      if (typeof el.getAttribute === 'function' && el.getAttribute('role')) return el.getAttribute('role');
      const tag = el.tagName.toLowerCase();
      if (tag === 'button') return 'button';
      if (tag === 'a') return 'link';
      if (tag === 'textarea') return 'textbox';
      if (tag === 'select') return 'combobox';
      if (tag === 'img') return 'img';
      if (tag === 'svg') return 'img';
      if (tag === 'input') {
        const type = (el.type || 'text').toLowerCase();
        if (['button', 'submit', 'reset'].includes(type)) return 'button';
        if (type === 'search') return 'searchbox';
        if (type === 'number') return 'spinbutton';
        if (type === 'range') return 'slider';
        if (['checkbox', 'radio'].includes(type)) return type;
        return 'textbox';
      }
      if (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tag)) return 'heading';
      if (tag === 'ul' || tag === 'ol') return 'list';
      if (tag === 'li') return 'listitem';
      if (tag === 'nav') return 'navigation';
      if (tag === 'main') return 'main';
      if (tag === 'form') return 'form';
      if (tag === 'header') return 'banner';
      if (tag === 'footer') return 'contentinfo';
      if (tag === 'article') return 'article';
      if (tag === 'section') return 'region';
      if (tag === 'table') return 'table';
      if (tag === 'td' || tag === 'th') return 'cell';
      if (tag === 'tr') return 'row';
      return 'generic';
    } catch(e) { return 'generic'; }
  };

  const getAccessibleName = (el) => {
    try {
      if (!el) return '';
      if (typeof el.getAttribute === 'function' && el.getAttribute('aria-label')) return el.getAttribute('aria-label');
      if (el.labels && el.labels.length > 0) {
        const labelText = Array.from(el.labels).map(l => l.innerText).join(' ').trim();
        if (labelText) return labelText.slice(0, 100);
      }
      if (el.title) return el.title;
      if (typeof el.getAttribute === 'function' && el.getAttribute('placeholder')) return el.getAttribute('placeholder');
      
      const isTextInput = (el.tagName === 'INPUT' && !['button', 'submit', 'reset', 'hidden', 'checkbox', 'radio'].includes((el.type || '').toLowerCase())) || el.tagName === 'TEXTAREA';
      
      // Guard innerText with !isTextInput — Chromium returns a text input's typed value as innerText,
      // which would record user-entered data as the element's identity and break replay.
      if (!isTextInput && el.innerText && el.innerText.trim()) return el.innerText.trim().slice(0, 100);
      if (!isTextInput && el.value && typeof el.value === 'string' && el.value.trim()) return el.value.trim().slice(0, 100);
      
      if (typeof el.getAttribute === 'function' && el.getAttribute('name')) return el.getAttribute('name');
      return '';
    } catch(e) { return ''; }
  };

  // --- react-select / SaaS combobox normalizer ---
  // Many forms (Greenhouse, Lever, Workday, anything using react-select) render
  // a closed dropdown as <div class="select__placeholder">Select...</div> inside
  // an unlabelled wrapper. Capturing that text + role='generic' is unreplayable.
  // This helper walks UP to the actual combobox container and returns it,
  // along with the field label that disambiguates which dropdown it is.
  const normalizeSelectTarget = (el) => {
    try {
      if (!el || !el.classList && !el.closest) return { el: el, label: '' };
      // Detect react-select internals: placeholder, control, indicator, single-value
      const isReactSelectPiece = (node) => {
        if (!node || !node.classList) return false;
        for (const c of node.classList) {
          if (c.indexOf('select__placeholder') === 0) return true;
          if (c.indexOf('select__indicator') === 0) return true;
          if (c.indexOf('select__single-value') === 0) return true;
          if (c.indexOf('select__multi-value') === 0) return true;
          if (c.indexOf('select__value-container') === 0) return true;
          if (c.indexOf('select__dropdown-indicator') === 0) return true;
        }
        return false;
      };
      let target = el;
      if (isReactSelectPiece(el)) {
        // Walk up to find select__control (the actual interactive wrapper).
        let p = el;
        for (let i = 0; i < 6 && p; i++, p = p.parentElement) {
          if (!p.classList) continue;
          let isControl = false;
          for (const c of p.classList) {
            if (c.indexOf('select__control') === 0) { isControl = true; break; }
          }
          if (isControl) { target = p; break; }
        }
        // From the control, look for a real <input role="combobox"> child.
        const innerCombo = target.querySelector && target.querySelector('input[role="combobox"], [role="combobox"]');
        if (innerCombo) target = innerCombo;
      }
      // Find the label: aria-labelledby on the wrapper, enclosing <label>,
      // or label[for=<id>] sibling, or nearest preceding label-like text.
      let label = '';
      try {
        const lb = target.getAttribute && target.getAttribute('aria-labelledby');
        if (lb) {
          const node = document.getElementById(lb.split(/\s+/)[0]);
          if (node) label = (node.innerText || node.textContent || '').trim().slice(0, 120);
        }
      } catch(_) {}
      if (!label) {
        try {
          const lab = target.closest && target.closest('label');
          if (lab) label = (lab.innerText || '').trim().slice(0, 120);
        } catch(_) {}
      }
      if (!label) {
        try {
          let w = target;
          for (let i = 0; i < 6 && w && w !== document.body; i++, w = w.parentElement) {
            const id = w.id;
            if (id) {
              const escId = (window.CSS && CSS.escape) ? CSS.escape(id) : id;
              const sib = document.querySelector('label[for="' + escId + '"]');
              if (sib) { label = (sib.innerText || '').trim().slice(0, 120); break; }
            }
          }
        } catch(_) {}
      }
      if (!label) {
        // Walk up looking for a sibling/ancestor label-ish text (last resort).
        try {
          let p = target.parentElement;
          for (let i = 0; i < 5 && p && p !== document.body; i++, p = p.parentElement) {
            const candidate = p.querySelector && p.querySelector('label, .label, [class*="label" i]');
            if (candidate && candidate !== target) {
              const text = (candidate.innerText || '').trim();
              if (text && text.toLowerCase() !== 'select...') {
                label = text.slice(0, 120);
                break;
              }
            }
          }
        } catch(_) {}
      }
      return { el: target, label: label };
    } catch(e) { return { el: el, label: '' }; }
  };

  const getFallbackSelector = (el) => {
    try {
      if (!el || !el.tagName) return '';
      if (el.id) return '#' + el.id;
      if (el.name) return '[name="' + el.name + '"]';
      if (typeof el.getAttribute === 'function') {
        if (el.getAttribute('data-test')) return '[data-test="' + el.getAttribute('data-test') + '"]';
        if (el.getAttribute('data-testid')) return '[data-testid="' + el.getAttribute('data-testid') + '"]';
      }
      return el.tagName.toLowerCase();
    } catch(e) { return ''; }
  };

  // --- P3.1: TargetDescriptor Facts ---
  const getTargetDescriptor = (el) => {
    try {
      if (!el) return {};
      const role = getAXRole(el);
      const ariaLabel = (typeof el.getAttribute === 'function' && el.getAttribute('aria-label')) || '';
      const placeholder = (typeof el.getAttribute === 'function' && el.getAttribute('placeholder')) || '';
      const elemId = el.id || '';
      const dataTestid = (typeof el.getAttribute === 'function' && el.getAttribute('data-testid')) || '';
      const nameAttr = (typeof el.getAttribute === 'function' && el.getAttribute('name')) || '';
      const isTextInput = (el.tagName === 'INPUT' && !['button', 'submit', 'reset', 'hidden', 'checkbox', 'radio'].includes((el.type || '').toLowerCase())) || el.tagName === 'TEXTAREA';
      const textContent = isTextInput ? '' : (el.innerText || '').trim().slice(0, 120);
      // Build a minimal dom_path: walk up to 4 ancestors, record tagName[id or index]
      let domPath = [];
      let cur = el;
      for (let i = 0; i < 4 && cur && cur.tagName; i++) {
        const tag = cur.tagName.toLowerCase();
        const id = cur.id ? '#' + cur.id : '';
        domPath.unshift(tag + id);
        cur = cur.parentElement;
      }

      // --- P4E Task 3A: Container Label ---
      // Walk up to find the nearest labelled container (product card, list item, etc.)
      // Signals: h1-h4 inside a common ancestor, [data-test*="name"], [class*="title"], [class*="name"]
      let containerLabel = '';
      let containerDataTest = '';
      let price = '';
      try {
        try {
          const labelledBy = el.getAttribute && el.getAttribute('aria-labelledby');
          if (labelledBy) {
            const labelNode = document.getElementById(labelledBy.split(/\s+/)[0]);
            if (labelNode) {
              containerLabel = (labelNode.innerText || labelNode.textContent || '').trim().slice(0, 100);
            }
          }
        } catch(_) {}
        if (!containerLabel) {
          try {
            const enclosingLabel = el.closest && el.closest('label');
            if (enclosingLabel) {
              containerLabel = (enclosingLabel.innerText || '').trim().slice(0, 100);
            }
          } catch(_) {}
        }
        if (!containerLabel) {
          try {
            const fs = el.closest && el.closest('fieldset');
            if (fs) {
              const legend = fs.querySelector('legend');
              if (legend) {
                containerLabel = (legend.innerText || '').trim().slice(0, 100);
              }
            }
          } catch(_) {}
        }
        if (!containerLabel) {
          try {
            let walker = el;
            for (let j = 0; j < 5 && walker && walker !== document.body; j++) {
              const id2 = walker.id;
              if (id2) {
                const escId = (window.CSS && CSS.escape) ? CSS.escape(id2) : id2;
                const sibLabel = document.querySelector('label[for="' + escId + '"]');
                if (sibLabel) {
                  containerLabel = (sibLabel.innerText || '').trim().slice(0, 100);
                  break;
                }
              }
              walker = walker.parentElement;
            }
          } catch(_) {}
        }
        let p = el.parentElement;
        for (let i = 0; i < 6 && p && p !== document.body; i++, p = p.parentElement) {
          if (!containerLabel) {
            const nameEl = p.querySelector(
              'h1,h2,h3,h4,[data-test*="name"],[class*="item_name"],[class*="product_name"],[class*="title"]'
            );
            if (nameEl && nameEl !== el) {
              containerLabel = (nameEl.innerText || '').trim().slice(0, 100);
            }
          }
          if (typeof p.getAttribute === 'function') {
            const dt = p.getAttribute('data-test');
            if (dt) { containerDataTest = dt; }
          }
          const priceEl = p.querySelector('[class*="price"]');
          if (priceEl && priceEl !== el) {
            price = (priceEl.innerText || '').trim().slice(0, 50);
          }
          if (containerLabel && containerDataTest) break;
        }
      } catch(e) {}
      
      // Task 3B: Selection Forensics - List Size
      // How many similar containers exist on the page?
      let listSize = 0;
      try {
          const name = getAccessibleName(el);
          if (role && name) {
              // rough approximation: how many elements with same role & name
              const allSame = Array.from(document.querySelectorAll(el.tagName.toLowerCase()))
                .filter(node => getAXRole(node) === role && getAccessibleName(node) === name);
              listSize = allSame.length;
          }
      } catch(e) {}

      return {
        role,
        accessible_name: ariaLabel,
        text_content: textContent,
        placeholder,
        dom_path: domPath.join(' > '),
        container_label: containerLabel,
        container_data_test: containerDataTest,
        price: price,
        list_size: listSize,
        id: elemId,
        data_testid: dataTestid,
        aria_label: ariaLabel,
        name: nameAttr,
      };
    } catch(e) { return {}; }
  };

  // --- WR-IR: Capability Context & Ordinal ---
  // capability_context: nearest labelled form / section ancestor text
  const getCapabilityContext = (el) => {
    try {
      let p = el.parentElement;
      for (let i = 0; i < 6 && p && p !== document.body; i++, p = p.parentElement) {
        if (p.tagName === 'FORM') {
          const action = (p.getAttribute('action') || '').toLowerCase();
          const label  = (p.getAttribute('aria-label') || '').toLowerCase();
          const id     = (p.id || '').toLowerCase();
          return action || label || id || 'form';
        }
        if (p.tagName === 'FIELDSET' || p.tagName === 'SECTION' || p.tagName === 'HEADER' || p.tagName === 'NAV') {
          const h = p.querySelector('legend, h1, h2, h3, h4, [aria-label]');
          if (h) return (h.getAttribute('aria-label') || h.innerText || '').toLowerCase().trim().slice(0, 60);
        }
      }
      return '';
    } catch(e) { return ''; }
  };

  // capability_ordinal: 1-indexed position among same-tag siblings under same parent
  const getCapabilityOrdinal = (el) => {
    try {
      const tag = el.tagName.toLowerCase();
      const type = el.type ? el.type.toLowerCase() : '';
      let siblings = [];
      // Walk up to find the nearest form or section container
      let container = el.parentElement;
      for (let i = 0; i < 5 && container && container !== document.body; i++, container = container.parentElement) {
        if (container.tagName === 'FORM' || container.tagName === 'FIELDSET') break;
      }
      if (!container || container === document.body) container = el.parentElement;
      if (type) {
        siblings = [...container.querySelectorAll(`${tag}[type="${type}"]`)];
      } else {
        siblings = [...container.querySelectorAll(tag)];
      }
      const idx = siblings.indexOf(el);
      return idx >= 0 ? idx + 1 : 1;
    } catch(e) { return 1; }
  };

  // --- P3.1: RecordingEvidence (transient DOM state) ---
  const getCandidateCount = (el) => {
    try {
      if (!el) return 0;
      const role = getAXRole(el);
      if (!role) return 0;
      // Count visible elements with the same tagName as a rough candidate proxy.
      const tag = el.tagName.toLowerCase();
      const allSame = document.querySelectorAll(tag);
      let count = 0;
      allSame.forEach(node => {
        if (getAXRole(node) === role) count++;
      });
      return count;
    } catch(e) { return 0; }
  };

  const isPassword = (el) => {
    try {
      return el && el.tagName === 'INPUT' && el.type === 'password';
    } catch(e) { return false; }
  };

  const isVisible = (el) => {
    try {
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
    } catch(e) { return false; }
  };

  const findSingleDescendantControl = (root) => {
    try {
      if (!root || typeof root.querySelectorAll !== 'function') return null;
      const selector = [
        'input:not([type="hidden"])',
        'textarea',
        'select',
        'button',
        'a[href]',
        '[role="button"]',
        '[role="link"]',
        '[role="combobox"]',
        '[role="textbox"]',
        '[role="option"]',
        '[role="checkbox"]',
        '[role="radio"]',
        '[role="switch"]'
      ].join(',');
      const candidates = Array.from(root.querySelectorAll(selector))
        .filter(node => node !== root && isVisible(node));
      if (candidates.length === 1) return candidates[0];

      const named = candidates.filter(node => getAccessibleName(node));
      if (named.length === 1) return named[0];
      return null;
    } catch(e) { return null; }
  };

  const getSemanticTarget = (el) => {
    let cur = el;
    let depth = 0;
    while (cur && cur !== document.body && cur !== document.documentElement) {
      const tag = cur.tagName.toLowerCase();
      if (['a', 'button', 'input', 'textarea', 'select', 'label', 'summary'].includes(tag)) {
        return cur;
      }
      if (typeof cur.getAttribute === 'function' && cur.getAttribute('role')) {
        return cur;
      }
      if (depth < 3) {
        const descendant = findSingleDescendantControl(cur);
        if (descendant) return descendant;
      }
      cur = cur.parentElement;
      depth += 1;
    }
    return el;
  };

  const send = (type, originalEl, extra) => {
    try {
      if (typeof window.__bmRecordSemanticAction !== 'function') return;

      const el = getSemanticTarget(originalEl);

      let val = extra && extra.value !== undefined ? String(extra.value) : null;
      let vault_ref = null;

      if (val !== null && el && isPassword(el)) {
          val = null; // NEVER send raw password
          vault_ref = "password";
      }

      const _norm = normalizeSelectTarget(el);
      const normEl = _norm.el || el;
      const fieldLabel = _norm.label || '';
      const descriptor = getTargetDescriptor(normEl);
      // If the normalizer rewrote a react-select placeholder click into a
      // combobox click, force the descriptor's container_label to the field
      // label so the runtime resolver can use _try_container_label.
      if (fieldLabel) {
        descriptor.container_label = descriptor.container_label || fieldLabel;
      }
      const candidateCount = getCandidateCount(normEl);
      const capabilityContext = getCapabilityContext(normEl);
      const capabilityOrdinal = getCapabilityOrdinal(normEl);

      // For a normalized select target: emit role='combobox' and use the
      // field label as the name. This is the single fix that lets templates
      // recorded on react-select forms (Greenhouse, Lever, Workday) replay.
      let outRole = getAXRole(normEl);
      let outName = getAccessibleName(normEl);
      if (fieldLabel && (outRole === 'generic' || !outName || outName === 'Select...')) {
        outRole = 'combobox';
        outName = fieldLabel;
      }

      window.__bmRecordSemanticAction({
        action_type: type,
        url: location.href,
        target_role: outRole,
        target_name: outName,
        target_selector: getFallbackSelector(normEl),
        value: val,
        vault_ref: vault_ref,
        meta: extra || {},
        descriptor: descriptor,
        recording_evidence: { candidate_count: candidateCount, page_url: location.href, normalized: fieldLabel ? 'react_select' : null },
        capability_context: capabilityContext,
        capability_ordinal: capabilityOrdinal,
      });
    } catch(e) {}
  };

  const pendingInputs = new Map();
  
  const flushInputs = () => {
    pendingInputs.forEach((el) => {
        // --- [BM-DIAG] Capture state BEFORE getSemanticTarget ---
        const _origTag = el ? el.tagName : 'NULL';
        const _origId  = el ? (el.id || '') : '';
        const _origVal = el ? (el.value || '') : '';
        const _origConn = el ? el.isConnected : false;

        const semanticEl = getSemanticTarget(el);

        const _semTag  = semanticEl ? semanticEl.tagName : 'NULL';
        const _semId   = semanticEl ? (semanticEl.id || '') : '';
        const _semRole = getAXRole(semanticEl);
        const _semName = getAccessibleName(semanticEl);

        // Only log on first fill (el.value is 1 char) or when there's divergence
        if (_origTag !== _semTag || _origId !== _semId) {
          console.warn('[BM-DIAG] flush divergence detected:',
            'orig=' + _origTag + '#' + _origId + ' val=' + _origVal + ' connected=' + _origConn,
            '→ semantic=' + _semTag + '#' + _semId + ' role=' + _semRole + ' name=' + _semName
          );
        }

        send('fill', el, { value: el.value });
    });
    pendingInputs.clear();
  };

  document.addEventListener('input', (e) => {
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) {
      pendingInputs.set(t, t);
    }
  }, true);

  document.addEventListener('click', (e) => {
    flushInputs();
    send('click', e.target, { x: e.clientX, y: e.clientY });
  }, true);
  
  document.addEventListener('submit', (e) => {
    flushInputs();
    // Resolve submit button — form element has role='form' with empty name, which TargetResolver
    // cannot locate. The submit button has a stable role='button' and accessible name.
    let submitTarget = e.target;
    try {
      const btn = e.target.querySelector(
        'button[type="submit"], input[type="submit"], button:not([type="button"]):not([type="reset"])'
      );
      if (btn) submitTarget = btn;
    } catch(err) {}
    send('submit', submitTarget, {});
  }, true);

  window.addEventListener('keydown', (e) => {
    if (['Enter', 'Tab', 'Escape'].includes(e.key)) {
      flushInputs();
      send('keydown', e.target, { key: e.key });
    }
  }, true);
})();
"""


class SemanticRecorder:
    """Attach semantic observer to Playwright page; takes screenshots on action."""

    def __init__(self, on_step: Callable[[Dict[str, Any]], None]):
        self._on_step = on_step
        self._buffer: List[Dict[str, Any]] = []
        self._page: Page | None = None
        self._classifier = CapabilityClassifier()
        # Track ordinal counts per capability per page to support ordinal disambiguation
        self._capability_ordinal_seen: Dict[str, int] = {}

    @property
    def buffer(self) -> List[Dict[str, Any]]:
        return list(self._buffer)

    async def attach(self, context: BrowserContext, page: Page):
        self._page = page
        
        async def _handler(payload: Dict[str, Any]):
            # --- WR-IR: Classify capability and enrich descriptor ---
            cap_context = payload.pop("capability_context", "") or ""
            cap_ordinal  = payload.pop("capability_ordinal", 1) or 1

            # Classify
            cap_fields = self._classifier.classify(
                payload,
                capability_context=cap_context,
                capability_ordinal=cap_ordinal,
            )
            # Merge into descriptor
            if "descriptor" not in payload or payload["descriptor"] is None:
                payload["descriptor"] = {}
            payload["descriptor"].update(cap_fields)

            # Take screenshot asynchronously to avoid blocking JS
            # Note: page.screenshot can fail if page navigates mid-screenshot, so catch exceptions
            shot_hash = ""
            try:
                if self._page and not self._page.is_closed():
                    shot = await self._page.screenshot(type="jpeg", quality=50)
                    shot_hash = hashlib.sha256(shot).hexdigest()
            except Exception as e:
                print(f"  [Recorder] Missed screenshot: {e}")
            
            payload["screenshot_hash"] = shot_hash
            payload["result_url"] = self._page.url if self._page and not self._page.is_closed() else payload.get("url", "")
            payload["result_state"] = "recorded"
            
            self._buffer.append(payload)
            self._on_step(payload)

        await context.expose_function("__bmRecordSemanticAction", _handler)
        # Use context.add_init_script to ensure all pages/frames get it
        await context.add_init_script(_SEMANTIC_OBSERVER_JS)
        await page.evaluate(_SEMANTIC_OBSERVER_JS)

    async def record_navigation(self, page: Page, reason: str = "goto"):
        shot_hash = ""
        try:
            if not page.is_closed():
                shot = await page.screenshot(type="jpeg", quality=50)
                shot_hash = hashlib.sha256(shot).hexdigest()
        except Exception:
            pass
            
        self._on_step(
            {
                "action_type": "navigate",
                "url": page.url,
                "target_role": "browser",
                "target_name": reason,
                "target_selector": "",
                "value": None,
                "vault_ref": None,
                "result_url": page.url,
                "result_state": "navigation",
                "screenshot_hash": shot_hash,
                "meta": {},
            }
        )
