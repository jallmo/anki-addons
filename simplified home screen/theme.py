from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence
from aqt import mw
from aqt.deckbrowser import DeckBrowser

from .htmlAndCss import (
    collapse_children_html,
    collapse_no_child,
    css,
    build_theme_overrides,
    deck_name,
    end_line,
    gear,
    js,
    number_cell,
    start_line,
)


@dataclass
class SimpleNode:
    name: str
    did: int
    review: int
    learn: int
    new: int
    children: Sequence

    @classmethod
    def from_raw(cls, node) -> "SimpleNode":
        """Support both tuple nodes (old Anki) and DeckTreeNode objects."""
        try:
            name, did, review, learn, new, children = node
        except Exception:
            name = getattr(node, "name")
            did = getattr(node, "deck_id")
            review = getattr(node, "review_count", 0)
            learn = getattr(node, "learn_count", 0)
            new = getattr(node, "new_count", 0)
            children = getattr(node, "children", []) or []
        return cls(
            name=name,
            did=did,
            review=review or 0,
            learn=learn or 0,
            new=new or 0,
            children=children or [],
        )

    @property
    def deck_dict(self):
        return mw.col.decks.get(self.did)

    @property
    def collapsed(self) -> bool:
        deck = self.deck_dict or {}
        return bool(deck.get("collapsed"))

    @property
    def is_filtered(self) -> bool:
        deck = self.deck_dict or {}
        return bool(deck.get("dyn"))


def install_theme() -> None:
    """Monkey-patch the deck browser rendering with the simplified theme."""
    DeckBrowser._renderDeckTree = _render_deck_tree  # type: ignore[assignment]
    DeckBrowser._deckRow = _deck_row  # type: ignore[assignment]


def _render_deck_tree(self: DeckBrowser, nodes: Iterable, depth: int = 0) -> str:
    if not nodes:
        return ""

    try:
        nodes = list(nodes)
    except TypeError:
        nodes = list(getattr(nodes, "children", []))

    if not nodes:
        return ""

    buf: List[str] = []
    if depth == 0:
        layout_css, config_js = build_theme_overrides()
        buf.append(f"<script>{config_js}</script>")
        buf.append(f"<style>{css}</style>")
        buf.append(f"<style>{layout_css}</style>")
        buf.append(f"<script>{js}</script>")
        buf.append(self._topLevelDragRow())

    for node in nodes:
        buf.append(self._deckRow(node, depth, len(nodes)))

    if depth == 0:
        buf.append(self._topLevelDragRow())

    return "".join(buf)


def _deck_row(self: DeckBrowser, node, depth: int, cnt: int) -> str:
    simple = SimpleNode.from_raw(node)
    css_class = _row_classes(simple)
    collapse = _collapse_html(simple)
    extra_class = " filtered" if simple.is_filtered else ""
    deck_name_html = deck_name(depth, collapse, extra_class, simple.did, "", simple.name)
    counts_html = _counts_html(simple)
    gear_html = gear(simple.did)

    card_html = f"""
    <td class = decktd>
      <div class = ios-row>
        <div class = "ios-row-card apple-glass" data-did = "{simple.did}">
          {deck_name_html}
          <div class = ios-row-right>
            {counts_html}
            {gear_html}
          </div>
        </div>
      </div>
    </td>"""

    children_html = ""
    if simple.children and not simple.collapsed:
        children_html = self._renderDeckTree(simple.children, depth + 1)

    return start_line(css_class, simple.did) + card_html + end_line + children_html


def _row_classes(node: SimpleNode) -> str:
    classes = ["deck"]
    if node.did == mw.col.get_config("curDeck"):
        classes.append("current")
    return " ".join(classes)


def _collapse_html(node: SimpleNode) -> str:
    if node.children:
        prefix = "+" if node.collapsed else "-"
        return collapse_children_html(node.did, node.name, prefix)
    return collapse_no_child


def _counts_html(node: SimpleNode) -> str:
    due_html = number_cell("var(--smw-due-color)", node.review, "", "DUE")
    new_html = number_cell("var(--smw-new-color)", node.new, "", "NEW")
    return due_html + new_html
