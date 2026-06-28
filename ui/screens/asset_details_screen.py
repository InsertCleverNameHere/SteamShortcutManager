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
from core.vdf_parser import update_shortcut_name, delete_shortcut
from ui.theme import PALETTE
from core.steam import get_asset_status
from core.asset_provider import download_assets, search_steam_apps
from enum import Enum, auto
from urllib.parse import urlparse


class SearchState(Enum):
    IDLE = auto()
    SEARCHING = auto()
    FOUND = auto()
    NOT_FOUND = auto()


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

        if isinstance(result, dict) and result.get("thumb_url"):
            try:
                url = result["thumb_url"]
                if url.startswith("//"):
                    url = "https:" + url

                parsed = urlparse(url)
                trusted_domains = (".steampowered.com", ".steamstatic.com")
                if not parsed.netloc.endswith(trusted_domains):
                    print(f"DEBUG: Blocked untrusted thumbnail URL: {url}")
                    result["thumb_bytes"] = None
                else:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    }
                    resp = requests.get(url, headers=headers, timeout=5)

                    if resp.status_code == 200:
                        result["thumb_bytes"] = resp.content
                    else:
                        result["thumb_bytes"] = None
            except Exception as e:
                print(f"DEBUG: Thumbnail download error: {e}")
                # Use .get() or check type before setting to be safe
                if isinstance(result, dict):
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


