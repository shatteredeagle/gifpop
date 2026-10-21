"""Main window, tray icon, settings, clipboard and the single-instance daemon.

The app stays resident: on Wayland the clipboard is served by the app that set it,
so quitting after a copy would make the paste fail. Running `gifpop` again just
asks the resident instance to show itself (and forwards the XDG activation token
from the global shortcut so KWin gives the window focus)."""
import os
import re
import shlex
import sys

from PyQt6.QtCore import QByteArray, QMimeData, QProcess, Qt, QTimer, QUrl
from PyQt6.QtGui import (QFont, QFontDatabase, QGuiApplication, QIcon,
                         QImage, QKeySequence, QShortcut)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                             QLabel, QLineEdit, QMenu, QPushButton, QStackedWidget,
                             QSystemTrayIcon, QVBoxLayout, QWidget)

from .config import ASSETS, OUT_DIR, Config, Recents
from . import __version__
from .gifs import GifPage
from .keys import BUILTIN_KLIPY
from .memes import MemeEditor, TemplatePage
from .net import Net

SOCKET = f"gifpop-{os.getuid()}"
GIF_SIZE = (480, 600)
MEME_SIZE = (1000, 680)

STYLE = """
QWidget { font-size: 10pt; }
#tile { background: palette(alternate-base); border-radius: 6px; }
#tile:hover { background: palette(highlight); }
#caption, #status, #attrib { color: palette(placeholder-text); font-size: 8.5pt; }
QPushButton#chip { padding: 3px 9px; border-radius: 11px; border: 1px solid palette(mid); }
QPushButton#chip[active="true"] { background: palette(highlight); color: palette(highlighted-text); }
QPushButton#tab { padding: 5px 12px; border: none; border-bottom: 2px solid transparent; }
QPushButton#tab:checked { border-bottom: 2px solid palette(highlight); font-weight: bold; }
QPushButton#primary { background: palette(highlight); color: palette(highlighted-text); padding: 5px 18px; }
#canvas { background: #202020; }
"""


def app_icon():
    path = ASSETS / "gifpop.svg"
    if path.exists():
        return QIcon(str(path))
    return QIcon.fromTheme("image-gif")


def safe_name(text, fallback):
    s = re.sub(r"[^\w-]+", "-", text.lower()).strip("-")[:40]
    return s or fallback


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GifPop settings")
        self.cfg = cfg
        self.provider = QComboBox()
        self.provider.addItem("KLIPY (what Discord/WhatsApp moved to)", "klipy")
        self.provider.addItem("GIPHY", "giphy")
        self.provider.setCurrentIndex(0 if cfg["provider"] == "klipy" else 1)
        self.klipy = QLineEdit(cfg["klipy_key"], echoMode=QLineEdit.EchoMode.Password)
        self.giphy = QLineEdit(cfg["giphy_key"], echoMode=QLineEdit.EchoMode.Password)
        if BUILTIN_KLIPY:
            self.klipy.setPlaceholderText("Built in. Leave empty unless you have your own.")
        self.filter = QComboBox()
        for v in ("off", "low", "medium", "high"):
            self.filter.addItem(v, v)
        self.filter.setCurrentText(cfg["content_filter"])
        self.quality = QComboBox()
        for label, v in (("High (big files)", "hd"), ("Medium", "md"), ("Small", "sm")):
            self.quality.addItem(label, v)
        self.quality.setCurrentIndex(["hd", "md", "sm"].index(cfg["copy_quality"]))
        self.mode = QComboBox()
        self.mode.addItem("GIF file (pastes as an attachment)", "file")
        self.mode.addItem("Link (pastes the URL as text)", "link")
        self.mode.setCurrentIndex(0 if cfg["copy_mode"] == "file" else 1)
        self.auto_hide = QCheckBox("Hide after copying / when focus leaves")
        self.auto_hide.setChecked(cfg["auto_hide"])
        self.emoji = QLineEdit(cfg["emoji_command"])

        links = QLabel('Free keys: <a href="https://partner.klipy.com">partner.klipy.com</a> · '
                       '<a href="https://developers.giphy.com/dashboard/">developers.giphy.com</a>')
        links.setOpenExternalLinks(True)
        about = QLabel(f"GifPop {__version__} · GPL-3.0 · independent app, not affiliated with "
                       "or endorsed by KLIPY or GIPHY")
        about.setObjectName("caption")
        form = QFormLayout(self)
        form.addRow("GIF source", self.provider)
        form.addRow("KLIPY key", self.klipy)
        form.addRow("GIPHY key", self.giphy)
        form.addRow(links)
        form.addRow("Content filter", self.filter)
        form.addRow("Copy quality", self.quality)
        form.addRow("Copy as", self.mode)
        form.addRow(self.auto_hide)
        form.addRow("Emoji button runs", self.emoji)
        form.addRow(about)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.setMinimumWidth(460)

    def accept(self):
        c = self.cfg
        c["provider"] = self.provider.currentData()
        c["klipy_key"] = self.klipy.text().strip()
        c["giphy_key"] = self.giphy.text().strip()
        c["content_filter"] = self.filter.currentData()
        c["copy_quality"] = self.quality.currentData()
        c["copy_mode"] = self.mode.currentData()
        c["auto_hide"] = self.auto_hide.isChecked()
        c["emoji_command"] = self.emoji.text().strip()
        c.save()
        super().accept()


