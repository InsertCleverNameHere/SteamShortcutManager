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

        clean_env = self._get_clean_host_env()

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

    def _get_clean_host_env(self) -> dict[str, str]:
        """
        Creates an execution environment safe for launching host binaries from an AppImage.
        Strips PyInstaller bundled paths, mount directories, and runtime overrides.
        """
        env = os.environ.copy()
        mount_dir = env.get("APPDIR", "")

        # 1. Restore or cleanse LD_LIBRARY_PATH
        orig_ld = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig_ld:
            # If LD_LIBRARY_PATH_ORIG exists, filter out any references to the AppImage mount
            clean_ld_parts = [
                p
                for p in orig_ld.split(":")
                if p and (not mount_dir or mount_dir not in p)
            ]
            if clean_ld_parts:
                env["LD_LIBRARY_PATH"] = ":".join(clean_ld_parts)
            else:
                env.pop("LD_LIBRARY_PATH", None)
        else:
            env.pop("LD_LIBRARY_PATH", None)

        # 2. Clean PATH of AppImage mount directories
        orig_path = env.get("PATH", "")
        if orig_path:
            clean_path_parts = [
                p
                for p in orig_path.split(":")
                if p and (not mount_dir or mount_dir not in p)
            ]
            env["PATH"] = ":".join(clean_path_parts)

        # 3. Strip Python, AppImage, and Qt runtime isolation variables
        for var in (
            "PYTHONHOME",
            "PYTHONPATH",
            "APPIMAGE",
            "APPDIR",
            "QT_PLUGIN_PATH",
            "QML2_IMPORT_PATH",
        ):
            env.pop(var, None)

        return env

    def open_folder(self, path: Path | str) -> bool:
        target = Path(path).resolve()
        if not target.is_dir():
            return False

        clean_env = self._get_clean_host_env()

        target_uri = target.as_uri()

        # Method 1: org.freedesktop.FileManager1.ShowFolders (native Dolphin / file manager D-Bus)
        try:
            ret = subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--dest=org.freedesktop.FileManager1",
                    "--type=method_call",
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowFolders",
                    f"array:string:{target_uri}",
                    "string:",
                ],
                env=clean_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=2,
            )
            if ret.returncode == 0:
                return True
        except Exception:
            pass

        # Method 2: org.freedesktop.portal.OpenURI (desktop portal D-Bus)
        try:
            ret = subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--dest=org.freedesktop.portal.Desktop",
                    "--type=method_call",
                    "/org/freedesktop/portal/desktop",
                    "org.freedesktop.portal.OpenURI.OpenURI",
                    "string:",
                    f"string:{target_uri}",
                    "dict:string:variant:",
                ],
                env=clean_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=2,
            )
            if ret.returncode == 0:
                return True
        except Exception:
            pass

        # Method 3: Fallback to xdg-open with sanitized host environment
        try:
            subprocess.Popen(
                ["xdg-open", str(target)],
                env=clean_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except Exception:
            return False

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

    def _get_library_folders(self, steam_root: Path) -> list[Path]:
        """Reads all library folder paths from steamapps/libraryfolders.vdf."""
        libs = [steam_root]
        lib_vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        if not lib_vdf.is_file():
            lib_vdf = steam_root / "config" / "libraryfolders.vdf"
            if not lib_vdf.is_file():
                return libs

        try:
            import vdf

            with open(lib_vdf, encoding="utf-8", errors="replace") as f:
                data = vdf.load(f)

            root_key = data.get("libraryfolders", data.get("LibraryFolders", {}))
            for k, val in root_key.items():
                if isinstance(val, dict):
                    raw_p = val.get("path")
                    if raw_p:
                        p = Path(raw_p)
                        if p.is_dir() and p not in libs:
                            libs.append(p)
                elif isinstance(val, str) and k.isdigit():
                    p = Path(val)
                    if p.is_dir() and p not in libs:
                        libs.append(p)
        except Exception:
            pass

        return libs

    def find_proton_prefix(
        self,
        appid: str,
        install: SteamInstall | None = None,
        launch_options: str = "",
    ) -> Path | None:
        """
        Locates the Wine or Proton prefix directory for an AppID on Linux:
        1. Checks WINEPREFIX= or STEAM_COMPAT_DATA_PATH= in launch_options.
        2. Searches steamapps/compatdata/<appid>/pfx across all Steam library folders.
        """
        import re

        clean_appid = str(appid).strip()
        if not clean_appid or clean_appid == "0":
            return None

        # 1. Check explicit environment variables in launch_options
        if launch_options:
            wine_match = re.search(
                r'WINEPREFIX=(?:"([^"]+)"|\'([^\']+)\'|(\S+))', launch_options
            )
            if wine_match:
                raw_pfx = (
                    wine_match.group(1) or wine_match.group(2) or wine_match.group(3)
                )
                p = Path(os.path.expanduser(os.path.expandvars(raw_pfx)))
                if p.is_dir():
                    return p

            compat_match = re.search(
                r'STEAM_COMPAT_DATA_PATH=(?:"([^"]+)"|\'([^\']+)\'|(\S+))',
                launch_options,
            )
            if compat_match:
                raw_compat = (
                    compat_match.group(1)
                    or compat_match.group(2)
                    or compat_match.group(3)
                )
                base_compat = Path(os.path.expanduser(os.path.expandvars(raw_compat)))
                for cand in (
                    base_compat / clean_appid / "pfx",
                    base_compat / clean_appid,
                    base_compat / "pfx",
                    base_compat,
                ):
                    if cand.is_dir():
                        return cand

        # 2. Collect candidate Steam root directories
        steam_roots: list[Path] = []
        if install and install.path and install.path.is_dir():
            steam_roots.append(install.path)
        else:
            for inst in self.discover_steam_installs():
                if inst.path.is_dir() and inst.path not in steam_roots:
                    steam_roots.append(inst.path)

        # 3. Search steamapps/compatdata/<appid> across all library folders
        for root in steam_roots:
            for lib in self._get_library_folders(root):
                pfx_dir = lib / "steamapps" / "compatdata" / clean_appid / "pfx"
                if pfx_dir.is_dir():
                    return pfx_dir
                compat_dir = lib / "steamapps" / "compatdata" / clean_appid
                if compat_dir.is_dir():
                    return compat_dir

        return None
