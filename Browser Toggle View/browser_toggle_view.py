"""
Transform the browser table into a stacked toggle document view (read-only, synced with card editor).
"""

from __future__ import annotations
import json
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Set

from aqt import mw
from aqt.browser import Browser
from aqt.gui_hooks import browser_menus_did_init, webview_did_receive_js_message
from aqt.qt import QAction, QKeySequence, QStackedWidget, QWidget, QCursor
from aqt.webview import AnkiWebView

from .config import gc
from .toolbar import getMenu


# --- Constants ---
DEFAULT_VIEW_TOGGLE = "Alt+4"
TEMPLATE_PATH = Path(__file__).with_name("toggle_view.html")
_TEMPLATE_CACHE: Optional[str] = None


def load_template_fragment() -> str:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        try:
            _TEMPLATE_CACHE = TEMPLATE_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            _TEMPLATE_CACHE = f"<html><body><p>Missing template: {exc}</p></body></html>"
    return _TEMPLATE_CACHE


def render_document_html(payload: dict) -> str:
    template = load_template_fragment()
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("__DOCVIEW_DATA__", data)


def night_mode_enabled() -> bool:
    try:
        pm = getattr(mw, "pm", None)
        if pm:
            flag = getattr(pm, "night_mode", None)
            if callable(flag):
                return bool(flag())
            if isinstance(flag, bool):
                return flag
            profile = getattr(pm, "profile", None)
            if isinstance(profile, dict):
                stored = profile.get("night_mode")
                if stored is not None:
                    return bool(stored)
    except Exception:
        pass
    return False


def resolve_field_name(note, configured: str, fallback_index: int) -> Optional[str]:
    try:
        model = note.model()
        fields = [fld.get("name") for fld in model.get("flds", [])]
    except Exception:
        return None

    if configured:
        for name in fields:
            if isinstance(name, str) and name.lower() == configured.lower():
                return name

    if 0 <= fallback_index < len(fields):
        return fields[fallback_index]

    return fields[0] if fields else None


def get_note_field_html(note, field_name: Optional[str], fallback_index: int) -> str:
    """Return the raw HTML stored in the requested field, falling back by index."""
    if not note:
        return ""

    if field_name:
        try:
            value = note[field_name]
        except Exception:
            value = None
        if value:
            return value

    try:
        fields = note.fields
    except Exception:
        fields = None

    if isinstance(fields, list) and 0 <= fallback_index < len(fields):
        return fields[fallback_index] or ""

    return ""


def render_browser_field(card, field_name: Optional[str], fallback_index: int) -> str:
    """Render field HTML via Anki's backend so it matches the Browser output."""
    if not card:
        return ""

    note = card.note()
    if not note:
        return ""

    name = field_name or resolve_field_name(note, "", fallback_index)
    col = getattr(mw, "col", None)
    backend = getattr(col, "backend", None) if col else None
    if name and backend:
        try:
            html = backend.render_browser_card(card_id=card.id, field_name=name)
            if html:
                return html
        except Exception as exc:
            print(f"[DocView] render_browser_field failed: {exc}")

    return get_note_field_html(note, name, fallback_index)


@dataclass
class ToggleEntry:
    question: str
    answer: str
    row: int
    card_id: Optional[int]
    note_id: Optional[int]
    answer_field: Optional[str]
    question_field: Optional[str]


# --- Init on Browser load ---
def on_browser_ready(browser: Browser) -> None:
    view_menu = getMenu(browser, "&View")

    setup_sidebar_toggle_action(browser, view_menu)

    action = QAction("Toggle Document View", browser)
    action.setShortcut(QKeySequence(gc("hotkey_toggle_document_view", DEFAULT_VIEW_TOGGLE)))
    action.triggered.connect(lambda _, b=browser: toggle_document_view(b))
    view_menu.addAction(action)
    browser._docview_toggle_action = action
    setup_embedded_view(browser)


browser_menus_did_init.append(on_browser_ready)


# --- Sidebar toggle ---
def setup_sidebar_toggle_action(browser: Browser, view_menu) -> None:
    if getattr(browser, "_docview_sidebar_action", None):
        return

    action = QAction("Show Browser Sidebar", browser)
    action.setCheckable(True)

    action.triggered.connect(lambda checked, b=browser: set_sidebar_visible(b, checked))
    view_menu.addAction(action)
    browser._docview_sidebar_action = action

    dock = getattr(browser, "sidebarDockWidget", None)
    if not dock:
        action.setEnabled(False)
        return

    def sync_action(visible: bool) -> None:
        prev = action.blockSignals(True)
        try:
            action.setChecked(bool(visible))
        finally:
            action.blockSignals(prev)

    dock.visibilityChanged.connect(sync_action)
    sync_action(dock.isVisible())


def set_sidebar_visible(browser: Browser, visible: bool) -> None:
    dock = getattr(browser, "sidebarDockWidget", None)
    if dock:
        dock.setVisible(bool(visible))