class AssetSlot(QWidget):
    """A persistent widget representing a single asset (Capsule, Hero, etc.)."""

    manual_upload_requested = Signal(str)

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.key = key
        self.setFixedWidth(320)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Click to manually upload {key.upper()}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        self.title_label = QLabel(key.upper())
        self.title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 900; letter-spacing: 1.5px; color: {PALETTE['accent']}; background: transparent;"
        )
        layout.addWidget(self.title_label)

        self.content_label = QLabel()
        self.content_label.setMinimumHeight(160)
        self.content_label.setAlignment(Qt.AlignTop)
        layout.addWidget(self.content_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.manual_upload_requested.emit(self.key)

    def update_slot(self, exists, path):
        """Updates the content without recreating the widget."""
        if exists:
            if self.key == "json":
                self.content_label.setPixmap(QPixmap())
                self.content_label.setText("✓ Position Data Found")
                self.content_label.setStyleSheet(
                    f"color: {PALETTE['success']}; font-size: 14px; font-weight: bold; background: transparent;"
                )
            else:
                pix = QPixmap(path)
                if not pix.isNull():
                    self.content_label.setPixmap(
                        pix.scaled(
                            320, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
                self.content_label.setText("")
                self.content_label.setStyleSheet("background: transparent;")
        else:
            self.content_label.setPixmap(QPixmap())
            self.content_label.setText("× Missing")
            self.content_label.setStyleSheet(
                f"color: {PALETTE['danger']}; font-size: 14px; font-weight: bold; background: transparent;"
            )


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
            # Re-create the effect to make sure it stays alive for the next cycle
            self._back_dim_effect = QGraphicsOpacityEffect(self)
            self._back_dim_effect.setOpacity(0.4)
            self.back_btn.setGraphicsEffect(self._back_dim_effect)
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
        self._search_state = SearchState.IDLE
        self._all_assets_present = False
        self._back_dim_effect = QGraphicsOpacityEffect(self)
        self._back_dim_effect.setOpacity(0.4)
        self._build_ui()

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)

        # --- Row 1: Toolbox (Back, Match, Status, Controls) ---
        toolbox_row = QHBoxLayout()
        toolbox_row.setSpacing(5)

        self.back_btn = QPushButton("← Back")
        self.back_btn.setObjectName("secondary")
        self.back_btn.setFixedSize(80, 35)
        self.back_btn.clicked.connect(self.back_requested)
        toolbox_row.addWidget(self.back_btn)

        # Smart Suggestion Badge
        self.suggestion_widget = QFrame()
        self.suggestion_widget.setFixedHeight(35)
        self.suggestion_widget.setFixedWidth(140)
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
        self.suggestion_thumb.setFixedSize(80, 28)
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
            f"color: {PALETTE['text_primary']}; font-size: 11px; font-weight: bold; margin-left: 10px;"
        )
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_label.setFixedWidth(200)
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
        self.title_label.setFixedWidth(600)  # Fix width to prevent window stretching
        self.title_label.setMinimumHeight(70)  # Fix height too
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
            alignment = Qt.AlignLeft if col == 0 else Qt.AlignRight
            self.grid.addWidget(slot, row, col, alignment | Qt.AlignTop)

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
        """Animates button and label states based on asset and search state."""
        can_inject = not self._all_assets_present or self.force_cb.isChecked()
        target_btn_opacity = 1.0 if can_inject else 0.3

        # Use the Enum instead of probing label text
        is_searching = self._search_state == SearchState.SEARCHING
        is_matched = self._search_state == SearchState.FOUND

        show_status = (
            (self._all_assets_present and not self.force_cb.isChecked())
            or is_searching
            or is_matched
        )

        target_status_opacity = 1.0 if show_status else 0.0

        # Only update text if we aren't in a searching/found state
        # (those states manage their own text)
        if show_status and self._search_state == SearchState.IDLE:
            self.status_label.setText("✅ All assets present")

        # 1. Animate Inject Button Opacity
        self.btn_anim = QPropertyAnimation(self.btn_opacity_effect, b"opacity", self)
        self.btn_anim.setDuration(250)  # milliseconds
        self.btn_anim.setEndValue(target_btn_opacity)
        self.btn_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.btn_anim.start()

        # 2. Animate Status Label Opacity
        self.status_anim = QPropertyAnimation(
            self.status_opacity_effect, b"opacity", self
        )
        self.status_anim.setDuration(250)
        self.status_anim.setEndValue(target_status_opacity)
        self.status_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.status_anim.start()

        # Keep the actual functional state
        self.inject_btn.setEnabled(can_inject)

    def _on_inject_clicked(self):
        # 1. Determine Steam ID and Force state
        default_id = self._suggested_steam_id if self._suggested_steam_id else ""
        steam_id, ok = QInputDialog.getText(
            self, "Inject Assets", "Enter Steam AppID:", text=default_id
        )

        # Guard against cancellation or empty input
        if not (ok and steam_id):
            return

        # Re-apply Sanitization and define 'force'
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
            # Refresh Missing assets badges on new shortcut added
            self.name_changed.emit()
        else:
            QMessageBox.critical(self, "Error", message)

    def _on_search_finished(self, result, original_query, generation):
        """Populates and fades in the smart suggestion bar."""
        # Guard: If this is an orphaned result, ignore it
        if generation != self._search_generation:
            return

        if isinstance(result, dict):
            self._search_state = SearchState.FOUND
            self._suggested_steam_id = result["id"]
            self.suggestion_text.setText(result["id"])

            if result.get("thumb_bytes"):
                pix = QPixmap()
                if pix.loadFromData(result["thumb_bytes"]):
                    self.suggestion_thumb.setPixmap(pix)
                    self.suggestion_thumb.show()
                else:
                    self.suggestion_thumb.hide()

            # Use self as parent to prevent GC mid-animation
            self.suggest_anim = QPropertyAnimation(
                self.suggestion_opacity, b"opacity", self
            )
            self.suggest_anim.setDuration(400)
            self.suggest_anim.setEndValue(1.0)
            self.suggest_anim.setEasingCurve(QEasingCurve.OutQuad)
            self.suggest_anim.start()

            self.status_label.setText(f"💡 Found Steam Match")
        elif result == "ERR_NETWORK":
            self._search_state = SearchState.NOT_FOUND
            self._suggested_steam_id = None
            self.status_label.setText("🌐 Search failed - check connection")

        else:
            self._search_state = SearchState.NOT_FOUND
            self._suggested_steam_id = None
            self.status_label.setText("❓ No match found")
        # Refresh visibility now that state changed
        self._update_button_state()

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

        status = get_asset_status(shortcuts_path, appid)
        self._all_assets_present = all(exists for exists, path in status.values())

        for key, (exists, path) in status.items():
            if key in self._asset_slots:
                self._asset_slots[key].update_slot(exists, path)

        self._update_button_state()

    def _toggle_edit_name(self):

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
                self._search_thread.worker.finished.disconnect(self._on_search_finished)
            except (AttributeError, TypeError, RuntimeError) as e:
                print(f"DEBUG: Signal disconnect error: {e}")
                pass
            # Move to registry so Python doesn't delete the C++ object mid-run
            AssetDetailsScreen._active_threads.add(self._search_thread)

        self._search_state = SearchState.SEARCHING
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
                            except Exception as e:
                                print(f"DEBUG: Could not delete {target_file}: {e}")

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
                    except Exception as e:
                        print(f"DEBUG: Could not remove old asset: {e}")
            # 3. Copy and Overwrite
            shutil.copy2(file_path, dest_path)

            # 4. Refresh UI to show the new asset
            self.load_assets(
                self._current_name, self._current_shortcuts_path, self._current_appid
            )

        except Exception as e:
            QMessageBox.critical(self, "Upload Error", f"Failed to copy file: {e}")
