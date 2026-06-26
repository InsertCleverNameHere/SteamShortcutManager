import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QScrollArea, QPushButton, QFrame, QLineEdit,
    QFileDialog, QMessageBox, QInputDialog, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from ui.theme import PALETTE
from core.vdf_parser import (
    load_shortcuts, 
    get_shortcut_list, 
    get_value_case_insensitive, 
    normalize_appid,
    add_new_shortcut,
)
from core.steam import get_asset_status
from core.utils_win import resolve_windows_shortcut, get_game_name_from_metadata

class ShortcutListScreen(QWidget):
    back_requested = Signal()
    shortcut_clicked = Signal(str, str, str)  # (game_name, shortcuts_path, appid)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._card_data = [] # Track widgets and names for filtering
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200) # Wait 200ms after last keystroke
        self._search_timer.timeout.connect(self._execute_filter)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        header = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondary")
        back_btn.clicked.connect(self.back_requested)
        header.addWidget(back_btn)
        
        header.addStretch()
        
        self.title_label = QLabel("Shortcuts")
        self.title_label.setObjectName("heading")
        header.addWidget(self.title_label)
        
        header.addSpacing(40)

        # --- Search Bar ---
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search by name...")
        self.search_bar.setFixedWidth(250)
        self.search_bar.textChanged.connect(lambda: self._search_timer.start())
        header.addWidget(self.search_bar)

        header.addStretch()
        
        # Add Shortcut Button
        add_btn = QPushButton("+ Add Shortcut")
        add_btn.clicked.connect(self._on_add_clicked)
        header.addWidget(add_btn)

        layout.addLayout(header)
        layout.addSpacing(20)

        # Scroll area for shortcuts
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # Only vertical scrolling
        # Prevent focus rectangle on scrollbar
        self.scroll.verticalScrollBar().setFocusPolicy(Qt.NoFocus)
        
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 12, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.setAlignment(Qt.AlignTop)
        
        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll)

    def _execute_filter(self):
        """Hides or shows cards based on the search text with layout suspension."""
        query = self.search_bar.text().lower().strip()
        
        # 1. Surgical Addition: Suspend updates to prevent jarring "snapping"
        self.list_container.setUpdatesEnabled(False)
        
        for card, game_name in self._card_data:
            card.setVisible(query in game_name)
            
        # 2. Surgical Addition: Resume and redraw once at the end
        self.list_container.setUpdatesEnabled(True)

    def _on_add_clicked(self):
        raw_path, _ = QFileDialog.getOpenFileName(
            self, "Select Game or Shortcut", "", "Games & Shortcuts (*.exe *.lnk);;All Files (*.*)"
        )
        if not raw_path: return

        # Get the name of the file the user actually clicked on (e.g. "Hades.lnk" -> "Hades")
        file_label = os.path.splitext(os.path.basename(raw_path))[0]

        if raw_path.lower().endswith('.lnk'):
            # PATH: Resolve the shortcut to find the real EXE
            exe_path = resolve_windows_shortcut(raw_path)
            # NAME: Trust the shortcut's filename over the EXE metadata
            derived_name = file_label
        else:
            # PATH: It is the EXE
            exe_path = raw_path
            # NAME: Try metadata, fallback to filename
            derived_name = get_game_name_from_metadata(exe_path)

        # Prompt user (pre-filled with our best guess)
        game_name, ok = QInputDialog.getText(
            self, "Add Shortcut", "Enter game name:", text=derived_name
        )
        
        if ok and game_name:
            vdf_path = self._current_user_obj.shortcuts_path
            
            # Automated Backup before writing
            if os.path.exists(vdf_path):
                import shutil
                shutil.copy2(vdf_path, vdf_path + ".bak")

            # Save to VDF
            success, msg, new_id = add_new_shortcut(
                vdf_path, 
                game_name, 
                exe_path,
                icon_path=exe_path
            )
            
            if success:
                # 1. Refresh the internal list data
                self.load_user_shortcuts(self._current_user_obj)
                
                # 2. SURGICAL CHANGE: Redirect to the Detail Screen
                # This triggers load_assets in the details screen, which
                # automatically starts the background search for the user.
                self.shortcut_clicked.emit(game_name, vdf_path, new_id)
            else:
                QMessageBox.critical(self, "Error", msg)

    def load_user_shortcuts(self, user_obj):
        """Called when a user is selected in the main menu."""
        # Store the current user object so the Add button knows which VDF to edit
        self._current_user_obj = user_obj 
        # Fallback to userdata_id if persona_name is missing
        display_name = user_obj.persona_name or user_obj.userdata_id
        self.title_label.setText(f"{display_name}'s Library")
        
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
            data = load_shortcuts(user_obj.shortcuts_path)
            shortcuts = get_shortcut_list(data)

            if not shortcuts:
                self.list_layout.addWidget(QLabel("No shortcuts found in this file."))
            
            for s in shortcuts:
                # 1. Extract Data
                name = get_value_case_insensitive(s, 'AppName', 'Unknown Game')
                raw_appid = get_value_case_insensitive(s, 'appid', '0')
                appid = normalize_appid(raw_appid)
                exe_path = get_value_case_insensitive(s, 'Exe', 'No Path Found')

                # 2. Check Assets
                status = get_asset_status(user_obj.shortcuts_path, appid)
                is_complete = all(exists for exists, path in status.values())

                # 3. Build Card
                card = QFrame()
                card.setCursor(Qt.PointingHandCursor)
                card.setStyleSheet(f"background: {PALETTE['bg_card']}; border: 1px solid {PALETTE['border']}; border-radius: 6px; padding: 8px;")
                # Use a lambda to emit our new signal when the card is clicked
                card.mousePressEvent = lambda e, n=name, p=user_obj.shortcuts_path, i=appid: self.shortcut_clicked.emit(n, p, i)
                card_layout = QVBoxLayout(card)
                card_layout.setSpacing(2) # Tighten space between title and subtitle
                
                #Title Row
                title_row = QHBoxLayout()
                title_lbl = QLabel(name)
                # Reduced font from 15px to 14px
                title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {PALETTE['text_primary']}; border: none; background: transparent;")
                title_row.addWidget(title_lbl)
                if not is_complete:
                    flag = QLabel("⚠ Missing Assets")
                    flag.setStyleSheet(f"color: {PALETTE['warning']}; font-size: 10px; font-weight: bold; background: transparent;")
                    title_row.addStretch()
                    title_row.addWidget(flag)

                card_layout.addLayout(title_row)

                # Subtitle (AppID and Exe Path)
                sub_text = f"AppID: {appid}  •  {exe_path}"
                sub_lbl = QLabel(sub_text)
                sub_lbl.setStyleSheet(f"font-size: 11px; color: {PALETTE['text_muted']}; border: none; background: transparent;")
                sub_lbl.setWordWrap(False) # Keep it on one line for a cleaner look
                sub_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred) # Allow horizontal shrinking
                card_layout.addWidget(sub_lbl)
                
                # Store reference for filtering
                self._card_data.append((card, name.lower()))
                
                self.list_layout.addWidget(card)
                
        except Exception as e:
            error_lbl = QLabel(f"Error loading shortcuts: {e}")
            error_lbl.setStyleSheet(f"color: {PALETTE['danger']};")
            self.list_layout.addWidget(error_lbl)