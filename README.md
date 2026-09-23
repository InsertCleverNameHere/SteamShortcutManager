# Steam Shortcut Manager 🎮

A robust, lightweight utility for managing Steam's binary `shortcuts.vdf` files on Windows and Linux (Bazzite, SteamOS, Fedora, Ubuntu). Add non-Steam games, customize their artwork and icons automatically via Steam's CDN, and keep your library synchronized across multiple user profiles.

![GitHub Release](https://img.shields.io/github/v/release/InsertCleverNameHere/SteamShortcutManager)
![License](https://img.shields.io/github/license/InsertCleverNameHere/SteamShortcutManager)

## ✨ Features

- **Cross-Platform Parity:** Runs natively on Windows 10/11 and Linux (primary target: Bazzite, plus SteamOS and standard distros).
- **Multi-User Support:** Automatically detects Steam installations (Native and Flatpak) and lists all user profiles.
- **Smart Asset & Icon Injection:** One-click fetching of official Steam Grid art (Capsule, Hero, Logo, Header), application icons, and positioning JSON directly from Steam's CDN.
- **Background Search:** Real-time Steam Store matching with thumbnail previews.
- **Transactional Safety:** Automatic timestamped rotating backups (`ssm-backups/`), atomic writes with `fsync`, and in-app backup restoration.
- **Steam-Running Guard:** Warns and blocks edits while Steam is running in the background to prevent edits from being overwritten on exit.
- **Binary Precision:** Native signed 32-bit VDF integer storage with CRC32 AppID generation to ensure native Steam client compatibility.
- **Portable & Fast:** Standalone Windows `.exe` and Linux `.AppImage` with zero installation required.

## 🚀 How to Run

### Option 1: Standalone Download (Recommended)

#### On Windows
1. Download `SteamShortcutManager.exe` from the [Latest Release](https://github.com/InsertCleverNameHere/SteamShortcutManager/releases).
2. **Note on Windows Security:** Since this executable is unsigned, Windows SmartScreen may display a "Windows protected your PC" prompt.
   - Click **"More Info"**
   - Click **"Run anyway"**
3. Select your Steam profile and start managing your shortcuts!

#### On Linux (Bazzite, SteamOS, Fedora, Ubuntu)
1. Download `SteamShortcutManager-x86_64.AppImage` from the [Latest Release](https://github.com/InsertCleverNameHere/SteamShortcutManager/releases).
2. Make it executable:
   ```bash
   chmod +x SteamShortcutManager-x86_64.AppImage
   ```
3. Double-click to run (or launch it via an AppImage manager such as Gear Lever).

---

### Option 2: Run from Source (Developers)

1. Clone the repository:
   ```bash
   git clone https://github.com/InsertCleverNameHere/SteamShortcutManager.git
   cd SteamShortcutManager
   ```

2. Create and activate a virtual environment:
   ```bash
   # Linux
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the app:
   ```bash
   python main.py
   ```

## 🛠️ Usage

1. **Locate Steam:** The app auto-detects your Steam installation. If it fails, point it to your Steam installation folder.
2. **Select Profile:** Choose the Steam user whose shortcuts you wish to edit.
3. **Manage Shortcuts:**
   - Click **+ Add Shortcut** to select a game executable (`.exe` on Linux, `.exe` or `.lnk` on Windows).
   - Use the **Pencil icon** to rename games.
   - Use the **Trash icon** to delete shortcuts and optionally clean up their grid art.
   - Click the **Sort button (`⇅`)** to sort shortcuts or **Restore from backup…** if you need to roll back changes.
4. **Artwork Injection:**
   - Open a game's details screen.
   - If a Steam match is found, click **Inject from Steam** to automatically download all artwork and the official client icon.
   - Alternatively, click any asset slot (e.g., "CAPSULE") to manually upload your own image.
5. **Sync:** After making changes, restart Steam (or switch to Game Mode on Bazzite/SteamOS) to see your new shortcuts, icons, and artwork in your library.

## 🛡️ Architecture & Safety

This project was built with a focus on "Hardened" stability:

- **Thread Safety:** All network and I/O tasks run on background workers to prevent UI freezes.
- **Registry Pattern:** Background worker threads are anchored in a central registry to prevent premature garbage-collection crashes.
- **Lockdown UI:** A fixed-width responsive layout ensures a consistent experience regardless of game title length or scaling.
- **Atomic Transactions:** Writes pass through `ShortcutsTransaction`, guaranteeing files are never partially written or corrupted during unexpected power loss or crashes.
- **Binary Precision:** Stores AppIDs as native 32-bit signed integers in `shortcuts.vdf` while mapping unsigned IDs for grid filenames, matching Steam's exact internal specifications.

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.

## 🙌 Credits

Built with Python 3, PySide6, and the `vdf` & `steam` libraries.
