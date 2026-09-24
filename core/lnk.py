"""
core/lnk.py
Parses Windows .lnk files and resolves target executable paths using LnkParse3.
Fully cross-platform; operates without win32com or Windows Shell APIs.
"""

from pathlib import Path

import LnkParse3


def resolve_lnk(path: str | Path) -> str | None:
    """
    If the path is a .lnk file, inspects its binary structure and returns
    the target executable path. If unresolvable or corrupted, returns None
    so the broken .lnk is not stored as an executable.
    """
    file_path = Path(path)
    if file_path.suffix.lower() != ".lnk":
        return str(path)

    if not file_path.is_file():
        return None

    try:
        with open(file_path, "rb") as f:
            lnk = LnkParse3.lnk_file(f)
            info = lnk.get_json()

        # 1. Try local base path (standard absolute Windows path)
        link_info = info.get("link_info", {})
        local_base_path = link_info.get("local_base_path")
        if (
            local_base_path
            and isinstance(local_base_path, str)
            and local_base_path.strip()
        ):
            return local_base_path.strip()

        # 2. Try relative path from string data
        string_data = info.get("string_data", {}) or info.get("data", {})
        rel_path = string_data.get("relative_path")
        if rel_path and isinstance(rel_path, str) and rel_path.strip():
            target_candidate = (file_path.parent / rel_path.strip()).resolve()
            return str(target_candidate)

        # 3. Fallback to command attribute if present
        command = getattr(lnk, "lnk_command", None)
        if command and isinstance(command, str) and command.strip():
            return command.strip()

    except Exception:
        pass

    return None


# Backward-compatibility alias matching the old utils_win naming
resolve_windows_shortcut = resolve_lnk
