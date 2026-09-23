from pathlib import Path
from unittest.mock import patch

from core.appid import to_uint32
from core.platform.linux import LinuxPlatform
from core.shortcuts_io import add_shortcut


def test_linux_data_path_formatting(tmp_path: Path):
    """
    Verify Plan §2.4 Linux data path rules:
    - Exe: Linux-visible path in double quotes
    - StartDir: Directory with trailing slash, unquoted
    - icon: Empty by default
    - grid filename ID: to_uint32(signed_appid)
    """
    linux_platform = LinuxPlatform()
    data = {"shortcuts": {}}
    exe_path = "/var/home/linuxiscool/Games/Doom/doom.exe"

    with patch("core.shortcuts_io.get_platform", return_value=linux_platform):
        unsigned_id_str, entry = add_shortcut(data, "Doom Eternal", exe_path)

    # 1. Exe must be quoted Linux-visible path
    assert entry["Exe"] == f'"{exe_path}"'

    # 2. StartDir must be unquoted directory with trailing /
    assert entry["StartDir"] == "/var/home/linuxiscool/Games/Doom/"

    # 3. icon must be empty by default
    assert entry["icon"] == ""

    # 4. Grid filename ID matches to_uint32
    signed_id = entry["appid"]
    assert str(to_uint32(signed_id)) == unsigned_id_str
