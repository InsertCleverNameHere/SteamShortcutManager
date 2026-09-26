import os
from enum import Enum, auto
from typing import Any

from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QPixmap

from core.asset_provider import download_assets
from core.grid import (
    SLOT_MAPPING,
    delete_all_assets,
    get_asset_status,
    validate_image_bytes,
    write_asset_atomic,
)
from core.log import get_logger
from core.net import (
    DEFAULT_TIMEOUT,
    create_steam_session,
    is_trusted_steam_url,
    search_steam_store,
)
from core.vdf_parser import delete_shortcut, update_shortcut_icon, update_shortcut_name
from ui.tasks import CancelToken, Task, TaskRunner
from ui.theme import PALETTE, get_icon
from ui.widgets.steam_guard import confirm_steam_closed

logger = get_logger("asset_details_screen")


class SearchState(Enum):
    IDLE = auto()
    SEARCHING = auto()
    FOUND = auto()
    NOT_FOUND = auto()


class SearchTask(Task):
    """Fetches store search results and thumbnail securely."""

    def __init__(self, query: str):
        self.query = query

    def run(self, token: CancelToken) -> dict[str, Any]:
        token.raise_if_cancelled()
        res = search_steam_store(self.query)
        token.raise_if_cancelled()

        thumb_bytes = None
        if res.status == "ok" and res.item and res.item.thumb_url:
            url = res.item.thumb_url
            if is_trusted_steam_url(url):
                try:
                    session = create_steam_session()
                    r = session.get(url, timeout=DEFAULT_TIMEOUT)
                    if r.status_code == 200:
                        thumb_bytes = r.content
                except Exception as e:
                    logger.debug(f"Failed to fetch search thumbnail: {e}")

        token.raise_if_cancelled()
        return {
            "status": res.status,
            "item": res.item,
            "thumb_bytes": thumb_bytes,
            "error": res.error_message,
        }


class DownloadTask(Task):
    """Executes official asset download and atomic injection."""

    def __init__(
        self,
        steam_id: str,
        local_id: str,
        grid_dir: str,
        force: bool,
    ):
        self.steam_id = steam_id
        self.local_id = local_id
        self.grid_dir = grid_dir
        self.force = force

    def run(self, token: CancelToken) -> tuple[bool, str, str]:
        success, message = download_assets(
            self.steam_id,
            self.local_id,
            self.grid_dir,
            force=self.force,
            status_callback=token.report_progress,
            abort_event=token,
        )
        return success, message, self.local_id


class AssetSlot(QtWidgets.QWidget):
    """A persistent widget representing a single asset (Capsule, Hero, etc.)."""

    manual_upload_requested = QtCore.Signal(str)

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedWidth(320)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip(f"Click to manually upload {key.upper()}")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(QtCore.Qt.AlignTop)

        self.title_label = QtWidgets.QLabel(key.upper())
        self.title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 900; letter-spacing: 1.5px; color: {PALETTE['accent']}; background: transparent;"
        )
        layout.addWidget(self.title_label)

        self.content_label = QtWidgets.QLabel()
        self.content_label.setMinimumHeight(160)
        self.content_label.setAlignment(QtCore.Qt.AlignTop)

        # Opacity effect for smooth artwork fade-in
        self._content_opacity = QtWidgets.QGraphicsOpacityEffect(self.content_label)
        self._content_opacity.setOpacity(1.0)
        self.content_label.setGraphicsEffect(self._content_opacity)
        self._current_path: str | None = None

        layout.addWidget(self.content_label)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.manual_upload_requested.emit(self.key)

    def update_slot(self, exists, path):
        """Updates the content without recreating the widget, smoothly fading in new images."""
        if exists:
            if self.key == "json":
                self._current_path = None
                self._content_opacity.setOpacity(1.0)
                self.content_label.setPixmap(QPixmap())
                self.content_label.setText("✓ Position Data Found")
                self.content_label.setStyleSheet(
                    f"color: {PALETTE['success']}; font-size: 14px; font-weight: bold; background: transparent;"
                )
            else:
                is_new_image = self._current_path != path
                self._current_path = path

                pix = QPixmap(path)
                if not pix.isNull():
                    # High-DPI / Wayland fractional scaling: scale at physical pixel resolution
                    dpr = self.devicePixelRatio()
                    target_w = int(320 * dpr)
                    target_h = int(160 * dpr)
                    scaled_pix = pix.scaled(
                        target_w,
                        target_h,
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation,
                    )
                    scaled_pix.setDevicePixelRatio(dpr)
                    self.content_label.setPixmap(scaled_pix)
                    self.content_label.setText("")
                    self.content_label.setStyleSheet("background: transparent;")

                    if is_new_image:
                        self._fade_anim = QtCore.QPropertyAnimation(
                            self._content_opacity, b"opacity", self
                        )
                        self._fade_anim.setDuration(300)
                        self._fade_anim.setStartValue(0.0)
                        self._fade_anim.setEndValue(1.0)
                        self._fade_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
                        self._fade_anim.start()
                    else:
                        self._content_opacity.setOpacity(1.0)
                else:
                    # Clear previous game's pixmap and display unreadable status
                    self.content_label.setPixmap(QPixmap())
                    self.content_label.setText("⚠ Unreadable Image")
                    self.content_label.setStyleSheet(
                        f"color: {PALETTE['warning']}; font-size: 14px; font-weight: bold; background: transparent;"
                    )
                    self._content_opacity.setOpacity(1.0)
        else:
            self._current_path = None
            self._content_opacity.setOpacity(1.0)
            self.content_label.setPixmap(QPixmap())
            self.content_label.setText("× Missing")
            self.content_label.setStyleSheet(
                f"color: {PALETTE['danger']}; font-size: 14px; font-weight: bold; background: transparent;"
            )


