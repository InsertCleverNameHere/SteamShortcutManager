# Steam Shortcut Manager 🎮

A robust, lightweight utility for managing Steam's binary `shortcuts.vdf` files. Add non-Steam games, customize their artwork automatically via Steam's CDN, and keep your library synchronized across multiple user profiles.

![GitHub Release](https://img.shields.io/github/v/release/InsertCleverNameHere/SteamShortcutManager)
![License](https://img.shields.io/github/license/InsertCleverNameHere/SteamShortcutManager)

## ✨ Features

- **Multi-User Support:** Automatically detects Steam installations and lists all user profiles.
- **Smart Asset Injection:** One-click fetching of official Steam Grid art (Capsule, Hero, Logo, Header) and positioning JSON.
- **Background Search:** Real-time Steam Store matching with thumbnail previews.
- **Safety First:** Automatic `.bak` backups are created before every write operation.
- **Binary Precision:** Handles Steam's VDF format using CRC32 AppID generation to ensure native compatibility.
- **Portable & Fast:** Optimized 58MB single-file executable with zero installation required.

## 🚀 How to Run

### Option 1: The Executable (Recommended)

1. Download `SteamShortcutManager.exe` from the [Latest Release](https://github.com/YOUR_USERNAME/SteamShortcutManager/releases).
2. **Note on Windows Security:** Since this executable is unsigned, Windows SmartScreen may display a "Windows protected your PC" prompt.
   - Click **"More Info"**
   - Click **"Run anyway"**
3. Select your Steam profile and start managing your shortcuts!

### Option 2: Run from Source (Developers)

1. Clone the repository:

   ```bash
   git clone https://github.com/YOUR_USERNAME/SteamShortcutManager.git
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:

   ```bash
   python main.py
   ```

## 🛠️ Usage

1. **Locate Steam:** The app auto-detects your Steam folder. If it fails, point it to your Steam installation directory.
2. **Select Profile:** Choose the Steam user whose shortcuts you wish to edit.
3. **Manage Shortcuts:**
   - Click **+ Add Shortcut** to select a `.lnk` or `.exe`.
   - Use the **Pencil icon** to rename games.
   - Use the **Trash icon** to delete shortcuts and optionally clean up their grid art.
4. **Artwork Injection:**
   - Open a game's details.
   - If a Steam match is found, click **Inject from Steam** to automatically download all artwork.
   - Alternatively, click any asset slot (e.g., "CAPSULE") to manually upload your own image.
5. **Sync:** After making changes, restart Steam to see your new shortcuts and artwork in your library.

## 🛡️ Architecture & Safety

This project was built with a focus on "Hardened" stability:

- **Thread Safety:** All network and I/O tasks run on background workers to prevent UI freezes.
- **Registry Pattern:** Background threads are anchored to prevent memory-related crashes.
- **Lockdown UI:** A fixed-width responsive layout ensures a consistent experience regardless of game title length or network status.
- **AppID Integrity:** Uses string-based ID storage to prevent 32-bit integer overflow/unpack errors common in VDF manipulation.

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.

## 🙌 Credits

Built with Python 3, PySide6, and the `steam` & `vdf` libraries.
