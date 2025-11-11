# __init__.py Connects the add-on to Anki, adds menu actions, and opens the week planner.
from __future__ import annotations
import datetime
from aqt import mw, gui_hooks  # type: ignore
from aqt.utils import tooltip  # type: ignore
from .config import get_config as _cfg, save_config as _save_cfg

from .deck_panel import inject_panel, on_js_msg, current_plan_snapshot, _refresh_plan_cache
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# Helper to add a deck to today's plan, handling config shape and de-duplication
# Helper to add a deck to today's plan, handling config shape and de-duplication
def _add_deck_to_today(did: int) -> None:
    today_iso = datetime.date.today().isoformat()

    # Start from canonical snapshot that Week Planner uses
    try:
        entries = current_plan_snapshot() or []
    except Exception:
        entries = []

    if not isinstance(entries, list):
        entries = []

    # Compute next order within today, and de-duplicate
    todays = [e for e in entries if isinstance(e, dict) and e.get("iso") == today_iso]
    next_order = len(todays)
    key_set = {
        (int(e.get("did", -1)), str(e.get("iso", "")))
        for e in entries
        if isinstance(e, dict)
    }
    key = (int(did), today_iso)
    if key not in key_set:
        entries.append({"iso": today_iso, "did": int(did), "order": next_order})

    # Save back using shared helpers
    try:
        cfg = _cfg() or {}
    except Exception:
        cfg = {}
    cfg["plan"] = entries
    try:
        _save_cfg(cfg)
    except Exception:
        pass

    # Refresh Week Planner UI
    try:
        if getattr(mw, "deckBrowser", None):
            mw.deckBrowser.refresh()
        else:
            mw.reset()
    except Exception:
        try:
            mw.reset()
        except Exception:
            pass

    try:
        tooltip(f"Added to Today: {mw.col.decks.name(did)}")
    except Exception:
        pass

def _on_profile_open() -> None:
    # prevent double-registration on profile reload
    if getattr(mw, "_week_planner_init_done", False):
        return
    mw._week_planner_init_done = True

    try:
        _refresh_plan_cache()
    except Exception:
        pass
    
    # Decks screen panel + JS bridge
    gui_hooks.deck_browser_did_render.append(inject_panel)
    gui_hooks.webview_did_receive_js_message.append(on_js_msg)

    def _on_sync_finished(*args, **kwargs) -> None:
        try:
            _refresh_plan_cache()
        except Exception:
            pass

    gui_hooks.sync_did_finish.append(_on_sync_finished)

    # Right-click context menu on deck rows: "Add to Review Today"


gui_hooks.profile_did_open.append(_on_profile_open)
