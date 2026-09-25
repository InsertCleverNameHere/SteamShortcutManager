import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import vdf

from core.appid import normalize_appid
from core.shortcuts_io import (
    ShortcutsFileError,
    ShortcutsTransaction,
    add_shortcut,
    create_backup,
    delete_shortcut,
    get_available_backups,
    load_shortcuts,
    restore_backup,
    save_shortcuts_atomic,
    update_shortcut_icon,
    update_shortcut_name,
)


def test_load_shortcuts_strict_rejects_corrupted_file(tmp_path: Path):
    """Audit 3.2 #1: Strict load must raise ShortcutsFileError on corrupted data."""
    bad_file = tmp_path / "corrupted.vdf"
    bad_file.write_bytes(b"\x00\x01\xffGARBAGE_BYTES_THAT_CANNOT_PARSE")

    with pytest.raises(ShortcutsFileError):
        load_shortcuts(bad_file, strict=True)


def test_create_backup_rotation(tmp_path: Path):
    """Audit 3.2 #1: Rotating backups must keep at most max_backups."""
    vdf_file = tmp_path / "shortcuts.vdf"
    vdf_file.write_bytes(b"\x00shortcuts\x00\x08\x08")

    # Generate 4 backups with max_backups=2
    for _ in range(4):
        create_backup(vdf_file, max_backups=2)

    backup_dir = tmp_path / "ssm-backups"
    assert backup_dir.is_dir()
    backups = list(backup_dir.glob("shortcuts_*.vdf.bak"))
    assert len(backups) == 2


def test_atomic_write_and_roundtrip(tmp_path: Path):
    """Verify atomic write creates a clean file that vdf can re-parse."""
    vdf_file = tmp_path / "shortcuts.vdf"
    data = {"shortcuts": {}}
    appid_str, entry = add_shortcut(data, "Hades", "/usr/bin/hades")

    save_shortcuts_atomic(vdf_file, data)
    assert vdf_file.is_file()

    # Re-parse directly with vdf library
    with open(vdf_file, "rb") as f:
        reloaded = vdf.binary_load(f)

    loaded_entry = reloaded["shortcuts"]["0"]
    assert loaded_entry["AppName"] == "Hades"
    # AppID must be packed as int32
    assert isinstance(loaded_entry["appid"], int)
    assert normalize_appid(loaded_entry["appid"]) == appid_str


def test_transaction_commits_cleanly(tmp_path: Path):
    """Verify ShortcutsTransaction creates a backup and commits mutations."""
    vdf_file = tmp_path / "shortcuts.vdf"
    vdf_file.write_bytes(b"\x00shortcuts\x00\x08\x08")

    with ShortcutsTransaction(vdf_file) as tx:
        add_shortcut(tx.data, "Celeste", "/usr/bin/celeste")

    reloaded = load_shortcuts(vdf_file)
    assert len(reloaded["shortcuts"]) == 1
    assert reloaded["shortcuts"]["0"]["AppName"] == "Celeste"

    # Backup should exist
    backup_dir = tmp_path / "ssm-backups"
    assert len(list(backup_dir.glob("*.bak"))) == 1


def test_transaction_rolls_back_on_caller_exception(tmp_path: Path):
    """If an exception happens inside the transaction, the original file is untouched."""
    vdf_file = tmp_path / "shortcuts.vdf"
    initial_bytes = b"\x00shortcuts\x00\x08\x08"
    vdf_file.write_bytes(initial_bytes)

    with pytest.raises(RuntimeError), ShortcutsTransaction(vdf_file) as tx:
        add_shortcut(tx.data, "FailingGame", "/bin/fail")
        raise RuntimeError("Simulated crash")

    # File must be identical to initial state
    assert vdf_file.read_bytes() == initial_bytes


def test_update_shortcut_name_preserves_case():
    """Audit 3.2 #8: Renaming must not duplicate keys when file uses lowercase 'appname'."""
    data = {
        "shortcuts": {
            "0": {
                "appid": -100,
                "appname": "Old Lowercase Name",
            }
        }
    }
    updated = update_shortcut_name(data, -100, "New Title")
    assert updated is True

    entry = data["shortcuts"]["0"]
    assert "appname" in entry
    assert "AppName" not in entry
    assert entry["appname"] == "New Title"


def test_delete_shortcut_reindexes_keys():
    """Deleting an item must re-index dictionary keys sequentially."""
    data = {"shortcuts": {}}
    id1, _ = add_shortcut(data, "Game 1", "/path/1")
    id2, _ = add_shortcut(data, "Game 2", "/path/2")
    id3, _ = add_shortcut(data, "Game 3", "/path/3")

    assert set(data["shortcuts"].keys()) == {"0", "1", "2"}

    # Delete the middle entry
    deleted = delete_shortcut(data, id2)
    assert deleted is True
    assert set(data["shortcuts"].keys()) == {"0", "1"}
    assert data["shortcuts"]["0"]["AppName"] == "Game 1"
    assert data["shortcuts"]["1"]["AppName"] == "Game 3"


def test_backup_listing_and_restore(tmp_path: Path):
    vdf_file = tmp_path / "shortcuts.vdf"
    vdf_file.write_bytes(b"\x00shortcuts\x00\x08\x08")

    # Initially no backups
    assert get_available_backups(vdf_file) == []

    # Create backup
    backup_file = create_backup(vdf_file)
    assert backup_file is not None

    backups = get_available_backups(vdf_file)
    assert len(backups) == 1
    assert backups[0] == backup_file

    # Overwrite target with different data
    vdf_file.write_bytes(b"\x00corrupted\x00")

    # Restore backup
    restored = restore_backup(backup_file, vdf_file)
    assert restored is True
    assert vdf_file.read_bytes() == b"\x00shortcuts\x00\x08\x08"


def test_add_shortcut_delegates_start_dir_to_platform():
    """Verify that add_shortcut uses PlatformServices.format_start_dir when start_dir is empty."""
    mock_platform = MagicMock()
    mock_platform.format_start_dir.return_value = "/mocked/start/dir/"

    raw_exe = "/custom/path/game.exe"
    expected_exe = os.path.normpath(raw_exe)

    data = {"shortcuts": {}}
    with patch("core.shortcuts_io.get_platform", return_value=mock_platform):
        _, entry = add_shortcut(data, "Custom Game", raw_exe)

    mock_platform.format_start_dir.assert_called_once_with(expected_exe)
    assert entry["StartDir"] == "/mocked/start/dir/"


def test_update_shortcut_icon_preserves_case():
    """Verify update_shortcut_icon updates the icon field and preserves key casing."""
    data = {
        "shortcuts": {
            "0": {
                "appid": -200,
                "AppName": "Test Game",
                "icon": "",
            }
        }
    }
    updated = update_shortcut_icon(data, -200, "/path/to/icon.ico")
    assert updated is True
    assert data["shortcuts"]["0"]["icon"] == "/path/to/icon.ico"
