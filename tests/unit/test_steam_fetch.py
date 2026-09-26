"""
tests/unit/test_steam_fetch.py
Hermetic unit tests for core.steam_fetch.
Validates child-process IPC parsing, timeout handling, and cancellation.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.steam_fetch import (
    SteamAppNotFoundError,
    SteamFetchTimeoutError,
    fetch_product_info,
)
from ui.tasks import CancelToken, TaskCancelledError


def test_fetch_product_info_success():
    """Verify that successful NDJSON stdout yields the expected dictionary."""
    mock_payload = {
        "appid": 400,
        "name": "Portal",
        "library_assets_full": {"library_capsule": {}},
        "library_assets": {},
        "clienticon": "abc123iconhash",
    }
    ndjson_lines = [
        json.dumps({"type": "status", "message": "Connecting to Steam..."}) + "\n",
        json.dumps({"type": "status", "message": "Fetching metadata..."}) + "\n",
        json.dumps({"type": "result", "payload": mock_payload}) + "\n",
    ]

    mock_proc = MagicMock()
    mock_proc.stdout = ndjson_lines
    mock_proc.poll.side_effect = [None, None, 0]
    mock_proc.returncode = 0

    with patch("subprocess.Popen", return_value=mock_proc):
        statuses = []
        result = fetch_product_info(
            400,
            status_callback=lambda s: statuses.append(s),
            timeout=5.0,
        )

        assert result == mock_payload
        assert statuses == ["Connecting to Steam...", "Fetching metadata..."]


def test_fetch_product_info_app_not_found():
    """Verify that child process returning not_found raises SteamAppNotFoundError."""
    ndjson_lines = [
        json.dumps(
            {
                "type": "error",
                "error": "not_found",
                "message": "AppID 999 not found on Steam.",
            }
        )
        + "\n",
    ]

    mock_proc = MagicMock()
    mock_proc.stdout = ndjson_lines
    mock_proc.poll.side_effect = [None, 1]
    mock_proc.returncode = 1

    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(SteamAppNotFoundError) as exc_info:
            fetch_product_info(999, timeout=5.0)

        assert "not found" in str(exc_info.value).lower()


def test_fetch_product_info_cancellation():
    """Verify that cancelling token terminates the child process and raises TaskCancelledError."""
    token = CancelToken()

    mock_proc = MagicMock()
    # Emulate an unresponsive pipe loop
    mock_proc.stdout = []
    mock_proc.poll.return_value = None

    # Cancel the token immediately before calling
    token.cancel()

    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(TaskCancelledError):
            fetch_product_info(400, token=token, timeout=5.0)


def test_fetch_product_info_timeout():
    """Verify that exceeding deadline kills the child process and raises SteamFetchTimeoutError."""
    import time

    def hanging_stdout():
        # Emulate an open pipe that produces no output and does not close
        time.sleep(0.5)
        yield "never reached\n"

    mock_proc = MagicMock()
    mock_proc.stdout = hanging_stdout()
    mock_proc.poll.return_value = None

    with patch("subprocess.Popen", return_value=mock_proc):
        with pytest.raises(SteamFetchTimeoutError):
            fetch_product_info(400, timeout=0.05)

        # Must have forcibly terminated the child process
        mock_proc.kill.assert_called()
