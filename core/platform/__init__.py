"""
core/platform
Platform abstraction layer. Provides get_platform() returning the active PlatformServices.
"""

import sys

from core.platform.base import PlatformServices

_current_platform: PlatformServices | None = None


def get_platform() -> PlatformServices:
    """Returns the singleton PlatformServices instance for the running operating system."""
    global _current_platform
    if _current_platform is not None:
        return _current_platform

    if sys.platform == "win32":
        from core.platform.windows import WindowsPlatform

        _current_platform = WindowsPlatform()
    elif sys.platform.startswith("linux"):
        from core.platform.linux import LinuxPlatform

        _current_platform = LinuxPlatform()
    else:
        # Default fallback for macOS or other Unix-like systems
        from core.platform.linux import LinuxPlatform

        _current_platform = LinuxPlatform()

    return _current_platform


def set_platform_override(platform_instance: PlatformServices | None) -> None:
    """Allows unit tests to inject a mock platform instance."""
    global _current_platform
    _current_platform = platform_instance
