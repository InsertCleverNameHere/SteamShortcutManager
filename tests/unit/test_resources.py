"""
tests/unit/test_resources.py
Verifies bundled application resources: application icon resolutions,
bundled SVG action icons, and Inter font database registration.
Paths are anchored to the repository root to prevent CWD flakiness.
"""

from pathlib import Path

from PySide6.QtGui import QFontDatabase

from ui.theme import get_app_icon, get_icon, load_bundled_fonts

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
ICONS_DIR = REPO_ROOT / "ui" / "resources" / "icons"


def test_app_icon_loads_non_null(qapp):
    """Verify that get_app_icon loads a valid, non-null application icon."""
    icon = get_app_icon()
    assert not icon.isNull(), "Application icon failed to load."


def test_bundled_png_icon_set_exists():
    """Verify that standard multi-resolution PNGs and ICO exist in assets/."""
    assert (ASSETS_DIR / "icon.png").is_file(), "Primary icon.png missing."
    assert (ASSETS_DIR / "icon.ico").is_file(), "Primary icon.ico missing."

    for size in (16, 32, 48, 64, 128, 256, 512):
        icon_path = ASSETS_DIR / f"icon-{size}.png"
        assert icon_path.is_file(), f"Missing resolution icon: {icon_path.name}"


def test_bundled_svg_action_icons_exist_and_load(qapp):
    """Verify that all SVG action icons exist and load into non-null QIcons."""
    expected_icons = ("check", "edit", "folder", "tools", "trash")
    for name in expected_icons:
        svg_file = ICONS_DIR / f"{name}.svg"
        assert svg_file.is_file(), f"SVG icon missing on disk: {svg_file.name}"

        icon = get_icon(name)
        assert not icon.isNull(), f"get_icon('{name}') failed to produce a valid QIcon."


def test_load_bundled_fonts_registers_inter(qtbot):
    """Verify that Inter.ttf registers into QFontDatabase and family is available."""
    success = load_bundled_fonts()
    assert success is True

    families = QFontDatabase.families()
    assert any(
        "Inter" in f for f in families
    ), "Inter font family not found in QFontDatabase."
