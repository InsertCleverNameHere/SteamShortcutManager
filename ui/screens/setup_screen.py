"""
Setup screen — shown when Steam cannot be found at a default path.
The user browses to their Steam installation directory.
"""
import os

from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal

from core.platform import get_platform
from core.steam import is_valid_steam_dir
from ui.theme import PALETTE, get_icon


class SetupScreen(QtWidgets.QWidget):
    """
    Emits `steam_dir_confirmed(path: str)` when the user provides
    a valid Steam directory, or `cancel_requested()` when cancelled.
    """

    steam_dir_confirmed = Signal(str)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── centred content column ──────────────────────────────────────────
        centre = QtWidgets.QWidget()
        centre.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        col = QtWidgets.QVBoxLayout(centre)
        col.setContentsMargins(64, 0, 64, 0)
        col.setSpacing(0)
        col.setAlignment(Qt.AlignCenter)

        icon_label = QtWidgets.QLabel()
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setPixmap(get_icon("tools").pixmap(48, 48))
        icon_label.setStyleSheet("margin-bottom: 24px; background: transparent;")
        col.addWidget(icon_label)

        heading = QtWidgets.QLabel("Locate Steam")
        heading.setObjectName("heading")
        heading.setAlignment(Qt.AlignCenter)
        col.addWidget(heading)

        col.addSpacing(8)

        sub = QtWidgets.QLabel(
            "Steam wasn't found in the default location.\n"
            "Point to your Steam installation folder to get started."
        )
        sub.setObjectName("subheading")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        col.addWidget(sub)

        col.addSpacing(36)

        ## ── path row ────────────────────────────────────────────────────────
        path_row = QtWidgets.QHBoxLayout()
        path_row.setSpacing(8)

        self._path_edit = QtWidgets.QLineEdit()
        self._path_edit.setPlaceholderText(get_platform().steam_dir_placeholder())
        self._path_edit.textChanged.connect(self._on_path_changed)
        path_row.addWidget(self._path_edit, 1)

        browse_btn = QtWidgets.QPushButton("Browse…")
        browse_btn.setObjectName("secondary")
        browse_btn.setFixedWidth(100)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)

        col.addLayout(path_row)

        col.addSpacing(8)

        if get_platform().name == "linux":
            hint_lbl = QtWidgets.QLabel(
                "Tip: Try pressing Ctrl+H in the file dialog to show hidden folders (e.g. .local)"
            )
            hint_lbl.setObjectName("muted")
            hint_lbl.setAlignment(Qt.AlignCenter)
            col.addWidget(hint_lbl)
            col.addSpacing(8)

        self._error_label = QtWidgets.QLabel("")
        self._error_label.setStyleSheet(f"color: {PALETTE['danger']}; font-size: 12px;")
        self._error_label.setAlignment(Qt.AlignCenter)
        col.addWidget(self._error_label)

        col.addSpacing(24)

        # ── action row (Cancel & Confirm buttons) ─────────────────────────────
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(12)
        action_row.setAlignment(Qt.AlignCenter)

        self._cancel_btn = QtWidgets.QPushButton("Cancel")
        self._cancel_btn.setObjectName("secondary")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)
        action_row.addWidget(self._cancel_btn)

        self._confirm_btn = QtWidgets.QPushButton("Confirm")
        self._confirm_btn.setFixedWidth(140)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._confirm)
        action_row.addWidget(self._confirm_btn)

        col.addLayout(action_row)

        root.addWidget(centre)

    # ── slots ────────────────────────────────────────────────────────────────

    def _browse(self):
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
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
        path = os.path.expanduser(self._path_edit.text().strip())
        if is_valid_steam_dir(path):
            self.steam_dir_confirmed.emit(path)

    # ── public ───────────────────────────────────────────────────────────────

    def set_error(self, message: str):
        self._error_label.setText(message)
