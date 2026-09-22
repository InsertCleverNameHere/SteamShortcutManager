from unittest.mock import MagicMock, patch

from ui.widgets.steam_guard import confirm_steam_closed, reset_session_warning


def test_confirm_steam_closed_returns_true_when_not_running(qtbot):
    """When Steam is confirmed not running, allow write immediately without dialog."""
    mock_platform = MagicMock()
    mock_platform.is_steam_running.return_value = False

    with patch("ui.widgets.steam_guard.get_platform", return_value=mock_platform):
        assert confirm_steam_closed(None) is True


def test_confirm_steam_closed_warns_once_per_session_when_unknown(qtbot):
    """When running status is unknown (None), warn once per session then proceed silently."""
    reset_session_warning()
    mock_platform = MagicMock()
    mock_platform.is_steam_running.return_value = None

    with patch("ui.widgets.steam_guard.get_platform", return_value=mock_platform):
        with patch("PySide6.QtWidgets.QMessageBox.information") as mock_info:
            # First call in session: shows notice and proceeds
            res1 = confirm_steam_closed(None)
            assert res1 is True
            assert mock_info.call_count == 1

            # Second call in same session: proceeds silently without popping notice again
            res2 = confirm_steam_closed(None)
            assert res2 is True
            assert mock_info.call_count == 1
