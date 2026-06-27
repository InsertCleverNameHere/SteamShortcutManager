import os
import shutil
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
    QFileDialog,
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

    finished = Signal(object, str, int)

    def __init__(self, query, generation):
        super().__init__()
        self.query = query
        self.generation = generation

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
        self.finished.emit(result, self.query, self.generation)


class DownloadWorker(QObject):
    """Handles the heavy network lifting in a separate thread."""

    finished = Signal(bool, str, str)
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
        self.finished.emit(success, message, self.local_id)


class AssetDetailsScreen(QWidget):
    back_requested = Signal()
    name_changed = Signal()

    _active_threads = set()

    def _set_busy(self, is_busy: bool):
        """Atomically enables or disables controls with visual feedback."""
        # is_busy=True means UI is locked
        enabled = not is_busy
        self.back_btn.setEnabled(enabled)
        self.inject_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        self.edit_btn.setEnabled(enabled)
        self.force_cb.setEnabled(enabled)

        # Visual dimming for the back button
        if is_busy:
            eff = QGraphicsOpacityEffect(self.back_btn)
            eff.setOpacity(0.4)
            self.back_btn.setGraphicsEffect(eff)
        else:
            self.back_btn.setGraphicsEffect(None)

    def _on_thread_finished(self):
        """Safely clears the thread reference after it is deleted."""
        self._thread = None

    def _on_search_thread_finished(self, thread_instance):
        """Removes a thread from the registry once it has safely finished."""
        if thread_instance in AssetDetailsScreen._active_threads:
            AssetDetailsScreen._active_threads.remove(thread_instance)

        if self._search_thread == thread_instance:
            self._search_thread = None

    def __init__(self, parent=None):
        super().__init__(parent)
        # ALL state variables must be here
        self._thread = None
        self._search_thread = None
        self._worker = None
        self._suggested_steam_id = None
        self._current_appid = None
        self._current_shortcuts_path = ""
        self._current_name = ""
        self._search_generation = 0
        self._all_assets_present = False
        self._build_ui()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)

        # --- Row 1: Toolbox (Back, Match, Status, Controls) ---
        toolbox_row = QHBoxLayout()

        self.back_btn = QPushButton("← Back")
        self.back_btn.setObjectName("secondary")
        self.back_btn.clicked.connect(self.back_requested)
        toolbox_row.addWidget(self.back_btn)

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

        # Delete button
        self.delete_btn = QPushButton("🗑️")
        self.delete_btn.setFixedSize(40, 40)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 20px;
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
        self.main_layout.addLayout(title_row)

        self.main_layout.addSpacing(40)

        # Asset Grid
        self.grid = QGridLayout()
        self.grid.setSpacing(0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.main_layout.addLayout(self.grid)
        self.main_layout.addStretch()

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

            steam_id = steam_id.strip()
            if not steam_id.isdigit():
                self.status_opacity_effect.setOpacity(1.0)
                self.status_label.setText("⚠️ AppID must be numeric")
                return

            force = self.force_cb.isChecked()

        # UI Feedback
        self._set_busy(True)
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
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def _on_download_finished(self, success, message, target_id):
        # Verify we are still viewing the same game
        if str(target_id) != str(self._current_appid):
            return

        self._set_busy(False)
        self.status_label.setText("")
        if success:
            # Refresh the view to show new assets
            self.load_assets(
                self._current_name, self._current_shortcuts_path, self._current_appid
            )
        else:
            QMessageBox.critical(self, "Error", message)

    def _on_search_finished(self, result, original_query, generation):
        """Populates and fades in the smart suggestion bar."""
        # Guard: If this is an orphaned result, ignore it
        if generation != self._search_generation:
            return

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

            # Use self as parent to prevent GC mid-animation (Phase 3 preview)
            self.suggest_anim = QPropertyAnimation(
                self.suggestion_opacity, b"opacity", self
            )
            self.suggest_anim.setDuration(400)
            self.suggest_anim.setEndValue(1.0)
            self.suggest_anim.setEasingCurve(QEasingCurve.OutQuad)
            self.suggest_anim.start()

            self.status_label.setText(f"💡 Found Steam Match")
        else:
            self._suggested_steam_id = None
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

            # Manual Upload
            container.setCursor(Qt.PointingHandCursor)
            container.setToolTip(f"Click to manually  upload {key.upper()}")
            # User a closure to capture the current 'key'
            container.mousePressEvent = lambda e, k=key: self._on_manual_upload(k)

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
        # Visual/Animation Reset
        if hasattr(self, "suggest_anim"):
            self.suggest_anim.stop()
        self.suggestion_opacity.setOpacity(0.0)
        self.suggestion_text.setText("")
        self.suggestion_thumb.setPixmap(QPixmap())
        self._suggested_steam_id = None

        # Thread Management: Handle existing search task
        if self._search_thread and self._search_thread.isRunning():
            try:
                # Disconnect UI slots so the old thread cannot update this screen
                self._search_thread.finished.disconnect(self._on_search_finished)
            except (TypeError, RuntimeError):
                pass
            # Move to registry so Python doesn't delete the C++ object mid-run
            AssetDetailsScreen._active_threads.add(self._search_thread)

        self._search_generation += 1
        current_gen = self._search_generation
        self.status_opacity_effect.setOpacity(1.0)
        self.status_label.setText("🔍 Searching Steam...")

        # Create the new thread and worker
        new_thread = QThread()
        worker = SearchWorker(game_name, current_gen)
        new_thread.worker = worker
        worker.moveToThread(new_thread)

        new_thread.started.connect(worker.run)
        worker.finished.connect(self._on_search_finished)
        worker.finished.connect(new_thread.quit)
        worker.finished.connect(worker.deleteLater)
        new_thread.finished.connect(new_thread.deleteLater)

        # Cleanup: Remove from registry and clear reference on finish
        new_thread.finished.connect(
            lambda t=new_thread: self._on_search_thread_finished(t)
        )
        AssetDetailsScreen._active_threads.add(new_thread)

        self._search_thread = new_thread
        self._search_thread.start()

    def _on_delete_clicked(self):
        import shutil
        from core.vdf_parser import delete_shortcut

        # 1. Primary Confirmation
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to remove '{self._current_name}' from Steam?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.No:
            return

        # 2. Asset Cleanup Option
        clean_assets = QMessageBox.question(
            self,
            "Cleanup Assets",
            "Would you also like to delete the associated images and JSON from the grid folder?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        # 3. Create Safety Backup
        vdf_path = self._current_shortcuts_path
        if os.path.exists(vdf_path):
            shutil.copy2(vdf_path, vdf_path + ".bak")

        # 4. Perform Deletion in VDF
        success, msg = delete_shortcut(vdf_path, self._current_appid)

        if success:
            # 5. Optional Asset File Cleanup
            if clean_assets == QMessageBox.Yes:
                grid_dir = os.path.join(os.path.dirname(vdf_path), "grid")
                # Look for all 5 patterns ({appid}p.jpg, {appid}.jpg, etc.)
                for suffix in ["p", "", "_hero", "_logo"]:
                    for ext in [".jpg", ".png", ".json"]:  # covers image and json
                        target_file = os.path.join(
                            grid_dir, f"{self._current_appid}{suffix}{ext}"
                        )
                        if os.path.exists(target_file):
                            try:
                                os.remove(target_file)
                            except:
                                pass

            # 6. Finalize and Exit
            self.name_changed.emit()  # Refresh the main list
            self.back_requested.emit()  # Go back to the list automatically
        else:
            QMessageBox.critical(self, "Error", msg)

    def _on_manual_upload(self, asset_type):
        """Opens a file dialog and copies a local image to the Steam grid folder."""
        if asset_type == "json":
            # Skip JSON
            return

        # 1. Pick the file
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {asset_type.capitalize()}",
            "",
            "Images (*.png *.jpg *.jpeg);;All Files (*.*)",
        )
        if not file_path:
            return

        # 2. Determine target filename based on asset type
        # Patterns: capsule='p', header='', hero='_hero', logo='_logo'
        suffix_map = {"capsule": "p", "header": "", "hero": "_hero", "logo": "_logo"}

        ext = os.path.splitext(file_path)[1].lower()
        new_filename = f"{self._current_appid}{suffix_map[asset_type]}{ext}"
        grid_dir = os.path.join(os.path.dirname(self._current_shortcuts_path), "grid")
        dest_path = os.path.join(grid_dir, new_filename)

        try:
            # Delete existing assets with other file extensions
            for existing_ext in [".jpg", ".png", ".jpeg"]:
                potential_old_file = os.path.join(
                    grid_dir,
                    f"{self._current_appid}{suffix_map[asset_type]}{existing_ext}",
                )
                if os.path.exists(potential_old_file):
                    try:
                        os.remove(potential_old_file)
                    except:
                        pass  # Ignore errors if file is locked
            # 3. Copy and Overwrite
            shutil.copy2(file_path, dest_path)

            # 4. Refresh UI to show the new asset
            self.load_assets(
                self._current_name, self._current_shortcuts_path, self._current_appid
            )

        except Exception as e:
            QMessageBox.critical(self, "Upload Error", f"Failed to copy file: {e}")
