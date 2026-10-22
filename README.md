# GifPop

**Win + . for GIFs and memes on Linux.** Press the hotkey, search, click, and the GIF is on your clipboard, ready to paste into Discord, Signal, Telegram, a browser or anywhere else that takes images.

Built for KDE Plasma on Wayland. It works on other desktops; there you set the hotkey yourself.

## Install

```sh
curl -fsSL https://github.com/shatteredeagle/gifpop/releases/latest/download/get.sh | bash
```

That downloads the latest release, checks its checksum and installs it for your user (no root, nothing else to install). On Plasma it asks whether Win + . should open GifPop.

**Updates:** GifPop checks GitHub for a new release once a day and tells you in the tray. Click it (or Settings > Updates) to update in place; your settings and Win + . stay as they are. Turn the check off in Settings if you'd rather not; running the install line again also updates.

Prefer doing it by hand? Download `gifpop-<version>.tar.gz` from [Releases](https://github.com/shatteredeagle/gifpop/releases), extract it and run `./install.sh`.

To remove it: `~/.local/lib/gifpop/uninstall.sh`. Add `--purge` to also delete settings and recents. Memes you made stay in `~/Pictures/GifPop`.

## Using it

**GIFs**
- Type to search, or browse Recent and Trending.
- Click a GIF (or press Enter for the first one) and it's copied as a real `.gif` file. Paste with Ctrl + V.
- Arrow keys move through the results; Esc closes the window.
- Right-click a GIF to copy its link instead, or to caption it in the meme maker.

**Memes**
- Pick a blank template, or open any image of your own.
- Click a caption to type into it; drag it to move it. Change size, width, caps and colours from the side panel.
- Ctrl + Enter copies the meme, Ctrl + S saves it to a file.
- Every meme you make is kept in **My memes** (`~/Pictures/GifPop`), so you can copy it again later. Turn that off or pick another folder in Settings.

**Other**
- 😀 opens your desktop's emoji picker.
- ⚙ Settings: GIF source, content filter, copy quality, copy as file or link, memes folder, and your own API key if you have one.

GifPop stays in the system tray after you close the window. On Wayland the app that copied something has to keep running for the paste to work, and it also makes the hotkey open instantly.

## Tiling window managers

GifPop floats on its own on Sway and i3 (its window has a fixed size), and it doesn't hide just because focus moved while you reach for it. Bind the hotkey and, where needed, make it float:

```ini
# Hyprland (hyprland.conf)
bind = SUPER, period, exec, gifpop
windowrulev2 = float, class:^(gifpop)$
windowrulev2 = center, class:^(gifpop)$

# Sway (~/.config/sway/config)
bindsym $mod+period exec gifpop

# i3 (~/.config/i3/config)
bindsym $mod+period exec gifpop

# niri (config.kdl): inside binds { }, and a window rule
Mod+Period { spawn "gifpop"; }
window-rule { match app-id="^gifpop$"; open-floating true; }
```

Start it once at login with `gifpop --background` (for example `exec gifpop --background` / `exec-once = gifpop --background`) so the hotkey opens it instantly. No system tray is needed; `gifpop --quit` stops it. Hyprland blurs GifPop's translucent window by itself.

## GIF search

Search is powered by [KLIPY](https://klipy.com). Release downloads include an API key, so it works straight away. If searches ever start failing because the shared key is busy, get a free key of your own at <https://partner.klipy.com> and add it in Settings. GIPHY works too with your own GIPHY key.

GifPop is an independent app. It is not affiliated with or endorsed by KLIPY or GIPHY.

## Command line

| | |
|---|---|
| `gifpop` | show the GIF tab |
| `gifpop --meme` | open the meme maker |
| `gifpop --toggle` | show, or hide if already focused |
| `gifpop --background` | start hidden in the tray |
| `gifpop --quit` | stop the running instance |

Settings live in `~/.config/gifpop/config.json`, recents in `~/.local/share/gifpop/`, cache in `~/.cache/gifpop/`. Drop blank images into `~/.local/share/gifpop/templates/` to add your own templates.

## Development

GifPop is Python + PyQt6. From a checkout:

```sh
PYTHONPATH=. python3 -m gifpop     # needs PyQt6 from your distro
python3 tests/smoke.py             # headless smoke test
python3 scripts/shots.py out/      # screenshots of every screen
```

Build the self-contained release locally with `pip install -r packaging/requirements-build.txt` (in a venv) and `scripts/build.sh`; the result lands in `dist/`.

Releases are built by GitHub Actions: push a tag `vX.Y.Z` that matches `gifpop/__init__.py` and has a section in `CHANGELOG.md`. The workflow freezes the app into a self-contained bundle, adds the KLIPY key from the `KLIPY_API_KEY` repository secret, and publishes the release with that changelog section as its notes. The key is never in the repository; in the build it's stored scrambled so key-scraping bots don't find it (it identifies the app; it doesn't protect anything private).

## Credits and license

GPL-3.0-or-later, see [LICENSE](LICENSE). Meme font: Anton (SIL Open Font License, `gifpop/assets/OFL.txt`). Meme templates: imgflip and [memegen.link](https://memegen.link). Optional: an imgflip API Premium key (Settings > Memes) lets template search cover all of imgflip; searches past Premium's 200 a month are billed to your imgflip account. GIFs: KLIPY or GIPHY.
