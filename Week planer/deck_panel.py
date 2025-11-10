# deck_panel.py , Manages all backend logic for saving, loading, and updating the deck plan data.
from __future__ import annotations
from typing import Any, Dict, List, Tuple
import json
import datetime
from pathlib import Path

from aqt import mw  # type: ignore
from aqt.utils import showInfo  # type: ignore
from .config import get_config as _cfg, save_config as _save_cfg

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

PlanEntry = Dict[str, Any]

WRAP_ARROWS_DEFAULT = False
WRAP_ARROWS = WRAP_ARROWS_DEFAULT


_USER_FILES_DIR = Path(__file__).resolve().parent / "user_files"
_PLAN_FILE = _USER_FILES_DIR / "plan.json"
_README_FILE = _USER_FILES_DIR / "README.txt"
_README_CONTENT = (
    "Week Planner user files\n"
    "=======================\n"
    "\n"
    "The add-on stores its persistent weekly plan in plan.json inside this\n"
    "folder. Feel free to back it up or place it under version control.\n"
)

def _apply_wrap_from_cfg(cfg: Dict[str, Any]) -> None:
    """Update the global WRAP_ARROWS flag based on config."""
    global WRAP_ARROWS
    try:
        WRAP_ARROWS = bool(cfg.get("wrap_arrows", WRAP_ARROWS_DEFAULT))
    except Exception:
        WRAP_ARROWS = WRAP_ARROWS_DEFAULT

def _today_date() -> datetime.date:
    return datetime.date.today()
def _iso(date_obj: datetime.date) -> str:
    return date_obj.isoformat()

def _iso_today() -> str:
    return _iso(_today_date())

def _week_start(date_obj: datetime.date | None = None) -> datetime.date:
    date_obj = date_obj or _today_date()
    return date_obj - datetime.timedelta(days=date_obj.weekday())

def _iso_dates_from_today(k: int) -> List[str]:
    base = _today_date()
    return [_iso(base + datetime.timedelta(days=i)) for i in range(max(1, int(k)))]

def _current_week_bounds(date_obj: datetime.date | None = None) -> Tuple[datetime.date, datetime.date]:
    """Return (start, end) covering the visible Monday–Friday window."""
    start = _week_start(date_obj)
    end = start + datetime.timedelta(days=4)
    return start, end

def _weekday_label_to_iso(label: str, base_week: datetime.date | None = None) -> str | None:
    label = (label or "").strip()[:3].title()
    if label not in DAYS:
        return None
    base_week = base_week or _week_start()
    idx = DAYS.index(label)
    target = base_week + datetime.timedelta(days=idx)
    return _iso(target)

def _valid_iso_date(value: str) -> bool:
    try:
        datetime.date.fromisoformat(value)
        return True
    except Exception:
        return False

def _coerce_int(value: Any) -> int | None:
    try:
        num = int(value)
    except Exception:
        return None
    return num if num >= 0 else None

def _canonicalize_plan(entries: List[PlanEntry]) -> Tuple[List[PlanEntry], bool]:
    """Return canonical plan list sorted by iso/order with deduplicated rows."""
    per_iso: Dict[str, List[PlanEntry]] = {}
    changed = False
    for row in entries:
        if not isinstance(row, dict):
            changed = True
            continue
        did = _coerce_int(row.get("did"))
        iso = row.get("iso") if isinstance(row.get("iso"), str) else None
        order = row.get("order")
        if did is None or not iso or not _valid_iso_date(iso):
            changed = True
            continue
        try:
            order_int = int(order)
        except Exception:
            order_int = 0
            changed = True
        per_iso.setdefault(iso, []).append({"did": did, "iso": iso, "order": order_int})

    canonical: List[PlanEntry] = []
    for iso in sorted(per_iso.keys()):
        seen: set[int] = set()
        bucket = sorted(per_iso[iso], key=lambda r: (r.get("order", 0), r["did"]))
        for idx, row in enumerate(bucket):
            if row["did"] in seen:
                changed = True
                continue
            seen.add(row["did"])
            if row.get("order") != idx:
                changed = True
            canonical.append({"did": row["did"], "iso": iso, "order": idx})
    return canonical, changed

