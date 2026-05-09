"""Minimal 8BitDo Micro controller add-on for Anki."""

from __future__ import annotations

from functools import partial
from os.path import abspath, dirname, join
from typing import Any, Callable, Literal

from anki.decks import DeckId
from aqt import gui_hooks, mw
from aqt.qt import (
    QAction,
    QCoreApplication,
    QDialog,
    QLabel,
    QKeyEvent,
    QPixmap,
    QSize,
    QSizePolicy,
    QTabWidget,
    Qt,
    QVBoxLayout,
    QWidget,
    qconnect,
)
from aqt.theme import theme_manager
from aqt.utils import current_window, tooltip
from aqt.webview import AnkiWebView

assert mw is not None

State = Literal[
    "all", "deckBrowser", "overview", "review", "question",
    "answer", "dialog", "config", "NoFocus",
]

ADDON_PATH = dirname(abspath(__file__))
NO_MOD = Qt.KeyboardModifier.NoModifier

CONTROLLER_SCRIPT = """
let polling, connected_index, indices, ready;
initialise();

function initialise() {
   if (ready) {
      return;
   }
   try {
      bridgeCommand("contanki::initialise");
   } catch (err) {
      setTimeout(initialise, 1000);
      return;
   }
   window.addEventListener("gamepadconnected", on_controller_connect);
   window.addEventListener("gamepaddisconnected", on_controller_disconnect);
   ready = true;
}

function on_controller_connect() {
   let controllers = window.navigator.getGamepads();
   let register = "contanki::register";
   indices = [];
   for (let i = 0; i < controllers.length; i++) {
      let con = controllers[i];
      if (con != null && con.connected) {
         indices.push(i);
         register += `::${con.id}%%%${con.buttons.length}%%%${con.axes.length}`;
      }
   }
   if (indices.length == 0) {
      bridgeCommand("contanki::message::No controllers detected. Please reconnect your controller.");
   } else {
      bridgeCommand(register);
   }
}

function connect_controller(i) {
   window.clearInterval(polling);
   let con = window.navigator.getGamepads()[i];
   if (con == null) {
      bridgeCommand("contanki::message::Could not find controller. Please reconnect your controller.");
      return;
   }
   bridgeCommand(`contanki::on_connect::${con.buttons.length}::${con.axes.length}::${con.id}`);
   connected_index = i;
   setTimeout(() => (polling = setInterval(poll, 50)), 500);
}

function on_controller_disconnect() {
   window.clearInterval(polling);
   connected_index = null;
}

function poll() {
   if (connected_index == null) {
      on_controller_disconnect();
      return;
   }
   let con = window.navigator.getGamepads()[connected_index];
   try {
      if (!con.connected) {
         on_controller_disconnect();
         return;
      }
   } catch (err) {
      on_controller_disconnect();
      return;
   }
   bridgeCommand(`contanki::poll::${con.buttons.map((button) => button.pressed)}::${con.axes}`);
}
"""

BINDINGS: dict[tuple[State, int], str] = {
    ("deckBrowser", 0): "Previous Due Deck",
    ("deckBrowser", 1): "Select",
    ("deckBrowser", 3): "Sync",
    ("deckBrowser", 4): "Next Due Deck",
    ("overview", 0): "Select",
    ("overview", 1): "Select",
    ("overview", 3): "Go to Review",
    ("overview", 4): "Rebuild",
    ("review", 0): "Enter",
    ("review", 1): "Enter",
    ("review", 3): "Undo",
    ("question", 0): "Go to Main Screen",
    ("question", 1): "Flip Card",
    ("question", 3): "Undo",
    ("answer", 0): "Go to Main Screen",
    ("answer", 1): "Good",
    ("answer", 3): "Undo",
    ("answer", 4): "Again",
    ("answer", 100): "Scroll Down Smooth",
    ("answer", 101): "Scroll Up Smooth",
    ("dialog", 0): "Select",
    ("dialog", 1): "Select",
    ("dialog", 3): "Escape",
    ("NoFocus", 0): "Focus Main Window",
}


