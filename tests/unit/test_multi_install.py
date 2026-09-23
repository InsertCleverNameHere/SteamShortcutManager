from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6 import QtWidgets

from core.platform.base import SteamInstall
from core.steam import SteamUserShortcuts, find_all_shortcuts
from ui.screens.library_screen import LibraryScreen
from ui.widgets.user_card import UserCard


def test_find_all_shortcuts_aggregates_multiple_installs():
    install1 = SteamInstall(
        path=Path("/steam/native"), kind="native", label="Steam (Native)"
    )
    install2 = SteamInstall(
        path=Path("/steam/flatpak"), kind="flatpak", label="Steam (Flatpak)"
    )

    mock_platform = MagicMock()
    mock_platform.discover_steam_installs.return_value = [install1, install2]

    user1 = SteamUserShortcuts("1", None, "User Native", "/path/1", 1, None, install1)
    user2 = SteamUserShortcuts("2", None, "User Flatpak", "/path/2", 2, None, install2)

    with patch("core.steam.get_platform", return_value=mock_platform):
        with patch("core.steam.find_shortcuts", side_effect=[[user1], [user2]]):
            all_users = find_all_shortcuts()
            assert len(all_users) == 2
            assert all_users[0].install == install1
            assert all_users[1].install == install2


def test_user_card_shows_install_label(qtbot):
    install = SteamInstall(path=Path("/test"), kind="native", label="Steam (Native)")
    user = SteamUserShortcuts("123", None, "Gamer", "/path", 0, None, install)

    card = UserCard(user)
    qtbot.addWidget(card)
    labels = [lbl.text() for lbl in card.findChildren(QtWidgets.QLabel)]
    assert any("Steam (Native)" in text for text in labels)


def test_library_screen_groups_multiple_installs(qtbot):
    install1 = SteamInstall(path=Path("/1"), kind="native", label="Native Steam")
    install2 = SteamInstall(path=Path("/2"), kind="flatpak", label="Flatpak Steam")

    user1 = SteamUserShortcuts("1", None, "U1", "/p1", 1, None, install1)
    user2 = SteamUserShortcuts("2", None, "U2", "/p2", 2, None, install2)

    screen = LibraryScreen()
    qtbot.addWidget(screen)
    screen.populate([user1, user2])

    assert len(screen._cards) == 2