def _filter_plan_to_current_week(entries: List[PlanEntry]) -> Tuple[List[PlanEntry], bool]:
    """Drop plan rows that fall outside the currently visible week."""
    start, end = _current_week_bounds()
    kept: List[PlanEntry] = []
    changed = False
    for row in entries:
        if not isinstance(row, dict):
            changed = True
            continue
        iso = row.get("iso")
        if not isinstance(iso, str) or not _valid_iso_date(iso):
            changed = True
            continue
        try:
            iso_date = datetime.date.fromisoformat(iso)
        except Exception:
            changed = True
            continue
        if start <= iso_date <= end:
            kept.append(row)
        else:
            changed = True
    if not changed:
        return entries, False
    canonical, _ = _canonicalize_plan(kept)
    return canonical, True

def _ensure_user_files() -> None:
    try:
        _USER_FILES_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return
    try:
        if not _README_FILE.exists():
            _README_FILE.write_text(_README_CONTENT, encoding="utf-8")
    except Exception:
        pass

def _write_plan_to_disk(plan: List[PlanEntry]) -> None:
    try:
        _ensure_user_files()
        payload = json.dumps(plan, indent=2)
        _PLAN_FILE.write_text(payload + "\n", encoding="utf-8")
    except Exception:
        pass

def _load_plan_from_disk() -> tuple[List[PlanEntry], bool]:
    _ensure_user_files()
    if not _PLAN_FILE.exists():
        return ([], False)
    try:
        raw_text = _PLAN_FILE.read_text(encoding="utf-8")
    except Exception:
        return ([], False)
    try:
        raw = json.loads(raw_text) if raw_text.strip() else []
    except Exception:
        return ([], False)
    plan, changed = _migrate_plan(raw)
    if changed:
        _write_plan_to_disk(plan)
    return (plan, True)

_ensure_user_files()

def _plan_rows_equal(a: List[PlanEntry] | None, b: List[PlanEntry] | None) -> bool:
    if a is b:
        return True
    if not a or not b:
        return not a and not b
    if len(a) != len(b):
        return False
    for idx in range(len(a)):
        row_a = a[idx]
        row_b = b[idx]
        if not isinstance(row_a, dict) or not isinstance(row_b, dict):
            return False
        if _coerce_int(row_a.get("did")) != _coerce_int(row_b.get("did")):
            return False
        if str(row_a.get("iso", "")) != str(row_b.get("iso", "")):
            return False
        try:
            order_a = int(row_a.get("order", -1))
            order_b = int(row_b.get("order", -1))
        except Exception:
            return False
        if order_a != order_b:
            return False
    return True

def _migrate_plan(raw: Any) -> Tuple[List[PlanEntry], bool]:
    """Normalize config plan value into the flat PLAN list structure."""
    changed = False
    entries: List[PlanEntry] = []

    if isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                changed = True
                continue
            did = _coerce_int(row.get("did"))
            iso = row.get("iso") if isinstance(row.get("iso"), str) else None
            order = row.get("order")
            if did is None or not iso or not _valid_iso_date(iso):
                changed = True
                continue
            try:
                order_int = int(order)
            except Exception:
                order_int = 0
                changed = True
            entries.append({"did": did, "iso": iso, "order": order_int})
    else:
        changed = True

    canonical, canonical_changed = _canonicalize_plan(entries)
    return canonical, changed or canonical_changed

_PLAN_CACHE: List[PlanEntry] | None = None
_SCRIPT_CACHE: str | None = None

def _load_script_template() -> str:
    global _SCRIPT_CACHE
    if _SCRIPT_CACHE is None:
        path = Path(__file__).with_name("deck_panel_script.js")
        try:
            _SCRIPT_CACHE = path.read_text(encoding="utf-8")
        except Exception as exc:
            raise RuntimeError(f"Week Planner script missing at {path}") from exc
    return _SCRIPT_CACHE