def get_state() -> State:
    if (focus := current_window()) is None:
        return "NoFocus"
    name = focus.objectName()
    if name == "MainWindow":
        return mw.reviewer.state if mw.state == "review" else mw.state  # type: ignore
    if name == "Preferences":
        return "dialog"
    if name == "Contanki Options":
        return "config"
    return "NoFocus"


def action_for(state: State, button: int) -> str:
    fallbacks = (state, "review", "all") if state in ("question", "answer") else (state, "all")
    for key in fallbacks:
        if action := BINDINGS.get((key, button)):
            return action
    return ""


def key_press(key: Qt.Key, mod=NO_MOD) -> None:
    for evt_type in (QKeyEvent.Type.KeyPress, QKeyEvent.Type.KeyRelease):
        QCoreApplication.sendEvent(mw.app.focusObject(), QKeyEvent(evt_type, key, mod))


def select() -> None:
    mw.web.eval("document.activeElement.click()")


def on_enter() -> None:
    if mw.state in ("deckBrowser", "overview"):
        select()
    elif mw.state == "review":
        mw.reviewer.onEnterKey()
    else:
        key_press(Qt.Key.Key_Enter)


def undo() -> None:
    if mw.undo_actions_info().can_undo:
        mw.undo()
    else:
        tooltip("Nothing to undo")


def show_answer_or_good() -> None:
    state = getattr(mw.reviewer, "state", None)
    if state == "question":
        mw.reviewer.onEnterKey()
    elif state == "answer":
        mw.reviewer._answerCard(3)  # pylint: disable=protected-access


def focus_main_window() -> None:
    mw.activateWindow()
    mw.raise_()
    mw.setFocus()


def deck_rows() -> tuple[list[DeckId], list[bool]]:
    def walk(node):
        yield node.deck_id, bool(node.review_count or node.learn_count or node.new_count)
        if node.children and not node.collapsed:
            for child in node.children:
                yield from walk(child)

    col = mw.col
    if col is None or (tree := col.sched.deck_due_tree()) is None:
        return [], []
    rows = [pair for child in tree.children for pair in walk(child)]
    if not rows:
        return [], []
    decks, dues = zip(*rows)
    return list(decks), list(dues)


def choose_deck(direction: bool) -> None:
    step = 1 if direction else -1

    def choose(current_deck: DeckId | str) -> None:
        decks, dues = deck_rows()
        if not decks or not any(dues):
            return
        current = DeckId(int(current_deck)) if current_deck else None
        index = decks.index(current) if current in decks else (-1 if direction else 0)
        index = (index + step) % len(decks)
        while not dues[index]:
            index = (index + step) % len(decks)
        if mw.state == "deckBrowser":
            mw.web.eval(
                f"document.getElementById({decks[index]}).getElementsByClassName('deck')[0].focus()"
            )
        elif mw.col is not None:
            mw.col.decks.select(decks[index])
            mw.moveToState("overview")

    mw.web.setFocus()
    if mw.state == "deckBrowser":
        mw.web.evalWithCallback(
            "document.activeElement.parentElement.parentElement.id", choose
        )
    elif mw.col is not None:
        choose(mw.col.decks.get_current_id())


def rebuild() -> None:
    if mw.col is None or not mw.col.decks.is_filtered(mw.col.decks.get_current_id()):
        tooltip("This action can only be done on filtered decks")
        return
    mw.overview.rebuild_current_filtered_deck()


BUTTON_ACTIONS: dict[str, Callable[[], Any]] = {
    "": lambda: None,
    "Again": partial(mw.reviewer._answerCard, 1),  # pylint: disable=protected-access
    "Enter": on_enter,
    "Escape": partial(key_press, Qt.Key.Key_Escape),
    "Flip Card": mw.reviewer.onEnterKey,
    "Focus Main Window": focus_main_window,
    "Go to Main Screen": partial(mw.moveToState, "deckBrowser"),
    "Go to Review": partial(mw.moveToState, "review"),
    "Good": partial(mw.reviewer._answerCard, 3),  # pylint: disable=protected-access
    "Next Due Deck": partial(choose_deck, True),
    "Previous Due Deck": partial(choose_deck, False),
    "Rebuild": rebuild,
    "Select": select,
    "Show Answer/Answer Good": show_answer_or_good,
    "Sync": mw.onSync,
    "Undo": undo,
}


