import os
from datetime import datetime

from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QAction, QActionGroup

from core import vdf_parser
from core.lnk import resolve_lnk
from core.log import get_logger
from core.pe_info import get_game_name_from_pe
from core.platform import get_platform
from core.shortcuts_io import ShortcutsFileError, get_available_backups, restore_backup
from ui.theme import PALETTE, get_icon
from ui.widgets.steam_guard import confirm_steam_closed

logger = get_logger("shortcut_list_screen")


class AddShortcutWorker(QtCore.QObject):
    """Resolves file metadata in the background to prevent UI lag."""

    finished = QtCore.Signal(str, str, str)  # (raw_path, exe_path, derived_name)

    def __init__(self, raw_path):
        super().__init__()
        self.raw_path = raw_path

    def run(self):
        file_label = os.path.splitext(os.path.basename(self.raw_path))[0]
        if self.raw_path.lower().endswith(".lnk"):
            exe_path = resolve_lnk(self.raw_path)
            derived_name = file_label
        else:
            exe_path = self.raw_path
            derived_name = get_game_name_from_pe(exe_path)
        self.finished.emit(self.raw_path, exe_path, derived_name)


class ShortcutListScreen(QtWidgets.QWidget):
    back_requested = QtCore.Signal()
    shortcut_clicked = QtCore.Signal(
        str, str, str
    )  # (game_name, shortcuts_path, appid)
    user_updated = QtCore.Signal()

    @property
    def current_user(self):
        """Public accessor for the currently loaded Steam user."""
        return self._current_user_obj

    def __init__(self, parent=None):
        super().__init__(parent)
        self._card_data = []  # Track widgets and names for filtering
        self._sort_mode = "default"  # "default" | "alpha" | "missing_first"
        self.setAcceptDrops(True)
        self._search_timer = QtCore.QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)  # Wait 200ms after last keystroke
        self._search_timer.timeout.connect(self._execute_filter)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        header = QtWidgets.QHBoxLayout()
        back_btn = QtWidgets.QPushButton("← Back")
        back_btn.setObjectName("secondary")
        back_btn.setFixedSize(80, 35)
        back_btn.clicked.connect(self.back_requested)
        header.addWidget(back_btn)

        header.addStretch()

        self.title_label = QtWidgets.QLabel("Shortcuts")
        self.title_label.setObjectName("heading")
        self.title_label.setMaximumWidth(300)
        header.addWidget(self.title_label)

        header.addSpacing(10)

        # --- Search Bar ---
        self.search_bar = QtWidgets.QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search by name...")
        self.search_bar.setFixedWidth(170)
        self.search_bar.textChanged.connect(lambda: self._search_timer.start())
        header.addWidget(self.search_bar)

        header.addStretch()

        # Compact Square Refresh Button
        self.refresh_btn = QtWidgets.QPushButton("↻")
        self.refresh_btn.setFixedSize(35, 35)  # Strict square dimensions
        self.refresh_btn.setObjectName("secondary")
        self.refresh_btn.setToolTip("Reload library from shortcuts.vdf")
        # Ensure the icon is centered and not padded
        self.refresh_btn.setStyleSheet(
            "font-size: 18px; padding: 0px; font-weight: bold;"
        )
        self.refresh_btn.clicked.connect(
            lambda: self.load_user_shortcuts(self._current_user_obj)
        )
        header.addWidget(self.refresh_btn)

        # Compact Square Sort Button
        self.sort_btn = QtWidgets.QPushButton("⇅")
        self.sort_btn.setFixedSize(35, 35)
        self.sort_btn.setObjectName("secondary")
        self.sort_btn.setToolTip("Sort shortcuts")
        self.sort_btn.setStyleSheet("font-size: 16px; padding: 0px; font-weight: bold;")
        self.sort_btn.clicked.connect(self._show_sort_menu)
        header.addWidget(self.sort_btn)

        # Add Shortcut Button
        self.add_btn = QtWidgets.QPushButton("+ Add Shortcut")
        self.add_btn.setFixedWidth(130)
        self.add_btn.setFixedHeight(35)
        self.add_btn.clicked.connect(self._on_add_clicked)
        header.addWidget(self.add_btn)

        layout.addLayout(header)
        layout.addSpacing(8)

        # Persistent Steam-Running Banner (Accordion Container)
        self.running_banner = QtWidgets.QFrame()
        self.running_banner.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(232, 168, 56, 20);
                border: 1px solid {PALETTE['warning']};
                border-radius: 6px;
            }}
            QLabel {{
                color: {PALETTE['warning']};
                font-size: 12px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)
        banner_layout = QtWidgets.QHBoxLayout(self.running_banner)
        banner_layout.setContentsMargins(12, 4, 12, 4)
        banner_lbl = QtWidgets.QLabel(
            "⚠️ Steam is running — changes may be overwritten on exit. We recommend closing Steam."
        )
        banner_lbl.setWordWrap(True)
        banner_lbl.setAlignment(QtCore.Qt.AlignCenter)
        banner_layout.addWidget(banner_lbl)

        # Opacity effect and zero-height initial state
        self._banner_opacity = QtWidgets.QGraphicsOpacityEffect(self.running_banner)
        self._banner_opacity.setOpacity(0.0)
        self.running_banner.setGraphicsEffect(self._banner_opacity)
        self.running_banner.setMaximumHeight(0)
        self.running_banner.setVisible(False)

        layout.addWidget(self.running_banner)
        layout.addSpacing(8)

        # Scroll area for shortcuts
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )  # Only vertical scrolling
        # Prevent focus rectangle on scrollbar
        self.scroll_area.verticalScrollBar().setFocusPolicy(QtCore.Qt.NoFocus)

        self.list_container = QtWidgets.QWidget()
        self.list_layout = QtWidgets.QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 12, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.setAlignment(QtCore.Qt.AlignTop)

        self.scroll_area.setWidget(self.list_container)
        layout.addWidget(self.scroll_area)

    def _execute_filter(self):
        """Hides or shows cards based on the search text with layout suspension."""
        query = self.search_bar.text().lower().strip()

        # 1. Surgical Addition: Suspend updates to prevent jarring "snapping"
        self.list_container.setUpdatesEnabled(False)

        for card, game_name in self._card_data:
            card.setVisible(query in game_name)

        # 2. Surgical Addition: Resume and redraw once at the end
        self.list_container.setUpdatesEnabled(True)

    def _animate_banner(self, show: bool):
        """Smoothly expands or collapses the banner with parallel height and opacity animations."""
        target_height = 36 if show else 0
        target_opacity = 1.0 if show else 0.0

        # Don't re-animate if already in the target state
        if (
            show
            and self.running_banner.isVisible()
            and self.running_banner.maximumHeight() == target_height
        ):
            return
        if not show and not self.running_banner.isVisible():
            return

        if (
            hasattr(self, "_banner_group")
            and self._banner_group.state() == QtCore.QAbstractAnimation.Running
        ):
            self._banner_group.stop()

        if show:
            self.running_banner.setVisible(True)

        self._banner_group = QtCore.QParallelAnimationGroup(self)

        # 1. Animate Opacity
        anim_op = QtCore.QPropertyAnimation(self._banner_opacity, b"opacity")
        anim_op.setDuration(380)
        anim_op.setStartValue(self._banner_opacity.opacity())
        anim_op.setEndValue(target_opacity)

        # 2. Animate Height (Smooth Accordion)
        anim_h = QtCore.QPropertyAnimation(self.running_banner, b"maximumHeight")
        anim_h.setDuration(380)
        anim_h.setStartValue(self.running_banner.maximumHeight())
        anim_h.setEndValue(target_height)
        anim_h.setEasingCurve(QtCore.QEasingCurve.InOutQuad)

        self._banner_group.addAnimation(anim_op)
        self._banner_group.addAnimation(anim_h)

        if not show:
            self._banner_group.finished.connect(
                lambda: self.running_banner.setVisible(False)
            )

        self._banner_group.start()

    def _show_sort_menu(self):
        """Builds and shows the sort options popup, anchored to the sort button."""
        menu = QtWidgets.QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)

        options = [
            ("default", "File order"),
            ("alpha", "Alphabetical (A–Z)"),
            ("missing_first", "Missing assets first"),
        ]

        for mode, label in options:
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(self._sort_mode == mode)
            action.triggered.connect(lambda checked, m=mode: self._on_sort_selected(m))
            group.addAction(action)
            menu.addAction(action)

        menu.addSeparator()
        restore_action = QAction("Restore from backup…", menu)
        restore_action.triggered.connect(self._on_restore_backup_clicked)
        menu.addAction(restore_action)

        # Anchor the menu directly under the button, left-aligned to it
        menu.exec(self.sort_btn.mapToGlobal(self.sort_btn.rect().bottomLeft()))

    def _on_sort_selected(self, mode: str):
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        self.load_user_shortcuts(self._current_user_obj)

    def _on_restore_backup_clicked(self):
        if not getattr(self, "_current_user_obj", None):
            return

        shortcuts_path = self._current_user_obj.shortcuts_path
        backups = get_available_backups(shortcuts_path)

        if not backups:
            QtWidgets.QMessageBox.information(
                self,
                "No Backups",
                "No automatic backups were found in 'ssm-backups' for this profile.",
            )
            return

        # Build readable labels with formatted timestamps
        labels = []
        for b in backups:
            try:
                mtime = datetime.fromtimestamp(b.stat().st_mtime)
                date_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
            except OSError:
                date_str = b.name
            size_kb = max(1, round(b.stat().st_size / 1024))
            labels.append(f"{date_str}  ({size_kb} KB)")

        chosen_label, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Restore Backup",
            "Select a backup to restore (replaces current shortcuts):",
            labels,
            0,
            False,
        )

        if not ok or not chosen_label:
            return

        if not confirm_steam_closed(self):
            return

        chosen_idx = labels.index(chosen_label)
        chosen_backup = backups[chosen_idx]

        try:
            success = restore_backup(chosen_backup, shortcuts_path)
            if success:
                QtWidgets.QMessageBox.information(
                    self,
                    "Backup Restored",
                    "The shortcuts file was successfully restored from backup.",
                )
                self.load_user_shortcuts(self._current_user_obj)
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Restore Failed", "Could not restore the selected backup."
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Restore Error", f"Failed to restore backup: {e}"
            )

    def _on_add_clicked(self):
        raw_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Game",
            "",
            get_platform().file_dialog_filter,
        )
        if not raw_path:
            return
        self._start_add_from_path(raw_path)

    def _start_add_from_path(self, raw_path: str):
        """
        Kicks off background metadata resolution for a given exe/lnk path.
        Shared entry point for both the file-dialog Add flow and drag-and-drop.
        """
        if not self.add_btn.isEnabled():
            return

        if not confirm_steam_closed(self):
            return

        # Ensure refresh button is disabled during resolution
        self.add_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)

        # Start background resolution
        self._add_thread = QtCore.QThread()
        self._add_worker = AddShortcutWorker(raw_path)
        self._add_worker.moveToThread(self._add_thread)

        self._add_thread.started.connect(self._add_worker.run)
        self._add_worker.finished.connect(self._on_shortcut_resolved)
        self._add_worker.finished.connect(self._add_thread.quit)
        self._add_worker.finished.connect(self._add_worker.deleteLater)
        self._add_thread.finished.connect(self._add_thread.deleteLater)

        self._add_thread.start()

    def _extract_droppable_path(self, mime_data) -> str | None:
        """Returns the local file path if the drop contains exactly one valid game executable."""
        if not mime_data.hasUrls():
            return None

        urls = mime_data.urls()
        if len(urls) != 1:
            return None

        url = urls[0]
        if not url.isLocalFile():
            return None

        path = url.toLocalFile()
        allowed = get_platform().droppable_extensions
        if path.lower().endswith(allowed) and os.path.isfile(path):
            return path
        return None

    def dragEnterEvent(self, event):
        # Accept drops that contain local files so dropEvent can process or explain errors
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return

        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            event.ignore()
            QtWidgets.QMessageBox.information(
                self,
                "Multiple Items Dropped",
                "Please drag and drop a single game executable at a time.",
            )
            return

        path = urls[0].toLocalFile()
        valid_path = self._extract_droppable_path(event.mimeData())

        if valid_path:
            event.acceptProposedAction()
            self._start_add_from_path(valid_path)
            return

        # Friendly rejection messages per Plan §2.1
        event.ignore()
        ext = os.path.splitext(path)[1].lower() or "folder"
        if ext in (".bat", ".msi"):
            msg = (
                f"'{ext}' files are scripts or installers and cannot be launched directly as games.\n\n"
                "Please drag and drop the main game executable (.exe) instead."
            )
        elif not os.path.isfile(path):
            msg = "Directories cannot be added as shortcuts. Please drop the main game executable (.exe)."
        else:
            allowed_str = ", ".join(get_platform().droppable_extensions)
            msg = (
                f"Unsupported file type ({ext}).\n\n"
                f"Only game executables ({allowed_str}) can be added on this platform."
            )

        QtWidgets.QMessageBox.information(self, "Unsupported Drop", msg)

    def _on_shortcut_resolved(self, raw_path, exe_path, derived_name):
        """Continues the Add Shortcut flow after background resolution."""
        # Re-enable buttons
        self.add_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        game_name, ok = QtWidgets.QInputDialog.getText(
            self, "Add Shortcut", "Enter game name:", text=derived_name
        )

        if ok and game_name:
            vdf_path = self._current_user_obj.shortcuts_path

            # Save to VDF (icon left empty by default per Plan §2.4)
            success, msg, new_id = vdf_parser.add_new_shortcut(
                vdf_path, game_name, exe_path
            )

            if success:
                # Manually update the data object's count
                if self._current_user_obj:
                    self._current_user_obj.shortcut_count += 1
                    # Signal the LibraryScreen (UserCard) to refresh its label
                    self.user_updated.emit()

                # Rebuild the local list of shortcut cards to include the new game
                self.load_user_shortcuts(self._current_user_obj)
                # Redirect to details
                self.shortcut_clicked.emit(game_name, vdf_path, new_id)
            else:
                QtWidgets.QMessageBox.critical(self, "Error", msg)

    @staticmethod
    def _asset_complete(appid: str, grid_files: set) -> bool:
        img_exts = (".jpg", ".png", ".jpeg")
        return (
            any(f"{appid}p{e}" in grid_files for e in img_exts)
            and any(f"{appid}{e}" in grid_files for e in img_exts)
            and any(f"{appid}_hero{e}" in grid_files for e in img_exts)
            and any(f"{appid}_logo{e}" in grid_files for e in img_exts)
            and f"{appid}.json" in grid_files
        )

    def load_user_shortcuts(self, user_obj):
        """Called when a user is selected in the main menu."""
        # Store the current user object so the Add button knows which VDF to edit
        self._current_user_obj = user_obj
        # Fallback to userdata_id if persona_name is missing
        display_name = user_obj.persona_name or user_obj.userdata_id
        self.title_label.setText(f"{display_name}'s Library")

        # Update persistent Steam-running banner with smooth accordion transition
        is_running = bool(get_platform().is_steam_running())
        self._animate_banner(is_running)

        # Pre-scan the grid folder once to avoid O(N) disk hits in the loop
        grid_dir = os.path.join(os.path.dirname(user_obj.shortcuts_path), "grid")
        grid_files = set(os.listdir(grid_dir)) if os.path.isdir(grid_dir) else set()

        # Reset search state
        self.search_bar.clear()
        self._card_data = []

        # Clear existing items
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Load the data
        try:
            self.add_btn.setEnabled(True)
            data = vdf_parser.load_shortcuts(user_obj.shortcuts_path)
            shortcuts = vdf_parser.get_shortcut_list(data)

            # Apply the selected sort order
            if self._sort_mode == "alpha":
                shortcuts = sorted(
                    shortcuts,
                    key=lambda s: vdf_parser.get_value_case_insensitive(
                        s, "AppName", "Unknown Game"
                    ).lower(),
                )
            elif self._sort_mode == "missing_first":
                shortcuts = sorted(
                    shortcuts,
                    key=lambda s: self._asset_complete(
                        vdf_parser.normalize_appid(
                            vdf_parser.get_value_case_insensitive(s, "appid", "0")
                        ),
                        grid_files,
                    ),
                )
            # Sync the count back to the user object
            self._current_user_obj.shortcut_count = len(shortcuts)
            self.user_updated.emit()  # Notify the rest of the app

            if not shortcuts:
                empty_container = QtWidgets.QWidget()
                empty_layout = QtWidgets.QVBoxLayout(empty_container)
                empty_layout.setAlignment(QtCore.Qt.AlignCenter)
                empty_layout.setContentsMargins(0, 80, 0, 0)
                empty_layout.setSpacing(10)

                icon_lbl = QtWidgets.QLabel()
                icon_lbl.setPixmap(get_icon("folder").pixmap(48, 48))
                icon_lbl.setStyleSheet("background: transparent;")
                icon_lbl.setAlignment(QtCore.Qt.AlignCenter)

                msg_lbl = QtWidgets.QLabel("No shortcuts found")
                msg_lbl.setObjectName("heading")
                msg_lbl.setAlignment(QtCore.Qt.AlignCenter)

                sub_lbl = QtWidgets.QLabel(
                    "This Steam profile doesn't have any non-Steam games yet.\n"
                    "Click '+ Add Shortcut' to get started."
                )
                sub_lbl.setObjectName("subheading")
                sub_lbl.setAlignment(QtCore.Qt.AlignCenter)
                sub_lbl.setStyleSheet(
                    f"color: {PALETTE['text_muted']}; background: transparent;"
                )

                empty_layout.addWidget(icon_lbl)
                empty_layout.addWidget(msg_lbl)
                empty_layout.addWidget(sub_lbl)
                self.list_layout.addWidget(empty_container)

            for s in shortcuts:
                # 1. Extract Data
                name = vdf_parser.get_value_case_insensitive(
                    s, "AppName", "Unknown Game"
                )
                raw_appid = vdf_parser.get_value_case_insensitive(s, "appid", "0")
                appid = vdf_parser.normalize_appid(raw_appid)
                exe_path = vdf_parser.get_value_case_insensitive(
                    s, "Exe", "No Path Found"
                )

                # 2. Check Assets
                is_complete = self._asset_complete(appid, grid_files)

                # 3. Build Card
                card = QtWidgets.QFrame()
                card.setCursor(QtCore.Qt.PointingHandCursor)
                card.setStyleSheet(
                    f"background: {PALETTE['bg_card']}; border: 1px solid {PALETTE['border']}; border-radius: 6px; padding: 8px;"
                )
                # Use a lambda to emit our new signal when the card is clicked
                card.mousePressEvent = lambda e, n=name, p=user_obj.shortcuts_path, i=appid: self.shortcut_clicked.emit(
                    n, p, i
                )
                card_layout = QtWidgets.QVBoxLayout(card)
                card_layout.setSpacing(2)  # Tighten space between title and subtitle

                # Title Row
                title_row = QtWidgets.QHBoxLayout()
                title_lbl = QtWidgets.QLabel(name)
                # Reduced font from 15px to 14px
                title_lbl.setStyleSheet(
                    f"font-size: 14px; font-weight: bold; color: {PALETTE['text_primary']}; border: none; background: transparent;"
                )
                title_row.addWidget(title_lbl)
                if not is_complete:
                    flag = QtWidgets.QLabel("⚠ Missing Assets")
                    flag.setStyleSheet(
                        f"color: {PALETTE['warning']}; font-size: 10px; font-weight: bold; background: transparent;"
                    )
                    title_row.addStretch()
                    title_row.addWidget(flag)

                card_layout.addLayout(title_row)

                # Subtitle (AppID and Exe Path)
                sub_text = f"AppID: {appid}  •  {exe_path}"
                sub_lbl = QtWidgets.QLabel(sub_text)
                sub_lbl.setStyleSheet(
                    f"font-size: 11px; color: {PALETTE['text_muted']}; border: none; background: transparent;"
                )
                sub_lbl.setWordWrap(False)  # Keep it on one line for a cleaner look
                sub_lbl.setMaximumWidth(650)
                sub_lbl.setSizePolicy(
                    QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
                )  # Allow horizontal shrinking
                card_layout.addWidget(sub_lbl)

                # Store reference for filtering
                self._card_data.append((card, name.lower()))

                self.list_layout.addWidget(card)

        except ShortcutsFileError as err:
            logger.error(f"Corruption detected in shortcuts file: {err}")
            self.add_btn.setEnabled(False)

            err_container = QtWidgets.QWidget()
            err_layout = QtWidgets.QVBoxLayout(err_container)
            err_layout.setAlignment(QtCore.Qt.AlignCenter)
            err_layout.setContentsMargins(0, 60, 0, 0)
            err_layout.setSpacing(12)

            icon_lbl = QtWidgets.QLabel("⚠️")
            icon_lbl.setStyleSheet("font-size: 48px; background: transparent;")
            icon_lbl.setAlignment(QtCore.Qt.AlignCenter)

            title_lbl = QtWidgets.QLabel("Shortcuts File Corrupted")
            title_lbl.setObjectName("heading")
            title_lbl.setAlignment(QtCore.Qt.AlignCenter)
            title_lbl.setStyleSheet(
                f"color: {PALETTE['danger']}; background: transparent;"
            )

            desc_lbl = QtWidgets.QLabel(
                "The shortcuts.vdf file is corrupted or improperly formatted.\n"
                "To prevent data loss, adding shortcuts is disabled until a backup is restored."
            )
            desc_lbl.setObjectName("subheading")
            desc_lbl.setAlignment(QtCore.Qt.AlignCenter)
            desc_lbl.setStyleSheet(
                f"color: {PALETTE['text_muted']}; background: transparent;"
            )

            restore_btn = QtWidgets.QPushButton("Restore from Backup…")
            restore_btn.setFixedWidth(200)
            restore_btn.setFixedHeight(38)
            restore_btn.clicked.connect(self._on_restore_backup_clicked)

            err_layout.addWidget(icon_lbl)
            err_layout.addWidget(title_lbl)
            err_layout.addWidget(desc_lbl)
            err_layout.addSpacing(8)
            err_layout.addWidget(restore_btn, alignment=QtCore.Qt.AlignCenter)

            self.list_layout.addWidget(err_container)

        except Exception as e:
            error_lbl = QtWidgets.QLabel(f"Error loading shortcuts: {e}")
            error_lbl.setStyleSheet(f"color: {PALETTE['danger']};")
            self.list_layout.addWidget(error_lbl)

        # Autofocus search bar in this screen
        self.search_bar.setFocus()