class AssetDetailsScreen(QtWidgets.QWidget):
    back_requested = QtCore.Signal()
    name_changed = QtCore.Signal()

    def _set_busy(self, is_busy: bool):
        """Toggles the 'download in progress' UI state."""
        self._is_busy = is_busy

        self.delete_btn.setEnabled(not is_busy)
        self.edit_btn.setEnabled(not is_busy)
        self.force_cb.setEnabled(not is_busy)
        self.back_btn.setEnabled(not is_busy)

        if is_busy:
            self._back_dim_effect = QtWidgets.QGraphicsOpacityEffect(self)
            self._back_dim_effect.setOpacity(0.4)
            self.back_btn.setGraphicsEffect(self._back_dim_effect)

            # Swap Inject ↔ Cancel
            self.inject_btn.setText("✕ Cancel")
            self.inject_btn.setEnabled(True)
            self.btn_opacity_effect.setOpacity(1.0)
            self.inject_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {PALETTE['danger']};
                    color: {PALETTE['text_primary']};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 20px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{ background-color: #e86060; }}
                QPushButton:pressed {{ background-color: #c04040; }}
            """)
        else:
            self.back_btn.setGraphicsEffect(None)  # type: ignore
            self.inject_btn.setText("↓ Inject from Steam")
            self.inject_btn.setStyleSheet("")
            self._update_button_state()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_runner = TaskRunner(self)
        self._suggested_steam_id = None
        self._current_appid: str = ""
        self._current_shortcuts_path = ""
        self._current_name = ""
        self._search_state = SearchState.IDLE
        self._all_assets_present = False
        self._is_busy = False
        self._build_ui()

    def _build_ui(self):
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)

        # --- Row 1: Toolbox (Back, Match, Status, Controls) ---
        toolbox_row = QtWidgets.QHBoxLayout()
        toolbox_row.setSpacing(5)

        self.back_btn = QtWidgets.QPushButton("← Back")
        self.back_btn.setObjectName("secondary")
        self.back_btn.setFixedSize(80, 35)
        # Route through _on_back_clicked — it aborts any active download first.
        self.back_btn.clicked.connect(self._on_back_clicked)
        toolbox_row.addWidget(self.back_btn)

        # Smart Suggestion Badge
        self.suggestion_widget = QtWidgets.QFrame()
        self.suggestion_widget.setFixedHeight(35)
        self.suggestion_widget.setFixedWidth(165)
        self.suggestion_widget.setStyleSheet(f"""
            QFrame {{
                background: {PALETTE['bg_card']};
                border: 1px solid {PALETTE['border']};
                border-radius: 4px;
            }}
        """)
        self.suggestion_layout = QtWidgets.QHBoxLayout(self.suggestion_widget)
        self.suggestion_layout.setContentsMargins(4, 0, 10, 0)
        self.suggestion_layout.setSpacing(8)

        self.suggestion_thumb = QtWidgets.QLabel()
        self.suggestion_thumb.setFixedSize(80, 28)
        self.suggestion_thumb.setScaledContents(True)
        self.suggestion_thumb.setStyleSheet(
            "background: #000; border-right: 1px solid #2e3340;"
        )
        self.suggestion_layout.addWidget(self.suggestion_thumb)

        self.suggestion_text = QtWidgets.QLabel("")
        self.suggestion_text.setStyleSheet(
            f"color: {PALETTE['accent']}; font-size: 11px; font-weight: 800; border: none; background: transparent;"
        )
        self.suggestion_layout.addWidget(self.suggestion_text)

        self.suggestion_opacity = QtWidgets.QGraphicsOpacityEffect(
            self.suggestion_widget
        )
        self.suggestion_widget.setGraphicsEffect(self.suggestion_opacity)
        self.suggestion_opacity.setOpacity(0.0)
        toolbox_row.addWidget(self.suggestion_widget)

        # This stretch pushes the controls to the far right
        toolbox_row.addStretch()

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet(
            f"color: {PALETTE['text_primary']}; font-size: 11px; font-weight: bold; margin-left: 10px;"
        )
        self.status_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        # Avoid hardcoded 200px constraint that clips long error messages
        self.status_label.setMinimumWidth(180)
        self.status_label.setMaximumWidth(320)
        toolbox_row.addWidget(self.status_label)

        self.force_cb = QtWidgets.QCheckBox("Force Overwrite")
        self.force_cb.setStyleSheet(
            f"color: {PALETTE['text_secondary']}; font-size: 11px;"
        )
        self.force_cb.stateChanged.connect(self._update_button_state)
        toolbox_row.addWidget(self.force_cb)

        # Inject button — shown in normal state, hidden while downloading
        self.inject_btn = QtWidgets.QPushButton("↓ Inject from Steam")
        self.inject_btn.setFixedWidth(160)
        self.inject_btn.clicked.connect(self._on_inject_clicked)
        toolbox_row.addWidget(self.inject_btn)

        # Delete button
        self.delete_btn = QtWidgets.QPushButton()
        self.delete_btn.setIcon(get_icon("trash"))
        self.delete_btn.setIconSize(QtCore.QSize(22, 22))
        self.delete_btn.setToolTip("Delete shortcut")
        self.delete_btn.setFixedSize(40, 40)
        self.delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(224, 82, 82, 40); /* Palette Danger red */
                border-radius: 20px;
            }
        """)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        toolbox_row.addWidget(self.delete_btn)

        self.main_layout.addLayout(toolbox_row)
        self.main_layout.addSpacing(20)

        # --- Row 2: Game Title ---
        title_row = QtWidgets.QHBoxLayout()
        title_row.addStretch()  # Left spacer

        # The Display Label
        self.title_label = QtWidgets.QLabel("Asset Details")
        self.title_label.setObjectName("heading")
        self.title_label.setWordWrap(True)
        self.title_label.setFixedWidth(600)  # Fix width to prevent window stretching
        self.title_label.setMinimumHeight(70)  # Fix height too
        self.title_label.setAlignment(
            QtCore.Qt.AlignCenter
        )  # Center text within the label
        title_row.addWidget(self.title_label)

        # Edit Input
        self.title_edit = QtWidgets.QLineEdit()
        self.title_edit.setFixedWidth(600)
        self.title_edit.setMinimumHeight(70)
        self.title_edit.setAlignment(QtCore.Qt.AlignCenter)
        self.title_edit.setVisible(False)
        self.title_edit.setStyleSheet(f"""
            font-size: 22px;
            font-weight: 700;
            color: {PALETTE['text_primary']};
            background: {PALETTE['bg_surface']};
            border: 1px solid {PALETTE['accent']};
            border-radius: 6px;
        """)
        self.title_edit.returnPressed.connect(self._toggle_edit_name)
        title_row.addWidget(self.title_edit)

        # The Edit/Save Button
        self.edit_btn = QtWidgets.QPushButton()
        self.edit_btn.setIcon(get_icon("edit"))
        self.edit_btn.setIconSize(QtCore.QSize(22, 22))
        self.edit_btn.setToolTip("Rename game")
        self.edit_btn.setFixedSize(40, 40)
        self.edit_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 20);
                border-radius: 20px;
            }
        """)
        self.edit_btn.clicked.connect(self._toggle_edit_name)
        title_row.addWidget(self.edit_btn)

        title_row.addStretch()  # Right spacer
        self.main_layout.addLayout(title_row)

        self.main_layout.addSpacing(40)

        # Asset Grid
        self.grid = QtWidgets.QGridLayout()
        self.grid.setSpacing(0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        # Initialize persistent slots
        self._asset_slots = {}
        positions = {
            "capsule": (0, 0),
            "header": (0, 1),
            "hero": (1, 0),
            "logo": (1, 1),
            "json": (2, 0),
        }

        for key, (row, col) in positions.items():
            slot = AssetSlot(key)
            slot.manual_upload_requested.connect(self._on_manual_upload)
            self._asset_slots[key] = slot
            alignment = QtCore.Qt.AlignLeft if col == 0 else QtCore.Qt.AlignRight
            self.grid.addWidget(slot, row, col, alignment | QtCore.Qt.AlignTop)

        self.main_layout.addLayout(self.grid)
        self.main_layout.addStretch()

        # Attach opacity effects for animations
        self.btn_opacity_effect = QtWidgets.QGraphicsOpacityEffect(self.inject_btn)
        self.inject_btn.setGraphicsEffect(self.btn_opacity_effect)

        self.status_opacity_effect = QtWidgets.QGraphicsOpacityEffect(self.status_label)
        self.status_label.setGraphicsEffect(self.status_opacity_effect)

        # Initial states
        self.status_opacity_effect.setOpacity(0.0)
        self.btn_opacity_effect.setOpacity(1.0)
        # Persistent, cancellable timer for status fades
        self._status_fade_timer = QtCore.QTimer(self)
        self._status_fade_timer.setSingleShot(True)
        self._status_fade_timer.timeout.connect(self._fade_out_status)

    def _on_back_clicked(self) -> None:
        """Cancels any running tasks, resets edit mode, and navigates back."""
        self._reset_edit_mode()
        self._task_runner.cancel_all()
        self.back_requested.emit()

    def _reset_edit_mode(self) -> None:
        """Ensures edit mode is cancelled and reset to view mode."""
        if hasattr(self, "title_edit") and self.title_edit.isVisible():
            self.title_edit.setVisible(False)
            self.title_label.setVisible(True)
            self.edit_btn.setIcon(get_icon("edit"))
            self.edit_btn.setToolTip("Rename game")

    def _cancel_active_download(self) -> None:
        """Requests cancellation of active download task."""
        self.status_label.setText("Cancelling…")
        self._task_runner.cancel("download")

    def _fade_out_status(self) -> None:
        self.status_anim = QtCore.QPropertyAnimation(
            self.status_opacity_effect, b"opacity", self
        )
        self.status_anim.setDuration(400)
        self.status_anim.setEndValue(0.0)
        self.status_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
        self.status_anim.start()

    def _update_button_state(self):
        """Animates button and label states based on asset and search state."""
        if getattr(self, "_is_busy", False):
            return

        can_inject = not self._all_assets_present or self.force_cb.isChecked()
        target_btn_opacity = 1.0 if can_inject else 0.3

        is_searching = self._search_state == SearchState.SEARCHING
        is_matched = self._search_state == SearchState.FOUND

        show_status = (
            (self._all_assets_present and not self.force_cb.isChecked())
            or is_searching
            or is_matched
        )

        target_status_opacity = 1.0 if show_status else 0.0

        if show_status and self._search_state == SearchState.IDLE:
            self.status_label.setText("✅ All assets present")

        self.btn_anim = QtCore.QPropertyAnimation(
            self.btn_opacity_effect, b"opacity", self
        )
        self.btn_anim.setDuration(250)
        self.btn_anim.setEndValue(target_btn_opacity)
        self.btn_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
        self.btn_anim.start()

        self.status_anim = QtCore.QPropertyAnimation(
            self.status_opacity_effect, b"opacity", self
        )
        self.status_anim.setDuration(250)
        self.status_anim.setEndValue(target_status_opacity)
        self.status_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
        self.status_anim.start()

        self.inject_btn.setEnabled(can_inject)

    def _on_inject_clicked(self):
        if self._is_busy:
            self._cancel_active_download()
            return

        if not confirm_steam_closed(self):
            return

        default_id = self._suggested_steam_id if self._suggested_steam_id else ""
        steam_id, ok = QtWidgets.QInputDialog.getText(
            self, "Inject Assets", "Enter Steam AppID:", text=default_id
        )

        if not (ok and steam_id):
            return

        steam_id = steam_id.strip()
        if not steam_id.isdigit():
            self.status_opacity_effect.setOpacity(1.0)
            self.status_label.setText("⚠️ AppID must be numeric")
            return

        force = self.force_cb.isChecked()

        if hasattr(self, "_status_fade_timer") and self._status_fade_timer.isActive():
            self._status_fade_timer.stop()
        if (
            hasattr(self, "status_anim")
            and self.status_anim.state() == QtCore.QPropertyAnimation.Running
        ):
            self.status_anim.stop()

        self._set_busy(True)
        self.status_opacity_effect.setOpacity(1.0)
        self.status_label.setText("Initializing...")

        grid_dir = os.path.join(os.path.dirname(self._current_shortcuts_path), "grid")
        task = DownloadTask(steam_id, self._current_appid, grid_dir, force)

        self._task_runner.start(
            task,
            key="download",
            on_result=self._on_download_finished,
            on_error=self._on_download_error,
            on_cancelled=self._on_download_cancelled,
            on_progress=self.status_label.setText,
        )

    def _on_download_finished(self, result: tuple[bool, str, str]):
        success, message, target_id = result
        if str(target_id) != str(self._current_appid):
            return

        self._set_busy(False)
        self.status_label.setText("")

        if success:
            grid_dir = os.path.join(
                os.path.dirname(self._current_shortcuts_path), "grid"
            )
            icon_candidate = os.path.join(grid_dir, f"{self._current_appid}_icon.ico")
            if os.path.isfile(icon_candidate):
                update_shortcut_icon(
                    self._current_shortcuts_path,
                    self._current_appid,
                    icon_candidate,
                )

            self.load_assets(
                self._current_name, self._current_shortcuts_path, self._current_appid
            )
            self.name_changed.emit()
        else:
            QtWidgets.QMessageBox.critical(self, "Download Failed", message)
            self.status_opacity_effect.setOpacity(0.0)

    def _on_download_error(self, exc: Exception):
        self._set_busy(False)
        self.status_opacity_effect.setOpacity(0.0)
        QtWidgets.QMessageBox.critical(
            self, "Download Error", f"Download operation failed: {exc}"
        )

    def _on_download_cancelled(self):
        self._set_busy(False)
        self.status_label.setText("Cancelled.")
        self.status_opacity_effect.setOpacity(1.0)
        self._status_fade_timer.start(2000)

    def _on_search_finished(self, data: dict[str, Any]):
        status = data.get("status")
        item = data.get("item")

        if status == "ok" and item:
            self._search_state = SearchState.FOUND
            self._suggested_steam_id = item.appid
            self.suggestion_text.setText(item.appid)

            thumb_bytes = data.get("thumb_bytes")
            if thumb_bytes:
                pix = QPixmap()
                if pix.loadFromData(thumb_bytes):
                    self.suggestion_thumb.setPixmap(pix)
                    self.suggestion_thumb.show()
                else:
                    self.suggestion_thumb.hide()
            else:
                self.suggestion_thumb.hide()

            self.suggest_anim = QtCore.QPropertyAnimation(
                self.suggestion_opacity, b"opacity", self
            )
            self.suggest_anim.setDuration(400)
            self.suggest_anim.setEndValue(1.0)
            self.suggest_anim.setEasingCurve(QtCore.QEasingCurve.OutQuad)
            self.suggest_anim.start()

            self.status_label.setText("💡 Found Steam Match")
        elif status == "error":
            self._search_state = SearchState.NOT_FOUND
            self._suggested_steam_id = None
            self.status_label.setText("🌐 Search failed - check connection")
        else:
            self._search_state = SearchState.NOT_FOUND
            self._suggested_steam_id = None
            self.status_label.setText("❓ No match found")

        self._update_button_state()

    def _on_search_error(self, exc: Exception):
        self._search_state = SearchState.NOT_FOUND
        self._suggested_steam_id = None
        self.status_label.setText("🌐 Search failed - check connection")
        self._update_button_state()

    def load_assets(self, game_name, shortcuts_path, appid):
        # Defuse any active rename edit state immediately
        self._reset_edit_mode()

        current_id = getattr(self, "_current_appid", None)
        is_new_game = str(appid) != str(current_id)

        self._current_name = game_name
        self._current_shortcuts_path = shortcuts_path
        self._current_appid = appid
        self.title_label.setText(game_name)

        if is_new_game:
            self._trigger_search(game_name)

        grid_dir = os.path.join(os.path.dirname(shortcuts_path), "grid")
        status = get_asset_status(grid_dir, appid)
        # Visual assets + JSON required for complete check
        self._all_assets_present = all(
            status[slot][0] for slot in ("capsule", "header", "hero", "logo", "json")
        )

        for key, (exists, path) in status.items():
            if key in self._asset_slots:
                self._asset_slots[key].update_slot(exists, path)

        self._update_button_state()

    def _toggle_edit_name(self):
        if not self.title_edit.isVisible():
            if not confirm_steam_closed(self):
                return

            self.title_edit.setText(self._current_name)
            self.title_label.setVisible(False)
            self.title_edit.setVisible(True)
            self.edit_btn.setIcon(get_icon("check"))
            self.edit_btn.setToolTip("Save new name")
            self.title_edit.setFocus()
        else:
            new_name = self.title_edit.text().strip()
            if self._current_appid and new_name and new_name != self._current_name:
                success, msg = update_shortcut_name(
                    self._current_shortcuts_path, self._current_appid, new_name
                )
                if success:
                    self._current_name = new_name
                    self.title_label.setText(new_name)
                    self.name_changed.emit()
                    self._trigger_search(new_name)
                else:
                    QtWidgets.QMessageBox.warning(self, "Error", msg)

            self.title_edit.setVisible(False)
            self.title_label.setVisible(True)
            self.edit_btn.setIcon(get_icon("edit"))
            self.edit_btn.setToolTip("Rename game")

    def _trigger_search(self, game_name):
        if hasattr(self, "suggest_anim"):
            self.suggest_anim.stop()

        if hasattr(self, "_status_fade_timer") and self._status_fade_timer.isActive():
            self._status_fade_timer.stop()
        if (
            hasattr(self, "status_anim")
            and self.status_anim.state() == QtCore.QPropertyAnimation.Running
        ):
            self.status_anim.stop()

        self.suggestion_opacity.setOpacity(0.0)
        self.suggestion_text.setText("")
        self.suggestion_thumb.setPixmap(QPixmap())
        self._suggested_steam_id = None

        self._search_state = SearchState.SEARCHING
        self.status_opacity_effect.setOpacity(1.0)
        self.status_label.setText("🔍 Searching Steam...")

        # Keyed execution: starting "search" supersedes any pending search task
        self._task_runner.start(
            SearchTask(game_name),
            key="search",
            on_result=self._on_search_finished,
            on_error=self._on_search_error,
        )

    def _on_delete_clicked(self):
        if not self._current_appid:
            return

        if not confirm_steam_closed(self):
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to remove '{self._current_name}' from Steam?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply == QtWidgets.QMessageBox.No:
            return

        clean_assets = QtWidgets.QMessageBox.question(
            self,
            "Cleanup Assets",
            "Would you also like to delete the associated images and JSON from the grid folder?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes,
        )

        vdf_path = self._current_shortcuts_path
        success, msg = delete_shortcut(vdf_path, self._current_appid)

        if success:
            if clean_assets == QtWidgets.QMessageBox.Yes:
                grid_dir = os.path.join(os.path.dirname(vdf_path), "grid")
                # Unified deletion cleaning all extensions and JSON
                delete_all_assets(grid_dir, self._current_appid)

            self.name_changed.emit()
            self._reset_edit_mode()
            self.back_requested.emit()
        else:
            QtWidgets.QMessageBox.critical(self, "Error", msg)

    def _on_manual_upload(self, asset_type):
        if asset_type == "json":
            return

        if not confirm_steam_closed(self):
            return

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            f"Select {asset_type.capitalize()}",
            "",
            "Images (*.png *.jpg *.jpeg);;All Files (*.*)",
        )
        if not file_path:
            return

        suffix = SLOT_MAPPING.get(asset_type, ("", ""))[0]
        ext = os.path.splitext(file_path)[1].lower()

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            if not validate_image_bytes(content, ext):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Image",
                    f"The selected file is not a valid {ext.upper()} image file.",
                )
                return

            grid_dir = os.path.join(
                os.path.dirname(self._current_shortcuts_path), "grid"
            )
            # Atomic replacement with sibling extension pruning
            write_asset_atomic(grid_dir, self._current_appid, suffix, ext, content)

            self.load_assets(
                self._current_name, self._current_shortcuts_path, self._current_appid
            )
            self.name_changed.emit()

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Upload Error", f"Failed to upload asset: {e}"
            )
