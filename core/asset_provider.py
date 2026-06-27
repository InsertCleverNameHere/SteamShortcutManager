import os
import json
import requests
import threading
import time
from steam.client import SteamClient

# The base URL for Steam's official assets
CDN_BASE = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps"


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


def download_assets(
    steam_appid: str,
    local_appid: str,
    grid_dir: str,
    force: bool = False,
    status_callback=None,
):
    """
    Fetches metadata and downloads assets. Reports progress via status_callback.
    """

    def report(msg):
        if status_callback:
            status_callback(msg)

    client = SteamClient()
    login_timed_out = False

    def watchdog():
        nonlocal login_timed_out
        login_timed_out = True
        client.disconnect()

    try:
        report("🌐 [1/4] Connecting to Steam...")

        # Start 15-second watchdog timer
        timer = threading.Timer(15.0, watchdog)
        timer.start()
        try:
            login_result = client.anonymous_login()
        finally:
            timer.cancel()  # Ensure timer stops regardless of success/fail

        if login_timed_out:
            return False, "❌ Connection timed out (Steam servers may be slow)."

        if login_result != 1:
            return False, "❌ Connection failed."

        if login_timed_out:
            return False, "❌ Operation aborted."  # Checkpoint 1

        report(f"📑 [2/4] Fetching manifest for {steam_appid}...")
        # AppIDs must be integers for the steam library lookup
        product_info = client.get_product_info(apps=[int(steam_appid)])

        if login_timed_out:
            return False, "❌ Operation aborted."  # Checkpoint 2

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

            report(f"📥 [3/4] Downloading {key.replace('library_', '')}...")
            download_success = False
            for attempt in range(2):
                try:
                    res = requests.get(url, timeout=15)
                    if res.status_code == 200:
                        with open(local_path, "wb") as f:
                            f.write(res.content)
                        downloaded_count += 1
                        download_success = True
                        break  # Exit retry loop on success
                except requests.exceptions.RequestException:
                    pass  # Let it retry or fail gracefully

                if attempt == 0:  # If first attempt failed, wait briefly
                    time.sleep(1)

            if not download_success:
                report(f"⚠️ Skipping {key.replace('library_', '')}: Download failed")

        # Handle JSON positioning
        json_path = os.path.join(grid_dir, f"{local_appid}.json")
        if force or not os.path.exists(json_path):
            report(f"📝 [4/4] Generating positioning JSON...")
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
        print(f"DEBUG: Global Download Error: {e}")
        return False, str(e)
    finally:
        client.disconnect()
