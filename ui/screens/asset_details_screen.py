import os
import requests
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGridLayout,
    QInputDialog,
    QMessageBox,
    QCheckBox,
    QGraphicsOpacityEffect,
    QSizePolicy,
    QLineEdit,
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import (
    Qt,
    QThread,
    QObject,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
)
from ui.theme import PALETTE
from core.steam import get_asset_status
from core.asset_provider import download_assets, search_steam_apps


class SearchWorker(QObject):
    """Fetches a potential AppID match and its thumbnail in the background."""

    finished = Signal(object)

    def __init__(self, query):
        super().__init__()
        self.query = query

    def run(self):
        """Perform the search and thumbnail download."""
        result = search_steam_apps(self.query)
        if result and result.get("thumb_url"):
            try:
                url = result["thumb_url"]
                if url.startswith("//"):
                    url = "https:" + url

                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                resp = requests.get(url, headers=headers, timeout=5)

                if resp.status_code == 200:
                    result["thumb_bytes"] = resp.content
                else:
                    result["thumb_bytes"] = None
            except Exception:
                result["thumb_bytes"] = None
        self.finished.emit(result)


class DownloadWorker(QObject):
    """Handles the heavy network lifting in a separate thread."""

    finished = Signal(bool, str)
    status_update = Signal(str)

    def __init__(self, steam_id, local_id, grid_dir, force):
        super().__init__()
        self.steam_id = steam_id
        self.local_id = local_id
        self.grid_dir = grid_dir
        self.force = force

    def run(self):
        # We pass the signal's emit function as the callback
        success, message = download_assets(
            self.steam_id,
            self.local_id,
            self.grid_dir,
            self.force,
            status_callback=self.status_update.emit,
        )
        self.finished.emit(success, message)


