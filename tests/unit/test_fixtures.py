from pathlib import Path

import vdf


def test_golden_single_vdf_structure(golden_single_vdf: Path):
    """Verify that the single-shortcut golden file parses and matches Steam's native format."""
    assert golden_single_vdf.is_file(), f"Fixture missing: {golden_single_vdf}"

    with open(golden_single_vdf, "rb") as f:
        data = vdf.binary_load(f)

    assert "shortcuts" in data
    shortcuts = data["shortcuts"]
    assert "0" in shortcuts

    entry = shortcuts["0"]
    assert entry.get("AppName") == "boot-windows"
    assert entry.get("Exe") == '"/usr/bin/boot-windows"'
    assert entry.get("StartDir") == "/usr/bin/"

    # Verify appid is parsed as an int (signed in binary VDF)
    raw_appid = entry.get("appid")
    assert isinstance(raw_appid, int)
    # Check that converting to unsigned matches our Phase 0 probe (3836504666)
    assert (raw_appid & 0xFFFFFFFF) == 3836504666


def test_golden_multi_vdf_structure(golden_multi_vdf: Path):
    """Verify that the multi-shortcut golden file parses cleanly."""
    assert golden_multi_vdf.is_file(), f"Fixture missing: {golden_multi_vdf}"

    with open(golden_multi_vdf, "rb") as f:
        data = vdf.binary_load(f)

    assert "shortcuts" in data
    shortcuts = data["shortcuts"]
    assert len(shortcuts) >= 1
