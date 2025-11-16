from __future__ import annotations

from copy import deepcopy
from typing import Dict, Mapping

from aqt import mw

DEFAULT_CONFIG = {
    "centered_width": "85vw",
}

_cached_config: Dict | None = None


def _load_config() -> Dict:
    stored = mw.addonManager.getConfig(__name__) or {}
    if not isinstance(stored, dict):
        stored = {}
    cfg = deepcopy(DEFAULT_CONFIG)
    # only keep keys we know
    for key in DEFAULT_CONFIG:
        if key in stored and stored[key] is not None:
            cfg[key] = stored[key]
    # write back the sanitized config so Anki's editor shows only the supported keys
    mw.addonManager.writeConfig(__name__, cfg)
    return cfg


def get_config() -> Dict:
    global _cached_config
    if _cached_config is None:
        _cached_config = _load_config()
    return deepcopy(_cached_config)


def refresh_config(*_args) -> None:
    global _cached_config
    _cached_config = None


mw.addonManager.setConfigUpdatedAction(__name__, refresh_config)


def layout_vars(cfg: Mapping | None = None) -> Dict[str, str]:
    cfg = cfg or get_config()
    return {
        "--smw-centered-width": cfg.get("centered_width", DEFAULT_CONFIG["centered_width"]),
    }
