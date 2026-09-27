"""
core/grid.py
Unified filesystem and asset management for Steam Grid artwork.
Single source of truth for asset slots, extensions, magic-byte validation,
atomic writes, sibling pruning, and backup cleanup.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from core.log import get_logger

logger = get_logger("grid")

# Slot specifications: slot_key -> (filename_suffix, default_filename)
SLOT_MAPPING: dict[str, tuple[str, str]] = {
    "capsule": ("p", "library_600x900.jpg"),
    "header": ("", "header.jpg"),
    "hero": ("_hero", "library_hero.jpg"),
    "logo": ("_logo", "logo.png"),
}

VALID_ARTWORK_EXTENSIONS = (".jpg", ".jpeg", ".png")
VALID_ICON_EXTENSIONS = (".ico",)
ALL_IMAGE_EXTENSIONS = VALID_ARTWORK_EXTENSIONS + VALID_ICON_EXTENSIONS


def validate_image_bytes(data: bytes, ext: str) -> bool:
    """
    Validates payload header magic bytes to prevent writing HTML or corrupt
    responses to image files.
    """
    if len(data) < 8:
        return False

    snippet = data[:64].strip().lower()
    if snippet.startswith((b"<!doctype", b"<html", b"<?xml", b"<head", b"<body")):
        return False

    ext_clean = ext.lower().lstrip(".")
    if ext_clean in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if ext_clean == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext_clean == "ico":
        return data.startswith(b"\x00\x00\x01\x00")

    return True


def prune_sibling_extensions(
    grid_dir: Path | str, local_appid: str, suffix: str, keep_ext: str
) -> None:
    """
    Deletes any sibling artwork files with different extensions for the same slot
    to prevent conflicting or stale assets.
    """
    folder = Path(grid_dir)
    keep_ext_clean = keep_ext.lower()

    for alt_ext in ALL_IMAGE_EXTENSIONS:
        if alt_ext.lower() != keep_ext_clean:
            sibling_file = folder / f"{local_appid}{suffix}{alt_ext}"
            if sibling_file.is_file():
                try:
                    sibling_file.unlink()
                except OSError as e:
                    logger.debug(f"Could not remove sibling asset {sibling_file}: {e}")


def write_asset_atomic(
    grid_dir: Path | str,
    local_appid: str,
    suffix: str,
    ext: str,
    content: bytes,
    validate: bool = True,
) -> Path:
    """
    Atomically writes an asset payload to the grid directory.

    1. Validates magic bytes (if validate=True).
    2. Writes content to a temporary `.part` file.
    3. Flushes and fsyncs to disk.
    4. Prunes sibling files with differing extensions for this slot.
    5. Atomically replaces target file with retry handling for Windows file locks.
    """
    ext_clean = ext.lower()
    if not ext_clean.startswith("."):
        ext_clean = f".{ext_clean}"

    if validate and not validate_image_bytes(content, ext_clean):
        raise ValueError(
            f"Content failed magic-byte header validation for '{ext_clean}'."
        )

    target_dir = Path(grid_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_filename = f"{local_appid}{suffix}{ext_clean}"
    target_path = target_dir / target_filename

    # Create temporary .part file in the same directory for atomic rename
    fd, tmp_path_str = tempfile.mkstemp(
        dir=target_dir,
        prefix=f".{local_appid}{suffix}_",
        suffix=f"{ext_clean}.part",
    )
    tmp_path = Path(tmp_path_str)

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # Prune existing sibling extensions before replace
        prune_sibling_extensions(target_dir, local_appid, suffix, ext_clean)

        # Atomic replacement with retries for Windows locks
        last_error = None
        for _ in range(5):
            try:
                os.replace(tmp_path, target_path)
                last_error = None
                break
            except PermissionError as pe:
                last_error = pe
                time.sleep(0.08)

        if last_error is not None:
            raise last_error

    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

    return target_path


def write_json_positioning(
    grid_dir: Path | str,
    local_appid: str,
    logo_position: dict[str, Any],
) -> Path:
    """
    Atomically creates the Steam logo positioning JSON file.
    """
    target_dir = Path(grid_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    json_data = {
        "nVersion": 1,
        "logoPosition": {
            "pinnedPosition": logo_position.get("pinned_position", "BottomLeft"),
            "nWidthPct": float(logo_position.get("width_pct", 50.0)),
            "nHeightPct": float(logo_position.get("height_pct", 50.0)),
        },
    }
    content = json.dumps(json_data, separators=(",", ":")).encode("utf-8")

    target_path = target_dir / f"{local_appid}.json"
    fd, tmp_str = tempfile.mkstemp(
        dir=target_dir, prefix=f".{local_appid}_pos_", suffix=".json.part"
    )
    tmp_path = Path(tmp_str)

    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

    return target_path


def get_asset_status(
    grid_dir: Path | str, appid: str | int
) -> dict[str, tuple[bool, str | None]]:
    """
    Checks for all 5 official assets + icon in the grid directory.
    Returns: { slot_name: (exists: bool, path: str | None) }
    """
    target_dir = Path(grid_dir)
    appid_str = str(appid)

    status: dict[str, tuple[bool, str | None]] = {}

    if not target_dir.is_dir():
        for slot in ("capsule", "header", "hero", "logo", "json", "icon"):
            status[slot] = (False, None)
        return status

    # 1. Visual art slots
    for slot_name, (suffix, _) in SLOT_MAPPING.items():
        found = False
        found_path = None
        for ext in VALID_ARTWORK_EXTENSIONS:
            cand = target_dir / f"{appid_str}{suffix}{ext}"
            if cand.is_file():
                found = True
                found_path = str(cand)
                break
        status[slot_name] = (found, found_path)

    # 2. JSON position file
    json_path = target_dir / f"{appid_str}.json"
    status["json"] = (
        json_path.is_file(),
        str(json_path) if json_path.is_file() else None,
    )

    # 3. Client icon
    icon_path = target_dir / f"{appid_str}_icon.ico"
    status["icon"] = (
        icon_path.is_file(),
        str(icon_path) if icon_path.is_file() else None,
    )

    return status


def is_complete(grid_dir: Path | str, appid: str | int) -> bool:
    """
    Returns True if the shortcut has all required artwork and positioning JSON.
    """
    status = get_asset_status(grid_dir, appid)
    # Visual assets + JSON positioning must all exist
    required_slots = ("capsule", "header", "hero", "logo", "json")
    return all(status[slot][0] for slot in required_slots)


def delete_all_assets(grid_dir: Path | str, appid: str | int) -> int:
    """
    Deletes all associated images, icons, JSON, and orphan .part files for appid.
    Returns count of removed files.
    """
    target_dir = Path(grid_dir)
    if not target_dir.is_dir():
        return 0

    appid_str = str(appid)
    removed_count = 0

    # Prune artwork and icon slots
    for suffix in ("p", "", "_hero", "_logo", "_icon"):
        for ext in ALL_IMAGE_EXTENSIONS + (".part",):
            file_cand = target_dir / f"{appid_str}{suffix}{ext}"
            if file_cand.is_file():
                try:
                    file_cand.unlink()
                    removed_count += 1
                except OSError as e:
                    logger.warning(f"Could not delete asset {file_cand}: {e}")

    # Prune JSON and JSON .part
    for ext in (".json", ".json.part"):
        json_cand = target_dir / f"{appid_str}{ext}"
        if json_cand.is_file():
            try:
                json_cand.unlink()
                removed_count += 1
            except OSError as e:
                logger.warning(f"Could not delete {json_cand}: {e}")

    # Prune any hidden temporary .part files for this AppID
    for part_cand in target_dir.glob(f".{appid_str}*.part"):
        if part_cand.is_file():
            try:
                part_cand.unlink()
                removed_count += 1
            except OSError as e:
                logger.warning(f"Could not delete temp asset {part_cand}: {e}")

    return removed_count


def clean_stale_temp_files(grid_dir: Path | str, max_age_seconds: int = 86400) -> int:
    """Housekeeping: cleans lingering .part files older than max_age_seconds."""
    target_dir = Path(grid_dir)
    if not target_dir.is_dir():
        return 0

    now = time.time()
    pruned = 0
    try:
        for p in target_dir.glob(".*.part"):
            if p.is_file() and (now - p.stat().st_mtime) > max_age_seconds:
                try:
                    p.unlink()
                    pruned += 1
                except OSError:
                    pass
    except Exception:
        pass
    return pruned
