from pathlib import Path

import vdf

from core import vdf_parser


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
