"""
Minimal entry point that injects a small JS helper into Anki's editor so that
typing `>` at the start of a line turns it into a <details> block.
"""

import os
from aqt import gui_hooks

_JS_CACHE = None


def _get_js():
    global _JS_CACHE
    if _JS_CACHE is None:
        js_path = os.path.join(os.path.dirname(__file__), "toggle.js")
        with open(js_path, "r", encoding="utf-8") as fh:
            _JS_CACHE = fh.read()
    return _JS_CACHE


def _inject_toggle_js(editor):
    editor.web.eval(_get_js())


gui_hooks.editor_did_load_note.append(_inject_toggle_js)
