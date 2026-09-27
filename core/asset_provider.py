"""
core/asset_provider.py
Streamlined artwork and icon injection provider.
Orchestrates isolated Steam PICS child process queries, robust CDN downloads,
and atomic grid filesystem operations without in-process gevent or SteamClient.
"""

import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from core.grid import (
    SLOT_MAPPING,
    get_asset_status,
    validate_image_bytes,
    write_asset_atomic,
    write_json_positioning,
)
from core.log import get_logger
from core.net import (
    DEFAULT_TIMEOUT,
    create_steam_session,
    is_network_available,
    is_trusted_steam_url,
    search_steam_store,
)
from core.steam_fetch import (
    SteamAppNotFoundError,
    SteamFetchError,
    SteamFetchTimeoutError,
    fetch_product_info,
)
from ui.tasks import CancelToken, TaskCancelledError

logger = get_logger("asset_provider")

# Base URLs for Steam's official CDN assets
CDN_BASE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps"
COMMUNITY_ICON_BASE = (
    "https://shared.fastly.steamstatic.com/community_assets/images/apps"
)


# Backward-compatibility alias for tests and existing callers
def is_valid_image_bytes(data: bytes, expected_ext: str) -> bool:
    return validate_image_bytes(data, expected_ext)


def is_internet_reachable(timeout: float = 3.0) -> bool:
    return is_network_available(timeout)


def search_steam_apps(query: str) -> dict[str, Any] | str | None:
    """
    Backward-compatible wrapper for search_steam_store.
    Returns dict with id, name, thumb_url on match, None on no match,
    or 'ERR_NETWORK' on error.
    """
    res = search_steam_store(query)
    if res.status == "ok" and res.item:
        return {
            "id": res.item.appid,
            "name": res.item.name,
            "thumb_url": res.item.thumb_url,
        }
    elif res.status == "error":
        return "ERR_NETWORK"
    return None


