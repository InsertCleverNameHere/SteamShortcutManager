import sys
import os
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from ui.theme import APP_STYLESHEET
from ui.screens.setup_screen import SetupScreen
from ui.screens.library_screen import LibraryScreen
from ui.screens.shortcut_list_screen import ShortcutListScreen
from ui.screens.asset_details_screen import AssetDetailsScreen
from core.steam import detect_default_steam_dir, find_shortcuts


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Steam Shortcut Manager")
        self.resize(800, 700)
        icon_path = get_resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(icon_path):
            from PySide6.QtGui import QIcon

            self.setWindowIcon(QIcon(icon_path))
        self.setStyleSheet(APP_STYLESHEET)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.setup_screen = SetupScreen()
        self.library_screen = LibraryScreen()
        self.shortcut_screen = ShortcutListScreen()
        self.asset_screen = AssetDetailsScreen()  # Standardized naming

        self.stack.addWidget(self.setup_screen)
        self.stack.addWidget(self.library_screen)
        self.stack.addWidget(self.shortcut_screen)
        self.stack.addWidget(self.asset_screen)

        # Connections
        self.setup_screen.steam_dir_confirmed.connect(self.on_steam_dir_found)
        self.library_screen.change_steam_dir.connect(
            lambda: self.stack.setCurrentWidget(self.setup_screen)
        )
        self.library_screen.user_selected.connect(self.on_user_confirmed)

        # Shortcut List Connections
        self.shortcut_screen.back_requested.connect(
            lambda: self.stack.setCurrentWidget(self.library_screen)
        )
        self.shortcut_screen.shortcut_clicked.connect(self.on_shortcut_selected)
        self.shortcut_screen.user_updated.connect(self.library_screen.refresh_card_data)

        # Asset Details Connections
        self.asset_screen.back_requested.connect(self.on_back_from_details)
        self.asset_screen.name_changed.connect(
            lambda: self.shortcut_screen.load_user_shortcuts(
                self.shortcut_screen.current_user
            )
        )

        # Auto-detect
        steam_path = detect_default_steam_dir()
        if steam_path:
            self.on_steam_dir_found(steam_path)
        else:
            self.stack.setCurrentWidget(self.setup_screen)

    def on_steam_dir_found(self, path):
        users = find_shortcuts(path)
        self.library_screen.populate(users)
        self.stack.setCurrentWidget(self.library_screen)

    def on_user_confirmed(self, user_shortcut_obj):
        self.shortcut_screen.load_user_shortcuts(user_shortcut_obj)
        self.stack.setCurrentWidget(self.shortcut_screen)

    def on_shortcut_selected(self, name, path, appid):
        """This is now correctly inside the class and uses the correct variable name."""
        self.asset_screen.load_assets(name, path, appid)
        self.stack.setCurrentWidget(self.asset_screen)

    def on_back_from_details(self):
        """Returns to the shortcut list while preserving the current window size."""
        self.stack.setCurrentWidget(self.shortcut_screen)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
