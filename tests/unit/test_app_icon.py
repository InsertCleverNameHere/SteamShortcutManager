from pathlib import Path

from ui.theme import get_app_icon


def test_app_icon_loads_non_null(qapp):
    """Verify that get_app_icon finds and loads a valid, non-null application icon."""
    icon = get_app_icon()
    assert not icon.isNull(), "Application icon failed to load."


def test_png_icon_set_exists():
    """Verify standard PNG resolutions were generated in assets/."""
    assets_dir = Path("assets")
    assert (assets_dir / "icon.png").is_file()
    for size in (16, 32, 48, 64, 128, 256, 512):
        assert (assets_dir / f"icon-{size}.png").is_file()
