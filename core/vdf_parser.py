"""
Thin wrapper around the vdf library for binary shortcuts.vdf read/write.
All higher-level shortcut manipulation goes here so the rest of the app
never touches vdf directly.
"""

import vdf
import zlib
import os


def load_shortcuts(path: str) -> dict:
    """Read a binary shortcuts.vdf and return the parsed dict."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {"shortcuts": {}}
    try:
        with open(path, "rb") as f:
            return vdf.binary_load(f)
    except Exception:
        # If the file is corrupted, return an empty structure to prevent crashes
        return {"shortcuts": {}}


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
    """
    for key, value in shortcut_dict.items():
        if key.lower() == target_key.lower():
            return value
    return default


def normalize_appid(appid) -> str:
    """Converts AppIDs (int or str) to unsigned strings (e.g. 3468334431)"""
    if appid is None:
        return "0"
    try:
        # Convert to int, then use bitmask to ensure it's a positive 32-bit value
        val = int(appid)
        return str(val & 0xFFFFFFFF)
    except (ValueError, TypeError):
        return str(appid)


def add_new_shortcut(vdf_path, game_name, exe_path, icon_path=""):
    """
    Parses current VDF, appends a new entry, and saves it.
    """
    try:
        data = load_shortcuts(vdf_path)
        if "shortcuts" not in data:
            data["shortcuts"] = {}

        start_dir = os.path.dirname(exe_path)
        unique_name = (exe_path + game_name).encode("utf-8")

        # Generate the ID exactly as the reference script does
        unsigned_appid = zlib.crc32(unique_name) | 0x80000000

        # We store the appid as a STRING.
        # This prevents "i format" and "unpack" errors in the vdf library.
        str_appid = str(unsigned_appid & 0xFFFFFFFF)

        new_entry = {
            "appid": str_appid,
            "AppName": game_name,
            "Exe": f'"{exe_path}"',
            "StartDir": f'"{start_dir}\\"',
            "icon": f'"{os.path.normpath(icon_path)}"' if icon_path else "",
            "ShortcutPath": "",
            "LaunchOptions": "",
            "IsHidden": 0,
            "AllowDesktopConfig": 1,
            "AllowOverlay": 1,
            "OpenVR": 0,
            "Devkit": 0,
            "DevkitGameID": "",
            "DevkitOverrideAppID": 0,
            "LastPlayTime": 0,
            "FlatpakAppID": "",
            "tags": {},
        }

        # Find the next numeric index ('0', '1', '2'...)
        next_idx = str(len(data["shortcuts"]))
        data["shortcuts"][next_idx] = new_entry

        save_shortcuts(vdf_path, data)
        return True, "Shortcut added!", str_appid

    except Exception as e:
        return False, f"Error: {str(e)}", None


def update_shortcut_name(vdf_path, appid, new_name):
    """Finds a shortcut by appid and updates its AppName."""
    try:
        data = load_shortcuts(vdf_path)
        if "shortcuts" not in data:
            return False, "No shortcuts found."

        found = False
        # Iterate through the numbered keys ('0', '1', etc.)
        for idx, entry in data["shortcuts"].items():
            if normalize_appid(entry.get("appid")) == normalize_appid(appid):
                entry["AppName"] = new_name
                found = True
                break

        if found:
            save_shortcuts(vdf_path, data)
            return True, "Name updated."
        return False, "Shortcut not found in file."
    except Exception as e:
        return False, str(e)


def delete_shortcut(vdf_path, appid):
    """
    Finds a shortcut by appid, removes it, and re-indexes the file.
    """
    try:
        data = load_shortcuts(vdf_path)
        shortcuts = data.get("shortcuts", {})

        # 1. Find the target key
        target_key = None
        for key, entry in shortcuts.items():
            if normalize_appid(entry.get("appid")) == normalize_appid(appid):
                target_key = key
                break

        if target_key is not None:
            # 2. Remove the entry
            del shortcuts[target_key]

            # 3. Re-index keys to be sequential: "0", "1", "2"...
            new_shortcuts = {}
            for i, val in enumerate(shortcuts.values()):
                new_shortcuts[str(i)] = val
            data["shortcuts"] = new_shortcuts

            save_shortcuts(vdf_path, data)
            return True, "Shortcut removed."

        return False, "Shortcut not found in file."
    except Exception as e:
        return False, str(e)