def _load_current_plan() -> List[PlanEntry]:
    cfg = _cfg()
    _apply_wrap_from_cfg(cfg)
    cfg_plan, cfg_changed = _migrate_plan(cfg.get("plan", []))
    disk_plan, disk_valid = _load_plan_from_disk()
    if disk_valid:
        plan, trimmed = _filter_plan_to_current_week(disk_plan)
        needs_save = trimmed
        if trimmed:
            _write_plan_to_disk(plan)
        if not _plan_rows_equal(cfg_plan, plan) or cfg.get("plan") is None:
            cfg["plan"] = plan
            needs_save = True
        if "wrap_arrows" not in cfg:
            cfg["wrap_arrows"] = WRAP_ARROWS
            needs_save = True
        if needs_save:
            _save_cfg(cfg)
        return plan
    plan, trimmed = _filter_plan_to_current_week(cfg_plan)
    needs_save = cfg_changed or trimmed
    if cfg_changed or trimmed:
        cfg["plan"] = plan
    if "wrap_arrows" not in cfg:
        cfg["wrap_arrows"] = WRAP_ARROWS
        needs_save = True
    if needs_save:
        _save_cfg(cfg)
    _write_plan_to_disk(plan)
    return plan

def _get_plan() -> List[PlanEntry]:
    global _PLAN_CACHE
    if _PLAN_CACHE is None:
        cached = _load_current_plan()
        _PLAN_CACHE = [dict(row) for row in cached]
    return _PLAN_CACHE

def _refresh_plan_cache() -> List[PlanEntry]:
    global _PLAN_CACHE
    cached = _load_current_plan()
    new_plan = [dict(row) for row in cached]
    _PLAN_CACHE = new_plan
    _broadcast_plan_to_web(new_plan)
    return _PLAN_CACHE

def _broadcast_plan_to_web(plan: List[PlanEntry]) -> None:
    try:
        deck_browser = getattr(mw, "deckBrowser", None)
        web = getattr(deck_browser, "web", None)
    except Exception:
        return
    if not web:
        return
    try:
        payload = json.dumps(plan)
        web.eval(f"if (window.WP_setPlan) {{ window.WP_setPlan({payload}); }}")
    except Exception:
        pass

def _save_plan(plan: List[PlanEntry]) -> None:
    global _PLAN_CACHE
    if not isinstance(plan, list):
        plan = [] 
    canonical, _ = _canonicalize_plan(plan)
    canonical, _ = _filter_plan_to_current_week(canonical)
    canonical_copy = [dict(row) for row in canonical]
    if _plan_rows_equal(_PLAN_CACHE, canonical_copy):
        return
    _PLAN_CACHE = canonical_copy
    cfg = _cfg()
    cfg["plan"] = canonical_copy
    cfg.setdefault("wrap_arrows", WRAP_ARROWS)
    _save_cfg(cfg)
    _write_plan_to_disk(canonical_copy)
    _broadcast_plan_to_web(canonical_copy)

def current_plan_snapshot() -> List[PlanEntry]:
    """Return a deep copy of the current plan cache for external consumers."""
    plan = _get_plan()
    return json.loads(json.dumps(plan))

def replace_plan_with_week_labels(day_map: Dict[str, List[int]]) -> None:
    """Overwrite plan using a mapping from weekday labels (Mon…) to deck IDs."""
    plan = list(_get_plan())
    base_week = _week_start()
    target_isos: List[str] = []
    for day_label in day_map.keys():
        iso = _weekday_label_to_iso(day_label, base_week)
        if iso:
            target_isos.append(iso)

    if target_isos:
        plan = [entry for entry in plan if entry.get("iso") not in target_isos]

    for day_label, deck_ids in day_map.items():
        iso = _weekday_label_to_iso(day_label, base_week)
        if not iso:
            continue
        for order, did in enumerate(deck_ids):
            did_int = _coerce_int(did)
            if did_int is None:
                continue
            plan.append({"did": did_int, "iso": iso, "order": order})

    _save_plan(plan)

