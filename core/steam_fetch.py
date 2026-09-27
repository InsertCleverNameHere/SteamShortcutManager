"""
core/steam_fetch.py
Parent-side IPC manager for isolated Steam PICS product information queries.
Spawns the application executable in child mode, monitors progress via NDJSON,
and provides deterministic cancellation and timeout handling.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.log import get_logger
from ui.tasks import CancelToken, TaskCancelledError

logger = get_logger("steam_fetch")


class SteamFetchError(Exception):
    """Base exception for Steam PICS fetch failures."""


class SteamFetchTimeoutError(SteamFetchError):
    """Raised when Steam servers do not respond within the deadline."""


class SteamAppNotFoundError(SteamFetchError):
    """Raised when an AppID is not found on Steam."""


def _get_subprocess_cmd(appid: int | str) -> list[str]:
    """Determines the appropriate command to self-spawn the application."""
    if getattr(sys, "frozen", False):
        # Running as PyInstaller executable or inside AppImage
        return [sys.executable, "--fetch-product-info", str(appid)]
    else:
        # Running from source
        repo_root = Path(__file__).resolve().parent.parent
        main_py = str(repo_root / "main.py")
        return [sys.executable, main_py, "--fetch-product-info", str(appid)]


def fetch_product_info(
    steam_appid: int | str,
    token: CancelToken | None = None,
    status_callback: Callable[[str], None] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Fetches product information for steam_appid via an isolated child process.

    Args:
        steam_appid: Target Steam AppID.
        token: Optional CancelToken for cooperative abortion.
        status_callback: Optional callable for human-readable status updates.
        timeout: Maximum seconds to wait before terminating child process.

    Returns:
        dict containing library_assets_full, library_assets, and clienticon.

    Raises:
        TaskCancelledError: If token was cancelled.
        SteamFetchTimeoutError: If fetch exceeded timeout.
        SteamAppNotFoundError: If AppID does not exist on Steam.
        SteamFetchError: If SteamClient failed or output was invalid.
    """
    if token and token.is_cancelled:
        raise TaskCancelledError("Fetch was cancelled before start.")

    cmd = _get_subprocess_cmd(steam_appid)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )

    line_queue: queue.Queue[str | None] = queue.Queue()

    def reader():
        try:
            if proc.stdout:
                for line in proc.stdout:
                    line_queue.put(line)
        except Exception:
            pass
        finally:
            line_queue.put(None)

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()

    start_time = time.perf_counter()
    result_payload: dict[str, Any] | None = None
    last_error: str | None = None
    error_kind: str | None = None

    try:
        while True:
            # 1. Check cancellation token
            if token and token.is_cancelled:
                proc.kill()
                proc.wait()
                raise TaskCancelledError("Steam metadata fetch cancelled.")

            # 2. Check timeout
            elapsed = time.perf_counter() - start_time
            if elapsed > timeout:
                proc.kill()
                proc.wait()
                raise SteamFetchTimeoutError(
                    f"Timed out fetching metadata for AppID {steam_appid} after {timeout:.0f}s."
                )

            # 3. Read pending output lines
            try:
                line = line_queue.get(timeout=0.05)
            except queue.Empty:
                if proc.poll() is not None and line_queue.empty():
                    break
                continue

            if line is None:
                # Reader reached EOF
                break

            stripped = line.strip()
            if not stripped:
                continue

            try:
                msg = json.loads(stripped)
            except json.JSONDecodeError:
                logger.debug(f"Unparsed child process output: {stripped}")
                continue

            msg_type = msg.get("type")
            if msg_type == "status":
                status_text = msg.get("message", "")
                if status_callback:
                    status_callback(status_text)
                if token:
                    token.report_progress(status_text)

            elif msg_type == "result":
                result_payload = msg.get("payload")

            elif msg_type == "error":
                error_kind = msg.get("error")
                last_error = msg.get("message", "Unknown error")

        proc.wait(timeout=2.0)

    except Exception:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise

    if proc.returncode != 0 or result_payload is None:
        if error_kind == "not_found":
            raise SteamAppNotFoundError(
                last_error or f"AppID {steam_appid} not found on Steam."
            )
        stderr_output = proc.stderr.read().strip() if proc.stderr else ""
        detail = (
            last_error or stderr_output or f"Process exited with code {proc.returncode}"
        )
        raise SteamFetchError(f"Failed to fetch Steam product info: {detail}")

    return result_payload
