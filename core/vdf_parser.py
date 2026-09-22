"""
core/vdf_parser.py
Backward-compatibility bridge routing calls through core.shortcuts_io and core.appid.
Protects all mutations with ShortcutsTransaction and atomic writes.
"""

from pathlib import Path

from core.shortcuts_io import (
    ShortcutsFileError,
    ShortcutsTransaction,
)
from core.shortcuts_io import (
    add_shortcut as _io_add_shortcut,
)
from core.shortcuts_io import (
    delete_shortcut as _io_delete_shortcut,
)
from core.shortcuts_io import (
    load_shortcuts as _io_load_shortcuts,
)
from core.shortcuts_io import (
    update_shortcut_name as _io_update_shortcut_name,
)


def load_shortcuts(path: str | Path) -> dict:
    """Loads shortcuts.vdf safely without crashing the UI on empty or missing files."""
    try:
        return _io_load_shortcuts(path, strict=True)
    except ShortcutsFileError:
        # Graceful fallback for UI compatibility
        return {"shortcuts": {}}


def add_new_shortcut(
    vdf_path: str, game_name: str, exe_path: str, icon_path: str = ""
) -> tuple[bool, str, str | None]:
    """
    Safely adds a new shortcut wrapped in ShortcutsTransaction.
    Stores appid natively as int32 and returns (success, msg, unsigned_str_appid).
    """
    try:
        with ShortcutsTransaction(vdf_path) as tx:
            appid_str, _ = _io_add_shortcut(
                tx.data,
                game_name=game_name,
                exe_path=exe_path,
                icon_path=icon_path,
            )
        return True, "Shortcut added!", appid_str
    except Exception as e:
        return False, f"Error: {e}", None


def update_shortcut_name(
    vdf_path: str, appid: str | int, new_name: str
) -> tuple[bool, str]:
    """Safely updates shortcut name wrapped in ShortcutsTransaction, preserving key casing."""
    try:
        with ShortcutsTransaction(vdf_path) as tx:
            found = _io_update_shortcut_name(tx.data, appid, new_name)
            if not found:
                return False, "Shortcut not found in file."
        return True, "Name updated."
    except Exception as e:
        return False, str(e)


def delete_shortcut(vdf_path: str, appid: str | int) -> tuple[bool, str]:
    """Safely removes a shortcut wrapped in ShortcutsTransaction with sequential re-indexing."""
    try:
        with ShortcutsTransaction(vdf_path) as tx:
            deleted = _io_delete_shortcut(tx.data, appid)
            if not deleted:
                return False, "Shortcut not found in file."
        return True, "Shortcut removed."
    except Exception as e:
        return False, str(e)