class AssetDetailsScreen(QWidget):
    back_requested = Signal()
    name_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # ALL state variables must be here
        self._thread = None
        self._search_thread = None
        self._worker = None
        self._suggested_steam_id = None
        self._current_appid = None  # Crucial fix
        self._all_assets_present = False
        self._build_ui()

    def _build_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 24, 24, 24)

        # --- Row 1: Toolbox (Back, Match, Status, Controls) ---
        toolbox_row = QHBoxLayout()

        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondary")
        back_btn.clicked.connect(self.back_requested)
        toolbox_row.addWidget(back_btn)

        # Smart Suggestion Badge
        self.suggestion_widget = QFrame()
        self.suggestion_widget.setFixedHeight(36)
        self.suggestion_widget.setFixedWidth(220)
        self.suggestion_widget.setStyleSheet(f"""
            QFrame {{
                background: {PALETTE['bg_card']}; 
                border: 1px solid {PALETTE['border']};
                border-radius: 4px;
            }}
        """)
        self.suggestion_layout = QHBoxLayout(self.suggestion_widget)
        self.suggestion_layout.setContentsMargins(4, 0, 10, 0)
        self.suggestion_layout.setSpacing(8)

        self.suggestion_thumb = QLabel()
        self.suggestion_thumb.setFixedSize(80, 30)
        self.suggestion_thumb.setScaledContents(True)
        self.suggestion_thumb.setStyleSheet(
            "background: #000; border-right: 1px solid #2e3340;"
        )
        self.suggestion_layout.addWidget(self.suggestion_thumb)

        self.suggestion_text = QLabel("")
        self.suggestion_text.setStyleSheet(
            f"color: {PALETTE['accent']}; font-size: 11px; font-weight: 800; border: none; background: transparent;"
        )
        self.suggestion_layout.addWidget(self.suggestion_text)

        self.suggestion_opacity = QGraphicsOpacityEffect(self.suggestion_widget)
        self.suggestion_widget.setGraphicsEffect(self.suggestion_opacity)
        self.suggestion_opacity.setOpacity(0.0)
        toolbox_row.addWidget(self.suggestion_widget)

        # This stretch pushes the controls to the far right
        toolbox_row.addStretch()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {PALETTE['text_primary']}; font-size: 11px; font-weight: bold; margin-right: 10px;"
        )
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        toolbox_row.addWidget(self.status_label)

        self.force_cb = QCheckBox("Force Overwrite")
        self.force_cb.setStyleSheet(
            f"color: {PALETTE['text_secondary']}; font-size: 11px;"
        )
        self.force_cb.stateChanged.connect(self._update_button_state)
        toolbox_row.addWidget(self.force_cb)

        self.inject_btn = QPushButton("↓ Inject from Steam")
        self.inject_btn.clicked.connect(self._on_inject_clicked)
        toolbox_row.addWidget(self.inject_btn)

        self.layout.addLayout(toolbox_row)
        self.layout.addSpacing(20)

        # --- Row 2: Game Title ---
        title_row = QHBoxLayout()
        title_row.addStretch()  # Left spacer

        # The Display Label
        self.title_label = QLabel("Asset Details")
        self.title_label.setObjectName("heading")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumWidth(750)  # Cap width to prevent window stretching
        self.title_label.setAlignment(Qt.AlignCenter)  # Center text within the label
        title_row.addWidget(self.title_label)

        # Edit Input
        self.title_edit = QLineEdit()
        self.title_edit.setFixedWidth(400)
        self.title_edit.setVisible(False)
        self.title_edit.setStyleSheet(f"""
            font-size: 22px; 
            font-weight: 700; 
            color: {PALETTE['text_primary']};
            background: {PALETTE['bg_surface']};
            border: 1px solid {PALETTE['accent']};
        """)
        title_row.addWidget(self.title_edit)

        # The Edit/Save Button
        self.edit_btn = QPushButton("🖊️")
        self.edit_btn.setFixedSize(40, 40)
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 20px;
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
        self.layout.addLayout(title_row)

        self.layout.addSpacing(40)

        # Asset Grid
        self.grid = QGridLayout()
        self.grid.setSpacing(0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.layout.addLayout(self.grid)
        self.layout.addStretch()

        # Attach opacity effects for animations
        self.btn_opacity_effect = QGraphicsOpacityEffect(self.inject_btn)
        self.inject_btn.setGraphicsEffect(self.btn_opacity_effect)

        self.status_opacity_effect = QGraphicsOpacityEffect(self.status_label)
        self.status_label.setGraphicsEffect(self.status_opacity_effect)

        # Initial states
        self.status_opacity_effect.setOpacity(0.0)
        self.btn_opacity_effect.setOpacity(1.0)

    def _update_button_state(self):
        """Animates button and label states based on asset presence and checkbox."""
        can_inject = not self._all_assets_present or self.force_cb.isChecked()

        # Determine target opacities
        target_btn_opacity = 1.0 if can_inject else 0.3

        # The label should be visible if:
        # 1. Assets are all present (and we aren't forcing)
        # 2. OR the label currently contains search/match text
        has_search_text = (
            "Searching" in self.status_label.text()
            or "match" in self.status_label.text()
        )
        show_status = (
            self._all_assets_present and not self.force_cb.isChecked()
        ) or has_search_text

        target_status_opacity = 1.0 if show_status else 0.0

        # Only show 'All assets present' if we aren't currently searching or connecting
        is_busy = (self._search_thread and self._search_thread.isRunning()) or (
            self._thread and self._thread.isRunning()
        )

        if show_status and not is_busy:
            self.status_label.setText("✅ All assets present")

        # 1. Animate Inject Button Opacity
        self.btn_anim = QPropertyAnimation(self.btn_opacity_effect, b"opacity")
        self.btn_anim.setDuration(250)  # milliseconds
        self.btn_anim.setEndValue(target_btn_opacity)
        self.btn_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.btn_anim.start()

        # 2. Animate Status Label Opacity
        self.status_anim = QPropertyAnimation(self.status_opacity_effect, b"opacity")
        self.status_anim.setDuration(250)
        self.status_anim.setEndValue(target_status_opacity)
        self.status_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.status_anim.start()

        # Keep the actual functional state
        self.inject_btn.setEnabled(can_inject)

    def _on_inject_clicked(self, auto_id=None):
        # 1. Determine Steam ID and Force state
        if auto_id:
            steam_id = auto_id
            force = False  # Never force on auto-fills
        else:
            default_id = self._suggested_steam_id if self._suggested_steam_id else ""
            steam_id, ok = QInputDialog.getText(
                self, "Inject Assets", "Enter Steam AppID:", text=default_id
            )
            if not (ok and steam_id):
                return
            force = self.force_cb.isChecked()

        # UI Feedback
        self.inject_btn.setEnabled(False)
        self.force_cb.setEnabled(False)
        self.status_opacity_effect.setOpacity(1.0)
        self.status_label.setText("Initializing...")

        # Setup Thread and Worker
        self._thread = QThread()
        grid_dir = os.path.join(os.path.dirname(self._current_shortcuts_path), "grid")
        self._worker = DownloadWorker(steam_id, self._current_appid, grid_dir, force)
        self._worker.moveToThread(self._thread)

        # Connect Signals
        self._thread.started.connect(self._worker.run)
        self._worker.status_update.connect(
            self.status_label.setText
        )  # Update text in real-time
        self._worker.finished.connect(self._on_download_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_download_finished(self, success, message):
        self.inject_btn.setEnabled(True)
        self.force_cb.setEnabled(True)
        self.status_label.setText("")
        if success:
            # Refresh the view to show new assets
            self.load_assets(
                self._current_name, self._current_shortcuts_path, self._current_appid
            )
        else:
            QMessageBox.critical(self, "Error", message)

    def _on_search_finished(self, result):
        """Populates and fades in the smart suggestion bar."""
        if result:
            self._suggested_steam_id = result["id"]
            self.suggestion_text.setText(f"MATCH: {result['id']}")

            if result.get("thumb_bytes"):
                pix = QPixmap()
                if pix.loadFromData(result["thumb_bytes"]):
                    self.suggestion_thumb.setPixmap(pix)
                    self.suggestion_thumb.show()
                else:
                    self.suggestion_thumb.hide()
            else:
                self.suggestion_thumb.hide()

            # Trigger fade-in animation
            self.suggest_anim = QPropertyAnimation(self.suggestion_opacity, b"opacity")
            self.suggest_anim.setDuration(400)
            self.suggest_anim.setEndValue(1.0)
            self.suggest_anim.setEasingCurve(QEasingCurve.OutQuad)
            self.suggest_anim.start()

            # Update status label to show we found something
            self.status_label.setText(f"💡 Found Steam Match")
        else:
            self._suggested_steam_id = None
            self.suggestion_opacity.setOpacity(0.0)
            self.status_label.setText("❓ No match found")

    def load_assets(self, game_name, shortcuts_path, appid):
        # 1. Improved new game detection with string conversion
        current_id = getattr(self, "_current_appid", None)
        is_new_game = str(appid) != str(current_id)

        self._current_name = game_name
        self._current_shortcuts_path = shortcuts_path
        self._current_appid = appid
        self.title_label.setText(game_name)

        if is_new_game:
            self._trigger_search(game_name)

        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        status = get_asset_status(shortcuts_path, appid)
        self._all_assets_present = all(exists for exists, path in status.values())
        self._update_button_state()

        positions = {
            "capsule": (0, 0),
            "header": (0, 1),
            "hero": (1, 0),
            "logo": (1, 1),
            "json": (2, 0),
        }

        for key, (exists, path) in status.items():
            container = QWidget()
            container.setFixedWidth(320)
            container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(10)
            container_layout.setAlignment(Qt.AlignTop)

            label = QLabel(key.upper())
            label.setStyleSheet(
                f"font-size: 12px; font-weight: 900; letter-spacing: 1.5px; color: {PALETTE['accent']}; background: transparent;"
            )
            container_layout.addWidget(label)

            if exists and key != "json":
                img_label = QLabel()
                pix = QPixmap(path)
                if not pix.isNull():
                    scaled_pix = pix.scaled(
                        320, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    img_label.setPixmap(scaled_pix)

                img_label.setStyleSheet("background: transparent;")
                img_label.setMinimumHeight(160)
                container_layout.addWidget(img_label)
            elif exists and key == "json":
                json_lbl = QLabel("✓ Position Data Found")
                json_lbl.setStyleSheet(
                    f"color: {PALETTE['success']}; font-size: 14px; font-weight: bold; background: transparent;"
                )
                container_layout.addWidget(json_lbl)
            else:
                msg = QLabel("× Missing")
                msg.setStyleSheet(
                    f"color: {PALETTE['danger']}; font-size: 14px; font-weight: bold; background: transparent;"
                )
                msg.setMinimumHeight(160)
                msg.setAlignment(Qt.AlignTop)
                container_layout.addWidget(msg)

            row, col = positions[key]
            # Column 0 (Capsule/Hero) sticks Left.
            # Column 1 (Header/Logo) sticks Right.
            alignment = Qt.AlignLeft if col == 0 else Qt.AlignRight
            self.grid.addWidget(container, row, col, alignment | Qt.AlignTop)

    def _toggle_edit_name(self):
        import shutil
        from core.vdf_parser import update_shortcut_name

        # Case: Transitioning from View to Edit
        if not self.title_edit.isVisible():
            # Trigger Backup immediately upon deciding to edit
            vdf_path = self._current_shortcuts_path
            if os.path.exists(vdf_path):
                shutil.copy2(vdf_path, vdf_path + ".bak")

            self.title_edit.setText(self._current_name)
            self.title_label.setVisible(False)
            self.title_edit.setVisible(True)
            self.edit_btn.setText("✅")
            self.title_edit.setFocus()

        # Case: Finalizing Changes (Transitioning from Edit to View)
        else:
            new_name = self.title_edit.text().strip()
            if new_name and new_name != self._current_name:
                success, msg = update_shortcut_name(
                    self._current_shortcuts_path, self._current_appid, new_name
                )
                if success:
                    self._current_name = new_name
                    self.title_label.setText(new_name)
                    self.name_changed.emit()
                    self._trigger_search(new_name)
                else:
                    QMessageBox.warning(self, "Error", msg)

            self.title_edit.setVisible(False)
            self.title_label.setVisible(True)
            self.edit_btn.setText("🖊️")

    def _trigger_search(self, game_name):
        """Triggers a background Steam search for the given name."""
        if self._search_thread is not None:
            try:
                if self._search_thread.isRunning():
                    self._search_thread.quit()
                    self._search_thread.wait()
            except:
                pass

        self.suggestion_opacity.setOpacity(0.0)
        self.suggestion_text.setText("")
        self._suggested_steam_id = None

        self.status_opacity_effect.setOpacity(1.0)
        self.status_label.setText("🔍 Searching Steam...")

        self._search_thread = QThread()
        self._search_worker = SearchWorker(game_name)
        self._search_worker.moveToThread(self._search_thread)
        self._search_thread.started.connect(self._search_worker.run)
        self._search_worker.finished.connect(self._on_search_finished)
        self._search_worker.finished.connect(self._search_thread.quit)
        self._search_thread.start()
