from pathlib import Path
from unittest.mock import MagicMock, patch

from core.platform.windows import WindowsPlatform


def test_windows_is_valid_steam_dir(tmp_path: Path):
    platform = WindowsPlatform()
    assert not platform.is_valid_steam_dir(tmp_path)

    # Valid if steam.exe is present
    (tmp_path / "steam.exe").touch()
    assert platform.is_valid_steam_dir(tmp_path)


def test_windows_format_start_dir():
    platform = WindowsPlatform()
    start_dir = platform.format_start_dir(r"D:\Games\Hades\hades.exe")
    assert start_dir == r'"D:\Games\Hades\"'


def test_windows_is_steam_running_detected():
    platform = WindowsPlatform()

    mock_proc = MagicMock()
    mock_proc.info = {"name": "steam.exe"}

    with patch("psutil.process_iter", return_value=[mock_proc]):
        assert platform.is_steam_running() is True


def test_windows_is_steam_running_stopped():
    platform = WindowsPlatform()

    mock_proc = MagicMock()
    mock_proc.info = {"name": "chrome.exe"}

    with patch("psutil.process_iter", return_value=[mock_proc]):
        assert platform.is_steam_running() is False


def test_windows_path_warnings_installer():
    platform = WindowsPlatform()
    warnings = platform.path_warnings(r"C:\Downloads\setup_game.exe")
    assert len(warnings) == 1
    assert "installer" in warnings[0].lower()

    no_warnings = platform.path_warnings(r"C:\Games\Doom\doom.exe")
    assert len(no_warnings) == 0


def test_windows_open_folder(tmp_path: Path):
    platform = WindowsPlatform()

    # Non-existent directory returns False
    assert platform.open_folder(tmp_path / "nonexistent") is False

    # Existing directory invokes os.startfile
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    with patch("os.startfile", create=True) as mock_startfile:
        assert platform.open_folder(target_dir) is True
        mock_startfile.assert_called_once_with(str(target_dir.resolve()))

    # Exception in os.startfile returns False
    with patch("os.startfile", side_effect=OSError("Boom"), create=True):
        assert platform.open_folder(target_dir) is False


def test_windows_find_proton_prefix_is_none():
    win = WindowsPlatform()
    assert win.find_proton_prefix("12345") is None
