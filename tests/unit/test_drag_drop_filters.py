from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QMimeData, QUrl

from ui.screens.shortcut_list_screen import ShortcutListScreen


def test_file_dialog_filter_uses_platform(qtbot):
    """Verify that clicking '+ Add Shortcut' queries platform.file_dialog_filter."""
    mock_platform = MagicMock()
    mock_platform.file_dialog_filter = "Custom Filter (*.exe)"

    with patch(
        "ui.screens.shortcut_list_screen.get_platform", return_value=mock_platform
    ):
        screen = ShortcutListScreen()
        qtbot.addWidget(screen)

        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=("", "")
        ) as mock_dialog:
            screen._on_add_clicked()
            mock_dialog.assert_called_once_with(
                screen, "Select Game", "", "Custom Filter (*.exe)"
            )


def test_extract_droppable_path_linux_rejects_lnk(qtbot, tmp_path: Path):
    """On Linux platform, .lnk files must not be accepted as droppable."""
    fake_lnk = tmp_path / "game.lnk"
    fake_lnk.touch()

    mock_platform = MagicMock()
    mock_platform.droppable_extensions = (".exe",)

    with patch(
        "ui.screens.shortcut_list_screen.get_platform", return_value=mock_platform
    ):
        screen = ShortcutListScreen()
        qtbot.addWidget(screen)

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(fake_lnk))])
        assert screen._extract_droppable_path(mime) is None


def test_extract_droppable_path_accepts_valid_exe(qtbot, tmp_path: Path):
    """Valid .exe must be accepted."""
    fake_exe = tmp_path / "game.exe"
    fake_exe.touch()

    mock_platform = MagicMock()
    mock_platform.droppable_extensions = (".exe",)

    with patch(
        "ui.screens.shortcut_list_screen.get_platform", return_value=mock_platform
    ):
        screen = ShortcutListScreen()
        qtbot.addWidget(screen)

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(fake_exe))])
        result = screen._extract_droppable_path(mime)
        assert result is not None
        assert Path(result) == fake_exe


def test_on_shortcut_resolved_warns_on_installer_path(qtbot):
    """Verify that resolving an installer path prompts a confirmation and respects cancellation."""
    from PySide6 import QtWidgets

    from core.steam import SteamUserShortcuts

    mock_platform = MagicMock()
    mock_platform.path_warnings.return_value = [
        "This file appears to be an installer or redistributable, not a game executable."
    ]

    with patch(
        "ui.screens.shortcut_list_screen.get_platform", return_value=mock_platform
    ):
        screen = ShortcutListScreen()
        qtbot.addWidget(screen)

        dummy_user = SteamUserShortcuts(
            userdata_id="12345",
            steam_id64=None,
            persona_name="Gamer",
            shortcuts_path="/tmp/shortcuts.vdf",
            shortcut_count=0,
            avatar_path=None,
            install=None,
        )
        screen._current_user_obj = dummy_user

        # Simulate user choosing 'No' on the warning dialog
        with patch.object(
            QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No
        ) as mock_question:
            with patch.object(QtWidgets.QInputDialog, "getText") as mock_input:
                screen._on_shortcut_resolved(
                    "/tmp/setup.exe", "/tmp/setup.exe", "Setup"
                )
                mock_question.assert_called_once()
                # Name dialog must not be reached if user cancels the warning
                mock_input.assert_not_called()
