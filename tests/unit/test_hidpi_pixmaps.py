from pathlib import Path

from PySide6.QtGui import QImage

from ui.screens.asset_details_screen import AssetSlot


def test_asset_slot_respects_device_pixel_ratio(qtbot, tmp_path: Path):
    """Verify that AssetSlot scales pixmap by devicePixelRatio and sets it on output."""
    test_img_path = tmp_path / "test_capsule.png"
    # Create a 600x900 test image
    img = QImage(600, 900, QImage.Format_RGB32)
    img.fill(0xFF00FF)
    img.save(str(test_img_path))

    slot = AssetSlot("capsule")
    qtbot.addWidget(slot)

    slot.update_slot(True, str(test_img_path))
    pix = slot.content_label.pixmap()

    assert not pix.isNull()
    # devicePixelRatio on scaled pixmap must match the widget's ratio
    assert pix.devicePixelRatio() == slot.devicePixelRatio()
