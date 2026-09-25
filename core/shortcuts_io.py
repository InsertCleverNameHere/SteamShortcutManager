"""
core/shortcuts_io.py
Strict, transactional binary shortcuts.vdf reader and writer.
Guarantees atomicity, permission preservation, and rotating backups.
"""

import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import vdf

from core.appid import generate_shortcut_appid, normalize_appid, to_int32
from core.platform import get_platform


class ShortcutsError(Exception):
    """Base exception for shortcut operations."""


class ShortcutsFileError(ShortcutsError):
    """Raised when shortcuts.vdf cannot be read, parsed, or verified."""


def load_shortcuts(path: str | Path, strict: bool = True) -> dict:
    """
    Reads and parses a binary shortcuts.vdf file.
    If strict=True (default), raises ShortcutsFileError on parse failures or truncation.
    """
    file_path = Path(path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return {"shortcuts": {}}

    try:
        with open(file_path, "rb") as f:
            data = vdf.binary_load(f)
    except Exception as e:
        if strict:
            raise ShortcutsFileError(
                f"Failed to parse binary shortcuts file at '{file_path}': {e}"
            ) from e
        return {"shortcuts": {}}

    if not isinstance(data, dict) or "shortcuts" not in data:
        if strict:
            raise ShortcutsFileError(
                f"Invalid shortcuts.vdf structure at '{file_path}': missing 'shortcuts' root key."
            )
        return {"shortcuts": {}}

    return data


def create_backup(shortcuts_path: str | Path, max_backups: int = 10) -> Path | None:
    """
    Creates a timestamped backup inside an 'ssm-backups' subfolder.
    Prunes older backups to keep at most max_backups files.
    """
    src = Path(shortcuts_path)
    if not src.is_file() or src.stat().st_size == 0:
        return None

    backup_dir = src.parent / "ssm-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"shortcuts_{timestamp}.vdf.bak"
    shutil.copy2(src, backup_path)

    # Ensure backup modification time reflects creation time, not source mtime
    try:
        os.utime(backup_path, None)
    except OSError:
        pass

    # Prune older backups sorted by microsecond-precise filename timestamp
    existing_backups = sorted(
        backup_dir.glob("shortcuts_*.vdf.bak"),
        key=lambda p: p.name,
        reverse=True,
    )
    for old_backup in existing_backups[max_backups:]:
        try:
            old_backup.unlink()
        except OSError:
            pass

    return backup_path


def save_shortcuts_atomic(path: str | Path, data: dict) -> None:
    """
    Atomically writes a dictionary to a binary shortcuts.vdf file.
    Resolves symlinks, flushes buffers, forces fsync, preserves POSIX mode,
    and retries on Windows PermissionError locks.
    """
    target = Path(path).resolve()
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Capture original file mode on POSIX if it exists
    original_mode = None
    if target.is_file():
        try:
            original_mode = target.stat().st_mode
        except OSError:
            pass

    fd, tmp_path_str = tempfile.mkstemp(
        dir=target_dir, prefix=".shortcuts_", suffix=".vdf.tmp"
    )
    tmp_path = Path(tmp_path_str)

    try:
        with os.fdopen(fd, "wb") as f:
            vdf.binary_dump(data, f)
            f.flush()
            os.fsync(f.fileno())

        if original_mode is not None:
            try:
                os.chmod(tmp_path, original_mode)
            except OSError:
                pass

        # Atomic replacement with retries for Windows file lock delays
        last_error = None
        for attempt in range(5):
            try:
                os.replace(tmp_path, target)
                last_error = None
                break
            except PermissionError as pe:
                last_error = pe
                time.sleep(0.1)

        if last_error is not None:
            raise last_error

    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


class ShortcutsTransaction:
    """
    Context manager for safe shortcut operations.
    1. Loads the file strictly.
    2. Takes a rotating timestamped backup.
    3. Yields the mutable transaction object.
    4. On exit, atomically writes and verifies the file.
    5. If verification fails, restores the backup and raises ShortcutsFileError.
    """

    def __init__(self, shortcuts_path: str | Path):
        self.shortcuts_path = Path(shortcuts_path)
        self.backup_path: Path | None = None
        self.data: dict = {}
        self._initial_mtime_ns: int | None = None
        self._initial_size: int | None = None

    def __enter__(self):
        self.data = load_shortcuts(self.shortcuts_path, strict=True)
        if self.shortcuts_path.is_file():
            stat = self.shortcuts_path.stat()
            self._initial_mtime_ns = stat.st_mtime_ns
            self._initial_size = stat.st_size
            self.backup_path = create_backup(self.shortcuts_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # An error occurred inside the caller's with-block; do not write
            return False

        # Optimistic concurrency: merge external changes if file was modified mid-transaction
        if self.shortcuts_path.is_file() and self._initial_mtime_ns is not None:
            try:
                current_stat = self.shortcuts_path.stat()
                if (
                    current_stat.st_mtime_ns != self._initial_mtime_ns
                    or current_stat.st_size != self._initial_size
                ):
                    external_data = load_shortcuts(self.shortcuts_path, strict=True)
                    for k, v in external_data.get("shortcuts", {}).items():
                        if k not in self.data.get("shortcuts", {}):
                            self.data.setdefault("shortcuts", {})[k] = v
            except Exception:
                pass

        # Attempt atomic write
        save_shortcuts_atomic(self.shortcuts_path, self.data)

        # Verification step: re-read file from disk and confirm it parses
        try:
            verified = load_shortcuts(self.shortcuts_path, strict=True)
            expected_count = len(self.data.get("shortcuts", {}))
            actual_count = len(verified.get("shortcuts", {}))
            if expected_count != actual_count:
                raise ShortcutsFileError(
                    f"Integrity check failed: expected {expected_count} entries, found {actual_count}."
                )
        except Exception as e:
            # Verification failed; restore backup if available
            if self.backup_path and self.backup_path.is_file():
                shutil.copy2(self.backup_path, self.shortcuts_path)
            raise ShortcutsFileError(
                f"Shortcut write verification failed (backup restored): {e}"
            ) from e

        return False


def get_available_backups(shortcuts_path: str | Path) -> list[Path]:
    """Returns all backup files in ssm-backups/ sorted newest first by filename timestamp."""
    src = Path(shortcuts_path)
    backup_dir = src.parent / "ssm-backups"
    if not backup_dir.is_dir():
        return []

    return sorted(
        backup_dir.glob("shortcuts_*.vdf.bak"),
        key=lambda p: p.name,
        reverse=True,
    )


def restore_backup(backup_path: str | Path, target_path: str | Path) -> bool:
    """
    Restores a selected backup file over target_path atomically.
    Takes a pre-restore safety snapshot of the current state first.
    """
    src = Path(backup_path)
    dst = Path(target_path)
    if not src.is_file():
        return False

    # Snapshot current state before restoring so restore is completely reversible
    if dst.is_file() and dst.stat().st_size > 0:
        create_backup(dst)

    data = load_shortcuts(src, strict=True)
    save_shortcuts_atomic(dst, data)
    return True


def get_shortcut_list(data: dict) -> list[dict]:
    """Returns shortcuts as a plain list from the dictionary."""
    return list(data.get("shortcuts", {}).values())


def get_value_case_insensitive(entry: dict, target_key: str, default: Any = "") -> Any:
    """Finds a key in a shortcut dictionary regardless of its casing."""
    target_lower = target_key.lower()
    for key, value in entry.items():
        if key.lower() == target_lower:
            return value
    return default


def set_value_case_preserving(entry: dict, target_key: str, new_value: Any) -> None:
    """
    Updates a key's value while preserving existing casing (e.g. 'AppName' vs 'appname').
    If the key does not already exist, adds it with target_key casing.
    """
    target_lower = target_key.lower()
    for key in list(entry.keys()):
        if key.lower() == target_lower:
            entry[key] = new_value
            return
    entry[target_key] = new_value


def add_shortcut(
    data: dict,
    game_name: str,
    exe_path: str,
    start_dir: str = "",
    icon_path: str = "",
    launch_options: str = "",
) -> tuple[str, dict]:
    """
    Appends a new shortcut entry using Steam's native data types (int32 appid).
    Returns (unsigned_appid_string, new_entry_dict).
    """
    shortcuts = data.setdefault("shortcuts", {})
    # Normalize slashes across platforms so dialogs and drag-drop yield identical AppIDs
    clean_exe = os.path.normpath(exe_path.strip().strip('"'))
    quoted_exe = f'"{clean_exe}"'

    # Sanitize game name: strip whitespace and fall back to executable stem if empty
    clean_name = game_name.strip()
    if not clean_name:
        clean_name = Path(clean_exe).stem or "Unnamed Game"

    if not start_dir:
        start_dir = get_platform().format_start_dir(clean_exe)

    # Disambiguate duplicate games to prevent shared AppID collisions
    existing_appids = {
        normalize_appid(get_value_case_insensitive(entry, "appid"))
        for entry in shortcuts.values()
    }
    unsigned_appid = generate_shortcut_appid(clean_exe, clean_name)
    duplicate_counter = 1
    original_base_name = clean_name
    while str(unsigned_appid) in existing_appids:
        clean_name = f"{original_base_name} ({duplicate_counter})"
        unsigned_appid = generate_shortcut_appid(clean_exe, clean_name)
        duplicate_counter += 1

    signed_appid = to_int32(unsigned_appid)

    new_entry = {
        "appid": signed_appid,
        "AppName": clean_name,
        "Exe": quoted_exe,
        "StartDir": start_dir,
        "icon": icon_path,
        "ShortcutPath": "",
        "LaunchOptions": launch_options,
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

    # Allocate the next available sequential numeric key
    numeric_keys = [int(k) for k in shortcuts.keys() if k.isdigit()]
    next_num = max(numeric_keys) + 1 if numeric_keys else 0
    next_idx = str(next_num)

    # Secondary safeguard: guarantee key is never overwritten
    while next_idx in shortcuts:
        next_num += 1
        next_idx = str(next_num)

    shortcuts[next_idx] = new_entry
    return str(unsigned_appid), new_entry


def update_shortcut_name(data: dict, appid: str | int, new_name: str) -> bool:
    """Finds shortcut by appid and updates its AppName while preserving key casing."""
    target_id = normalize_appid(appid)
    for entry in data.get("shortcuts", {}).values():
        current_id = normalize_appid(get_value_case_insensitive(entry, "appid"))
        if current_id == target_id:
            set_value_case_preserving(entry, "AppName", new_name)
            return True
    return False


def update_shortcut_icon(data: dict, appid: str | int, icon_path: str) -> bool:
    """Finds shortcut by appid and updates its icon path while preserving key casing."""
    target_id = normalize_appid(appid)
    for entry in data.get("shortcuts", {}).values():
        current_id = normalize_appid(get_value_case_insensitive(entry, "appid"))
        if current_id == target_id:
            set_value_case_preserving(entry, "icon", icon_path)
            return True
    return False


def delete_shortcut(data: dict, appid: str | int) -> bool:
    """Removes a shortcut by appid and re-indexes keys sequentially ('0', '1', '2'...)."""
    shortcuts = data.get("shortcuts", {})
    target_id = normalize_appid(appid)

    target_key = None
    for key, entry in shortcuts.items():
        current_id = normalize_appid(get_value_case_insensitive(entry, "appid"))
        if current_id == target_id:
            target_key = key
            break

    if target_key is None:
        return False

    del shortcuts[target_key]

    # Re-index remaining entries
    new_shortcuts = {str(i): entry for i, entry in enumerate(shortcuts.values())}
    data["shortcuts"] = new_shortcuts
    return True
