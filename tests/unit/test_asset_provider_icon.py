import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.asset_provider import download_assets


def test_download_assets_fetches_client_icon(tmp_path: Path):
    """Verify that download_assets fetches clienticon.ico from Community CDN."""
    grid_dir = str(tmp_path / "grid")

    mock_client = MagicMock()
    mock_client.anonymous_login.return_value = 1
    mock_client.get_product_info.return_value = {
        "apps": {
            400: {
                "common": {
                    "clienticon": "c7cb09b9f0fbb9589b4bd5a8217c8333c4d8204e",
                    "library_assets_full": {},
                }
            }
        }
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"\x00\x00\x01\x00FAKE_ICO_CONTENT"

    with patch("core.asset_provider.SteamClient", return_value=mock_client):
        with patch("core.asset_provider.is_internet_reachable", return_value=True):
            with patch("requests.get", return_value=mock_response):
                success, msg = download_assets(
                    steam_appid="400",
                    local_appid="12345",
                    grid_dir=grid_dir,
                    force=True,
                )

                assert success is True
                icon_path = os.path.join(grid_dir, "12345_icon.ico")
                assert os.path.isfile(icon_path)
                assert open(icon_path, "rb").read() == b"\x00\x00\x01\x00FAKE_ICO_CONTENT"