class MainWindow(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.net = Net(self)
        self.recents = Recents()
        self.setWindowTitle("GifPop")
        self.setWindowIcon(app_icon())
        self.resize(*GIF_SIZE)

        fid = QFontDatabase.addApplicationFont(str(ASSETS / "Anton-Regular.ttf"))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        meme_font = fams[0] if fams else QFont("DejaVu Sans").family()

        self.gifs = GifPage(cfg, self.net, self.recents)
        self.templates = TemplatePage(self.net)
        self.editor = MemeEditor(meme_font)
        self.stack = QStackedWidget()
        for w in (self.gifs, self.templates, self.editor):
            self.stack.addWidget(w)

        self.gifs.picked.connect(self.copy_gif)
        self.gifs.copy_link.connect(self.copy_link)
        self.gifs.save_as.connect(self.save_gif)
        self.gifs.caption.connect(self.caption_gif)
        self.templates.open_image.connect(self.open_editor)
        self.editor.back.connect(lambda: self.show_page("meme"))
        self.editor.copy_image.connect(self.copy_meme)
        self.editor.save_image.connect(self.save_meme)

        self.tab_gif = self._tab("GIF")
        self.tab_meme = self._tab("Meme")
        group = QButtonGroup(self)
        group.addButton(self.tab_gif)
        group.addButton(self.tab_meme)
        self.tab_gif.clicked.connect(lambda: self.show_page("gif"))
        self.tab_meme.clicked.connect(lambda: self.show_page("meme"))
        emoji = QPushButton("😀")
        emoji.setToolTip("Emoji picker")
        emoji.setFlat(True)
        emoji.clicked.connect(self.launch_emoji)
        gear = QPushButton("⚙")
        gear.setToolTip("Settings")
        gear.setFlat(True)
        gear.clicked.connect(self.open_settings)

        bar = QHBoxLayout()
        bar.setSpacing(2)
        bar.addWidget(self.tab_gif)
        bar.addWidget(self.tab_meme)
        bar.addStretch()
        bar.addWidget(emoji)
        bar.addWidget(gear)

        self.toast = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.toast.setObjectName("status")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.addLayout(bar)
        lay.addWidget(self.stack, 1)
        lay.addWidget(self.toast)

        QShortcut(QKeySequence("Escape"), self, self.escape)
        QShortcut(QKeySequence("Ctrl+M"), self, lambda: self.show_page("meme"))
        QShortcut(QKeySequence("Ctrl+G"), self, lambda: self.show_page("gif"))
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)

        self.blur_timer = QTimer(self, singleShot=True, interval=200)
        self.blur_timer.timeout.connect(self._blur_check)
        self.show_page("gif")

    def _tab(self, text):
        b = QPushButton(text)
        b.setObjectName("tab")
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    # ---- pages & visibility --------------------------------------------
    def show_page(self, page):
        if page == "gif":
            self.stack.setCurrentWidget(self.gifs)
            self.tab_gif.setChecked(True)
            self.resize(*GIF_SIZE)
            if not self.gifs.tiles and not self.gifs.loading:
                self.gifs.refresh()
            self.gifs.focus_search()
        elif page == "meme":
            self.stack.setCurrentWidget(self.templates)
            self.tab_meme.setChecked(True)
            self.resize(*GIF_SIZE)
            self.templates.ensure_loaded()
            self.templates.filter.setFocus()
        self.toast.clear()

    def summon(self, page="gif", token=""):
        if token:
            os.environ["XDG_ACTIVATION_TOKEN"] = token  # Qt's Wayland plugin consumes this
        if self.isVisible() and self.isActiveWindow() and page == "toggle":
            self.hide()
            return
        if page in ("gif", "meme"):
            self.show_page(page)
        self.show()
        self.raise_()
        self.activateWindow()

    def escape(self):
        if self.stack.currentWidget() is self.editor:
            self.show_page("meme")
        elif self.gifs.search.text():
            self.gifs.search.clear()
        else:
            self.hide()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.ActivationChange and not self.isActiveWindow():
            self.blur_timer.start()

    def _blur_check(self):
        # Hide when the user clicks elsewhere, like Win+. does — but not while one of
        # our own dialogs has focus, and not mid-meme.
        if (self.cfg["auto_hide"] and self.isVisible() and QApplication.activeWindow() is None
                and self.stack.currentWidget() is not self.editor):
            self.hide()

    def closeEvent(self, e):
        e.ignore()
        self.hide()

    def flash(self, msg, hide=False):
        self.toast.setText(msg)
        if hide and self.cfg["auto_hide"]:
            QTimer.singleShot(450, self.hide)

    # ---- clipboard -----------------------------------------------------
    def _set_clipboard(self, mime):
        QGuiApplication.clipboard().setMimeData(mime)

    def copy_gif(self, gif):
        if self.cfg["copy_mode"] == "link":
            self.copy_link(gif)
            return
        self.flash("Downloading…")

        def ok(data):
            # Only the GIF on the clipboard is kept on disk; no library of downloads.
            for old in OUT_DIR.glob("*.gif"):
                old.unlink(missing_ok=True)
            path = OUT_DIR / f"{safe_name(gif.title, 'gif')}-{safe_name(gif.id, 'x')}.gif"
            path.write_bytes(data)
            mime = QMimeData()
            url = QUrl.fromLocalFile(str(path))
            mime.setUrls([url])
            mime.setData("image/gif", QByteArray(data))
            mime.setData("x-special/gnome-copied-files",
                         QByteArray(b"copy\n" + url.toEncoded().data()))
            self._set_clipboard(mime)
            self.recents.add(gif.to_dict())
            self.gifs.report_share(gif)
            self.flash("Copied — press Ctrl+V to paste", hide=True)
        self.net.get(gif.full, ok, lambda m: self.flash(f"Download failed: {m}"), store=False)

    def copy_link(self, gif):
        QGuiApplication.clipboard().setText(gif.url)
        self.recents.add(gif.to_dict())
        self.gifs.report_share(gif)
        self.flash("Link copied — press Ctrl+V to paste", hide=True)

    def save_gif(self, gif):
        name = f"{safe_name(gif.title, 'gif')}.gif"
        path, _ = QFileDialog.getSaveFileName(self, "Save GIF", os.path.expanduser(f"~/{name}"),
                                              "GIF (*.gif)")
        if path:
            self.net.get(gif.full, lambda d: (open(path, "wb").write(d),
                                              self.flash(f"Saved {os.path.basename(path)}")),
                         lambda m: self.flash(f"Download failed: {m}"), store=False)

    def caption_gif(self, gif):
        self.flash("Opening first frame in the meme maker…")
        self.net.get(gif.full, lambda d: self.open_editor(QImage.fromData(d), 2),
                     lambda m: self.flash(f"Download failed: {m}"), store=False)

    def open_editor(self, image, boxes):
        if image.isNull():
            self.flash("Couldn't open that image.")
            return
        self.tab_meme.setChecked(True)
        self.stack.setCurrentWidget(self.editor)
        self.resize(*MEME_SIZE)
        self.editor.load(image, boxes)
        self.toast.clear()

    def copy_meme(self, image):
        path = OUT_DIR / "meme.png"
        n = 1
        while path.exists():  # keep earlier copies valid for apps that paste lazily
            n += 1
            path = OUT_DIR / f"meme-{n}.png"
        image.save(str(path), "PNG")
        mime = QMimeData()
        mime.setImageData(image)
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        self._set_clipboard(mime)
        self.flash("Meme copied — press Ctrl+V to paste", hide=True)

    def save_meme(self, image):
        path, _ = QFileDialog.getSaveFileName(self, "Save meme", os.path.expanduser("~/meme.png"),
                                              "PNG (*.png);;JPEG (*.jpg)")
        if path:
            image.save(path)
            self.flash(f"Saved {os.path.basename(path)}")

    # ---- misc ----------------------------------------------------------
    def launch_emoji(self):
        cmd = shlex.split(self.cfg["emoji_command"] or "")
        if cmd and QProcess.startDetached(cmd[0], cmd[1:]):
            self.hide()
        else:
            self.flash("Set the emoji picker command in Settings.")

    def open_settings(self):
        if SettingsDialog(self.cfg, self).exec():
            self.gifs.reload_provider()


