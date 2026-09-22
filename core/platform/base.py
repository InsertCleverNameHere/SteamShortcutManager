"""
core/platform/base.py
Protocol and data structures defining platform-specific services.
All OS-specific logic (Windows, Linux) sits behind this interface.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

InstallKind = Literal["native", "flatpak", "custom"]


@dataclass(frozen=True)
class SteamInstall:
    """Represents a discovered Steam installation directory and its environment."""

    path: Path
    kind: InstallKind
    label: str  # e.g. "Steam (Native)", "Steam (Flatpak)"


@runtime_checkable
class PlatformServices(Protocol):
    """Abstract interface for all OS-dependent operations."""

    name: str  # "windows" | "linux"
    droppable_extensions: tuple[str, ...]
    file_dialog_filter: str

    def discover_steam_installs(self) -> list[SteamInstall]:
        """Discovers all valid Steam installations on the system."""
        ...

    def is_valid_steam_dir(self, path: Path | str) -> bool:
        """Returns True if the path contains a valid Steam root directory."""
        ...

    def is_steam_running(self, install: SteamInstall | None = None) -> bool | None:
        """
        Returns True if Steam is actively running, False if stopped,
        or None if running state cannot be determined (e.g. inside a strict sandbox).
        """
        ...

    def request_steam_shutdown(self, install: SteamInstall | None = None) -> bool:
        """Requests Steam to shut down gracefully. Returns True if command sent."""
        ...

    def format_start_dir(self, exe_path: str) -> str:
        """Formats the StartDir string for a shortcut according to OS conventions."""
        ...

    def steam_dir_placeholder(self) -> str:
        """Returns typical default path placeholder for the manual setup screen."""
        ...

    def is_sandboxed(self) -> bool:
        """Returns True if the app itself is running in a sandbox (e.g. Flatpak)."""
        ...

    def path_warnings(
        self, exe_path: str, install: SteamInstall | None = None
    ) -> list[str]:
        """Returns user-facing warning strings if the game path has compatibility risks."""
        ...
