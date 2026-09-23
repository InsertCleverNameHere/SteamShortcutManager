#!/bin/bash
set -e

# Move to the repository root directory
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

echo "=== Building Steam Shortcut Manager AppImage ==="

# 1. Compile with PyInstaller if payload does not exist
if [ ! -f "dist/steamshortcutmanager/steamshortcutmanager" ]; then
    echo "Compiling PyInstaller payload..."
    pyinstaller --clean build.spec
fi

# 2. Assemble AppDir
APPDIR="build/AppDir"
echo "Assembling AppDir at ${APPDIR}..."
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/share/metainfo"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/256x256/apps"

# Copy PyInstaller binaries and bundled resources
cp -r dist/steamshortcutmanager/* "${APPDIR}/"

# Copy AppImage integration files
cp packaging/linux/AppRun "${APPDIR}/AppRun"
chmod +x "${APPDIR}/AppRun"
cp packaging/linux/steamshortcutmanager.desktop "${APPDIR}/steamshortcutmanager.desktop"
cp packaging/linux/steamshortcutmanager.metainfo.xml "${APPDIR}/steamshortcutmanager.metainfo.xml"
cp packaging/linux/steamshortcutmanager.metainfo.xml "${APPDIR}/usr/share/metainfo/steamshortcutmanager.metainfo.xml"

# Copy icons (root icon and hicolor icon)
cp assets/icon.png "${APPDIR}/steamshortcutmanager.png"
cp assets/icon.png "${APPDIR}/.DirIcon"
cp assets/icon-256.png "${APPDIR}/usr/share/icons/hicolor/256x256/apps/steamshortcutmanager.png"

# Bundle libxcb-cursor.so.0 into AppDir/usr/lib for Qt 6.5+ compatibility
mkdir -p "${APPDIR}/usr/lib"
for lib_candidate in /usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0* /usr/lib64/libxcb-cursor.so.0* /usr/lib/libxcb-cursor.so.0*; do
    if [ -e "${lib_candidate}" ]; then
        cp -P "${lib_candidate}" "${APPDIR}/usr/lib/"
    fi
done

# 3. Locate or fetch appimagetool
APPIMAGETOOL=""
if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="appimagetool"
elif [ -f "build/appimagetool" ]; then
    APPIMAGETOOL="build/appimagetool"
else
    echo "Fetching appimagetool..."
    mkdir -p build
    curl -sL -o build/appimagetool "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x build/appimagetool
    APPIMAGETOOL="build/appimagetool"
fi

# 4. Generate AppImage
mkdir -p dist
export ARCH=x86_64
OUTPUT_APPIMAGE="dist/SteamShortcutManager-x86_64.AppImage"
rm -f "${OUTPUT_APPIMAGE}"

echo "Packaging AppImage with appimagetool..."
if [ "${APPIMAGETOOL}" = "appimagetool" ]; then
    appimagetool "${APPDIR}" "${OUTPUT_APPIMAGE}"
else
    # Use extract-and-run to run appimagetool itself without requiring FUSE 2 on Bazzite/CI
    "${APPIMAGETOOL}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT_APPIMAGE}"
fi

chmod +x "${OUTPUT_APPIMAGE}"
echo "=== AppImage successfully created at: ${OUTPUT_APPIMAGE} ==="