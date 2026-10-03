"""
core/prefix_store.py
Persistent storage for user-defined prefix folder overrides.
Stores AppID -> prefix directory mappings in an atomic prefixes.json
inside the OS standard state directory, completely decoupled from shortcuts.vdf.
"""

import json
import os
import tempfile
from pathlib import Path

from core.log import get_log_dir, get_logger

logger = get_logger("prefix_store")


def get_prefixes_file() -> Path:
    """Returns the path to prefixes.json inside the user state directory."""
    state_dir = get_log_dir().parent
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "prefixes.json"


def load_prefix_overrides() -> dict[str, str]:
    """Reads and parses the prefix overrides dictionary from disk."""
    path = get_prefixes_file()
    if not path.is_file():
        return {}

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception as e:
        logger.warning(f"Could not load prefixes.json: {e}")

    return {}


def _save_prefix_overrides_atomic(data: dict[str, str]) -> None:
    """Atomically writes the overrides dictionary to disk."""
    path = get_prefixes_file()
    target_dir = path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_str = tempfile.mkstemp(
        dir=target_dir, prefix=".prefixes_", suffix=".json.tmp"
    )
    tmp_path = Path(tmp_str)

    try:
        payload = json.dumps(data, indent=2).encode("utf-8")
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def get_prefix_override(appid: str | int) -> Path | None:
    """
    Returns the user-defined prefix override Path for an AppID,
    or None if no override has been defined.
    """
    appid_str = str(appid).strip()
    overrides = load_prefix_overrides()
    raw_path = overrides.get(appid_str)
    if raw_path and raw_path.strip():
        return Path(raw_path.strip())
    return None


def set_prefix_override(appid: str | int, prefix_path: str | Path) -> None:
    """
    Sets and atomically persists a custom prefix directory override for an AppID.
    """
    appid_str = str(appid).strip()
    clean_path = str(Path(prefix_path).resolve())

    overrides = load_prefix_overrides()
    overrides[appid_str] = clean_path
    _save_prefix_overrides_atomic(overrides)


def clear_prefix_override(appid: str | int) -> bool:
    """
    Removes any custom prefix override for an AppID, restoring auto-detection.
    Returns True if an override was removed, False if none existed.
    """
    appid_str = str(appid).strip()
    overrides = load_prefix_overrides()
    if appid_str in overrides:
        del overrides[appid_str]
        _save_prefix_overrides_atomic(overrides)
        return True
    return False
