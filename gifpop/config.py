"""Settings, paths and the recent-GIFs list. Plain JSON under XDG dirs."""
import json
import os
import uuid
from pathlib import Path

from .keys import BUILTIN_KLIPY

APP = "gifpop"


def _xdg(var, default):
    return Path(os.environ.get(var) or Path.home() / default) / APP


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config")
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share")
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache")
OUT_DIR = CACHE_DIR / "out"             # files handed to the clipboard
HTTP_CACHE = CACHE_DIR / "http"
TEMPLATES_DIR = DATA_DIR / "templates"  # drop your own blank templates here
ASSETS = Path(__file__).parent / "assets"
# Tiling WMs move focus with the mouse, so "hide when focus leaves" would close the popup
# while you reach for it. There we only hide after copying or on Esc.
TILING_WM = next((name for var, name in (("HYPRLAND_INSTANCE_SIGNATURE", "hyprland"),
                                         ("SWAYSOCK", "sway"), ("NIRI_SOCKET", "niri"),
                                         ("I3SOCK", "i3"))
                  if os.environ.get(var)), "")


def _pictures():
    # XDG_PICTURES_DIR from user-dirs.dirs, else ~/Pictures
    try:
        for line in (Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
                     / "user-dirs.dirs").read_text().splitlines():
            if line.startswith("XDG_PICTURES_DIR="):
                return Path(os.path.expandvars(line.split("=", 1)[1].strip().strip('"')))
    except OSError:
        pass
    return Path.home() / "Pictures"


DEFAULT_MEMES_DIR = _pictures() / "GifPop"

DEFAULTS = {
    "provider": "klipy",          # klipy | giphy
    "klipy_key": "",
    "giphy_key": "",
    "content_filter": "medium",   # klipy: off/low/medium/high; mapped to a giphy rating
    "copy_quality": "md",         # size bucket used for the copied file: hd/md/sm
    "copy_mode": "file",          # file = paste as a GIF attachment, link = paste the URL
    "auto_hide": True,
    "emoji_command": "plasma-emojier",
    "customer_id": "",
    "save_memes": True,           # keep a copy of every meme you make
    "memes_dir": "",              # empty = ~/Pictures/GifPop
}


class Config(dict):
    path = CONFIG_DIR / "config.json"

    def __init__(self):
        super().__init__(DEFAULTS)
        try:
            self.update(json.loads(self.path.read_text()))
        except (OSError, ValueError):
            pass
        if not self["customer_id"]:
            # Klipy wants a stable per-user id for its recents/ranking.
            self["customer_id"] = uuid.uuid4().hex
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self, indent=2))

    @property
    def klipy(self):
        """The key typed into Settings, else the one baked into release builds."""
        return self["klipy_key"] or BUILTIN_KLIPY

    @property
    def memes_dir(self):
        return Path(os.path.expanduser(self["memes_dir"])) if self["memes_dir"] else DEFAULT_MEMES_DIR

    @property
    def api_key(self):
        return self.klipy if self["provider"] == "klipy" else self["giphy_key"]


class Recents:
    path = DATA_DIR / "recent.json"
    limit = 48

    def __init__(self):
        try:
            self.items = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.items = []

    def add(self, gif_dict):
        self.items = [g for g in self.items if g["full"] != gif_dict["full"]]
        self.items.insert(0, gif_dict)
        del self.items[self.limit:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items))


for d in (OUT_DIR, HTTP_CACHE, TEMPLATES_DIR):
    d.mkdir(parents=True, exist_ok=True)
