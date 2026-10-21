# GifPop

A Win + . style GIF picker and meme maker for Linux, built for KDE Plasma on Wayland.

- **GIF**: search KLIPY or GIPHY, click a GIF and it's on the clipboard as a real `.gif` file. Ctrl+V into Discord, Signal, Telegram, browsers, Dolphin. Enter copies the top result. Right-click a GIF to copy its link, save it, or caption it.
- **Meme**: pick a blank template (top 100 from imgflip, plus anything in `~/.local/share/gifpop/templates/`) or open your own image. Classic outlined captions; drag to move; size, width, colours, caps per box. Copy or Save.
- **😀** opens your emoji picker (default: Flemozi; change in Settings).

Tenor's API shut down on 2026-06-30, so GIF search needs a free KLIPY key (<https://partner.klipy.com>) or a GIPHY key. Add it in ⚙ Settings.

## Install

```sh
pacman -S --needed python-pyqt6 qt6-imageformats   # via pkexec
./install.sh
gifpop
```

`install.sh` adds `~/.local/bin/gifpop`, an app-menu entry and an autostart entry (`gifpop --background`), so the window opens instantly from the hotkey.

### Hotkey

System Settings → Keyboard → Shortcuts → **Add New → Application → GifPop**, then set the key. To take over Meta+. from the current emoji picker, assign Meta+. and accept the reassign prompt.

## Why it stays running

On Wayland the app that copied something serves the clipboard. If GifPop quit after copying, the paste would fail, so it stays in the tray. Running `gifpop` again shows the existing window and passes along the shortcut's XDG activation token so KWin gives it focus.

## Command line

| | |
|---|---|
| `gifpop` | show the GIF tab |
| `gifpop --meme` | open the meme maker |
| `gifpop --toggle` | show, or hide if already focused |
| `gifpop --background` | start hidden (autostart) |
| `gifpop --quit` | stop the running instance |

Config: `~/.config/gifpop/config.json`. Cache: `~/.cache/gifpop/`. Recents: `~/.local/share/gifpop/recent.json`.

## Credits

Meme font: Anton (SIL Open Font License, `gifpop/assets/OFL.txt`). Templates: imgflip. GIFs: KLIPY / GIPHY.
