"""
UserCard — a selectable card showing one discovered shortcuts.vdf file.
Displays: avatar, persona name (or fallback ID), shortcut count.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor

from ui.theme import PALETTE
from core.steam import SteamUserShortcuts


def _round_pixmap(pixmap: QPixmap, size: int) -> QPixmap:
    """Crop a pixmap into a circular thumbnail."""
    scaled = pixmap.scaled(
        size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
    output = QPixmap(size, size)
    output.fill(Qt.transparent)
    painter = QPainter(output)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    # centre-crop
    x = (scaled.width() - size) // 2
    y = (scaled.height() - size) // 2
    painter.drawPixmap(0, 0, scaled, x, y, size, size)
    painter.end()
    return output


def _avatar_placeholder(size: int, initials: str) -> QPixmap:
    """Generate a simple coloured circle with initials when no avatar is available."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(PALETTE["accent_dim"]))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.setPen(QColor(PALETTE["text_primary"]))
    font = painter.font()
    font.setPixelSize(size // 3)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(0, 0, size, size, Qt.AlignCenter, initials.upper()[:2])
    painter.end()
    return pixmap


AVATAR_SIZE = 56

_CARD_BASE = f"""
    UserCard {{
        background-color: {PALETTE['bg_card']};
        border: 1px solid {PALETTE['border']};
        border-radius: 10px;
    }}
"""

_CARD_HOVER = f"""
    UserCard {{
        background-color: {PALETTE['bg_card_hover']};
        border: 1px solid {PALETTE['border']};
        border-radius: 10px;
    }}
"""

_CARD_SELECTED = f"""
    UserCard {{
        background-color: {PALETTE['bg_card_sel']};
        border: 2px solid {PALETTE['accent']};
        border-radius: 10px;
    }}
"""


class UserCard(QFrame):
    """
    Emits `selected(SteamUserShortcuts)` when clicked.
    """

    selected = Signal(object)  # SteamUserShortcuts

    @property
    def user(self) -> SteamUserShortcuts:
        """Expose the user data associated with this card."""
        return self._user

    def __init__(self, user: SteamUserShortcuts, parent=None):
        super().__init__(parent)
        self._user = user
        self._is_selected = False
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(_CARD_BASE)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(16)

        # ── avatar ───────────────────────────────────────────────────────────
        avatar_label = QLabel()
        avatar_label.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        avatar_label.setAttribute(Qt.WA_TranslucentBackground)

        if self._user.avatar_path:
            raw = QPixmap(self._user.avatar_path)
            if not raw.isNull():
                avatar_label.setPixmap(_round_pixmap(raw, AVATAR_SIZE))
            else:
                avatar_label.setPixmap(
                    _avatar_placeholder(AVATAR_SIZE, self._display_initials())
                )
        else:
            avatar_label.setPixmap(
                _avatar_placeholder(AVATAR_SIZE, self._display_initials())
            )

        layout.addWidget(avatar_label)

        # ── text column ──────────────────────────────────────────────────────
        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(self._user.persona_name or f"User {self._user.userdata_id}")
        name_label.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {PALETTE['text_primary']}; background: transparent;"
        )
        text_col.addWidget(name_label)

        id_label = QLabel(f"ID: {self._user.userdata_id}")
        id_label.setStyleSheet(
            f"font-size: 11px; color: {PALETTE['text_muted']}; background: transparent;"
        )
        text_col.addWidget(id_label)

        layout.addLayout(text_col, 1)

        # ── shortcut count badge ─────────────────────────────────────────────
        count_widget = QWidget()
        count_widget.setAttribute(Qt.WA_TranslucentBackground)
        count_col = QVBoxLayout(count_widget)
        count_col.setContentsMargins(0, 0, 0, 0)
        count_col.setSpacing(2)
        count_col.setAlignment(Qt.AlignCenter)

        count_num = QLabel(str(self._user.shortcut_count))
        count_num.setAlignment(Qt.AlignCenter)
        count_num.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {PALETTE['accent']}; background: transparent;"
        )
        count_col.addWidget(count_num)

        count_lbl = QLabel("shortcuts")
        count_lbl.setAlignment(Qt.AlignCenter)
        count_lbl.setStyleSheet(
            f"font-size: 10px; color: {PALETTE['text_muted']}; background: transparent;"
        )
        count_col.addWidget(count_lbl)

        layout.addWidget(count_widget)

        # ── arrow ────────────────────────────────────────────────────────────
        arrow = QLabel("›")
        arrow.setStyleSheet(
            f"font-size: 20px; color: {PALETTE['text_muted']}; background: transparent;"
        )
        layout.addWidget(arrow)

    # ── interaction ──────────────────────────────────────────────────────────

    def _display_initials(self) -> str:
        name = self._user.persona_name or self._user.userdata_id
        parts = name.split()
        if len(parts) >= 2:
            return parts[0][0] + parts[1][0]
        return name[:2]

    def set_selected(self, selected: bool):
        self._is_selected = selected
        if selected:
            self.setStyleSheet(_CARD_SELECTED)
        else:
            self.setStyleSheet(_CARD_BASE)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._user)

    def enterEvent(self, event):
        if not self._is_selected:
            self.setStyleSheet(_CARD_HOVER)

    def leaveEvent(self, event):
        if not self._is_selected:
            self.setStyleSheet(_CARD_BASE)
