import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.platform.base import SteamInstall
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


def test_linux_discover_steam_installs_expands_xdg_data_home(tmp_path: Path):
    """Verify that $XDG_DATA_HOME is expanded and discovered."""
    custom_xdg = tmp_path / "custom_xdg"
    custom_steam = custom_xdg / "Steam"
    (custom_steam / "userdata").mkdir(parents=True)

    platform = LinuxPlatform()
    with patch.dict(os.environ, {"XDG_DATA_HOME": str(custom_xdg)}):
        installs = platform.discover_steam_installs()
        assert any(i.path == custom_steam.resolve() for i in installs)


def test_linux_discover_steam_installs_deduplicates_symlinks(tmp_path: Path):
    """Verify that symlinks pointing to the same Steam root are deduplicated."""
    real_steam = tmp_path / "real_steam"
    (real_steam / "userdata").mkdir(parents=True)

    symlink_steam = tmp_path / "symlink_steam"
    symlink_steam.symlink_to(real_steam)

    platform = LinuxPlatform()
    platform.CANDIDATES = [
        (str(real_steam), "native", "Real"),
        (str(symlink_steam), "native", "Symlink"),
    ]

    installs = platform.discover_steam_installs()
    assert len(installs) == 1
    assert installs[0].path == real_steam.resolve()


def test_linux_is_steam_running_registry_fallback_active(tmp_path: Path):
    """Verify registry.vdf fallback reports True when ActiveProcess has non-zero pid."""
    platform = LinuxPlatform()
    reg_file = tmp_path / "registry.vdf"
    reg_file.write_text("""
    "Registry"
    {
        "HKCU"
        {
            "Software"
            {
                "Valve"
                {
                    "Steam"
                    {
                        "ActiveProcess"
                        {
                            "pid" "2632"
                            "ActiveUser" "207370295"
                        }
                    }
                }
            }
        }
    }
    """)

    with patch.object(platform, "is_sandboxed", return_value=True):
        with patch("psutil.process_iter", return_value=[]):
            with patch("core.platform.linux.Path.home", return_value=tmp_path):
                # Put file at tmp_path/.steam/registry.vdf
                steam_dir = tmp_path / ".steam"
                steam_dir.mkdir(parents=True, exist_ok=True)
                (steam_dir / "registry.vdf").write_text(reg_file.read_text())

                assert platform.is_steam_running() is True


def test_linux_request_steam_shutdown_flatpak():
    """Verify Flatpak Steam command is used when install.kind is flatpak."""
    platform = LinuxPlatform()
    flatpak_install = SteamInstall(
        path=Path("/steam"), kind="flatpak", label="Steam Flatpak"
    )

    with patch("subprocess.run") as mock_run:
        res = platform.request_steam_shutdown(flatpak_install)
        assert res is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["flatpak", "run", "com.valvesoftware.Steam", "-shutdown"]


def test_linux_request_steam_shutdown_native_blocked_in_sandbox():
    """Verify native Steam shutdown is blocked if app itself is running in sandbox."""
    platform = LinuxPlatform()
    native_install = SteamInstall(
        path=Path("/steam"), kind="native", label="Steam Native"
    )

    with patch.object(platform, "is_sandboxed", return_value=True):
        with patch("subprocess.run") as mock_run:
            res = platform.request_steam_shutdown(native_install)
            assert res is False
            mock_run.assert_not_called()


def test_linux_is_steam_running_registry_inactive(tmp_path: Path):
    """Verify registry.vdf with pid '0' reports False."""
    platform = LinuxPlatform()
    steam_dir = tmp_path / ".steam"
    steam_dir.mkdir(parents=True, exist_ok=True)
    (steam_dir / "registry.vdf").write_text("""
    "Registry"
    {
        "HKCU"
        {
            "Software"
            {
                "Valve"
                {
                    "Steam"
                    {
                        "ActiveProcess"
                        {
                            "pid" "0"
                            "ActiveUser" "0"
                        }
                    }
                }
            }
        }
    }
    """)

    with patch("psutil.process_iter", return_value=[]):
        with patch("core.platform.linux.Path.home", return_value=tmp_path):
            assert platform.is_steam_running() is False


def test_linux_is_steam_running_sandboxed_inconclusive_returns_none(tmp_path: Path):
    """Verify that inside a sandbox with no signals, is_steam_running returns None."""
    platform = LinuxPlatform()

    with patch.object(platform, "is_sandboxed", return_value=True):
        with patch("psutil.process_iter", return_value=[]):
            with patch("core.platform.linux.Path.home", return_value=tmp_path):
                with patch.object(
                    platform, "_read_registry_vdf_active", return_value=None
                ):
                    assert platform.is_steam_running() is None


def test_linux_open_folder(tmp_path: Path):
    platform = LinuxPlatform()

    # Non-existent directory returns False
    assert platform.open_folder(tmp_path / "nonexistent") is False

    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Test sanitized environment stripping
    env_patch = {
        "PYTHONHOME": "/tmp/appimage_py",
        "APPIMAGE": "/path/to/app.AppImage",
        "LD_LIBRARY_PATH": "/tmp/.mount_1234/lib:/usr/lib",
    }
    with patch.dict(os.environ, env_patch):
        with patch("subprocess.Popen") as mock_popen:
            assert platform.open_folder(target_dir) is True
            mock_popen.assert_called_once()
            args, kwargs = mock_popen.call_args
            assert args[0] == ["xdg-open", str(target_dir.resolve())]
            assert kwargs.get("start_new_session") is True

            passed_env = kwargs.get("env", {})
            assert "PYTHONHOME" not in passed_env
            assert "APPIMAGE" not in passed_env
            assert passed_env.get("LD_LIBRARY_PATH") == "/usr/lib"

    # Exception during launch returns False cleanly
    with patch("subprocess.Popen", side_effect=OSError("Boom")):
        assert platform.open_folder(target_dir) is False


def test_linux_find_proton_prefix_compatdata(tmp_path):
    from core.platform.base import SteamInstall
    from core.platform.linux import LinuxPlatform

    linux = LinuxPlatform()
    steam_root = tmp_path / "Steam"
    compat_pfx = steam_root / "steamapps" / "compatdata" / "3829104812" / "pfx"
    compat_pfx.mkdir(parents=True)

    install = SteamInstall(path=steam_root, kind="native", label="Steam")
    found = linux.find_proton_prefix("3829104812", install=install)

    assert found is not None
    assert found == compat_pfx

    # AppID without prefix returns None
    assert linux.find_proton_prefix("9999999", install=install) is None


def test_linux_find_proton_prefix_launch_options(tmp_path):
    from core.platform.linux import LinuxPlatform

    linux = LinuxPlatform()
    custom_wine = tmp_path / "custom_wine_prefix"
    custom_wine.mkdir()

    opts = f'WINEPREFIX="{custom_wine}" %command%'
    found = linux.find_proton_prefix("12345", launch_options=opts)

    assert found == custom_wine
