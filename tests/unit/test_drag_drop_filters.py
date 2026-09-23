from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QMimeData, QUrl

from ui.screens.shortcut_list_screen import ShortcutListScreen


def test_file_dialog_filter_uses_platform(qtbot):
    """Verify that clicking '+ Add Shortcut' queries platform.file_dialog_filter."""
    mock_platform = MagicMock()
    mock_platform.file_dialog_filter = "Custom Filter (*.exe)"

    with patch("ui.screens.shortcut_list_screen.get_platform", return_value=mock_platform):
        screen = ShortcutListScreen()
        qtbot.addWidget(screen)

        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=("", "")) as mock_dialog:
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

    with patch("ui.screens.shortcut_list_screen.get_platform", return_value=mock_platform):
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

    with patch("ui.screens.shortcut_list_screen.get_platform", return_value=mock_platform):
        screen = ShortcutListScreen()
        qtbot.addWidget(screen)

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(fake_exe))])
        assert screen._extract_droppable_path(mime) == str(fake_exe)
