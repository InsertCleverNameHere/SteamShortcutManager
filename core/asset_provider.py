import os
import json
import requests
import threading
import time
import socket
from steam.client import SteamClient

# The base URL for Steam's official assets
CDN_BASE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps"

# Timeouts
_ASSET_REQUEST_TIMEOUT = (
    8  # seconds per CDN image download (was 15 — 2 retries × 15s = 30s lag)
)
_STEAM_CLIENT_TIMEOUT = (
    30  # seconds for the entire SteamClient phase (login + product info)
)


def search_steam_apps(query: str):
    """
    Queries Steam Store search to find a potential match for the name.
    Returns a dict with id, name, and thumbnail URL or None.
    """
    # Clean query: Replace hyphens/colons with spaces to help Steam's literal API
    clean_query = query.replace("-", " ").replace(":", " ")
    url = f"https://store.steampowered.com/api/storesearch/?term={clean_query}&l=english&cc=US"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("total", 0) > 0:
            item = data["items"][0]
            return {
                "id": str(item.get("id")),
                "name": item.get("name"),
                "thumb_url": item.get("tiny_image"),
            }
        return None  # No results found (successfully queried)
    except (requests.RequestException, ValueError) as e:
        print(f"DEBUG: Steam Store Search error: {e}")
        return "ERR_NETWORK"  # Specific error indicator


def is_internet_reachable(timeout=2):
    """Lightning-fast check to see if we can reach a public DNS server."""
    try:
        # Connect to Cloudflare's public DNS port 53
        socket.create_connection(("1.1.1.1", 53), timeout=timeout)
        return True
    except OSError:
        pass
    return False


