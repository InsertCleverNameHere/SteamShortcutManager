"""
Setup screen — shown when Steam cannot be found at a default path.
The user browses to their Steam installation directory.
"""

import os
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ui.theme import PALETTE
from core.steam import is_valid_steam_dir


class SetupScreen(QWidget):
    """
    Emits `steam_dir_confirmed(path: str)` when the user provides
    a valid Steam directory.
    """

    steam_dir_confirmed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── centred content column ──────────────────────────────────────────
        centre = QWidget()
        centre.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        col = QVBoxLayout(centre)
        col.setContentsMargins(64, 0, 64, 0)
        col.setSpacing(0)
        col.setAlignment(Qt.AlignCenter)

        # Steam icon placeholder  ·  could be swapped for a real SVG later
        icon_label = QLabel("⚙")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"font-size: 48px; color: {PALETTE['accent']}; margin-bottom: 24px;"
        )
        col.addWidget(icon_label)

        heading = QLabel("Locate Steam")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignCenter)
        col.addWidget(heading)

        col.addSpacing(8)

        sub = QLabel(
            "Steam wasn't found in the default location.\n"
            "Point to your Steam installation folder to get started."
        )
        sub.setObjectName("subheading")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        col.addWidget(sub)

        col.addSpacing(36)

        # ── path row ────────────────────────────────────────────────────────
        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText(r"C:\Program Files (x86)\Steam")
        self._path_edit.textChanged.connect(self._on_path_changed)
        path_row.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("secondary")
        browse_btn.setFixedWidth(100)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)

        col.addLayout(path_row)

        col.addSpacing(8)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet(f"color: {PALETTE['danger']}; font-size: 12px;")
        self._error_label.setAlignment(Qt.AlignCenter)
        col.addWidget(self._error_label)

        col.addSpacing(24)

        # ── confirm button ───────────────────────────────────────────────────
        self._confirm_btn = QPushButton("Confirm")
        self._confirm_btn.setFixedWidth(180)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._confirm)
        col.addWidget(self._confirm_btn, alignment=Qt.AlignCenter)

        root.addWidget(centre)

    # ── slots ────────────────────────────────────────────────────────────────

    def _browse(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Steam installation folder", ""
        )
        if chosen:
            self._path_edit.setText(chosen)

    def _on_path_changed(self, text: str):
        valid = is_valid_steam_dir(text)
        self._confirm_btn.setEnabled(valid)
        if text and not valid:
            self._error_label.setText("This doesn't look like a valid Steam folder.")
        else:
            self._error_label.setText("")

    def _confirm(self):
        path = self._path_edit.text().strip()
        if is_valid_steam_dir(path):
            self.steam_dir_confirmed.emit(path)

    # ── public ───────────────────────────────────────────────────────────────

    def set_error(self, message: str):
        self._error_label.setText(message)