def make_tray(win):
    tray = QSystemTrayIcon(app_icon(), win)
    tray.setToolTip("GifPop")
    menu = QMenu()
    menu.addAction("Search GIFs", lambda: win.summon("gif"))
    menu.addAction("Make a meme", lambda: win.summon("meme"))
    menu.addAction("Settings", lambda: (win.summon(""), win.open_settings()))
    menu.addSeparator()
    menu.addAction("Quit", QApplication.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda r: win.summon("toggle") if r == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray._menu = menu
    tray.show()
    return tray


def send_to_running(msg):
    sock = QLocalSocket()
    sock.connectToServer(SOCKET)
    if not sock.waitForConnected(300):
        return False
    sock.write(msg.encode())
    sock.flush()
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    page = "meme" if "--meme" in argv else "toggle" if "--toggle" in argv else "gif"
    token = os.environ.pop("XDG_ACTIVATION_TOKEN", "")
    if "--quit" in argv:
        return 0 if send_to_running("quit") else 1
    QGuiApplication.setDesktopFileName("gifpop")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("gifpop")
    app.setQuitOnLastWindowClosed(False)
    if send_to_running(f"{page} {token}" if "--background" not in argv else "noop"):
        return 0

    QLocalServer.removeServer(SOCKET)  # stale socket from a crash
    server = QLocalServer()
    server.listen(SOCKET)
    app.setStyleSheet(STYLE)
    win = MainWindow(Config())

    def on_conn():
        s = server.nextPendingConnection()

        def read():
            parts = bytes(s.readAll()).decode().split()
            if not parts:
                return
            if parts[0] == "quit":
                app.quit()
            elif parts[0] != "noop":
                win.summon(parts[0], parts[1] if len(parts) > 1 else "")
        s.readyRead.connect(read)
        s.disconnected.connect(s.deleteLater)
    server.newConnection.connect(on_conn)

    win._tray = make_tray(win) if QSystemTrayIcon.isSystemTrayAvailable() else None
    if "--background" not in argv:
        win.summon(page if page != "toggle" else "gif", token)
    return app.exec()
