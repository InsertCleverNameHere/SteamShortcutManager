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

    # Candidate directories to discover on Linux (expand vars + expanduser + dedupe)
    CANDIDATES: list[tuple[str, InstallKind, str]] = [
        ("~/.local/share/Steam", "native", "Steam (Native)"),
        ("$XDG_DATA_HOME/Steam", "native", "Steam (Native)"),
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
            # Expand environment variables ($XDG_DATA_HOME) and tildes (~)
            expanded_str = os.path.expanduser(os.path.expandvars(raw_path))
            if "$" in expanded_str:  # Unset environment variable, skip
                continue

            expanded = Path(expanded_str)
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
        # Expand user tilde (~) and environment variables
        expanded = os.path.expanduser(os.path.expandvars(str(path)))
        p = Path(expanded)
        if not p.is_dir():
            return False
        # On Linux, userdata/ is the universal indicator
        return (p / "userdata").is_dir()

    def _read_registry_vdf_active(
        self, install: SteamInstall | None = None
    ) -> bool | None:
        """
        Inspects registry.vdf under ActiveProcess to check if Steam is flagged running.
        Returns True if running, False if stopped (pid is 0), or None if file cannot be read.
        """
        # Determine registry.vdf location (Native vs Flatpak)
        candidates = [
            Path.home() / ".steam" / "registry.vdf",
            Path.home() / ".local" / "share" / "Steam" / "registry.vdf",
            Path.home()
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / ".steam"
            / "registry.vdf",
        ]
        if install and install.path:
            candidates.insert(0, install.path / "registry.vdf")

        for reg_path in candidates:
            if not reg_path.is_file():
                continue
            try:
                # Text VDF parse of registry.vdf
                import vdf

                with open(reg_path, encoding="utf-8", errors="replace") as f:
                    data = vdf.load(f)

                # Search case-insensitively for Registry -> HKCU -> Software -> Valve -> Steam -> ActiveProcess
                reg_root = data.get("Registry", data.get("registry", {}))
                hkcu = reg_root.get("HKCU", reg_root.get("hkcu", {}))
                software = hkcu.get("Software", hkcu.get("software", {}))
                valve = software.get("Valve", software.get("valve", {}))
                steam = valve.get("Steam", valve.get("steam", {}))
                active_proc = steam.get("ActiveProcess", steam.get("activeprocess", {}))

                pid_val = str(
                    active_proc.get("pid", active_proc.get("PID", "0"))
                ).strip()
                active_user = str(active_proc.get("ActiveUser", "0")).strip()

                if pid_val.isdigit() and int(pid_val) > 0 and active_user != "0":
                    return True
                if pid_val == "0":
                    return False
            except Exception:
                continue

        return None

    def is_steam_running(self, install: SteamInstall | None = None) -> bool | None:
        """
        Three-tier detection:
        1. Preferred: psutil scan for process named 'steam'
        2. PID check: ~/.steam/steam.pid
        3. Sandbox fallback: ~/.steam/registry.vdf ActiveProcess
        """
        # 1. Preferred psutil process scan
        try:
            for proc in psutil.process_iter(attrs=["name"]):
                name = proc.info.get("name")
                if name and name.lower() == "steam":
                    return True
        except Exception:
            pass

        # 2. Check ~/.steam/steam.pid
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

        # 3. Sandbox fallback via registry.vdf
        reg_active = self._read_registry_vdf_active(install)
        if reg_active is not None:
            return reg_active

        # If inside a sandbox and no process or registry info could be verified, return None (unknown)
        if self.is_sandboxed():
            return None

        return False

    def request_steam_shutdown(self, install: SteamInstall | None = None) -> bool:
        """
        Attempts graceful Steam shutdown:
        - Native: 'steam -shutdown' (only allowed when not sandboxed)
        - Flatpak: 'flatpak run com.valvesoftware.Steam -shutdown'
        """
        is_flatpak = install is not None and install.kind == "flatpak"

        # Host commands to native Steam are blocked from inside a sandbox
        if self.is_sandboxed() and not is_flatpak:
            return False

        cmd = (
            ["flatpak", "run", "com.valvesoftware.Steam", "-shutdown"]
            if is_flatpak
            else ["steam", "-shutdown"]
        )

        # Sanitize environment: strip AppImage runtime variables before launching subprocesses
        clean_env = os.environ.copy()
        for var in ("PYTHONHOME", "PYTHONPATH", "APPIMAGE", "APPDIR"):
            clean_env.pop(var, None)
        ld_path = clean_env.get("LD_LIBRARY_PATH", "")
        if ld_path:
            cleaned_paths = [p for p in ld_path.split(":") if not p.startswith("/tmp/.mount_")]
            clean_env["LD_LIBRARY_PATH"] = ":".join(cleaned_paths)

        try:
            subprocess.run(
                cmd,
                env=clean_env,
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
