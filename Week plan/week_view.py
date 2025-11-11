# week_view.py , Builds the main week planner UI (lists, columns, and interaction logic).
from __future__ import annotations
import datetime
from typing import Dict, List, Tuple

from aqt import mw  # type: ignore
from aqt.qt import (  # type: ignore
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QLabel,
    QLineEdit,
    Qt,
    QFrame,
    QPushButton,
)
from aqt.utils import showInfo # < add this
from .deck_panel import current_plan_snapshot, replace_plan_with_week_labels

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MIME = "application/x-weekplanner-deck"  # custom drag payload key
def _all_decks() -> List[Tuple[int, str]]:
    """Return [(id, name)] for all regular decks."""
    col = mw.col
    try:
        items = col.decks.all_names_and_ids()  # recent Anki
        return [(did, name) for name, did in items]
    except Exception:
        # Fallback
        decks = col.decks.all()
        return [(d["id"], d["name"]) for d in decks if not d.get("dyn")]


def _deck_name(did: int) -> str:
    try:
        return mw.col.decks.name(did)
    except Exception:
        return ""


class DeckList(QListWidget):
    """Source list of decks with search."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.refresh()

    def refresh(self, query: str = "") -> None:
        self.clear()
        for did, name in _all_decks():
            if query and query.lower() not in name.lower():
                continue
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, did)
            self.addItem(it)

    # provide custom mime with deck id
    def mimeData(self, items):
        md = super().mimeData(items)
        if items:
            did = items[0].data(Qt.ItemDataRole.UserRole)
            if did is not None:
                md.setData(MIME, str(did).encode("utf-8"))
        return md


class DayColumn(QListWidget):
    """Droppable day column that stores deck ids."""

    def __init__(self, day: str, parent=None):
        super().__init__(parent)
        self.day = day
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # header
        header = QListWidgetItem(day)
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        self.addItem(header)

    def current_ids(self) -> List[int]:
        ids: List[int] = []
        for i in range(1, self.count()):
            did = self.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(did, int):
                ids.append(did)
        return ids

    def _add_deck(self, did: int) -> None:
        # prevent duplicates
        if did in self.current_ids():
            return
        name = _deck_name(did)
        if not name:
            return
        it = QListWidgetItem(name)
        it.setData(Qt.ItemDataRole.UserRole, did)
        self.addItem(it)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME) or e.source() is not None:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        self.dragEnterEvent(e)

    def dropEvent(self, e):
        did = None
        if e.mimeData().hasFormat(MIME):
            try:
                did = int(bytes(e.mimeData().data(MIME)).decode("utf-8"))
            except Exception:
                did = None
        else:
            # drag from another DayColumn: read selected item's UserRole
            src = e.source()
            if isinstance(src, QListWidget) and src is not self:
                item = src.currentItem()
                if item:
                    did = item.data(Qt.ItemDataRole.UserRole)
                    # remove from source if it was a real deck item
                    if isinstance(did, int):
                        row = src.row(item)
                        if row > 0:
                            src.takeItem(row)
        if isinstance(did, int):
            self._add_deck(did)
            persist_plan()
            e.acceptProposedAction()
        else:
            e.ignore()

class WeekBoard(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Week Planner")
        root = QHBoxLayout(self)

        # left: deck library with search
        left = QVBoxLayout()
        left.addWidget(QLabel("Decks"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search decks…")
        self.search.textChanged.connect(self._on_search)
        left.addWidget(self.search)
        self.deck_list = DeckList()
        left.addWidget(self.deck_list)
        root.addLayout(left, 1)

        # right: week columns
        self.columns: Dict[str, DayColumn] = {}
        right = QHBoxLayout()
        for d in DAYS:
            col = DayColumn(d)
            right.addWidget(col)
            self.columns[d] = col
        root.addLayout(right, 3)

        # add simple "Add Deck" button
        self.add_btn = QPushButton("Add Deck")
        self.add_btn.clicked.connect(self.add_deck_to_monday)
        left.addWidget(self.add_btn)

        self._load_from_cfg()

    def add_deck_to_monday(self):
        """Add first available deck under Monday column."""
        from aqt import mw
        decks = mw.col.decks.all_names_and_ids()
        if not decks:
            showInfo("No decks found")
            return
        name, did = decks[0]
        item = QListWidgetItem(name)
        self.columns["Mon"].addItem(item)
        persist_plan()

    def _on_search(self, text: str) -> None:
        self.deck_list.refresh(text)

    def _load_from_cfg(self) -> None:
        plan = current_plan_snapshot()
        for day in DAYS:
            self.columns[day].clear()
            self.columns[day].addItem(self._header(day))
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
                    day = DAYS[idx]
                    order_hint = 0
                    try:
                        order_hint = int(row.get("order", 0))
                    except Exception:
                        order_hint = 0
                    per_day.setdefault(day, []).append((order_hint, did_int))
            for day, bucket in per_day.items():
                col = self.columns.get(day)
                if not col:
                    continue
                for _, did in sorted(bucket, key=lambda r: (r[0], r[1])):
                    col._add_deck(did)
        elif isinstance(plan, dict):
            for did_str, entry in plan.items():
                try:
                    did = int(did_str)
                except Exception:
                    continue
                if isinstance(entry, dict):
                    dates = entry.get("dates", {})
                    for iso in dates:
                        try:
                            dt = datetime.date.fromisoformat(iso)
                        except Exception:
                            continue
                        idx = dt.weekday()
                        if 0 <= idx < len(DAYS):
                            day = DAYS[idx]
                            if day in self.columns:
                                self.columns[day]._add_deck(did)
                elif isinstance(entry, list):
                    for day in entry:
                        if day in self.columns:
                            self.columns[day]._add_deck(did)

    @staticmethod
    def _header(day: str) -> QListWidgetItem:
        it = QListWidgetItem(day)
        it.setFlags(Qt.ItemFlag.NoItemFlags)
        return it

    # Remove selected deck with Delete key
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete:
            for day, col in self.columns.items():
                it = col.currentItem()
                if it and col.row(it) > 0:
                    col.takeItem(col.row(it))
                    persist_plan()
                    return
        super().keyPressEvent(e)

def persist_plan() -> None:
    """Serialize UI → config and save."""
    w = mw.app.focusWidget()
    while w and not isinstance(w, WeekBoard):
        w = w.parent()
    if not isinstance(w, WeekBoard):
        return
    day_map: Dict[str, List[int]] = {}
    for day, col in w.columns.items():
        deck_ids: List[int] = []
        for i in range(1, col.count()):
            did = col.item(i).data(Qt.ItemDataRole.UserRole)
            if isinstance(did, int):
                deck_ids.append(did)
        if deck_ids:
            day_map[day] = deck_ids
    replace_plan_with_week_labels(day_map)
