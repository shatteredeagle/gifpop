# GifPop

A Win + . style GIF picker and meme maker for Linux, built for KDE Plasma on Wayland.

- **GIF**: search KLIPY (or GIPHY), click a GIF and it's on the clipboard as a real `.gif` file. Ctrl+V into Discord, Signal, Telegram, browsers, Dolphin. Enter copies the top result. Right-click a GIF to copy its link, save it, or caption it.
- **Meme**: pick a blank template (top 100 from imgflip, plus anything in `~/.local/share/gifpop/templates/`) or open your own image. Classic outlined captions; drag to move; size, width, colours, caps per box. Copy or Save.
- **😀** opens your emoji picker (default: Plasma's; change in Settings).

GifPop is an independent app. It is not affiliated with or endorsed by KLIPY or GIPHY.

## Install

1. Install PyQt6 from your distro:
   - Arch: `sudo pacman -S --needed python-pyqt6 qt6-imageformats`
   - Debian/Ubuntu: `sudo apt install python3-pyqt6 qt6-image-formats-plugins`
   - Fedora: `sudo dnf install python3-pyqt6 qt6-qtimageformats`
2. Download `gifpop-<version>.tar.gz` from [Releases](https://github.com/shatteredeagle/gifpop/releases), extract it, and run `./install.sh` in the folder.
3. Press **Win + .**

`install.sh` copies the app to `~/.local/lib/gifpop`, adds `~/.local/bin/gifpop`, an app-menu entry and an autostart entry (`gifpop --background`, so the window opens instantly). On Plasma it offers to bind Win+. to GifPop and moves Plasma's emoji picker to Meta+Ctrl+Alt+Shift+Space. Use `--hotkey` / `--no-hotkey` to skip the question.

Remove it with `./uninstall.sh` (`--purge` also deletes settings and recents).

### API key

Release downloads have a KLIPY key built in, so search works straight away. Running from a git checkout has no key: get a free one at <https://partner.klipy.com> (or a GIPHY key) and add it in ⚙ Settings. A key in Settings always overrides the built-in one.

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

## Development

- Run from a checkout: `./install.sh` (it copies the checkout, so re-run it after changes), or `PYTHONPATH=. python3 -m gifpop`.
- Smoke test: `python3 tests/smoke.py` (headless).
- Build a release tarball locally: `KLIPY_API_KEY=... scripts/build.sh` → `dist/`.
- Release: bump `gifpop/__init__.py`, add the version's section to `CHANGELOG.md`, commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`. GitHub Actions builds the tarball with the key from the `KLIPY_API_KEY` repo secret and publishes the release with that changelog section as the notes.

The key is never in the repo. Release builds store it scrambled (`gifpop/_builtin.py`, generated at build time) so bots that scrape for API keys don't find a plain string. Anyone determined can still extract it, which is normal for GIF API keys: they identify the app and don't protect anything private.

## Credits and license

GifPop is GPL-3.0-or-later (see `LICENSE`). Meme font: Anton (SIL Open Font License, `gifpop/assets/OFL.txt`). Icon: original to GifPop. Templates: imgflip. GIFs: KLIPY / GIPHY.
