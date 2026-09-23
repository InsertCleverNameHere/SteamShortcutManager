"""
core/appid.py
Pure AppID generation, normalization, and conversion functions.
Matches Steam's binary shortcuts.vdf and grid filename specifications.
"""

import zlib
from typing import Any


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
