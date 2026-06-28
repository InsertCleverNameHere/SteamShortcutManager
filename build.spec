# build.spec
from PyInstaller.utils.hooks import collect_all

# Collect everything steam.client needs (protobuf, enums, protobufs)
steam_datas, steam_binaries, steam_hiddenimports = collect_all("steam")
gevent_datas, gevent_binaries, gevent_hiddenimports = collect_all("gevent")


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=steam_binaries + gevent_binaries,
    datas=[
        ("assets/icon.ico", "assets"),          # App icon
        *steam_datas,
        *gevent_datas,
    ],
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
        # pywin32
        "win32api",
        "win32com.client",
        "win32com.shell",
        "pywintypes",
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
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

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