from pathlib import Path
from unittest.mock import MagicMock, patch

from core.lnk import resolve_lnk


def test_resolve_lnk_returns_path_if_not_lnk(tmp_path: Path):
    exe_file = tmp_path / "game.exe"
    exe_file.touch()
    assert resolve_lnk(exe_file) == str(exe_file)


def test_resolve_lnk_handles_missing_file():
    missing = Path("/nonexistent/path/game.lnk")
    assert resolve_lnk(missing) is None


def test_resolve_lnk_handles_corrupt_lnk(tmp_path: Path):
    corrupt_lnk = tmp_path / "broken.lnk"
    corrupt_lnk.write_bytes(b"INVALID_LNK_DATA")
    assert resolve_lnk(corrupt_lnk) is None


def test_resolve_lnk_extracts_local_base_path(tmp_path: Path):
    fake_lnk = tmp_path / "test.lnk"
    fake_lnk.touch()

    mock_json = {"link_info": {"local_base_path": r"D:\Games\Silksong\silksong.exe"}}

    mock_lnk_obj = MagicMock()
    mock_lnk_obj.get_json.return_value = mock_json

    with patch("LnkParse3.lnk_file", return_value=mock_lnk_obj):
        target = resolve_lnk(fake_lnk)
        assert target == r"D:\Games\Silksong\silksong.exe"
