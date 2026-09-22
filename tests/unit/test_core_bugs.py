from pathlib import Path

from core.steam import get_asset_status


def test_asset_status_detects_jpeg(tmp_path: Path):
    """Audit 3.2 #7: Verify that .jpeg files are recognized and not marked Missing."""
    userdata_dir = tmp_path / "userdata" / "12345" / "config"
    grid_dir = userdata_dir / "grid"
    grid_dir.mkdir(parents=True)

    shortcuts_vdf = userdata_dir / "shortcuts.vdf"
    shortcuts_vdf.touch()

    appid = "3836504666"

    # Create .jpeg files
    capsule = grid_dir / f"{appid}p.jpeg"
    capsule.write_bytes(b"dummy_image_data")
    header = grid_dir / f"{appid}.jpeg"
    header.write_bytes(b"dummy_image_data")

    status = get_asset_status(str(shortcuts_vdf), appid)

    assert status["capsule"][0] is True
    assert status["capsule"][1] == str(capsule)
    assert status["header"][0] is True
    assert status["header"][1] == str(header)
    assert status["hero"][0] is False  # Missing
