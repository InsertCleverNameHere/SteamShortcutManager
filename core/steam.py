"""
Steam installation discovery and shortcuts.vdf detection.
"""

import os
import vdf
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_STEAM_PATHS = [
    r"C:\Program Files (x86)\Steam",
    r"C:\Program Files\Steam",
]


@dataclass
class SteamUserShortcuts:
    """Represents one discovered shortcuts.vdf file and its owning Steam user."""
    userdata_id: str          # The numeric folder name under userdata/
    steam_id64: Optional[str] # Full 64-bit Steam ID if resolvable
    persona_name: Optional[str]
    shortcuts_path: str       # Full path to shortcuts.vdf
    shortcut_count: int
    avatar_path: Optional[str] = None  # Path to locally cached avatar, if found


STEAM_ID64_BASE = 76561197960265728


def userdata_id_to_steamid64(userdata_id: str) -> str:
    return str(STEAM_ID64_BASE + int(userdata_id))


def is_valid_steam_dir(path: str) -> bool:
    """Check that the given path looks like a real Steam installation."""
    if not path or not os.path.isdir(path):
        return False
    # steam.exe or a userdata folder are both good signals
    has_exe = os.path.isfile(os.path.join(path, "steam.exe"))
    has_userdata = os.path.isdir(os.path.join(path, "userdata"))
    return has_exe or has_userdata


def detect_default_steam_dir() -> Optional[str]:
    """Return the first default Steam path that actually exists, or None."""
    for path in DEFAULT_STEAM_PATHS:
        if is_valid_steam_dir(path):
            return path
    return None


def get_persona_name(steam_dir: str, steamid64: str) -> Optional[str]:
    """Look up a display name from loginusers.vdf using the full 64-bit Steam ID."""
    login_users_path = os.path.join(steam_dir, "config", "loginusers.vdf")
    if not os.path.isfile(login_users_path):
        return None
    try:
        with open(login_users_path, encoding="utf-8", errors="replace") as f:
            data = vdf.load(f)
        users = data.get("users", {})
        user = users.get(steamid64, {})
        return user.get("PersonaName") or user.get("AccountName") or None
    except Exception:
        return None


def get_avatar_path(steam_dir: str, steamid64: str) -> Optional[str]:
    """
    Try to find a locally cached avatar image for this user.
    Steam stores them as <steamid64>.jpg or <steamid64_small>.jpg inside
    config/avatarcache/ (varies by Steam version).
    """
    cache_dirs = [
        os.path.join(steam_dir, "config", "avatarcache"),
        os.path.join(steam_dir, "avatarcache"),
    ]
    for cache_dir in cache_dirs:
        for ext in (".jpg", ".png"):
            candidate = os.path.join(cache_dir, f"{steamid64}{ext}")
            if os.path.isfile(candidate):
                return candidate
    return None


def count_shortcuts(shortcuts_path: str) -> int:
    """Parse a binary shortcuts.vdf and return the number of entries."""
    try:
        with open(shortcuts_path, "rb") as f:
            data = vdf.binary_load(f)
        return len(data.get("shortcuts", {}))
    except Exception:
        return 0


def find_shortcuts(steam_dir: str) -> list[SteamUserShortcuts]:
    """
    Scan <steam_dir>/userdata/ for every shortcuts.vdf that exists.
    Returns a list of SteamUserShortcuts, one per discovered file.
    """
    results: list[SteamUserShortcuts] = []
    userdata_root = os.path.join(steam_dir, "userdata")

    if not os.path.isdir(userdata_root):
        return results

    for entry in os.listdir(userdata_root):
        if not entry.isdigit() or entry == "0":
            continue

        shortcuts_path = os.path.join(userdata_root, entry, "config", "shortcuts.vdf")
        if not os.path.isfile(shortcuts_path):
            continue

        steamid64 = userdata_id_to_steamid64(entry)
        persona = get_persona_name(steam_dir, steamid64)
        avatar = get_avatar_path(steam_dir, steamid64)
        count = count_shortcuts(shortcuts_path)

        results.append(SteamUserShortcuts(
            userdata_id=entry,
            steam_id64=steamid64,
            persona_name=persona,
            shortcuts_path=shortcuts_path,
            shortcut_count=count,
            avatar_path=avatar,
        ))
        

    return results

def get_asset_status(shortcuts_vdf_path: str, appid: str) -> dict:
    """
    Checks for the 5 required assets in the grid folder.
    Returns a dict: { 'type': (exists: bool, path: str) }
    """
    grid_dir = os.path.join(os.path.dirname(shortcuts_vdf_path), "grid")
    
    # Define patterns to check. We check for .jpg then .png for images.
    # For JSON, it is strictly .json.
    patterns = {
        "capsule": [f"{appid}p.jpg", f"{appid}p.png"],
        "header":  [f"{appid}.jpg", f"{appid}.png"],
        "hero":    [f"{appid}_hero.jpg", f"{appid}_hero.png"],
        "logo":    [f"{appid}_logo.png", f"{appid}_logo.jpg"],
        "json":    [f"{appid}.json"]
    }
    
    status = {}
    for key, filenames in patterns.items():
        found_path = None
        for f in filenames:
            full_path = os.path.join(grid_dir, f)
            if os.path.isfile(full_path):
                found_path = full_path
                break
        status[key] = (found_path is not None, found_path)
        
    return status