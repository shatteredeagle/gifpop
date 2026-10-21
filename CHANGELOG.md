# Changelog

All notable changes to GifPop. Each release's notes on GitHub come from its section here.

## [0.1.0] - 2026-10-21

The first public release: a Win + . style GIF picker and meme maker for KDE Plasma on Wayland.

### New
- **GIF search out of the box.** Release downloads include a KLIPY key, so search works without signing up for anything. If you have your own KLIPY or GIPHY key, add it in ⚙ Settings and it takes over.
- **Copy a GIF in one click.** It lands on the clipboard as a real `.gif` file, so Ctrl+V works in Discord, Signal, Telegram, browsers and Dolphin. Enter copies the top result. Right-click a GIF to copy its link, save it, or put a caption on it.
- **Meme maker.** Pick a blank template (imgflip's top 100, plus your own in `~/.local/share/gifpop/templates/`) or open any image. Classic outlined captions that you can drag, resize and recolour. Then copy or save.
- **Emoji button.** 😀 opens Plasma's emoji picker. You can change the command in Settings.
- **Win+. hotkey.** `install.sh` offers to bind Win+. to GifPop on Plasma and moves Plasma's emoji picker to Meta+Ctrl+Alt+Shift+Space.
- **Installer and uninstaller.** `install.sh` copies the app to `~/.local/lib/gifpop` and adds it to the app menu and autostart. `uninstall.sh` removes it again (add `--purge` to delete settings too).

### Known limits
- Built and tested on KDE Plasma 6 on Wayland (Arch). Other desktops should run it, but you have to set the hotkey yourself, and the Wayland clipboard needs the app to stay running in the tray.
- Needs PyQt6 from your distro; the installer tells you the package name if it's missing.
- The installer has only been tested on Arch so far.
