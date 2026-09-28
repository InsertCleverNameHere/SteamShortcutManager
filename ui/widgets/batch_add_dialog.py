"""
ui/widgets/batch_add_dialog.py
Steam-style "Add Non-Steam Game" modal dialog for batch shortcut selection.
Allows accumulating executables across different folders, filtering,
toggling checkmarks, and batching additions into a single transaction.
"""

import os
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from core.lnk import resolve_lnk
from core.pe_info import get_game_name_from_pe
from core.platform import get_platform
from ui.theme import PALETTE, get_app_icon


class BatchAddDialog(QtWidgets.QDialog):
    """
    Modal dialog allowing users to accumulate, review, and select multiple
    non-Steam game executables before adding them to Steam.
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        initial_paths: list[str] | None = None,
        install=None,
    ):
        super().__init__(parent)
        self._install = install
        self._items: dict[str, dict] = {}  # exe_path -> {name, raw_path, warning}

        self.setWindowTitle("Add Non-Steam Game")
        self.resize(650, 500)
        self.setMinimumSize(560, 380)
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self._build_ui()

        if initial_paths:
            for path in initial_paths:
                self.add_executable(path)

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        header_col = QtWidgets.QVBoxLayout()
        header_col.setSpacing(4)

        title_lbl = QtWidgets.QLabel("Add Non-Steam Game")
        title_lbl.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {PALETTE['text_primary']};"
        )
        header_col.addWidget(title_lbl)

        sub_lbl = QtWidgets.QLabel(
            "Select programs to add to your Steam Library"
        )
        sub_lbl.setStyleSheet(
            f"font-size: 13px; color: {PALETTE['text_secondary']};"
        )
        header_col.addWidget(sub_lbl)

        layout.addLayout(header_col)

        # ── Search Filter ─────────────────────────────────────────────────────
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search list...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_edit)

        # ── Program Table ─────────────────────────────────────────────────────
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["PROGRAM", "LOCATION"])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows
        )
        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection
        )

        h_header = self.table.horizontalHeader()
        h_header.setStretchLastSection(True)
        h_header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.Interactive
        )
        h_header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table.setColumnWidth(0, 240)

        self.table.setSortingEnabled(True)
        self.table.itemChanged.connect(self._on_item_changed)

        layout.addWidget(self.table, 1)

        # ── Bottom Action Row ─────────────────────────────────────────────────
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.setSpacing(10)

        self.browse_btn = QtWidgets.QPushButton("Browse…")
        self.browse_btn.setObjectName("secondary")
        self.browse_btn.setFixedHeight(35)
        self.browse_btn.clicked.connect(self._on_browse_clicked)
        bottom_row.addWidget(self.browse_btn)

        bottom_row.addStretch()

        self.add_btn = QtWidgets.QPushButton("Add Selected Programs")
        self.add_btn.setFixedHeight(35)
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._on_confirm_add)
        bottom_row.addWidget(self.add_btn)

        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondary")
        self.cancel_btn.setFixedHeight(35)
        self.cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(self.cancel_btn)

        layout.addLayout(bottom_row)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_executable(
        self, raw_path: str, custom_name: str | None = None
    ) -> bool:
        """
        Resolves executable and appends it to the table if valid.
        Returns True if added or updated.
        """
        clean_raw = os.path.normpath(raw_path.strip().strip('"'))
        if not os.path.isfile(clean_raw):
            return False

        if clean_raw.lower().endswith(".lnk"):
            exe_path = resolve_lnk(clean_raw)
            default_name = Path(clean_raw).stem
        else:
            exe_path = clean_raw
            default_name = get_game_name_from_pe(exe_path)

        if not exe_path:
            return False

        exe_path = os.path.normpath(exe_path)
        game_name = custom_name.strip() if custom_name else default_name

        # Check platform warnings
        warnings = get_platform().path_warnings(
            exe_path, install=self._install
        )
        warning_text = "\n".join(warnings) if warnings else None

        # Check if already present in table
        for row in range(self.table.rowCount()):
            existing_path_item = self.table.item(row, 1)
            if (
                existing_path_item
                and existing_path_item.text().lower() == exe_path.lower()
            ):
                # Ensure it is checked
                name_item = self.table.item(row, 0)
                if name_item:
                    name_item.setCheckState(QtCore.Qt.Checked)
                return True

        self.table.setSortingEnabled(False)
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)

        # Column 0: Program Name + Checkbox
        display_text = f"⚠️ {game_name}" if warning_text else game_name
        name_item = QtWidgets.QTableWidgetItem(display_text)
        name_item.setFlags(
            QtCore.Qt.ItemIsUserCheckable
            | QtCore.Qt.ItemIsEnabled
            | QtCore.Qt.ItemIsSelectable
            | QtCore.Qt.ItemIsEditable
        )
        name_item.setCheckState(QtCore.Qt.Checked)
        name_item.setData(QtCore.Qt.UserRole, game_name)  # Clean game name
        if warning_text:
            name_item.setToolTip(f"Compatibility Warning:\n{warning_text}")
            name_item.setData(QtCore.Qt.UserRole + 1, warning_text)

        # Column 1: Location Path
        path_item = QtWidgets.QTableWidgetItem(exe_path)
        path_item.setFlags(
            QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        )
        path_item.setForeground(
            QtGui.QColor(PALETTE["text_secondary"])
        )
        path_item.setToolTip(exe_path)

        self.table.setItem(row_idx, 0, name_item)
        self.table.setItem(row_idx, 1, path_item)
        self.table.setSortingEnabled(True)

        self._update_add_button_state()
        return True

    def get_selected_shortcuts(self) -> list[tuple[str, str]]:
        """Returns list of (game_name, exe_path) for all currently checked rows."""
        selected: list[tuple[str, str]] = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            path_item = self.table.item(row, 1)
            if name_item and name_item.checkState() == QtCore.Qt.Checked:
                # Use edited text or stored clean name
                raw_text = name_item.text().replace("⚠️ ", "").strip()
                exe_path = path_item.text().strip() if path_item else ""
                if raw_text and exe_path:
                    selected.append((raw_text, exe_path))
        return selected

    # ── Slots & Helpers ───────────────────────────────────────────────────────

    def _on_search_changed(self, text: str):
        query = text.lower().strip()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            path_item = self.table.item(row, 1)
            name_str = name_item.text().lower() if name_item else ""
            path_str = path_item.text().lower() if path_item else ""
            matches = query in name_str or query in path_str
            self.table.setRowHidden(row, not matches)

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem):
        if item.column() == 0:
            self._update_add_button_state()

    def _update_add_button_state(self):
        checked_count = sum(
            1
            for row in range(self.table.rowCount())
            if self.table.item(row, 0)
            and self.table.item(row, 0).checkState() == QtCore.Qt.Checked
        )
        if checked_count > 0:
            self.add_btn.setEnabled(True)
            self.add_btn.setText(
                f"Add Selected Programs ({checked_count})"
                if checked_count > 1
                else "Add Selected Program"
            )
        else:
            self.add_btn.setEnabled(False)
            self.add_btn.setText("Add Selected Programs")

    def _on_browse_clicked(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select Programs",
            "",
            get_platform().file_dialog_filter,
        )
        for f in files:
            self.add_executable(f)

    def _on_confirm_add(self):
        # Gather warnings for checked items
        flagged: list[str] = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            if name_item and name_item.checkState() == QtCore.Qt.Checked:
                warn = name_item.data(QtCore.Qt.UserRole + 1)
                if warn:
                    clean_name = name_item.text().replace("⚠️ ", "").strip()
                    flagged.append(f"• {clean_name}:\n  {warn}")

        if flagged:
            bullet_text = "\n\n".join(flagged)
            reply = QtWidgets.QMessageBox.question(
                self,
                "Compatibility Warning",
                f"The following program(s) have compatibility warnings:\n\n"
                f"{bullet_text}\n\nDo you want to add them anyway?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return

        self.accept()