from pathlib import Path
from unittest.mock import MagicMock, patch

from core.platform.linux import LinuxPlatform


def test_linux_is_valid_steam_dir(tmp_path: Path):
    platform = LinuxPlatform()
    assert not platform.is_valid_steam_dir(tmp_path)

    (tmp_path / "userdata").mkdir()
    assert platform.is_valid_steam_dir(tmp_path)


def test_linux_format_start_dir():
    platform = LinuxPlatform()
    start_dir = platform.format_start_dir("/home/deck/Games/Doom/doom.exe")
    assert start_dir == "/home/deck/Games/Doom/"


def test_linux_is_steam_running_via_psutil():
    platform = LinuxPlatform()
    mock_proc = MagicMock()
    mock_proc.info = {"name": "steam"}

    # Mock pid file to not exist so it exercises the psutil path
    with patch.object(Path, "is_file", return_value=False):
        with patch("psutil.process_iter", return_value=[mock_proc]):
            assert platform.is_steam_running() is True


def test_linux_path_warnings_installer():
    platform = LinuxPlatform()
    warnings = platform.path_warnings("/home/user/Downloads/setup_game.exe")
    assert any("installer" in w.lower() for w in warnings)
