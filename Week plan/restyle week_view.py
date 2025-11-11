# restyle week_view.py , Provides a visually improved and simplified version of the week planner interface.
from __future__ import annotations
import datetime
from typing import Dict, List, Tuple
from aqt import mw  # type: ignore
from aqt.qt import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
                    QAbstractItemView, QLabel, QLineEdit, Qt, QFrame, QSizePolicy, QPushButton)
from aqt.utils import showInfo
from .deck_panel import current_plan_snapshot, replace_plan_with_week_labels

DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
MIME = "application/x-weekplanner-deck"

# ---- minimal app-wide style (Tweek-like) ----
BASE_CSS = """
QWidget { background: #fafafa; }
QFrame.column { background: transparent; }
QLabel.day { font-weight: 600; color: #111; letter-spacing: .2px; padding: 6px 2px; }
QListWidget {
  background: #fff; border: 1px solid #e6e6e6; border-radius: 12px;
  padding: 4px; outline: 0;
}
QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #f2f2f2; }
QListWidget::item:selected { background: #e9f0ff; color: #111; }
"""

def _all_decks() -> List[Tuple[int,str]]:
    try:
        items = mw.col.decks.all_names_and_ids()
        return [(did, name) for name, did in items]
    except Exception:
        decks = mw.col.decks.all()
        return [(d["id"], d["name"]) for d in decks if not d.get("dyn")]

def _deck_name(did: int) -> str:
    try: return mw.col.decks.name(did)
    except Exception: return ""

class DeckList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDragEnabled(True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.refresh()

    def refresh(self, q: str = ""):
        self.clear()
        for did, name in _all_decks():
            if q and q.lower() not in name.lower(): continue
            it = QListWidgetItem(name); it.setData(Qt.ItemDataRole.UserRole, did)
            self.addItem(it)

    def mimeData(self, items):
        md = super().mimeData(items)
        if items:
            did = items[0].data(Qt.ItemDataRole.UserRole)
            if did is not None: md.setData(MIME, str(did).encode())
        return md

class DayColumn(QFrame):
    def __init__(self, day: str):
        super().__init__()
        self.setObjectName("column")
        lay = QVBoxLayout(self); lay.setContentsMargins(8,0,8,0); lay.setSpacing(6)
        h = QLabel(day); h.setObjectName("day"); h.setAlignment(Qt.AlignmentFlag.AlignLeft)
        h.setProperty("class", "day")  # for stylesheet
        self.list = QListWidget()
        self.list.setAcceptDrops(True)
        self.list.setDragEnabled(True)
        self.list.setDragDropMode(QAbstractItemView.DragDrop)
        self.list.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.list.setUniformItemSizes(True)
        lay.addWidget(h); lay.addWidget(self.list)
        self.day = day
        # enable row delete via keyboard (handled in WeekBoard.keyPressEvent)

    def add_deck(self, did: int):
        # no duplicates
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == did: return
        name = _deck_name(did); 
        if not name: return
        it = QListWidgetItem(name); it.setData(Qt.ItemDataRole.UserRole, did)
        self.list.addItem(it)

    def deck_ids(self) -> List[int]:
        ids = []
        for i in range(self.list.count()):
            did = self.list.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(did, int): ids.append(did)
        return ids

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME) or isinstance(e.source(), QListWidget):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        did = None
        if e.mimeData().hasFormat(MIME):
            try: did = int(bytes(e.mimeData().data(MIME)).decode())
            except Exception: did = None
        else:
            src = e.source()
            if isinstance(src, QListWidget):
                it = src.currentItem()
                if it:
                    did = it.data(Qt.ItemDataRole.UserRole)
                    # moving across days: remove from source
                    if isinstance(did, int) and src is not self.list:
                        src.takeItem(src.row(it))
        if isinstance(did, int):
            self.add_deck(did); persist_plan(self.parent())
            e.acceptProposedAction()
        else:
            e.ignore()