def download_assets(
    steam_appid: str,
    local_appid: str,
    grid_dir: str,
    force: bool = False,
    status_callback=None,
    abort_event: threading.Event | None = None,
    client_holder: list | None = None,
):
    """
    Fetches metadata and downloads Steam Grid assets.

    Args:
        steam_appid:     Real Steam AppID to look up.
        local_appid:     Local/non-Steam AppID used for file naming.
        grid_dir:        Path to the user's Steam grid folder.
        force:           If True, overwrite existing assets.
        status_callback: Optional callable(str) for live progress messages.
        abort_event:     threading.Event; set externally to cancel the operation.
                         When set, download_assets returns (False, "❌ Cancelled.").
        client_holder:   Single-element list populated with the live SteamClient so
                         the caller can call disconnect() to unblock a hanging network
                         call (e.g. from an abort button or a watchdog).
    """

    def report(msg: str) -> None:
        if status_callback:
            status_callback(msg)

    def is_aborted() -> bool:
        return bool(abort_event and abort_event.is_set())

    client = None
    timed_out = False

    def watchdog() -> None:
        """
        Called by the timer thread when _STEAM_CLIENT_TIMEOUT elapses.
        Disconnects the SteamClient so any blocking call raises immediately.
        """
        nonlocal timed_out
        timed_out = True
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass

    # One timer covers the entire SteamClient phase (login + product info).
    # It is only cancelled after client.disconnect() below, once we no longer need it.
    timer = threading.Timer(_STEAM_CLIENT_TIMEOUT, watchdog)
    timer.start()

    try:
        if is_aborted():
            return False, "❌ Cancelled."

        if not is_internet_reachable():
            return False, "❌ No internet connection detected."

        report("🌐 [1/4] Connecting to Steam...")

        try:
            client = SteamClient()
            if client_holder is not None:
                client_holder[0] = client  # Expose client for external abort
            login_result = client.anonymous_login()
        except Exception as e:
            if timed_out:
                return False, "❌ Connection timed out (Steam servers may be slow)."
            if is_aborted():
                return False, "❌ Cancelled"
            return False, f"❌ Steam API Error: {str(e)}"

        if timed_out:
            return False, "❌ Operation aborted."
        if is_aborted():
            return False, "❌ Cancelled"
        if not client or login_result != 1:
            return False, "❌ Connection failed."

        report(f"📑 [2/4] Fetching manifest...")
        try:
            # AppIDs must be integers for the steam library lookup
            product_info = client.get_product_info(apps=[int(steam_appid)])
        except BaseException as e:
            if timed_out:
                return (
                    False,
                    "❌ Timed out fetching app metadata. Check your connection.",
                )
            if is_aborted():
                return False, "❌ Cancelled."
            return False, f"❌ Connection lost during manifest fetch: {str(e)}"

        if timed_out:
            return False, "❌ Timed out fetching app metadata. Check your connection."
        if is_aborted():
            return False, "❌ Cancelled."

        # SteamClient work is done — cancel the watchdog and cleanly disconnect.
        timer.cancel()
        try:
            client.disconnect()
        except Exception:
            pass
        client = None
        if client_holder is not None:
            client_holder[0] = None

        app_data = product_info.get("apps", {}).get(int(steam_appid))
        if not app_data:
            return False, "❌ AppID not found on Steam."

        common = app_data.get("common", {})
        assets_full = common.get("library_assets_full", {})
        assets_meta = common.get("library_assets", {})

        mapping = {
            "p": ("library_capsule", "library_600x900.jpg"),
            "": ("library_header", "header.jpg"),
            "_hero": ("library_hero", "library_hero.jpg"),
            "_logo": ("library_logo", "logo.png"),
        }

        downloaded_count = 0
        for suffix, (key, default_name) in mapping.items():
            if is_aborted():
                return False, "❌ Cancelled"

            asset_entry = assets_full.get(key, {})
            img_hash_path = asset_entry.get("image", {}).get("english")

            if img_hash_path:
                safe_hash = os.path.basename(img_hash_path)
                url = f"{CDN_BASE}/{steam_appid}/{safe_hash}"
            else:
                url = f"{CDN_BASE}/{steam_appid}/{default_name}"

            ext = os.path.splitext(url)[1] or ".jpg"
            local_filename = f"{local_appid}{suffix}{ext}"
            local_path = os.path.join(grid_dir, local_filename)

            # --- FORCE LOGIC: Skip if file exists and we aren't forcing ---
            if not force and os.path.exists(local_path):
                continue

            display_name = key.replace("library_", "") or "header"
            report(f"📥 [3/4] Downloading {key.replace('library_', '')}...")
            download_success = False
            for attempt in range(2):
                if is_aborted():
                    return False, "❌ Cancelled"
                try:
                    res = requests.get(url, timeout=_ASSET_REQUEST_TIMEOUT)
                    if res.status_code == 200:
                        with open(local_path, "wb") as f:
                            f.write(res.content)
                        downloaded_count += 1
                        download_success = True
                        break  # Exit retry loop on success
                except requests.exceptions.Timeout:
                    suffix_msg = "retrying..." if attempt == 0 else "skipping"
                    report(f"⚠️ {display_name} timed out — {suffix_msg}")
                except requests.exceptions.RequestException:
                    pass  # Let it retry or fail gracefully

                if (
                    attempt == 0 and not is_aborted
                ):  # If first attempt failed, wait briefly
                    time.sleep(1)

            if not download_success:
                report(f"⚠️ Skipping {display_name}: download failed after 2 attempts")

        if is_aborted():
            return False, "❌ Cancelled."

        # Handle JSON positioning
        json_path = os.path.join(grid_dir, f"{local_appid}.json")
        if force or not os.path.exists(json_path):
            report(f"📝 [4/4] Generating JSON...")
            logo_pos = assets_meta.get("logo_position")
            if logo_pos:
                json_data = {
                    "nVersion": 1,
                    "logoPosition": {
                        "pinnedPosition": logo_pos.get("pinned_position", "BottomLeft"),
                        "nWidthPct": float(logo_pos.get("width_pct", 50)),
                        "nHeightPct": float(logo_pos.get("height_pct", 50)),
                    },
                }
                with open(json_path, "w") as f:
                    json.dump(json_data, f, separators=(",", ":"))
                downloaded_count += 1

        return True, f"✅ Successfully injected {downloaded_count} assets."

    except Exception as e:
        if is_aborted():
            return False, "❌ Cancelled."
        if timed_out:
            return False, "❌ Operation timed out. Check your connection and try again."
        print(f"DEBUG: Global Download Error: {e}")
        return False, f"❌ Download error: {str(e)}"
    finally:
        timer.cancel()
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass
        if client_holder is not None:
            client_holder[0] = None
