import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.asset_provider import download_assets


def test_download_assets_fetches_client_icon(tmp_path: Path):
    """Verify that download_assets fetches clienticon.ico via isolated product info."""
    grid_dir = str(tmp_path / "grid")

    mock_product_info = {
        "appid": 400,
        "name": "Portal",
        "library_assets_full": {},
        "library_assets": {},
        "clienticon": "c7cb09b9f0fbb9589b4bd5a8217c8333c4d8204e",
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"\x00\x00\x01\x00" + b"\x00" * 32  # Valid ICO magic header

    with patch(
        "core.asset_provider.fetch_product_info", return_value=mock_product_info
    ):
        with patch("core.asset_provider.is_network_available", return_value=True):
            with patch("requests.Session.get", return_value=mock_response):
                success, msg = download_assets(
                    steam_appid="400",
                    local_appid="12345",
                    grid_dir=grid_dir,
                    force=True,
                )

                assert success is True
                icon_path = os.path.join(grid_dir, "12345_icon.ico")
                assert os.path.isfile(icon_path)
                assert open(icon_path, "rb").read() == mock_response.content
