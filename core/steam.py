"""
Steam installation discovery and shortcuts.vdf detection.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import vdf

from core.log import get_logger
from core.platform import get_platform
from core.platform.base import SteamInstall

logger = get_logger("steam")


@dataclass
class SteamUserShortcuts:
    """Represents one discovered shortcuts.vdf file and its owning Steam user."""

    userdata_id: str  # The numeric folder name under userdata/
    steam_id64: str | None  # Full 64-bit Steam ID if resolvable
    persona_name: str | None
    shortcuts_path: str  # Full path to shortcuts.vdf
    shortcut_count: int
    avatar_path: str | None = None  # Path to locally cached avatar, if found
    install: SteamInstall | None = None  # Associated Steam installation


STEAM_ID64_BASE = 76561197960265728


def userdata_id_to_steamid64(userdata_id: str) -> str:
    return str(STEAM_ID64_BASE + int(userdata_id))


def is_valid_steam_dir(path: str | Path) -> bool:
    """Check that the given path looks like a real Steam installation using the platform layer."""
    if not path:
        return False
    return get_platform().is_valid_steam_dir(path)


def detect_default_steam_dir() -> str | None:
    """Return the first discovered Steam installation path from the platform layer, or None."""
    installs = get_platform().discover_steam_installs()
    if installs:
        return str(installs[0].path)
    return None


def get_persona_name(steam_dir: str, steamid64: str) -> str | None:
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
    except Exception as e:
        logger.warning(f"Persona lookup error for {steamid64}: {e}")
        return None


def get_avatar_path(steam_dir: str, steamid64: str) -> str | None:
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
    except Exception as e:
        logger.warning(f"VDF Parse error in {shortcuts_path}: {e}")
        return 0


def find_shortcuts(steam_dir: str | Path | SteamInstall) -> list[SteamUserShortcuts]:
    """
    Scan <steam_dir>/userdata/ for every shortcuts.vdf that exists.
    Returns a list of SteamUserShortcuts, tagged with its SteamInstall.
    """
    if isinstance(steam_dir, SteamInstall):
        install_obj = steam_dir
        root_path = Path(steam_dir.path)
    else:
        root_path = Path(steam_dir).resolve()
        known_installs = get_platform().discover_steam_installs()
        matched = next(
            (i for i in known_installs if i.path.resolve() == root_path), None
        )
        install_obj = matched or SteamInstall(
            path=root_path, kind="custom", label="Steam (Custom)"
        )

    results: list[SteamUserShortcuts] = []
    userdata_root = root_path / "userdata"

    if not userdata_root.is_dir():
        return results

    for entry in os.listdir(userdata_root):
        if not entry.isdigit() or entry == "0":
            continue

        shortcuts_path = userdata_root / entry / "config" / "shortcuts.vdf"
        if not shortcuts_path.is_file():
            continue

        steamid64 = userdata_id_to_steamid64(entry)
        persona = get_persona_name(str(root_path), steamid64)
        avatar = get_avatar_path(str(root_path), steamid64)
        count = count_shortcuts(str(shortcuts_path))

        results.append(
            SteamUserShortcuts(
                userdata_id=entry,
                steam_id64=steamid64,
                persona_name=persona,
                shortcuts_path=str(shortcuts_path),
                shortcut_count=count,
                avatar_path=avatar,
                install=install_obj,
            )
        )

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
        "capsule": [f"{appid}p.jpg", f"{appid}p.png", f"{appid}p.jpeg"],
        "header": [f"{appid}.jpg", f"{appid}.png", f"{appid}.jpeg"],
        "hero": [f"{appid}_hero.jpg", f"{appid}_hero.png", f"{appid}_hero.jpeg"],
        "logo": [f"{appid}_logo.png", f"{appid}_logo.jpg", f"{appid}_logo.jpeg"],
        "json": [f"{appid}.json"],
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


def find_all_shortcuts() -> list[SteamUserShortcuts]:
    """Discovers shortcuts across all detected Steam installations on the system."""
    installs = get_platform().discover_steam_installs()
    all_users: list[SteamUserShortcuts] = []
    for install in installs:
        all_users.extend(find_shortcuts(install))
    return all_users
