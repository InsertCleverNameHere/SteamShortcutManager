"""
Library screen — lists all discovered shortcuts.vdf files as selectable cards.
Shown after the Steam directory is confirmed.
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QPushButton,
    QSizePolicy,
    QFrame,
)
from PySide6.QtCore import Qt, Signal

from ui.theme import PALETTE
from ui.widgets.user_card import UserCard
from core.steam import SteamUserShortcuts


class LibraryScreen(QWidget):
    """
    Emits `user_selected(SteamUserShortcuts)` when the user clicks a card
    and then confirms with the "Open" button.
    """

    user_selected = Signal(object)  # SteamUserShortcuts
    change_steam_dir = Signal()

    def refresh_card_data(self):
        """Forces all visible cards to update their labels from their user objects."""
        for card in self._cards:
            card.update_labels()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[UserCard] = []
        self._selected_user: SteamUserShortcuts | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── top bar ──────────────────────────────────────────────────────────
        topbar = QWidget()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(
            f"background-color: {PALETTE['bg_surface']};"
            f"border-bottom: 1px solid {PALETTE['border']};"
        )
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(24, 0, 24, 0)

        app_title = QLabel("Steam Shortcut Manager")
        app_title.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {PALETTE['text_primary']};"
            f"letter-spacing: 0.5px;"
        )
        topbar_layout.addWidget(app_title)
        topbar_layout.addStretch()

        change_btn = QPushButton("Change Steam folder")
        change_btn.setObjectName("secondary")
        change_btn.setFixedHeight(36)
        change_btn.clicked.connect(self.change_steam_dir)
        topbar_layout.addWidget(change_btn)

        root.addWidget(topbar)

        # ── body ─────────────────────────────────────────────────────────────
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(48, 36, 48, 36)
        body_layout.setSpacing(0)

        heading = QLabel("Select a shortcuts file")
        heading.setObjectName("heading")
        body_layout.addWidget(heading)

        body_layout.addSpacing(6)

        self._sub_label = QLabel("Found 0 Steam user profiles with shortcuts.")
        self._sub_label.setObjectName("subheading")
        body_layout.addWidget(self._sub_label)

        body_layout.addSpacing(28)

        # scrollable card list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(10)
        self._card_layout.addStretch()
        self._card_container.mousePressEvent = lambda e: self._deselect_all()

        scroll.setWidget(self._card_container)
        body_layout.addWidget(scroll, 1)

        body_layout.addSpacing(24)

        # ── bottom action bar ─────────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.addStretch()

        self._open_btn = QPushButton("Open →")
        self._open_btn.setFixedSize(140, 40)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open)
        action_row.addWidget(self._open_btn)

        body_layout.addLayout(action_row)

        root.addWidget(body, 1)

    # ── public API ────────────────────────────────────────────────────────────

    def populate(self, users: list[SteamUserShortcuts]):
        """Replace the card list with a fresh set of user results."""
        # clear existing cards
        for card in self._cards:
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._selected_user = None
        self._open_btn.setEnabled(False)

        count = len(users)
        profile_word = "profile" if count == 1 else "profiles"
        self._sub_label.setText(
            f"Found {count} Steam user {profile_word} with a shortcuts file."
            if count > 0
            else "No shortcuts.vdf files found in this Steam installation."
        )

        # insert cards before the trailing stretch
        stretch_index = self._card_layout.count() - 1
        for user in users:
            card = UserCard(user)
            card.selected.connect(self._on_card_selected)
            self._cards.append(card)
            self._card_layout.insertWidget(stretch_index, card)
            stretch_index += 1

    # ── slots ─────────────────────────────────────────────────────────────────

    def _on_card_selected(self, user: SteamUserShortcuts):
        self._selected_user = user
        for card in self._cards:
            card.set_selected(card.user is user)
        self._open_btn.setEnabled(True)

    def _on_open(self):
        if self._selected_user:
            self.user_selected.emit(self._selected_user)

    def _deselect_all(self):
        """Clears selection and disables the open button."""
        self._selected_user = None
        for card in self._cards:
            card.set_selected(False)
        self._open_btn.setEnabled(False)
