"""
core/platform/linux.py
Linux-specific platform services implementation (Bazzite, SteamOS, standard distros).
"""

import os
import subprocess
from pathlib import Path

import psutil

from core.platform.base import InstallKind, PlatformServices, SteamInstall


class LinuxPlatform(PlatformServices):
    name = "linux"
    droppable_extensions = (".exe",)
    file_dialog_filter = "Windows Executables (*.exe);;All Files (*.*)"

    # Candidate directories to discover on Linux (expanduser + resolve symlinks)
    CANDIDATES: list[tuple[str, InstallKind, str]] = [
        ("~/.local/share/Steam", "native", "Steam (Native)"),
        ("~/.steam/steam", "native", "Steam (Native)"),
        ("~/.steam/debian-installation", "native", "Steam (Debian)"),
        (
            "~/.var/app/com.valvesoftware.Steam/.local/share/Steam",
            "flatpak",
            "Steam (Flatpak)",
        ),
    ]

    def discover_steam_installs(self) -> list[SteamInstall]:
        results: list[SteamInstall] = []
        seen_paths: set[Path] = set()

        for raw_path, kind, label in self.CANDIDATES:
            expanded = Path(os.path.expanduser(raw_path))
            if not expanded.exists():
                continue

            try:
                resolved = expanded.resolve()
            except OSError:
                resolved = expanded

            if resolved in seen_paths:
                continue

            if self.is_valid_steam_dir(resolved):
                seen_paths.add(resolved)
                results.append(
                    SteamInstall(
                        path=resolved,
                        kind=kind,
                        label=label,
                    )
                )

        return results

    def is_valid_steam_dir(self, path: Path | str) -> bool:
        p = Path(path)
        if not p.is_dir():
            return False
        # On Linux, userdata/ is the universal indicator
        return (p / "userdata").is_dir()

    def is_steam_running(self, install: SteamInstall | None = None) -> bool | None:
        """
        Fast two-factor check:
        1. Check ~/.steam/steam.pid
        2. Fall back to scanning active processes for 'steam'
        """
        pid_file = Path.home() / ".steam" / "steam.pid"
        if pid_file.is_file():
            try:
                pid_str = pid_file.read_text().strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    proc_comm = Path(f"/proc/{pid}/comm")
                    if proc_comm.is_file():
                        comm = proc_comm.read_text().strip().lower()
                        if "steam" in comm:
                            return True
            except OSError:
                pass

        # Fallback via psutil
        try:
            for proc in psutil.process_iter(attrs=["name"]):
                name = proc.info.get("name")
                if name and name.lower() == "steam":
                    return True
            return False
        except Exception:
            return None

    def request_steam_shutdown(self, install: SteamInstall | None = None) -> bool:
        """Attempts graceful shutdown via 'steam -shutdown'."""
        try:
            cmd = ["steam", "-shutdown"]
            if install and install.kind == "flatpak":
                cmd = ["flatpak", "run", "com.valvesoftware.Steam", "-shutdown"]

            subprocess.run(
                cmd,
                check=False,
                timeout=5,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def format_start_dir(self, exe_path: str) -> str:
        """Native Steam on Linux uses forward slashes, trailing slash, no quotes."""
        clean_exe = exe_path.strip().strip('"')
        parent = os.path.dirname(clean_exe)
        return f"{parent}/"

    def steam_dir_placeholder(self) -> str:
        return "~/.local/share/Steam"

    def is_sandboxed(self) -> bool:
        """Detects if we are running inside Flatpak or Snap sandbox."""
        return Path("/.flatpak-info").exists() or "SNAP" in os.environ

    def path_warnings(
        self, exe_path: str, install: SteamInstall | None = None
    ) -> list[str]:
        warnings = []
        clean_path = exe_path.strip().strip('"')
        filename = os.path.basename(clean_path).lower()

        if any(
            filename.startswith(prefix)
            for prefix in ("setup", "unins", "vc_redist", "dxsetup")
        ):
            warnings.append(
                "This file appears to be an installer or redistributable, not a game executable."
            )

        # Check for NTFS / fuseblk filesystem mounts (Phase 0 finding)
        try:
            mountinfo = Path("/proc/self/mountinfo")
            if mountinfo.is_file():
                for line in mountinfo.read_text(errors="replace").splitlines():
                    parts = line.split(" - ")
                    if len(parts) == 2:
                        m_pt = parts[0].split()[4]
                        fs_type = parts[1].split()[0].lower()
                        if fs_type in ("fuseblk", "ntfs", "ntfs3", "vfat", "exfat"):
                            if clean_path.startswith(m_pt):
                                warnings.append(
                                    f"The game is located on a {fs_type.upper()} partition ('{m_pt}'). "
                                    "Games on NTFS/FAT drives often encounter permission issues under Proton."
                                )
                                break
        except Exception:
            pass

        return warnings
