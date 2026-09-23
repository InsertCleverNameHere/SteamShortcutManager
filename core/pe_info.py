"""
core/pe_info.py
Extracts game metadata (ProductName, FileDescription) from Windows PE binaries
using pefile. Fully cross-platform; runs on Linux and Windows.
"""

from pathlib import Path

import pefile

GENERIC_NAMES = {
    "unity",
    "unreal engine",
    "unrealengine",
    "godot",
    "gamemaker",
    "game maker",
    "nw.js",
    "electron",
    "launcher",
    "bootstrap",
    "setup",
    "installer",
}


def get_game_name_from_pe(exe_path: str | Path) -> str:
    """
    Attempts to read 'ProductName' or 'FileDescription' from the executable's
    version resources using pefile. Falls back to the filename stem if not found.
    """
    path = Path(exe_path)
    fallback = path.stem

    if not path.is_file() or path.suffix.lower() != ".exe":
        return fallback

    try:
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )

        if not hasattr(pe, "FileInfo"):
            pe.close()
            return fallback

        product_name: str | None = None
        file_description: str | None = None

        # Traverse FileInfo entries
        file_info_list = pe.FileInfo if isinstance(pe.FileInfo, list) else [pe.FileInfo]
        for sub_list in file_info_list:
            items = sub_list if isinstance(sub_list, list) else [sub_list]
            for item in items:
                string_tables = getattr(item, "StringTable", [])
                for st in string_tables:
                    entries = getattr(st, "entries", {})
                    for raw_key, raw_val in entries.items():
                        key = (
                            raw_key.decode("utf-8", errors="ignore")
                            if isinstance(raw_key, bytes)
                            else str(raw_key)
                        ).lower()
                        val = (
                            raw_val.decode("utf-8", errors="ignore")
                            if isinstance(raw_val, bytes)
                            else str(raw_val)
                        ).strip()

                        if not val:
                            continue

                        if key == "productname" and not product_name:
                            product_name = val
                        elif key == "filedescription" and not file_description:
                            file_description = val

        pe.close()

        candidate = product_name or file_description
        if candidate:
            candidate_clean = candidate.strip()
            # Reject generic names or overly long strings
            if (
                0 < len(candidate_clean) <= 60
                and candidate_clean.lower() not in GENERIC_NAMES
            ):
                return candidate_clean

    except Exception:
        pass

    return fallback
