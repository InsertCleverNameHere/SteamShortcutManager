from pathlib import Path

from core.platform.base import PlatformServices, SteamInstall
from core.platform.linux import LinuxPlatform
from core.platform.windows import WindowsPlatform


def test_steam_install_dataclass():
    install = SteamInstall(
        path=Path("/home/user/.steam"), kind="native", label="Steam (Native)"
    )
    assert install.path == Path("/home/user/.steam")
    assert install.kind == "native"
    assert install.label == "Steam (Native)"


def test_production_platforms_satisfy_protocol():
    """Verify that both production platform classes satisfy PlatformServices."""
    linux_platform = LinuxPlatform()
    windows_platform = WindowsPlatform()

    assert isinstance(linux_platform, PlatformServices)
    assert isinstance(windows_platform, PlatformServices)
