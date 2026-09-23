from PySide6.QtGui import QFontDatabase

from ui.theme import load_bundled_fonts


def test_load_bundled_fonts_registers_inter(qtbot):
    """Verify that Inter.ttf registers into QFontDatabase and family is available."""
    success = load_bundled_fonts()
    assert success is True

    families = QFontDatabase.families()
    assert any(
        "Inter" in f for f in families
    ), "Inter font family not found in QFontDatabase."
