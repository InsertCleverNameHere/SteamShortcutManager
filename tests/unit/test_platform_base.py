from pathlib import Path

from core.platform.base import PlatformServices, SteamInstall


def test_steam_install_dataclass():
    install = SteamInstall(
        path=Path("/home/user/.steam"), kind="native", label="Steam (Native)"
    )
    assert install.path == Path("/home/user/.steam")
    assert install.kind == "native"
    assert install.label == "Steam (Native)"


def test_platform_services_protocol_conformance():
    class DummyPlatform:
        name = "dummy"
        droppable_extensions = (".exe",)
        file_dialog_filter = "All Files (*.*)"

        def discover_steam_installs(self):
            return []

        def is_valid_steam_dir(self, path):
            return True

        def is_steam_running(self, install=None):
            return False

        def request_steam_shutdown(self, install=None):
            return True

        def format_start_dir(self, exe_path):
            return "/dir/"

        def steam_dir_placeholder(self):
            return "/path"

        def is_sandboxed(self):
            return False

        def path_warnings(self, exe_path, install=None):
            return []

    dummy = DummyPlatform()
    assert isinstance(dummy, PlatformServices)
