from unittest.mock import MagicMock, patch

from ui.screens.setup_screen import SetupScreen


def test_setup_screen_uses_platform_placeholder(qtbot):
    """Verify that SetupScreen queries the platform for its placeholder text."""
    mock_platform = MagicMock()
    mock_platform.name = "linux"
    mock_platform.steam_dir_placeholder.return_value = "~/.local/share/Steam"

    with patch("ui.screens.setup_screen.get_platform", return_value=mock_platform):
        screen = SetupScreen()
        qtbot.addWidget(screen)
        assert screen._path_edit.placeholderText() == "~/.local/share/Steam"