def download_assets(
    steam_appid: str | int,
    local_appid: str | int,
    grid_dir: str | Path,
    force: bool = False,
    status_callback: Callable[[str], None] | None = None,
    abort_event: threading.Event | CancelToken | None = None,
    client_holder: list | None = None,
) -> tuple[bool, str]:
    """
    Fetches official Steam grid assets, icon, and logo positioning.

    Args:
        steam_appid: Real Steam AppID.
        local_appid: Local shortcut AppID for grid filenames.
        grid_dir: Path to Steam userdata grid folder.
        force: Overwrite existing assets if True.
        status_callback: Live progress callback(str).
        abort_event: CancelToken or threading.Event to signal cancellation.
        client_holder: Deprecated compatibility list (set to None).

    Returns:
        (success: bool, message: str)
    """

    def report(msg: str) -> None:
        if status_callback:
            status_callback(msg)

    # Adapt CancelToken or threading.Event
    if isinstance(abort_event, CancelToken):
        token = abort_event
    else:
        token = CancelToken()
        if isinstance(abort_event, threading.Event):
            token._event = abort_event

    if client_holder is not None:
        client_holder[0] = None

    if token.is_cancelled:
        return False, "❌ Cancelled."

    if not is_network_available():
        return False, "❌ No internet connection detected."

    # 1. Fetch metadata in isolated child process (B2)
    report("🌐 [1/4] Connecting to Steam...")
    try:
        product_info = fetch_product_info(
            steam_appid,
            token=token,
            status_callback=lambda s: report(f"📑 {s}"),
            timeout=30.0,
        )
    except TaskCancelledError:
        return False, "❌ Cancelled."
    except SteamFetchTimeoutError:
        return False, "❌ Connection timed out (Steam servers may be slow)."
    except SteamAppNotFoundError:
        return False, f"❌ AppID {steam_appid} not found on Steam."
    except SteamFetchError as e:
        return False, f"❌ Steam metadata error: {e}"
    except Exception as e:
        logger.exception(f"Unexpected metadata fetch error: {e}")
        return False, f"❌ Failed to fetch Steam metadata: {e}"

    if token.is_cancelled:
        return False, "❌ Cancelled."

    assets_full = product_info.get("library_assets_full", {})
    assets_meta = product_info.get("library_assets", {})
    client_icon_hash = product_info.get("clienticon", "")
    appid_str = str(local_appid)
    steam_id_str = str(steam_appid)

    session = create_steam_session()
    # Hook instant socket abort upon token cancellation
    token.register_callback(session.close)

    downloaded_count = 0
    existing_status = get_asset_status(grid_dir, appid_str)

    # 2. Download visual artwork slots (Capsule, Header, Hero, Logo)
    for slot_name, (suffix, default_name) in SLOT_MAPPING.items():
        if token.is_cancelled:
            return False, "❌ Cancelled."

        # If not forcing, skip slots that already have a valid asset
        if not force and existing_status.get(slot_name, (False,))[0]:
            continue

        asset_entry = assets_full.get(f"library_{slot_name}", {})
        img_hash_path = asset_entry.get("image", {}).get("english")

        if img_hash_path:
            clean_path = img_hash_path.lstrip("/").replace("\\", "/")
            url = f"{CDN_BASE}/{steam_id_str}/{clean_path}"
        else:
            url = f"{CDN_BASE}/{steam_id_str}/{default_name}"

        if not is_trusted_steam_url(url):
            logger.warning(f"Blocked untrusted CDN URL: {url}")
            continue

        ext = os.path.splitext(url)[1].lower() or ".jpg"
        display_name = slot_name.capitalize()
        report(f"📥 [2/4] Downloading {display_name}...")

        try:
            resp = session.get(url, timeout=DEFAULT_TIMEOUT, stream=True)
            if resp.status_code == 200:
                write_asset_atomic(grid_dir, appid_str, suffix, ext, resp.content)
                downloaded_count += 1
            elif resp.status_code == 404:
                report(f"⚠️ {display_name} not available on Steam.")
            else:
                report(f"⚠️ {display_name} download error: HTTP {resp.status_code}")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if token.is_cancelled:
                return False, "❌ Cancelled."
            logger.warning(f"Network failure while downloading {display_name}: {e}")
            return (
                False,
                f"❌ Network connection lost or timed out while downloading {display_name}. Please check your connection.",
            )
        except Exception as e:
            if token.is_cancelled:
                return False, "❌ Cancelled."
            logger.warning(f"Failed downloading {display_name} from {url}: {e}")
            report(f"⚠️ Failed downloading {display_name}: {e}")

    if token.is_cancelled:
        return False, "❌ Cancelled."

    # 3. Download official client icon (.ico)
    if client_icon_hash:
        if force or not existing_status.get("icon", (False,))[0]:
            icon_url = f"{COMMUNITY_ICON_BASE}/{steam_id_str}/{client_icon_hash}.ico"
            if is_trusted_steam_url(icon_url):
                report("📥 [3/4] Downloading icon...")
                try:
                    resp = session.get(icon_url, timeout=DEFAULT_TIMEOUT, stream=True)
                    if resp.status_code == 200:
                        write_asset_atomic(
                            grid_dir, appid_str, "_icon", ".ico", resp.content
                        )
                        downloaded_count += 1
                    else:
                        report(f"⚠️ Icon download returned HTTP {resp.status_code}")
                except (
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                ) as e:
                    if token.is_cancelled:
                        return False, "❌ Cancelled."
                    logger.warning(f"Network failure while downloading icon: {e}")
                    return (
                        False,
                        "❌ Network connection lost or timed out while downloading icon. Please check your connection.",
                    )
                except Exception as e:
                    if token.is_cancelled:
                        return False, "❌ Cancelled."
                    logger.warning(f"Failed downloading icon from {icon_url}: {e}")
                    report(f"⚠️ Failed downloading icon: {e}")

    if token.is_cancelled:
        return False, "❌ Cancelled."

    # 4. Generate JSON logo positioning
    logo_pos = assets_meta.get("logo_position")
    if logo_pos and (force or not existing_status.get("json", (False,))[0]):
        report("📝 [4/4] Generating logo positioning JSON...")
        try:
            write_json_positioning(grid_dir, appid_str, logo_pos)
            downloaded_count += 1
        except Exception as e:
            logger.warning(f"Failed writing positioning JSON: {e}")

    # 5. Outcome verification
    if downloaded_count == 0:
        refreshed_status = get_asset_status(grid_dir, appid_str)
        has_any_visual = any(
            refreshed_status[slot][0] for slot in ("capsule", "header", "hero", "logo")
        )
        if not has_any_visual:
            return False, "❌ No artwork could be downloaded from Steam for this game."
        elif not force:
            return True, "✅ All artwork is already up to date."
        else:
            return False, "❌ No new artwork was downloaded."

    return True, f"✅ Successfully injected {downloaded_count} assets."