class WeekBoard(QWidget):
    """7 columns. No dates."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Week Planner")
        self.setStyleSheet(BASE_CSS)
        root = QHBoxLayout(self); root.setContentsMargins(16,16,16,16); root.setSpacing(12)

        # Optional left library (hide if you only want columns)
        left = QVBoxLayout(); left.setSpacing(6)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search decks")
        self.search.textChanged.connect(lambda t: self.deck_list.refresh(t))
        self.deck_list = DeckList()
        left.addWidget(self.search); left.addWidget(self.deck_list)
        # comment next line to hide the library
        root.addLayout(left, 1)

        # Week columns
        self.columns: Dict[str, DayColumn] = {}
        for d in DAYS:
            col = DayColumn(d)
            col.setMinimumWidth(180)
            root.addWidget(col, 1)
            self.columns[d] = col

        # Add horizontal layout with "Add Deck" buttons above each weekday column
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)
        buttons_layout.setContentsMargins(16, 0, 16, 0)
        for day in DAYS:
            btn = QPushButton("Add Deck")
            btn.setMinimumWidth(180)
            btn.clicked.connect(lambda checked, d=day: self.add_deck_to_day(d))
            buttons_layout.addWidget(btn)
        root.insertLayout(root.count() - len(DAYS), buttons_layout)

        self._load_from_cfg()

    def _load_from_cfg(self):
        plan = current_plan_snapshot()
        for col in self.columns.values():
            col.list.clear()
        if isinstance(plan, list):
            per_day: Dict[str, List[Tuple[int, int]]] = {}
            for row in plan:
                if not isinstance(row, dict):
                    continue
                iso = row.get("iso")
                did = row.get("did")
                try:
                    did_int = int(did)
                except Exception:
                    continue
                if not isinstance(iso, str):
                    continue
                try:
                    dt = datetime.date.fromisoformat(iso)
                except Exception:
                    continue
                idx = dt.weekday()
                if 0 <= idx < len(DAYS):
                    order_hint = 0
                    try:
                        order_hint = int(row.get("order", 0))
                    except Exception:
                        order_hint = 0
                    per_day.setdefault(DAYS[idx], []).append((order_hint, did_int))
            for day, bucket in per_day.items():
                col = self.columns.get(day)
                if not col:
                    continue
                for _, did in sorted(bucket, key=lambda r: (r[0], r[1])):
                    col.add_deck(did)
        elif isinstance(plan, dict):
            for did_s, days in plan.items():
                try:
                    did = int(did_s)
                except Exception:
                    continue
                if isinstance(days, dict):
                    for iso in days.get("dates", {}):
                        try:
                            dt = datetime.date.fromisoformat(iso)
                        except Exception:
                            continue
                        idx = dt.weekday()
                        if 0 <= idx < len(DAYS):
                            day = DAYS[idx]
                            if day in self.columns:
                                self.columns[day].add_deck(did)
                elif isinstance(days, list):
                    for day in days:
                        if day in self.columns:
                            self.columns[day].add_deck(did)

    def add_deck_to_day(self, day: str):
        decks = _all_decks()
        if not decks:
            showInfo("No decks found")
            return
        did, name = decks[0]
        col = self.columns.get(day)
        if col:
            col.add_deck(did)
            persist_plan(self)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete:
            # remove focused deck from a day
            for col in self.columns.values():
                it = col.list.currentItem()
                if it:
                    col.list.takeItem(col.list.row(it))
                    persist_plan(self); return
        super().keyPressEvent(e)

def persist_plan(board: WeekBoard | None):
    """Serialize UI → config and save."""
    if board is None:
        return
    day_map: Dict[str, List[int]] = {}
    for day, col in board.columns.items():
        ids: List[int] = []
        for i in range(col.list.count()):
            did = col.list.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(did, int):
                ids.append(did)
        if ids:
            day_map[day] = ids
    replace_plan_with_week_labels(day_map)
