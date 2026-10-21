"""Headless screenshots of every screen, for design work. Not shipped.
Usage: /usr/bin/python3 scripts/shots.py OUT_DIR   (uses your real KLIPY key if one is set,
read from ~/.config/gifpop/config.json; everything else runs in a throwaway profile)."""
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
real_cfg = Path.home() / ".config/gifpop/config.json"
key = ""
try:
    key = json.loads(real_cfg.read_text()).get("klipy_key", "")
except (OSError, ValueError):
    pass

tmp = Path(tempfile.mkdtemp(prefix="gifpop-shots-"))
for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
    os.environ[var] = str(tmp / var.lower())
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
(tmp / "xdg_config_home/gifpop").mkdir(parents=True)
(tmp / "xdg_config_home/gifpop/config.json").write_text(json.dumps(
    {"klipy_key": key, "memes_dir": str(tmp / "memes")}))
sys.path.insert(0, str(root))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from gifpop import app as gp  # noqa: E402
from gifpop.config import Config  # noqa: E402

app = QApplication([])
app.setStyleSheet(gp.STYLE)
win = gp.MainWindow(Config())
steps = []


def shot(name, widget=None):
    (widget or win).grab().save(str(out / f"{name}.png"))
    print("shot", name)


def step(ms):
    def deco(fn):
        steps.append((ms, fn))
        return fn
    return deco


@step(100)
def _():
    win.summon("gif")


@step(6000)
def _():
    shot("1-gif-trending")
    win.gifs.search.setText("happy dance")
    win.gifs._run_search()


@step(6000)
def _():
    shot("2-gif-search")
    win.copy_gif(win.gifs.tiles[0].gif) if win.gifs.tiles else None


@step(3000)
def _():
    shot("3-gif-copied-toast")
    win.summon("meme")


@step(6000)
def _():
    shot("4-meme-templates")
    if win.templates.tiles:
        win.templates._pick(win.templates.tiles[0].tpl)


@step(4000)
def _():
    if win.editor.items:
        win.editor.items[0].set(text="WHEN THE BUILD")
        if len(win.editor.items) > 1:
            win.editor.items[1].set(text="PASSES FIRST TRY")
    shot("5-meme-editor")
    win.copy_meme(win.editor.render())


@step(1500)
def _():
    win.show_page("meme")
    win.templates.mine.setChecked(True)


@step(1500)
def _():
    shot("6-my-memes")
    saved = list((tmp / "memes").glob("*.png"))
    print("kept memes:", len(saved))
    win.templates.mine.setChecked(False)
    dlg = gp.SettingsDialog(win.cfg, win)
    dlg.show()
    QTimer.singleShot(300, lambda: (shot("7-settings", dlg), dlg.close()))


@step(800)
def _():
    app.quit()


t = 0
for ms, fn in steps:
    t += ms
    QTimer.singleShot(t, fn)
app.exec()
