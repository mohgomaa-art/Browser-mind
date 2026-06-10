"""
rich_text_executor.py — Fills rich text editors that ignore standard fill().

Supported: Quill, TipTap, ProseMirror, CKEditor 5, CodeMirror, Monaco, TinyMCE.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page


class RichTextExecutor:
    """
    Fills rich text editors that cannot be targeted by standard input fill.

    Detection order (first match wins):
      1. Monaco (VSCode-based editors)
      2. CodeMirror 6
      3. CodeMirror 5
      4. TinyMCE (iframe-based)
      5. Quill
      6. TipTap / ProseMirror
      7. CKEditor 5
      8. contenteditable fallback
    """

    def __init__(self, page: "Page") -> None:
        self._page = page

    async def detect_editor(self, container: "Locator") -> Optional[str]:
        """Return the editor type or None if not a rich text editor."""
        try:
            kind = await container.evaluate(
                """(el) => {
                    if (el.classList.contains('monaco-editor') ||
                        el.querySelector('.monaco-editor')) return 'monaco';
                    if (el.querySelector('.cm-editor')) return 'codemirror6';
                    if (el.querySelector('.CodeMirror')) return 'codemirror5';
                    if (el.querySelector('.ql-editor')) return 'quill';
                    if (el.querySelector('.ProseMirror')) return 'prosemirror';
                    if (el.querySelector('.ck-editor__editable')) return 'ckeditor5';
                    if (el.tagName === 'IFRAME' &&
                        el.id && el.id.includes('tinymce')) return 'tinymce_iframe';
                    const editable = el.querySelector('[contenteditable]');
                    if (editable) return 'contenteditable';
                    return null;
                }"""
            )
            return kind
        except Exception:
            return None

    async def fill(self, container: "Locator", text: str) -> bool:
        """
        Fill a rich text editor. Returns True on success.

        Falls back to keyboard entry if JS injection fails.
        """
        kind = await self.detect_editor(container)
        if kind is None:
            return False

        try:
            if kind == "monaco":
                return await self._fill_monaco(container, text)
            if kind == "codemirror6":
                return await self._fill_cm6(container, text)
            if kind == "codemirror5":
                return await self._fill_cm5(container, text)
            if kind == "quill":
                return await self._fill_quill(container, text)
            if kind in ("prosemirror", "tiptap"):
                return await self._fill_prosemirror(container, text)
            if kind == "ckeditor5":
                return await self._fill_ckeditor5(container, text)
            if kind == "tinymce_iframe":
                return await self._fill_tinymce(container, text)
            if kind == "contenteditable":
                return await self._fill_contenteditable(container, text)
        except Exception:
            pass

        # Last resort: focus + select all + type
        return await self._keyboard_fill(container, text)

    async def clear(self, container: "Locator") -> bool:
        return await self.fill(container, "")

    # ------------------------------------------------------------------ #
    # Per-editor fill strategies                                           #
    # ------------------------------------------------------------------ #

    async def _fill_quill(self, container: "Locator", text: str) -> bool:
        await container.evaluate(
            """(el, t) => {
                const editor = el.querySelector('.ql-editor');
                if (!editor) return;
                editor.focus();
                const quill = Quill.find(editor);
                if (quill) {
                    quill.setText(t);
                } else {
                    editor.innerHTML = '';
                    document.execCommand('insertText', false, t);
                }
            }""",
            text,
        )
        return True

    async def _fill_prosemirror(self, container: "Locator", text: str) -> bool:
        editable = container.locator(".ProseMirror[contenteditable]")
        await editable.click()
        await self._page.keyboard.press("Control+a")
        await self._page.keyboard.type(text)
        return True

    async def _fill_ckeditor5(self, container: "Locator", text: str) -> bool:
        editable = container.locator(".ck-editor__editable")
        await editable.evaluate(
            """(el, t) => {
                el.focus();
                const editor = el.ckeditorInstance;
                if (editor) {
                    editor.setData(t);
                } else {
                    el.innerHTML = '';
                    document.execCommand('insertText', false, t);
                }
            }""",
            text,
        )
        return True

    async def _fill_cm6(self, container: "Locator", text: str) -> bool:
        cm = container.locator(".cm-editor")
        await cm.evaluate(
            """(el, t) => {
                const view = el.__cmView || window.__cmView;
                if (view) {
                    view.dispatch({
                        changes: { from: 0, to: view.state.doc.length, insert: t }
                    });
                    return;
                }
                // Fallback: select all + type
                el.querySelector('.cm-content')?.focus();
            }""",
            text,
        )
        if not text:
            return True
        # If view dispatch didn't work, keyboard fallback
        cm_content = container.locator(".cm-content")
        try:
            await cm_content.click()
            await self._page.keyboard.press("Control+a")
            await self._page.keyboard.type(text)
        except Exception:
            pass
        return True

    async def _fill_cm5(self, container: "Locator", text: str) -> bool:
        await container.evaluate(
            """(el, t) => {
                const cm = el.querySelector('.CodeMirror').CodeMirror;
                if (cm) cm.setValue(t);
            }""",
            text,
        )
        return True

    async def _fill_monaco(self, container: "Locator", text: str) -> bool:
        await container.evaluate(
            """(el, t) => {
                const findEditor = (root) => {
                    if (root._modelData) return root;
                    if (root.querySelector) {
                        const inner = root.querySelector('.monaco-editor');
                        if (inner && inner._modelData) return inner;
                    }
                    return null;
                };
                const monacoEl = findEditor(el);
                if (monacoEl && monacoEl._modelData) {
                    const model = monacoEl._modelData.model;
                    if (model) {
                        model.setValue(t);
                        return;
                    }
                }
                // Fallback via monaco global
                if (typeof monaco !== 'undefined') {
                    const editors = monaco.editor.getEditors();
                    if (editors.length > 0) editors[0].setValue(t);
                }
            }""",
            text,
        )
        return True

    async def _fill_tinymce(self, container: "Locator", text: str) -> bool:
        frame_id = await container.evaluate("el => el.id")
        await self._page.evaluate(
            """([id, t]) => {
                if (typeof tinymce !== 'undefined') {
                    const ed = tinymce.get(id);
                    if (ed) { ed.setContent(t); return; }
                    if (tinymce.editors.length > 0) {
                        tinymce.editors[0].setContent(t);
                    }
                }
            }""",
            [frame_id, text],
        )
        return True

    async def _fill_contenteditable(self, container: "Locator", text: str) -> bool:
        editable = container.locator("[contenteditable]").first
        await editable.evaluate(
            """(el, t) => {
                el.focus();
                el.innerHTML = '';
                document.execCommand('insertText', false, t);
            }""",
            text,
        )
        return True

    async def _keyboard_fill(self, container: "Locator", text: str) -> bool:
        try:
            await container.click()
            await self._page.keyboard.press("Control+a")
            await self._page.keyboard.type(text)
            return True
        except Exception:
            return False
