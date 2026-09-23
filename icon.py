"""
icon.py
Comprehensive diagnostic probe: Deep inspection of library_assets and testing
store_item_assets for jpg, jpeg, png, ico formats.
"""

import json
import os

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import requests
from steam.client import SteamClient

STORE_ASSET_BASE = (
    "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps"
)
SHARED_COMMUNITY_BASE = (
    "https://shared.fastly.steamstatic.com/community_assets/images/apps"
)

SAMPLE_APPIDS = [
    ("400", "Portal"),
    ("1145360", "Hades"),
    ("504230", "Celeste"),
]

IMAGE_EXTENSIONS = [".ico", ".png", ".jpg", ".jpeg"]


def check_url(label: str, url: str) -> bool:
    try:
        r = requests.head(url, timeout=4, allow_redirects=True)
        exists = r.status_code == 200
        marker = "✓" if exists else "✗"
        if exists:
            print(f"  [{marker}] {label} (HTTP {r.status_code})")
            print(f"      -> URL: {url}")
            print(f"      -> Content-Type: {r.headers.get('Content-Type')}")
        return exists
    except Exception:
        return False


def probe_deep():
    print("Connecting to Steam anonymously...")
    c = SteamClient()
    if c.anonymous_login() != 1:
        print("Failed to connect to Steam.")
        return

    for appid_str, title in SAMPLE_APPIDS:
        appid = int(appid_str)
        print(f"\n{'=' * 70}\n{title} (AppID: {appid_str})\n{'=' * 70}")
        info = c.get_product_info(apps=[appid])
        app_data = info.get("apps", {}).get(appid, {})
        common = app_data.get("common", {})

        # 1. Complete raw dump of library_assets and library_assets_full
        print("\n--- 1. Raw Contents of library_assets ---")
        print(json.dumps(common.get("library_assets", {}), indent=2))

        print("\n--- 2. Raw Contents of library_assets_full ---")
        print(json.dumps(common.get("library_assets_full", {}), indent=2))

        # Collect all candidate hashes from common
        candidate_hashes = {
            "clienticon": common.get("clienticon"),
            "icon": common.get("icon"),
            "linuxclienticon": common.get("linuxclienticon"),
            "logo_small": common.get("logo_small"),
        }
        print("\n--- 3. Candidate Hashes in common ---")
        for k, v in candidate_hashes.items():
            if v:
                print(f"  - {k}: {v}")

        # 4. Probe store_item_assets (Test A) with all extensions
        print(f"\n--- 4. Probing Store Base: {STORE_ASSET_BASE}/{appid_str}/ ---")
        found_in_store = False

        # Test standard static filenames
        static_names = [
            "icon",
            "clienticon",
            "app_icon",
            "logo_small",
            "capsule_sm_120",
        ]
        for name in static_names:
            for ext in IMAGE_EXTENSIONS:
                target_url = f"{STORE_ASSET_BASE}/{appid_str}/{name}{ext}"
                if check_url(f"Static '{name}{ext}'", target_url):
                    found_in_store = True

        # Test all candidate hashes under store_item_assets
        for hash_label, h_val in candidate_hashes.items():
            if not h_val:
                continue
            for ext in IMAGE_EXTENSIONS:
                target_url = f"{STORE_ASSET_BASE}/{appid_str}/{h_val}{ext}"
                if check_url(f"Hash {hash_label} '{h_val}{ext}'", target_url):
                    found_in_store = True

        if not found_in_store:
            print("  [✗] No icon files found under store_item_assets.")

        # 5. Probe community_assets on the SAME Fastly host (shared.fastly.steamstatic.com)
        print(
            f"\n--- 5. Probing Community on Same Host: {SHARED_COMMUNITY_BASE}/{appid_str}/ ---"
        )
        for hash_label, h_val in candidate_hashes.items():
            if not h_val:
                continue
            for ext in IMAGE_EXTENSIONS:
                target_url = f"{SHARED_COMMUNITY_BASE}/{appid_str}/{h_val}{ext}"
                check_url(f"Community {hash_label} ({ext})", target_url)

    c.disconnect()
    print("\n=== Probe Complete ===")


if __name__ == "__main__":
    probe_deep()
