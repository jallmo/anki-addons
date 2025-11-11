# config.py Manages loading, saving, and default values for the add-on’s configuration.
from typing import Dict, List, Any
from aqt import mw  # type: ignore

# Default structure for new installs
DEFAULTS: Dict[str, Any] = {
    "plan": [],               # list of {"did": int, "iso": str, "order": int}
    "include_children": True, # placeholder for future options
    "wrap_arrows": False      # allow wrap-around navigation buttons
}


def get_config() -> Dict[str, Any]:
    """Load add-on config and merge with defaults."""
    # getConfig takes the add-on name without the .config suffix
    base_name = __name__.rsplit(".", 1)[0]
    cfg = mw.addonManager.getConfig(base_name) or {}
    for k, v in DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    """Persist configuration changes to disk."""
    base_name = __name__.rsplit(".", 1)[0]
    mw.addonManager.writeConfig(base_name, cfg)
