"""
tests/unit/test_net_grid.py
Unit and regression tests for core.net and core.grid.
Validates URL allowlists, search encoding, atomic writes,
magic-byte validation, sibling pruning, and asset completeness.
"""

from pathlib import Path

import pytest
import requests_mock

from core.grid import (
    delete_all_assets,
    is_complete,
    validate_image_bytes,
    write_asset_atomic,
    write_json_positioning,
)
from core.net import (
    is_trusted_steam_url,
    search_steam_store,
)

# ── core/net.py Tests ────────────────────────────────────────────────────────


def test_is_trusted_steam_url():
    """Verify host allowlist enforces HTTPS and approved Valve CDN subdomains."""
    assert is_trusted_steam_url(
        "https://cdn.cloudflare.steamstatic.com/apps/400/header.jpg"
    )
    assert is_trusted_steam_url(
        "https://shared.fastly.steamstatic.com/apps/400/logo.png"
    )
    assert is_trusted_steam_url("https://steamcdn-a.akamaihd.net/apps/400/capsule.jpg")
    assert is_trusted_steam_url("https://store.steampowered.com/api/storesearch/")

    # Insecure HTTP must be rejected
    assert not is_trusted_steam_url(
        "http://cdn.cloudflare.steamstatic.com/apps/400/header.jpg"
    )
    # Subdomain spoofing must be rejected
    assert not is_trusted_steam_url("https://malicious-steamstatic.com/evil.jpg")
    assert not is_trusted_steam_url(
        "https://evil.com/fake/cdn.cloudflare.steamstatic.com"
    )
    assert not is_trusted_steam_url("")


def test_search_steam_store_parameter_encoding():
    """Verify search queries with special characters are safely parameter-encoded."""
    with requests_mock.Mocker() as m:
        m.get(
            "https://store.steampowered.com/api/storesearch/",
            json={
                "total": 1,
                "items": [
                    {
                        "id": 400,
                        "name": "Portal & Testing",
                        "tiny_image": "//cdn.steamstatic.com/thumb.jpg",
                    }
                ],
            },
        )
        res = search_steam_store("Portal & Testing + Special#Chars")
        assert res.status == "ok"
        assert res.item is not None
        assert res.item.appid == "400"
        assert res.item.thumb_url == "https://cdn.steamstatic.com/thumb.jpg"

        # Verify query string in the intercepted request
        history = m.request_history
        assert len(history) == 1
        assert "term=portal+%26+testing+%2b+special%23chars" in history[0].query.lower()


def test_search_steam_store_total_greater_than_zero_empty_items():
    """Guard against API returning total > 0 but items list is empty."""
    with requests_mock.Mocker() as m:
        m.get(
            "https://store.steampowered.com/api/storesearch/",
            json={"total": 5, "items": []},
        )
        res = search_steam_store("GhostGame")
        assert res.status == "none"
        assert res.item is None


def test_search_steam_store_rate_limited():
    """Verify HTTP 429 returns clean error status without uncaught exception."""
    with requests_mock.Mocker() as m:
        m.get(
            "https://store.steampowered.com/api/storesearch/",
            status_code=429,
            headers={"Retry-After": "10"},
        )
        res = search_steam_store("SpamQuery")
        assert res.status == "error"
        assert "rate limited" in res.error_message.lower()


# ── core/grid.py Tests ───────────────────────────────────────────────────────


def test_validate_image_bytes():
    """Verify magic-byte validation accepts valid formats and rejects HTML/text."""
    valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    valid_jpg = b"\xff\xd8\xff" + b"\x00" * 16
    valid_ico = b"\x00\x00\x01\x00" + b"\x00" * 16

    assert validate_image_bytes(valid_png, ".png")
    assert validate_image_bytes(valid_jpg, ".jpg")
    assert validate_image_bytes(valid_jpg, ".jpeg")
    assert validate_image_bytes(valid_ico, ".ico")

    # Mismatched magic bytes
    assert not validate_image_bytes(valid_png, ".jpg")
    assert not validate_image_bytes(valid_jpg, ".png")

    # Rejection of HTML captive portal payloads
    html_payload = b"<!DOCTYPE html><html><body>Login Required</body></html>"
    assert not validate_image_bytes(html_payload, ".jpg")
    assert not validate_image_bytes(html_payload, ".png")
    assert not validate_image_bytes(b"short", ".jpg")


def test_write_asset_atomic_and_sibling_pruning(tmp_path: Path):
    """Verify atomic write creates destination and purges sibling extensions."""
    valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    valid_jpg = b"\xff\xd8\xff" + b"\x00" * 16

    # 1. Write initial PNG capsule
    png_path = write_asset_atomic(tmp_path, "12345", "p", ".png", valid_png)
    assert png_path.is_file()

    # 2. Overwrite slot with JPG -> PNG must be pruned automatically
    jpg_path = write_asset_atomic(tmp_path, "12345", "p", ".jpg", valid_jpg)
    assert jpg_path.is_file()
    assert not png_path.exists(), "Previous sibling extension was not pruned!"

    # 3. Verify no lingering .part files remain
    part_files = list(tmp_path.glob("*.part"))
    assert len(part_files) == 0


def test_write_asset_atomic_rejects_corrupted_payload(tmp_path: Path):
    """Verify write_asset_atomic refuses to write corrupt payloads to disk."""
    corrupt_body = b"NOT_AN_IMAGE_PAYLOAD"
    with pytest.raises(ValueError):
        write_asset_atomic(tmp_path, "12345", "p", ".jpg", corrupt_body, validate=True)

    assert not (tmp_path / "12345p.jpg").exists()
    assert len(list(tmp_path.glob("*.part"))) == 0


def test_is_complete_semantics(tmp_path: Path):
    """Verify completeness strictly requires all 4 art slots + json"""
    valid_jpg = b"\xff\xd8\xff" + b"\x00" * 16
    valid_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    appid = "12345"

    # Initially missing all
    assert not is_complete(tmp_path, appid)

    # Add capsule, header, hero, logo
    write_asset_atomic(tmp_path, appid, "p", ".jpg", valid_jpg)
    write_asset_atomic(tmp_path, appid, "", ".jpg", valid_jpg)
    write_asset_atomic(tmp_path, appid, "_hero", ".jpg", valid_jpg)
    write_asset_atomic(tmp_path, appid, "_logo", ".png", valid_png)

    # Artwork present, but JSON missing -> must be False
    assert not is_complete(tmp_path, appid)

    # Add JSON positioning -> must now be True
    write_json_positioning(tmp_path, appid, {"width_pct": 50, "height_pct": 50})
    assert is_complete(tmp_path, appid)


def test_delete_all_assets(tmp_path: Path):
    """Verify delete_all_assets clears all extensions including .jpeg and .part."""
    appid = "12345"
    files_to_create = [
        f"{appid}p.jpg",
        f"{appid}p.jpeg",
        f"{appid}.png",
        f"{appid}_hero.jpg",
        f"{appid}_logo.png",
        f"{appid}_icon.ico",
        f"{appid}.json",
        f".{appid}_temp.part",
    ]
    for f in files_to_create:
        (tmp_path / f).write_bytes(b"dummy_data")

    deleted_count = delete_all_assets(tmp_path, appid)
    assert deleted_count >= 7
    assert len(list(tmp_path.iterdir())) == 0