class ContankiConfig(QDialog):
    def __init__(self, parent: QWidget, contanki) -> None:
        super().__init__(parent)
        self.contanki = contanki
        self.contanki.config_window = self
        self.setWindowTitle("Controller Layout")
        self.setObjectName("Contanki Options")

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0px; }")
        self.tabs.setTabPosition(QTabWidget.TabPosition.South)
        if theme_manager.night_mode:
            image_tabs = (
                ("dark mode review .png", "Dark Mode Reviewing"),
                ("dark mode home.png", "Dark Mode Home"),
            )
        else:
            image_tabs = (
                ("Light Mode Reviewing.png", "Light Mode Reviewing"),
                ("Light Mode Home.png", "Light Mode Home"),
            )
        for image_name, label in image_tabs:
            self.tabs.addTab(ImageTab(image_name), label)
        layout.addWidget(self.tabs)

        self.setMinimumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.resize(self.sizeHint())
        self.show()

    def closeEvent(self, event) -> None:  # noqa: D401
        if getattr(self.contanki, "config_window", None) is self:
            self.contanki.config_window = None
        super().closeEvent(event)


class ImageTab(QWidget):
    def __init__(self, image_name: str) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.pixmap = QPixmap(join(ADDON_PATH, "Image", image_name))
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(520, round(520 * self.pixmap.height() / self.pixmap.width()))
        self.update_image()

    def sizeHint(self) -> QSize:  # noqa: D401
        return QSize(717, round(717 * self.pixmap.height() / self.pixmap.width()))

    def resizeEvent(self, event) -> None:  # noqa: D401
        self.update_image()
        super().resizeEvent(event)

    def update_image(self) -> None:
        ratio = max(1.0, self.devicePixelRatioF())
        size = lambda w, h: QSize(max(1, round(w)), max(1, round(h)))  # noqa: E731
        source = size(self.pixmap.width() / ratio, self.pixmap.height() / ratio)
        target = (
            source.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            if self.width() < source.width() or self.height() < source.height()
            else source
        )
        scaled = self.pixmap.scaled(
            size(target.width() * ratio, target.height() * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(ratio)
        self.label.setPixmap(scaled)
        self.label.setGeometry(
            (self.width() - target.width()) // 2,
            (self.height() - target.height()) // 2,
            target.width(),
            target.height(),
        )


class Contanki(AnkiWebView):
    def __init__(self, parent) -> None:
        super().__init__(parent=parent)
        self.connected = False
        self.config_window = None
        self.buttons: list[bool] = []
        self.axes: list[bool] = []
        self.len_buttons = 0
        self.len_axes = 0
        self.scroll_up = False
        self.scroll_down = False

        mw.addonManager.setConfigAction(__name__, self.on_config)
        self.menu_item = QAction("Controller Layout", mw)
        qconnect(self.menu_item.triggered, self.on_config)
        gui_hooks.webview_did_receive_js_message.append(self.on_receive_message)
        gui_hooks.profile_will_close.append(lambda: self.stdHtml(""))
        gui_hooks.profile_did_open.append(self.resume)
        self.resume()
        self.setFixedSize(0, 0)

    @staticmethod
    def _is_micro(controller_id: str) -> bool:
        cid = controller_id.lower()
        return "8bitdo" in cid and "micro" in cid

    def resume(self) -> None:
        self.stdHtml(f"""<script type="text/javascript">\n{CONTROLLER_SCRIPT}\n</script>""")

    def on_config(self) -> None:
        if focus := current_window():
            ContankiConfig(focus, self)

    def on_receive_message(
        self, handled: tuple[bool, Any], message: str, _
    ) -> tuple[bool, Any]:
        if not message.startswith("contanki"):
            return handled
        parts = message.split("::")
        if len(parts) < 2:
            return (True, None)
        _, func, *args = parts
        handlers: dict[str, Callable[..., Any]] = {
            "message": lambda *a: tooltip("::".join(a)),
            "register": self.register_controllers,
            "on_connect": self.on_connect,
            "poll": self.poll,
            "on_disconnect": lambda *a: self.reset_controller(),
        }
        if handler := handlers.get(func):
            handler(*args)
        return (True, None)

    def poll(self, input_buttons: str, input_axes: str) -> None:
        if not self.connected:
            return
        state = get_state()
        if state in ("NoFocus", "config"):
            return

        buttons = [b == "true" for b in input_buttons.split(",") if b]
        axes = [float(a) for a in input_axes.split(",") if a]
        buttons += [False] * (self.len_buttons - len(buttons))
        axes += [0.0] * (self.len_axes - len(axes))
        self.buttons += [False] * (len(buttons) - len(self.buttons))
        self.axes += [False] * (len(axes) - len(self.axes))

        changed = [(i, v) for i, v in enumerate(buttons) if v != self.buttons[i]]
        self.buttons = buttons
        for index, value in changed:
            self.do_action(state, index, release=not value)
        if any(axes) or any(self.axes):
            self.do_axes_actions(state, axes)

    def do_action(self, state: State, button: int, release: bool = False) -> None:
        action = action_for(state, button)
        if action in ("Scroll Up Smooth", "Scroll Down Smooth"):
            self.smooth_scroll(action == "Scroll Up Smooth", not release)
            return
        if release:
            return
        try:
            BUTTON_ACTIONS.get(action, BUTTON_ACTIONS[""])()
        except Exception as err:  # pylint: disable=broad-except
            tooltip("Error: " + repr(err))

    def do_axes_actions(self, state: State, axes: list[float]) -> None:
        for axis, value in enumerate(axes[:2]):
            pressed = abs(value) > 0.5
            if pressed and not self.axes[axis]:
                self.do_action(state, axis * 2 + int(value > 0) + 100)
            elif not pressed and self.axes[axis]:
                self.do_action(state, axis * 2 + 100, release=True)
                self.do_action(state, axis * 2 + 101, release=True)
            self.axes[axis] = pressed

    def on_connect(self, buttons: str | int, axes: str | int, *controller_parts: str) -> None:
        if not self._is_micro("::".join(controller_parts)):
            return
        self.reset_controller()
        self.len_buttons = max(int(buttons), 20)
        self.len_axes = max(int(axes), 2)
        self.buttons = [False] * self.len_buttons
        self.axes = [False] * self.len_axes
        self.connected = True
        mw.form.menuTools.addAction(self.menu_item)
        tooltip("8BitDo Micro Connected")

    def reset_controller(self) -> None:
        try:
            mw.form.menuTools.removeAction(self.menu_item)
        except RuntimeError:
            pass
        self.buttons = []
        self.axes = []
        self.connected = False

    def register_controllers(self, *controllers: str) -> None:
        for index, controller in enumerate(controllers):
            if self._is_micro(controller.split("%%%")[0]):
                self._evalWithCallback(f"connect_controller(indices[{index}]);", None)  # type: ignore
                return

    def smooth_scroll(self, up: bool, active: bool) -> None:
        self.scroll_up, self.scroll_down = (active, False) if up else (False, active)
        velocity = -18 if self.scroll_up else 18 if self.scroll_down else 0
        mw.web.eval(
            f"""
            (() => {{
                const targetVelocity = {velocity};
                if (window.__contankiSmoothScrollTargetVelocity !== targetVelocity) {{
                    window.__contankiSmoothScrollCurrentVelocity = 0;
                }}
                window.__contankiSmoothScrollTargetVelocity = targetVelocity;
                if (window.__contankiSmoothScrollFrame) {{
                    return;
                }}
                const step = () => {{
                    const target = window.__contankiSmoothScrollTargetVelocity || 0;
                    let current = window.__contankiSmoothScrollCurrentVelocity || 0;
                    if (!target) {{
                        window.__contankiSmoothScrollFrame = null;
                        window.__contankiSmoothScrollCurrentVelocity = 0;
                        return;
                    }}
                    current += (target - current) * 0.18;
                    if (Math.abs(target - current) < 0.2) {{
                        current = target;
                    }}
                    window.__contankiSmoothScrollCurrentVelocity = current;
                    window.scrollBy(0, current);
                    window.__contankiSmoothScrollFrame = window.requestAnimationFrame(step);
                }};
                window.__contankiSmoothScrollFrame = window.requestAnimationFrame(step);
            }})();
            """
        )


mw.contanki = Contanki(mw)  # type: ignore[attr-defined]