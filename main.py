import os
import sys

# Ensure modern protobuf works cleanly with steam.client
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

# Silence noisy host portal lookup warning when running uninstalled
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.services=false")

from core.log import setup_logging

setup_logging()

# Fast path: handle --version before loading GUI dependencies
if "--version" in sys.argv:
    from core.version import __version__

    print(f"Steam Shortcut Manager v{__version__}")
    sys.exit(0)


from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from core.steam import detect_default_steam_dir, find_all_shortcuts, find_shortcuts
from ui.screens.asset_details_screen import AssetDetailsScreen
from ui.screens.library_screen import LibraryScreen
from ui.screens.setup_screen import SetupScreen
from ui.screens.shortcut_list_screen import ShortcutListScreen
from ui.theme import APP_STYLESHEET, get_app_icon, load_bundled_fonts


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
        setup_logging() # Ensure app.log is created on startup
        self.setWindowTitle("Steam Shortcut Manager")
        self.resize(800, 700)
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
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
        self.setup_screen.cancel_requested.connect(
            lambda: self.stack.setCurrentWidget(self.library_screen)
        )
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

        # Auto-detect across all discovered installs
        all_users = find_all_shortcuts()
        if all_users:
            self.library_screen.populate(all_users)
            self.stack.setCurrentWidget(self.library_screen)
        else:
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

    def closeEvent(self, event):
        """Ensures background worker threads are cleanly terminated before window destruction (F22)."""
        from ui.screens.asset_details_screen import AssetDetailsScreen

        # 1. Signal active download worker to abort if running
        if hasattr(self.asset_screen, "_worker") and self.asset_screen._worker:
            self.asset_screen._worker.abort()

        # 2. Wait up to 1.5s for all active background threads to finish
        for thread in list(AssetDetailsScreen._active_threads):
            if thread.isRunning():
                thread.quit()
                thread.wait(1500)
        AssetDetailsScreen._active_threads.clear()

        event.accept()    


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer

        app = QApplication(sys.argv)
        load_bundled_fonts()
        QGuiApplication.setDesktopFileName("steamshortcutmanager")
        window = MainWindow()
        # Verify startup and exit immediately with code 0
        QTimer.singleShot(100, app.quit)
        sys.exit(app.exec())

    app = QApplication(sys.argv)
    load_bundled_fonts()
    QGuiApplication.setDesktopFileName("steamshortcutmanager")
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
