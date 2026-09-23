# build.spec
import os
import sys
from PyInstaller.utils.hooks import collect_all

# Collect everything steam.client needs (protobuf, enums, protobufs)
steam_datas, steam_binaries, steam_hiddenimports = collect_all("steam")
gevent_datas, gevent_binaries, gevent_hiddenimports = collect_all("gevent")

# Common data assets for both platforms (icons, fonts, and Steam library data)
common_datas = [
    ("assets", "assets"),
    ("ui/resources", "ui/resources"),
    *steam_datas,
    *gevent_datas,
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=steam_binaries + gevent_binaries,
    datas=common_datas,
    hiddenimports=[
        # steam.client internals missed by static analysis
        "steam.client",
        "steam.client.builtins",
        "steam.enums",
        "steam.enums.common",
        "steam.protobufs",
        "steam.core.msg",
        "steam.core.crypto",
        # gevent cooperative networking
        "gevent.monkey",
        "gevent._util",
        "gevent.resolver.thread",
        # zope
        "zope.event",
        "zope.interface",
        *steam_hiddenimports,
        *gevent_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "doctest",
        "difflib",
        "asyncio",      # gevent replaces this
        "test",
        # Unused heavy Qt modules to keep binary lean
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.Qt3DCore",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ── Platform Branching ─────────────────────────────────────────────────────────

if sys.platform == "win32":
    # Exact Windows single-file portable executable (preserved 100% to spec)
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="SteamShortcutManager",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,              # Leave UPX off — antivirus flags UPX-packed exes
        console=False,          # No console window
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon="assets/icon.ico",
        version=None,
    )
else:
    # Linux onedir payload for AppImage packaging
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="steamshortcutmanager",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="steamshortcutmanager",
    )