def _rebuild_plan_with_move(plan: List[PlanEntry], did: int, from_iso: str | None,
                            to_iso: str, new_order: int) -> List[PlanEntry]:
    if not _valid_iso_date(to_iso):
        return list(plan)
    from_iso_valid = from_iso if isinstance(from_iso, str) and _valid_iso_date(from_iso) else None
    try:
        target_index = int(new_order)
    except Exception:
        target_index = 0
    if target_index < 0:
        target_index = 0

    per_iso: Dict[str, List[PlanEntry]] = {}
    for row in plan:
        if not isinstance(row, dict):
            continue
        iso = row.get("iso")
        row_did = _coerce_int(row.get("did"))
        if not isinstance(iso, str) or row_did is None or not _valid_iso_date(iso):
            continue
        if row_did == did and (iso == to_iso or (from_iso_valid and iso == from_iso_valid)):
            # skip existing copy for the moving deck
            continue
        order_hint = row.get("order")
        try:
            order_int = int(order_hint)
        except Exception:
            order_int = 0
        per_iso.setdefault(iso, []).append({"did": row_did, "iso": iso, "order": order_int})

    bucket = per_iso.get(to_iso, [])
    bucket = sorted(bucket, key=lambda r: (r.get("order", 0), r["did"]))
    if target_index > len(bucket):
        target_index = len(bucket)
    bucket.insert(target_index, {"did": did, "iso": to_iso, "order": target_index})
    per_iso[to_iso] = bucket

    rebuilt: List[PlanEntry] = []
    for iso in sorted(per_iso.keys()):
        rows = per_iso[iso]
        rows_sorted = sorted(rows, key=lambda r: (r.get("order", 0), r["did"]))
        for idx, row in enumerate(rows_sorted):
            rebuilt.append({"did": row["did"], "iso": iso, "order": idx})
    return rebuilt

def _rebuild_plan_without_entry(plan: List[PlanEntry], did: int, iso: str) -> List[PlanEntry]:
    if not _valid_iso_date(iso):
        return list(plan)
    rebuilt: List[PlanEntry] = []
    per_iso: Dict[str, List[PlanEntry]] = {}
    for row in plan:
        if not isinstance(row, dict):
            continue
        row_iso = row.get("iso")
        row_did = _coerce_int(row.get("did"))
        if not isinstance(row_iso, str) or row_did is None or not _valid_iso_date(row_iso):
            continue
        if row_did == did and row_iso == iso:
            continue
        order_hint = row.get("order")
        try:
            order_int = int(order_hint)
        except Exception:
            order_int = 0
        per_iso.setdefault(row_iso, []).append({"did": row_did, "iso": row_iso, "order": order_int})

    for iso_key in sorted(per_iso.keys()):
        rows = sorted(per_iso[iso_key], key=lambda r: (r.get("order", 0), r["did"]))
        for idx, row in enumerate(rows):
            rebuilt.append({"did": row["did"], "iso": iso_key, "order": idx})
    return rebuilt

def _study_range(k: int, deck_name: str) -> None:
    """
    Build/refresh a filtered deck using decks planned for the next k days
    (k=1 => today only). Then select it and jump to Review.
    """
    wanted = set(_iso_dates_from_today(k))

    plan = _get_plan()

    # Resolve deck IDs that intersect the window
    deck_ids: set[int] = set()
    for row in plan:
        if not isinstance(row, dict):
            continue
        iso = row.get("iso")
        did = _coerce_int(row.get("did"))
        if did is None or iso not in wanted:
            continue
        deck_ids.add(did)

    if not deck_ids:
        showInfo("No decks scheduled in the selected window.")
        return

    # Resolve names & escape double quotes for search
    col = mw.col
    names: List[str] = []
    for did in deck_ids:
        name = col.decks.name(did)
        if name:
            names.append(name.replace('"', '\\"'))
    if not names:
        showInfo("Scheduled decks were not found.")
        return

    search = "(" + " or ".join(f'deck:"{n}"' for n in names) + ") is:due"

    did = col.decks.id(deck_name)
    d = col.decks.get(did)
    d["dyn"] = True
    col.decks.save(d)
    col.sched.rebuild_filtered_deck(did, search=search, resched=False, limit=999999)

    mw.col.decks.select(did)
    mw.reset()
    try:
        mw.moveToState("review")
    except Exception:
        try:
            mw.moveToState("overview")
        except Exception:
            pass

