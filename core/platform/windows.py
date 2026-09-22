"""
core/platform/windows.py
Windows-specific platform services implementation.
"""

import ntpath
import subprocess
from pathlib import Path

import psutil

from core.platform.base import PlatformServices, SteamInstall

try:
    import winreg
except ImportError:
    winreg = None  # None when running or testing on Linux


class WindowsPlatform(PlatformServices):
    name = "windows"
    droppable_extensions = (".exe", ".lnk")
    file_dialog_filter = "Games (*.exe *.lnk);;All Files (*.*)"

    DEFAULT_PATHS = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
    ]

    def _get_registry_steam_path(self) -> Path | None:
        """Reads the active Steam installation path from HKCU\\Software\\Valve\\Steam."""
        if winreg is None:
            return None
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"
            ) as key:
                val, _ = winreg.QueryValueEx(key, "SteamPath")
                if val and isinstance(val, str):
                    resolved = Path(val).resolve()
                    if resolved.is_dir():
                        return resolved
        except OSError:
            pass
        return None

    def discover_steam_installs(self) -> list[SteamInstall]:
        candidates: list[Path] = []

        # 1. Query registry for custom install directory (D:\, E:\, etc.)
        reg_path = self._get_registry_steam_path()
        if reg_path and reg_path not in candidates:
            candidates.append(reg_path)

        # 2. Check standard default paths
        for p_str in self.DEFAULT_PATHS:
            p = Path(p_str)
            if p.is_dir():
                resolved = p.resolve()
                if resolved not in candidates:
                    candidates.append(resolved)

        results: list[SteamInstall] = []
        for path in candidates:
            if self.is_valid_steam_dir(path):
                results.append(
                    SteamInstall(
                        path=path,
                        kind="native",
                        label="Steam (Windows)",
                    )
                )
        return results

    def is_valid_steam_dir(self, path: Path | str) -> bool:
        p = Path(path)
        if not p.is_dir():
            return False
        has_exe = (p / "steam.exe").is_file()
        has_userdata = (p / "userdata").is_dir()
        return has_exe or has_userdata

    def is_steam_running(self, install: SteamInstall | None = None) -> bool | None:
        try:
            for proc in psutil.process_iter(attrs=["name"]):
                name = proc.info.get("name")
                if name and name.lower() == "steam.exe":
                    return True
            return False
        except Exception:
            return None

    def request_steam_shutdown(self, install: SteamInstall | None = None) -> bool:
        steam_exe = None
        if install and (install.path / "steam.exe").is_file():
            steam_exe = install.path / "steam.exe"
        else:
            for p_str in self.DEFAULT_PATHS:
                cand = Path(p_str) / "steam.exe"
                if cand.is_file():
                    steam_exe = cand
                    break

        if steam_exe:
            try:
                subprocess.run(
                    [str(steam_exe), "-shutdown"],
                    check=False,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return True
            except Exception:
                pass
        return False

    def format_start_dir(self, exe_path: str) -> str:
        clean_exe = exe_path.strip().strip('"')
        parent = ntpath.dirname(clean_exe)
        return f'"{parent}\\"'

    def steam_dir_placeholder(self) -> str:
        return r"C:\Program Files (x86)\Steam"

    def is_sandboxed(self) -> bool:
        return False

    def path_warnings(
        self, exe_path: str, install: SteamInstall | None = None
    ) -> list[str]:
        warnings = []
        filename = ntpath.basename(exe_path).lower()
        if any(
            filename.startswith(prefix)
            for prefix in ("setup", "unins", "vc_redist", "dxsetup")
        ):
            warnings.append(
                "This file appears to be an installer or redistributable, not a game executable."
            )
        return warnings
