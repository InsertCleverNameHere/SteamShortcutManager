from pathlib import Path

import pytest
import vdf

from core import vdf_parser
from core.shortcuts_io import ShortcutsFileError


def test_vdf_parser_add_update_delete_lifecycle(tmp_path: Path):
    """Verify that vdf_parser's UI-facing API safely mutates files and creates backups."""
    vdf_file = tmp_path / "shortcuts.vdf"
    vdf_file.write_bytes(b"\x00shortcuts\x00\x08\x08")

    # 1. Add shortcut
    success, msg, appid = vdf_parser.add_new_shortcut(
        str(vdf_file), "Dead Cells", "/usr/bin/deadcells"
    )
    assert success is True
    assert appid is not None
    assert appid.isdigit()

    # Verify backup was automatically created in ssm-backups/
    backup_dir = tmp_path / "ssm-backups"
    assert backup_dir.is_dir()
    assert len(list(backup_dir.glob("*.bak"))) == 1

    # Verify binary structure via raw vdf.binary_load
    with open(vdf_file, "rb") as f:
        data = vdf.binary_load(f)
    assert data["shortcuts"]["0"]["AppName"] == "Dead Cells"
    # AppID must be stored natively as int32
    assert isinstance(data["shortcuts"]["0"]["appid"], int)

    # 2. Update shortcut name
    rename_ok, rename_msg = vdf_parser.update_shortcut_name(
        str(vdf_file), appid, "Dead Cells (Updated)"
    )
    assert rename_ok is True

    with open(vdf_file, "rb") as f:
        data = vdf.binary_load(f)
    assert data["shortcuts"]["0"]["AppName"] == "Dead Cells (Updated)"

    # 3. Delete shortcut
    del_ok, del_msg = vdf_parser.delete_shortcut(str(vdf_file), appid)
    assert del_ok is True

    with open(vdf_file, "rb") as f:
        data = vdf.binary_load(f)
    assert len(data["shortcuts"]) == 0


def test_vdf_parser_re_exports():
    """Ensure essential UI helper functions remain exported by vdf_parser."""
    assert hasattr(vdf_parser, "get_shortcut_list")
    assert hasattr(vdf_parser, "get_value_case_insensitive")
    assert hasattr(vdf_parser, "normalize_appid")
    assert hasattr(vdf_parser, "save_shortcuts")


def test_vdf_parser_load_corrupted_raises(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt_shortcuts.vdf"
    corrupt_file.write_bytes(b"\x00\xff_NOT_A_VALID_VDF_BINARY_FILE")

    with pytest.raises(ShortcutsFileError):
        vdf_parser.load_shortcuts(corrupt_file)


def test_update_shortcut_icon_integration(tmp_path: Path):
    """Verify vdf_parser.update_shortcut_icon sets icon in shortcuts.vdf atomically."""
    vdf_file = tmp_path / "shortcuts.vdf"
    vdf_file.write_bytes(b"\x00shortcuts\x00\x08\x08")

    # Add game
    _, _, appid = vdf_parser.add_new_shortcut(
        str(vdf_file), "Hades", "/games/hades.exe"
    )
    assert appid is not None

    # Update icon
    icon_path = str(tmp_path / "grid" / f"{appid}_icon.ico")
    ok, msg = vdf_parser.update_shortcut_icon(str(vdf_file), appid, icon_path)
    assert ok is True

    # Reload directly with vdf to verify storage
    with open(vdf_file, "rb") as f:
        data = vdf.binary_load(f)
    assert data["shortcuts"]["0"]["icon"] == icon_path
