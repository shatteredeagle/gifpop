# Changelog

All notable changes to GifPop. Each release's notes on GitHub come from its section here.

## [Unreleased]

### New
- **Bring your own imgflip key for every template imgflip has.** Settings > Memes has an optional imgflip API key. With an imgflip **API Premium** key, pausing in the template search also searches imgflip's whole database (alternate names too) and adds what it finds to the grid. Each search is sent once per session, since imgflip includes 200 a month and bills for more. Free imgflip keys don't unlock search, and a key imgflip rejects is reported once and then left alone until you change it.

### Fixed
- **Quit didn't quit while the GifPop window was open.** The tray menu's *Quit* and `gifpop --quit` were silently ignored whenever the window was showing (it only hid). They now close GifPop every time.

## [0.1.2] - 2026-10-22

### New
- **GifPop tells you when there's an update, and installs it for you.** It checks GitHub once a day; when a new version is out you get a tray message and an *Update to …* item in the tray menu. One click downloads it, checks it, installs it and restarts GifPop, keeping your settings and Win + . shortcut. Settings > Updates has *Check now* and a switch to turn the daily check off.
- **About 200 more meme templates.** The template list now also includes the full [memegen.link](https://memegen.link) catalog, alongside imgflip's top 100. Search matches template names and memegen's keywords, so things like "galaxy" find Galaxy Brain. Templates both sites have only show once.

### Fixed
- **Filtering meme templates froze the window and lost the pictures.** Every letter you typed rebuilt the whole template grid and reloaded every thumbnail, so typing stalled and tiles showed their names with no image. Filtering now just shows and hides the tiles that are already there, so it's instant and the pictures stay.

## [0.1.1] - 2026-10-21

### Fixed
- **Win + . didn't open GifPop right after installing on KDE Plasma.** The installer saved the shortcut, but Plasma only started listening for it after you logged out and back in. It now works straight away.
- `gifpop --quit` (and opening GifPop from the hotkey) could occasionally be ignored by the running copy. Fixed.

### After upgrading
- If Win + . did nothing for you on 0.1.0, run the install line again and answer yes to the Win + . question (or just log out and back in):
  `curl -fsSL https://github.com/shatteredeagle/gifpop/releases/latest/download/get.sh | bash`

## [0.1.0] - 2026-10-21

The first public release: a Win + . style GIF picker and meme maker for Linux, built for KDE Plasma on Wayland.

### New
- **Nothing to install first.** The download is self-contained (about 46 MB). One line installs or updates it:
  `curl -fsSL https://github.com/shatteredeagle/gifpop/releases/latest/download/get.sh | bash`
- **GIF search out of the box.** A KLIPY key is built in, so search works without signing up for anything. Have your own KLIPY or GIPHY key? Add it in Settings and it takes over.
- **One click to copy.** The GIF lands on the clipboard as a real `.gif` file, so Ctrl + V works in Discord, Signal, Telegram, browsers and file managers. Enter copies the top result, arrow keys move through the results, right-click copies the link or opens the GIF in the meme maker.
- **Results that look like a GIF picker.** GIFs keep their shape in a three-column layout, with placeholders while they load and clear messages when there's nothing to show.
- **Meme maker.** Pick a blank template or open any image, click a caption and type. Colour swatches, size and width sliders, ALL CAPS and outline. Ctrl + Enter copies, Ctrl + S saves.
- **My memes.** Every meme you make is kept in `~/Pictures/GifPop` and listed under My memes: click to copy it again, hover for edit or delete (with undo). Turn it off or pick a folder in Settings.
- **Win + . hotkey.** On Plasma the installer offers to bind Win + . to GifPop and moves Plasma's emoji picker to Meta + Ctrl + Alt + Shift + Space. The 😀 button still opens the emoji picker.
- **A cleaner look** that follows your light or dark theme: rounded frameless window, pill tabs and chips, floating "Copied" toast.

### Known limits
- Built and tested on KDE Plasma 6 on Wayland (Arch). Other desktops should work, but you set the hotkey yourself.
- The frosted-glass blur only shows when GifPop runs on your system's own Qt (a source install on Plasma). The self-contained download draws the same window without blur.
- x86-64 only for now.
- KLIPY's free key allows a limited number of searches per hour, shared by everyone using the built-in key. If you hit it, GifPop says so and you can add your own free key.
