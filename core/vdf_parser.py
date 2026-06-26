"""
Thin wrapper around the vdf library for binary shortcuts.vdf read/write.
All higher-level shortcut manipulation goes here so the rest of the app
never touches vdf directly.
"""

import vdf


def load_shortcuts(path: str) -> dict:
    """Read a binary shortcuts.vdf and return the parsed dict."""
    with open(path, "rb") as f:
        return vdf.binary_load(f)


def save_shortcuts(path: str, data: dict) -> None:
    """Write a shortcuts dict back to a binary shortcuts.vdf."""
    with open(path, "wb") as f:
        vdf.binary_dump(data, f)


def get_shortcut_list(data: dict) -> list[dict]:
    """Return the shortcuts as a plain list, normalised from the keyed dict."""
    return list(data.get("shortcuts", {}).values())


def get_value_case_insensitive(shortcut_dict: dict, target_key: str, default=""):
    """
    Searches for a key in the shortcut dictionary regardless of its casing.
    (e.g. will find 'appname' even if it is stored as 'AppName')
    """
    for key, value in shortcut_dict.items():
        if key.lower() == target_key.lower():
            return value
    return default

def normalize_appid(appid) -> str:
    """Converts signed 32-bit integers to unsigned strings (e.g. -826632865 -> 3468334431)"""
    if isinstance(appid, str):
        try:
            appid = int(appid)
        except ValueError:
            return appid
    # Use bitmask to convert to unsigned 32-bit
    return str(appid & 0xffffffff)