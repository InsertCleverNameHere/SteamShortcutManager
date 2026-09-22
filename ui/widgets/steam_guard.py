"""
ui/widgets/steam_guard.py
Steam-running detection guard dialog. Prevents users from writing files
while Steam is running without explicit acknowledgment.
"""

import time

from PySide6 import QtCore, QtWidgets

from core.platform import get_platform


def confirm_steam_closed(parent: QtWidgets.QWidget | None = None) -> bool:
    """
    Checks if Steam is currently running. If running, displays an actionable dialog:
    - Close Steam: sends shutdown request and waits for process to terminate.
    - Continue anyway: proceeds with file operations despite the risk.
    - Cancel: aborts the operation.

    Returns True if safe/confirmed to proceed, False if aborted.
    """
    platform = get_platform()
    is_running = platform.is_steam_running()

    # If Steam is not running or running status cannot be determined, proceed
    if not is_running:
        return True

    msg_box = QtWidgets.QMessageBox(parent)
    msg_box.setWindowTitle("Steam is Running")
    msg_box.setIcon(QtWidgets.QMessageBox.Warning)
    msg_box.setText("<h3>Steam is currently running</h3>")
    msg_box.setInformativeText(
        "Steam caches shortcuts in memory while open and may overwrite your "
        "changes when it exits.\n\n"
        "Would you like to close Steam before making changes?"
    )

    close_btn = msg_box.addButton("Close Steam", QtWidgets.QMessageBox.ActionRole)
    continue_btn = msg_box.addButton(
        "Continue anyway", QtWidgets.QMessageBox.AcceptRole
    )
    cancel_btn = msg_box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
    msg_box.setDefaultButton(close_btn)

    msg_box.exec()
    clicked = msg_box.clickedButton()

    if clicked == cancel_btn:
        return False

    if clicked == continue_btn:
        return True

    if clicked == close_btn:
        # Request shutdown and poll for up to 4 seconds
        platform.request_steam_shutdown()

        progress = QtWidgets.QProgressDialog("Closing Steam...", "", 0, 8, parent)
        progress.setCancelButton(None)
        progress.setWindowTitle("Please Wait")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(200)
        progress.show()

        for step in range(8):
            QtCore.QCoreApplication.processEvents()
            time.sleep(0.5)
            progress.setValue(step + 1)
            if not platform.is_steam_running():
                progress.close()
                return True

        progress.close()

        # If Steam didn't exit in time, ask user whether to continue anyway
        retry = QtWidgets.QMessageBox.question(
            parent,
            "Steam Still Open",
            "Steam is taking longer than expected to close.\n\n"
            "Do you want to continue with your changes anyway?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        return retry == QtWidgets.QMessageBox.Yes

    return False
