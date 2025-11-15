from . import changeFunction

from aqt import gui_hooks, mw

def skip_overview(handled, message, context):
    # if another handler used it, respect that
    if handled and handled[0]:
        return handled

    # intercept “open:<did>”
    if isinstance(message, str) and message.startswith("open:") and message.count(":") == 1:
        try:
            did = int(message.split(":")[1])
        except ValueError:
            return handled

        if did > 0:
            mw.col.decks.select(did)
            mw.moveToState("review")
            return (True, None)

    return handled

gui_hooks.webview_did_receive_js_message.append(skip_overview)