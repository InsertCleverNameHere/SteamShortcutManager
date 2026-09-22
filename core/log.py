"""
core/log.py
Centralized rotating file logger for Steam Shortcut Manager.
Logs to OS-standard app data/log directories with console mirroring in dev.
"""

import logging
import os
import sys
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
    Initializes the application logger with both console and rotating file handlers.
    Returns the path to the active log file.
    """
    global _log_file_path
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)

    # Avoid adding duplicate handlers if setup_logging is called more than once
    if logger.handlers:
        return _log_file_path or (get_log_dir() / "app.log")

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Rotating file handler (keeps up to 3 backups of 1MB each)
    log_dir = get_log_dir()
    log_file = log_dir / "app.log"
    _log_file_path = log_file

    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return log_file


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