# --- Stack layout ---
def setup_embedded_view(browser: Browser) -> None:
    if getattr(browser, "_docview_stack", None):
        return

    table = browser.form.tableView
    parent = table.parent()
    layout = parent.layout()
    if not layout:
        return

    stack = QStackedWidget(parent)
    stack.setObjectName("DocViewStack")

    index = layout.indexOf(table)
    layout.removeWidget(table)
    layout.insertWidget(index if index >= 0 else 0, stack)

    stack.addWidget(table)
    document = DocumentView(browser, stack)
    stack.addWidget(document)

    browser._docview_stack = stack
    browser.document_view = document
    browser._docview_model = None
    if not hasattr(browser, "_docview_open_cards"):
        browser._docview_open_cards = set()

    install_model_watch(browser)
    refresh_document_view(browser)
    stack.setCurrentWidget(document)


# --- Model updates ---
def install_model_watch(browser: Browser) -> None:
    model = browser.form.tableView.model()
    if not model or getattr(browser, "_docview_model", None) is model:
        return

    browser._docview_model = model

    def refresh(*_):
        refresh_document_view(browser)

    model.modelReset.connect(refresh)
    model.layoutChanged.connect(refresh)
    model.rowsInserted.connect(refresh)
    model.rowsRemoved.connect(refresh)


# --- Toggle between table and doc view ---
def toggle_document_view(browser: Browser) -> None:
    """Toggle between the browser table and the document-style view."""
    setup_embedded_view(browser)
    stack = getattr(browser, "_docview_stack", None)
    table = browser.form.tableView
    document = getattr(browser, "document_view", None)
    if not stack or not isinstance(document, DocumentView):
        return

    if stack.currentWidget() is table:
        refresh_document_view(browser)
        stack.setCurrentWidget(document)
        document.setFocus()
    else:
        stack.setCurrentWidget(table)
        table.setFocus()


# --- Refresh doc view ---
def refresh_document_view(browser: Browser) -> None:
    install_model_watch(browser)
    document: Optional[DocumentView] = getattr(browser, "document_view", None)
    if not document:
        return

    entries, truncated, total, shown, error = collect_entries(browser)
    if error or not entries:
        document.show_placeholder(error or "Nothing to show.")
    else:
        open_cards = getattr(browser, "_docview_open_cards", set())
        document.populate(entries, open_cards=open_cards, truncated=truncated, total=total, shown=shown)


# --- Extract data from Browser table ---
def collect_entries(browser: Browser) -> Tuple[Optional[List[ToggleEntry]], bool, int, int, Optional[str]]:
    model = browser.form.tableView.model()
    if not model:
        return None, False, 0, 0, "Browser table not ready."

    answer_field_pref = gc("answer_field_name", "").strip()
    question_field_pref = gc("question_field_name", "").strip()

    row_count = model.rowCount()
    if not row_count:
        return None, False, 0, 0, "No rows found."

    try:
        max_rows_setting = int(gc("max_rows", 250))
    except Exception:
        max_rows_setting = 250
    max_rows = min(row_count, max_rows_setting)
    entries: List[ToggleEntry] = []
    for r in range(max_rows):
        index0 = model.index(r, 0)
        card = model.get_card(index0)
        if not card:
            continue
        note = card.note()
        if not note or not getattr(note, "fields", None):
            continue

        question_field_name = resolve_field_name(note, question_field_pref, 0)
        answer_field_name = resolve_field_name(note, answer_field_pref, 1)
        question_html = render_browser_field(card, question_field_name, 0)
        answer_html = render_browser_field(card, answer_field_name, 1)
        card_id = getattr(card, "id", None)
        note_id = getattr(note, "id", None)

        entries.append(
            ToggleEntry(
                question=question_html,
                answer=answer_html,
                row=r,
                card_id=card_id,
                note_id=note_id,
                answer_field=answer_field_name,
                question_field=question_field_name,
            )
        )
    return entries, row_count > max_rows, row_count, len(entries), None


# --- WebView ---
class DocumentView(AnkiWebView):
    def __init__(self, browser: Browser, parent: QWidget) -> None:
        super().__init__(parent)
        self.browser = browser

    def show_placeholder(self, message: str) -> None:
        self.stdHtml(f"<p>{message or 'Nothing to show.'}</p>", context=self.browser)

    def populate(
        self,
        entries: List[ToggleEntry],
        *,
        open_cards: Optional[Set[int]] = None,
        truncated=False,
        total=0,
        shown=0,
    ) -> None:
        open_cards = open_cards or set()

        def ensure_html(text: Optional[str], fallback: str) -> str:
            if not text:
                return fallback
            content = text or ""
            stripped = content.strip()
            if "<" in stripped and ">" in stripped:
                return content
            return content.replace("\n", "<br>")

        def format_question(text: Optional[str]) -> str:
            return ensure_html(text, "(empty question)")

        def format_answer(text: Optional[str]) -> str:
            return ensure_html(text, "—")

        entry_payload = [
            {
                "row": entry.row,
                "cardId": entry.card_id,
                "noteId": entry.note_id,
                "answerField": entry.answer_field,
                "questionField": entry.question_field,
                "questionHtml": format_question(entry.question),
                "answerHtml": format_answer(entry.answer),
                "isOpen": bool(entry.card_id and entry.card_id in open_cards),
            }
            for entry in entries
        ]

        payload = {
            "entries": entry_payload,
            "meta": {
                "truncated": truncated,
                "total": total,
                "shown": shown,
                "nightMode": night_mode_enabled(),
            },
        }

        html = render_document_html(payload)
        self.stdHtml(html, context=self.browser)


