"""
core/log.py
Centralized rotating file logger for Steam Shortcut Manager.
Logs to OS-standard app data/log directories with console mirroring in dev.
"""

import logging
import os
import sys
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "ssm"
_log_file_path: Path | None = None


def get_log_dir() -> Path:
    """Determines the standard directory for application logs based on OS."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        log_dir = Path(base) / "SteamShortcutManager" / "logs"
    elif sys.platform.startswith("linux"):
        state_home = os.environ.get(
            "XDG_STATE_HOME", os.path.expanduser("~/.local/state")
        )
        log_dir = Path(state_home) / "steam-shortcut-manager" / "logs"
    else:
        log_dir = Path.home() / ".steam-shortcut-manager" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(level: int = logging.DEBUG) -> Path:
    """
    Initializes or updates the application logger with console and rotating file handlers.
    Ensures app.log is created in the active log directory.
    """
    global _log_file_path
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)

    target_log_dir = get_log_dir()
    target_log_file = target_log_dir / "app.log"

    # Check if a file handler already points to the current active log directory
    has_target_handler = False
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler):
            if Path(handler.baseFilename).resolve() == target_log_file.resolve():
                has_target_handler = True
            else:
                logger.removeHandler(handler)
                handler.close()

    _log_file_path = target_log_file

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Console handler (only attach if sys.stdout is available, preventing windowed crashes)
    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in logger.handlers
    )
    if not has_console and sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 2. Rotating file handler with fallbacks
    if not has_target_handler:
        try:
            file_handler = RotatingFileHandler(
                str(target_log_file),
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            # Guarantee the log file exists on disk
            if not target_log_file.is_file():
                try:
                    target_log_file.touch()
                except OSError:
                    pass
        except OSError:
            # Fall back to OS temp directory if state dir is unwritable
            try:
                fallback_log = (
                    Path(tempfile.gettempdir()) / "steam-shortcut-manager-app.log"
                )
                file_handler = RotatingFileHandler(
                    str(fallback_log),
                    maxBytes=1_000_000,
                    backupCount=3,
                    encoding="utf-8",
                )
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                _log_file_path = fallback_log
            except OSError:
                # Last resort fallback: NullHandler so startup never crashes
                logger.addHandler(logging.NullHandler())

    return _log_file_path or target_log_file


def get_logger(module_name: str | None = None) -> logging.Logger:
    """Returns a child logger scoped to the calling module."""
    if module_name:
        clean_name = module_name.replace("core.", "").replace("ui.", "")
        return logging.getLogger(f"{LOGGER_NAME}.{clean_name}")
    return logging.getLogger(LOGGER_NAME)


def get_recent_log_lines(count: int = 200) -> list[str]:
    """Reads and returns the last N lines from the active log file (for diagnostics)."""
    log_file = _log_file_path or (get_log_dir() / "app.log")
    if not log_file.is_file():
        return []

    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-count:]
    except Exception:
        return []
