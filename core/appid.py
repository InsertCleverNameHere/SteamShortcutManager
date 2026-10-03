"""
core/appid.py
Pure AppID generation, normalization, and conversion functions.
Matches Steam's binary shortcuts.vdf and grid filename specifications.
"""

import re
import zlib
from typing import Any

_APPID_URL_PATTERN = re.compile(
    r"(?:store\.steampowered\.com|steamdb\.info)/app/(\d+)", re.IGNORECASE
)


def extract_appid(text: str | None) -> str | None:
    """
    Extracts a numeric Steam AppID from raw user input.
    Accepts:
    - Pure numeric AppID string (e.g. '1205520')
    - Steam Store URL (e.g. 'https://store.steampowered.com/app/1205520/Game_Name/')
    - SteamDB URL (e.g. 'https://steamdb.info/app/1205520/')

    Returns unsigned AppID string, or None if no valid AppID could be resolved.
    """
    if not text:
        return None

    clean = text.strip()
    match = _APPID_URL_PATTERN.search(clean)
    if match:
        appid = match.group(1)
        return appid if appid != "0" else None

    if clean.isdigit():
        return clean if clean != "0" else None

    return None


def generate_shortcut_appid(exe_path: str, game_name: str) -> int:
    """
    Generates the standard 32-bit unsigned Steam AppID for a non-Steam shortcut.
    Hashes the quoted executable path concatenated with the game name,
    and sets the high bit (0x80000000).
    """
    clean_exe = exe_path.strip()
    if not (clean_exe.startswith('"') and clean_exe.endswith('"')):
        quoted_exe = f'"{clean_exe}"'
    else:
        quoted_exe = clean_exe

    unique_key = (quoted_exe + game_name).encode("utf-8")
    return (zlib.crc32(unique_key) & 0xFFFFFFFF) | 0x80000000


def to_int32(u: int) -> int:
    """
    Converts an unsigned 32-bit integer to a signed 32-bit integer.
    This is what Steam's binary VDF stores (type 0x02).
    """
    val = u & 0xFFFFFFFF
    return val - 0x1_0000_0000 if val >= 0x8000_0000 else val


def to_uint32(i: int) -> int:
    """
    Converts a signed 32-bit integer to an unsigned 32-bit integer.
    This is what grid filenames and config.vdf keys use.
    """
    return i & 0xFFFFFFFF


def normalize_appid(appid: Any) -> str:
    """
    Normalizes an AppID (int, str, signed or unsigned) into an unsigned 32-bit string.
    Returns '0' on failure or None.
    """
    if appid is None:
        return "0"
    try:
        val = int(appid)
        return str(val & 0xFFFFFFFF)
    except (ValueError, TypeError):
        return str(appid).strip()