# --- Sync selection with card editor ---
def record_toggle_open_state(browser: Browser, card_id: int, is_open: bool) -> None:
    if card_id is None:
        return
    open_cards: Optional[Set[int]] = getattr(browser, "_docview_open_cards", None)
    if open_cards is None:
        open_cards = set()
        browser._docview_open_cards = open_cards
    if is_open:
        open_cards.add(card_id)
    else:
        open_cards.discard(card_id)


def sync_browser_row(browser: Browser, row: int) -> bool:
    table = getattr(browser.form, "tableView", None)
    model = table.model() if table else None
    if not table or not model or row < 0 or row >= model.rowCount():
        return False

    index = model.index(row, 0)
    selection = table.selectionModel()
    if selection:
        selection.clearSelection()
    table.selectRow(row)
    table.setCurrentIndex(index)
    table.scrollTo(index)

    card = model.get_card(index)
    note = card.note() if card else None
    if not card or not note:
        return False

    browser.card = card
    editor = getattr(browser, "editor", None)
    if editor:
        editor.card = card
        editor.set_note(note)
        editor.load_note()

    browser._current_row = row
    return True


def on_docview_message(handled, message, context):
    try:
        if message == "DOCVIEW_SELECT_ALL":
            browser = getattr(context, "browser", None) or mw.app.activeWindow()
            if isinstance(browser, Browser):
                table = getattr(browser.form, "tableView", None)
                if table is not None:
                    table.selectAll()
            return (True, None)

        if message.startswith("DOCVIEW_CONTEXT:"):
            try:
                row = int(message.split(":")[1])
            except ValueError:
                return (True, None)

            browser = getattr(context, "browser", None) or mw.app.activeWindow()
            if not isinstance(browser, Browser):
                return (True, None)

            table = getattr(browser.form, "tableView", None)
            model = table.model() if table else None
            if not table or not model or row < 0 or row >= model.rowCount():
                return (True, None)

            index = model.index(row, 0)
            table.setCurrentIndex(index)
            table.selectRow(row)

            handler = getattr(browser, "onContextMenu", None)
            if handler:
                local_pos = table.viewport().mapFromGlobal(QCursor.pos())
                handler(local_pos)

            return (True, None)

        if message.startswith("DOCVIEW_OPEN:"):
            parts = message.split(":")
            if len(parts) >= 3:
                try:
                    card_id = int(parts[1])
                except ValueError:
                    return (True, None)
                is_open = parts[2] == "1"
                browser = getattr(context, "browser", None) or mw.app.activeWindow()
                if isinstance(browser, Browser):
                    record_toggle_open_state(browser, card_id, is_open)
            return (True, None)

        if message.startswith("DOCVIEW_UPDATE:"):
            payload = message[len("DOCVIEW_UPDATE:") :]
            browser = getattr(context, "browser", None) or mw.app.activeWindow()
            if not isinstance(browser, Browser):
                return (True, None)
            apply_inline_update(browser, payload)
            return (True, None)

        if not message.startswith("DOCVIEW_SELECT:"):
            return handled

        row = int(message.split(":")[1])
        browser = getattr(context, "browser", None)
        if not browser:
            browser = mw.app.activeWindow()

        if not isinstance(browser, Browser):
            return (True, None)

        if not sync_browser_row(browser, row):
            return (True, None)

    except Exception as e:
        print(f"[DocView] Selection error: {e}")

    return (True, None)


webview_did_receive_js_message.append(on_docview_message)


def apply_inline_update(browser: Browser, data_payload: str) -> None:
    try:
        padding = (-len(data_payload)) % 4
        decoded = base64.b64decode(data_payload + ("=" * padding))
        data = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        print(f"[DocView] Failed to decode inline update: {exc}")
        return

    card_id = data.get("cardId")
    note_id = data.get("noteId")
    field_name = data.get("field")
    html = data.get("html", "")

    if not field_name:
        return

    try:
        col = getattr(mw, "col", None)
        if not col:
            return

        note = None
        if note_id:
            note = col.get_note(note_id)
        if not note and card_id:
            card = col.get_card(card_id)
            note = card.note() if card else None
        if not note:
            return

        if field_name not in note:
            print(f"[DocView] Field '{field_name}' missing on note {note.id}")
            return

        if note[field_name] == html:
            return

        note[field_name] = html
        note.flush()

        editor = getattr(browser, "editor", None)
        if editor and editor.note and editor.note.id == note.id:
            editor.set_note(note)
            editor.load_note()
    except Exception as exc:
        print(f"[DocView] Failed to apply inline update: {exc}")
