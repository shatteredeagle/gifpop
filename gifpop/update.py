"""Update check against GitHub's latest release, and one-click update for installed bundles.

The update downloads the release tarball and checks it against SHA256SUMS here, so a bad
download shows up in the app. Then a detached install.sh takes over: it quits this copy,
replaces ~/.local/lib/gifpop and starts the new one. Source checkouts only get told."""
import hashlib
import json
import re
import shlex
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from . import __version__
from .config import CACHE_DIR

REPO = "shatteredeagle/gifpop"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD = f"https://github.com/{REPO}/releases/download"
INSTALL_DIR = Path.home() / ".local/lib/gifpop"
LOG = CACHE_DIR / "update.log"
FIRST_CHECK_MS = 60 * 1000
EVERY_MS = 24 * 3600 * 1000


def parse_version(v):
    """'v0.1.10' -> (0, 1, 10); anything unparsable sorts lowest."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    return tuple(map(int, m.groups())) if m else (0, 0, 0)


def can_self_update():
    # Only the bundle that install.sh put in ~/.local/lib/gifpop; a checkout updates with git.
    return bool(getattr(sys, "frozen", False)) and Path(sys.executable).resolve().is_relative_to(
        INSTALL_DIR.resolve())


class Updater(QObject):
    changed = pyqtSignal()        # state/latest/message changed: refresh any UI showing it
    found = pyqtSignal(str)       # a newer version turned up (once per check)

    def __init__(self, net, cfg, parent=None):
        super().__init__(parent)
        self.net = net
        self.cfg = cfg
        self.state = "idle"       # idle | checking | updating
        self.latest = None        # {"version", "url"} when newer than us
        self.message = ""
        self.timer = QTimer(self, interval=EVERY_MS)
        self.timer.timeout.connect(self.check)

    def start(self):
        """Automatic checks: once shortly after launch, then daily, unless turned off."""
        if self.cfg["check_updates"]:
            QTimer.singleShot(FIRST_CHECK_MS, self.check)
            self.timer.start()

    def set_auto(self, on):
        self.timer.start() if on else self.timer.stop()

    def check(self, manual=False):
        if self.state != "idle" or not (manual or self.cfg["check_updates"]):
            return
        self.state = "checking"
        self.message = "Checking…"
        self.changed.emit()
        self.net.get(LATEST, self._got, self._failed, prefer_cache=False, store=False)

    def _got(self, raw):
        self.state = "idle"
        try:
            rel = json.loads(raw)
            tag, url = rel["tag_name"], rel["html_url"]
        except (ValueError, KeyError, TypeError) as e:
            self._failed(f"unexpected reply ({e})")
            return
        self.cfg["last_update_check"] = int(time.time())
        self.cfg.save()
        if parse_version(tag) > parse_version(__version__):
            self.latest = {"version": tag.lstrip("v"), "tag": tag, "url": url}
            self.message = f"GifPop {self.latest['version']} is out."
            self.changed.emit()
            self.found.emit(self.latest["version"])
        else:
            self.latest = None
            self.message = "You're on the latest version."
            self.changed.emit()

    def _failed(self, msg):
        self.state = "idle"
        self.message = f"Couldn't check for updates: {msg}"
        self.changed.emit()

    # ---------------------------------------------------------------- update
    def update(self):
        if not self.latest or self.state != "idle" or not can_self_update():
            return
        self.state = "updating"
        self.message = f"Downloading GifPop {self.latest['version']}…"
        self.changed.emit()
        base = f"{DOWNLOAD}/{self.latest['tag']}"
        self.net.get(f"{base}/SHA256SUMS",
                     lambda sums: self.net.get(f"{base}/gifpop.tar.gz",
                                               lambda tar: self._install(sums, tar),
                                               self._update_failed, prefer_cache=False, store=False),
                     self._update_failed, prefer_cache=False, store=False)

    def _install(self, sums, tar):
        want = next((line.split()[0] for line in sums.decode(errors="replace").splitlines()
                     if line.endswith(" gifpop.tar.gz")), None)
        if not want or hashlib.sha256(tar).hexdigest() != want:
            self._update_failed("the download didn't match its checksum")
            return
        try:
            work = Path(tempfile.mkdtemp(prefix="gifpop-update-"))
            (work / "gifpop.tar.gz").write_bytes(tar)
            with tarfile.open(work / "gifpop.tar.gz") as t:
                t.extractall(work, filter="data")
            folder = next(work.glob("gifpop-*/install.sh")).parent
        except (OSError, tarfile.TarError, StopIteration) as e:
            self._update_failed(f"couldn't unpack it ({e})")
            return
        LOG.parent.mkdir(parents=True, exist_ok=True)
        # Detached: install.sh quits this process, so it must not be our child.
        # --no-hotkey leaves an existing Win+. binding as it is.
        script = (f"{shlex.quote(str(folder / 'install.sh'))} --no-hotkey >{shlex.quote(str(LOG))} 2>&1;"
                  f" rm -rf {shlex.quote(str(work))}")
        if not QProcess.startDetached("setsid", ["-f", "bash", "-c", script])[0]:
            self._update_failed("couldn't start the installer")
            return
        self.message = f"Installing GifPop {self.latest['version']}…"
        self.changed.emit()

    def _update_failed(self, msg):
        self.state = "idle"
        self.message = f"Update failed: {msg}"
        self.changed.emit()