def _study_today():
    _study_range(1, "Planned Today")

def inject_panel(deck_browser) -> None:
    plan = _refresh_plan_cache()
    decks = [{"id": d["id"], "name": d["name"]}
             for d in mw.col.decks.all() if not d.get("dyn")]

    plan_js = json.dumps(plan)
    decks_js = json.dumps(decks)
    today_js = json.dumps(_iso_today())
    wrap_js = "true" if WRAP_ARROWS else "false"
    script_template = _load_script_template()
    script = (script_template
              .replace("__PLAN_JSON__", plan_js)
              .replace("__DECKS_JSON__", decks_js)
              .replace("__TODAY_ISO__", today_js)
              .replace("__WRAP_ARROWS__", wrap_js))

    deck_browser.web.eval(script)
    _broadcast_plan_to_web(plan)

def on_js_msg(*args):
    """
    Compatible with:
      (handled, msg, context)
      (handled, msg, webview, context)
    Always returns (handled, result).
    """
    if len(args) == 3:
        handled, msg, context = args
        webview = None
    elif len(args) == 4:
        handled, msg, webview, context = args
    else:
        return (False, None)

    try:
        if msg == "wp_today":
            _study_today()
            return (True, None)

        if msg.startswith("wp_open:"):
            try:
                did = int(msg.split(":", 1)[1])
            except Exception:
                return (True, None)
            mw.col.decks.select(did)
            mw.reset()
            try:
                mw.moveToState("review")
            except Exception:
                try:
                    mw.moveToState("overview")
                except Exception:
                    pass
            return (True, None)

        if msg.startswith("wp_move:"):
            try:
                _, did_s, from_iso, to_iso, order_s = msg.split(":", 4)
            except ValueError:
                return (True, None)
            did = _coerce_int(did_s)
            if did is None or not _valid_iso_date(to_iso):
                return (True, None)
            try:
                order_int = int(order_s)
            except Exception:
                order_int = 0
            plan = _get_plan()
            next_plan = _rebuild_plan_with_move(plan, did, from_iso or None, to_iso, order_int)
            _save_plan(next_plan)
            return (True, None)

        if msg.startswith("wp_assign:"):
            try:
                _, did_s, iso = msg.split(":", 2)
            except ValueError:
                return (True, None)
            did = _coerce_int(did_s)
            if did is None or not _valid_iso_date(iso):
                return (True, None)
            plan = _get_plan()
            existing_count = sum(1 for row in plan if isinstance(row, dict) and row.get("iso") == iso)
            next_plan = _rebuild_plan_with_move(plan, did, None, iso, existing_count)
            _save_plan(next_plan)
            return (True, None)

        if msg.startswith("wp_remove:"):
            try:
                _, did_s, iso = msg.split(":", 2)
            except ValueError:
                return (True, None)
            did = _coerce_int(did_s)
            if did is None or not _valid_iso_date(iso):
                return (True, None)
            plan = _get_plan()
            next_plan = _rebuild_plan_without_entry(plan, did, iso)
            _save_plan(next_plan)
            return (True, None)

        # Optional: quick connectivity ping
        if msg == "wp_ping":
            # from aqt.utils import showInfo; showInfo("Week Planner bridge OK")
            return (True, None)

    except Exception:
        return (True, None)

    # Not our message → pass through in the shape Anki expects
    return handled if isinstance(handled, tuple) else (handled, None)

def add_decks_to_today(deck_ids):
    plan = _get_plan()
    today = _iso_today()
    existing = [row for row in plan if isinstance(row, dict) and row.get('iso') == today]
    base_order = len(existing)
    updated = list(plan)
    offset = 0
    for did in deck_ids:
        if any(str(row.get('did')) == str(did) and row.get('iso') == today for row in plan if isinstance(row, dict)):
            continue
        updated.append({"did": int(did), "iso": today, "order": base_order + offset})
        offset += 1
    if offset:
        _save_plan(updated)
        if getattr(mw, 'deckBrowser', None):
            try:
                mw.deckBrowser.refresh()
            except Exception:
                pass
