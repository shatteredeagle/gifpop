"""Main window, tray icon, settings, clipboard and the single-instance daemon.

The app stays resident: on Wayland the clipboard is served by the app that set it,
so quitting after a copy would make the paste fail. Running `gifpop` again just
asks the resident instance to show itself (and forwards the XDG activation token
from the global shortcut so KWin gives the window focus)."""
import hashlib
import os
import re
import shlex
import sys
import time

from PyQt6.QtCore import (QBuffer, QByteArray, QMimeData, QProcess, QPropertyAnimation, Qt,
                          QTimer, QUrl)
from PyQt6.QtGui import (QFont, QFontDatabase, QGuiApplication, QIcon,
                         QImage, QKeySequence, QShortcut)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                             QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
                             QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QPushButton, QStackedWidget, QSystemTrayIcon, QToolButton,
                             QVBoxLayout, QWidget)

from .config import ASSETS, DEFAULT_MEMES_DIR, OUT_DIR, Config, Recents
from . import __version__, theme
from .gifs import GifPage
from .keys import BUILTIN_KLIPY
from .memes import MemeEditor, TemplatePage
from .net import Net

SOCKET = f"gifpop-{os.getuid()}"
GIF_SIZE = (480, 600)
MEME_SIZE = (760, 600)



def apply_theme(app):
    """Fusion + our QSS: Breeze paints opaque strips behind scrollbars in a translucent
    window, and the QSS covers nearly everything anyway. Follows dark/light switches."""
    app.setStyle("Fusion")
    app.setStyleSheet(theme.style())
    app.styleHints().colorSchemeChanged.connect(lambda _: app.setStyleSheet(theme.style()))


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
        self.provider.addItem("KLIPY", "klipy")
        self.provider.addItem("GIPHY (needs your own key)", "giphy")
        self.provider.setCurrentIndex(0 if cfg["provider"] == "klipy" else 1)
        self.filter = QComboBox()
        for label, v in (("Off", "off"), ("Low", "low"), ("Medium", "medium"), ("High", "high")):
            self.filter.addItem(label, v)
        self.filter.setCurrentIndex(max(0, self.filter.findData(cfg["content_filter"])))
        self.quality = QComboBox()
        for label, v in (("High (bigger files)", "hd"), ("Medium", "md"), ("Small", "sm")):
            self.quality.addItem(label, v)
        self.quality.setCurrentIndex(["hd", "md", "sm"].index(cfg["copy_quality"]))
        self.mode = QComboBox()
        self.mode.addItem("GIF file (pastes as an attachment)", "file")
        self.mode.addItem("Link (pastes the URL as text)", "link")
        self.mode.setCurrentIndex(0 if cfg["copy_mode"] == "file" else 1)

        self.own_key = QCheckBox("Use my own API key")
        self.own_key.setChecked(bool(cfg["klipy_key"] or cfg["giphy_key"]) or not BUILTIN_KLIPY)
        self.klipy = QLineEdit(cfg["klipy_key"], echoMode=QLineEdit.EchoMode.Password,
                               placeholderText="KLIPY key")
        self.giphy = QLineEdit(cfg["giphy_key"], echoMode=QLineEdit.EchoMode.Password,
                               placeholderText="GIPHY key")
        key_hint = QLabel(
            ("GifPop includes a KLIPY key. Add your own only if searches start failing. "
             if BUILTIN_KLIPY else "") +
            'Free keys: <a href="https://partner.klipy.com">partner.klipy.com</a> · '
            '<a href="https://developers.giphy.com/dashboard/">developers.giphy.com</a>',
            objectName="hint", wordWrap=True, openExternalLinks=True)

        self.save_memes = QCheckBox("Keep a copy of every meme I make")
        self.save_memes.setChecked(cfg["save_memes"])
        self.memes_dir = QLineEdit(cfg["memes_dir"], placeholderText=str(DEFAULT_MEMES_DIR))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        folder = QHBoxLayout()
        folder.addWidget(self.memes_dir, 1)
        folder.addWidget(browse)
        self.save_memes.toggled.connect(self.memes_dir.setEnabled)
        self.save_memes.toggled.connect(browse.setEnabled)
        self.memes_dir.setEnabled(cfg["save_memes"])
        browse.setEnabled(cfg["save_memes"])

        self.auto_hide = QCheckBox("Hide after copying or when I click elsewhere")
        self.auto_hide.setChecked(cfg["auto_hide"])
        self.emoji = QLineEdit(cfg["emoji_command"])

        form = QFormLayout(self)
        form.setVerticalSpacing(8)
        section = lambda t: form.addRow(QLabel(t, objectName="sectionTitle"))  # noqa: E731
        section("GIFs")
        form.addRow("Source", self.provider)
        form.addRow("Content filter", self.filter)
        form.addRow("Copy quality", self.quality)
        form.addRow("Copy as", self.mode)
        form.addRow(self.own_key)
        form.addRow("KLIPY key", self.klipy)
        form.addRow("GIPHY key", self.giphy)
        form.addRow(key_hint)
        section("Memes")
        form.addRow(self.save_memes)
        form.addRow("Folder", folder)
        section("General")
        form.addRow(self.auto_hide)
        form.addRow("Emoji button runs", self.emoji)

        about = QLabel(f"GifPop {__version__} · GPL-3.0 · independent, not affiliated with "
                       "KLIPY or GIPHY", objectName="caption", wordWrap=True)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(about, 1)
        bottom.addWidget(bb)
        form.addRow(bottom)

        def sync():
            own, giphy = self.own_key.isChecked(), self.provider.currentData() == "giphy"
            form.setRowVisible(self.klipy, own)
            form.setRowVisible(self.giphy, own or giphy)
        self.own_key.toggled.connect(sync)
        self.provider.currentIndexChanged.connect(sync)
        sync()
        self.setMinimumWidth(480)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "My memes folder",
                                             self.memes_dir.text() or str(DEFAULT_MEMES_DIR))
        if d:
            self.memes_dir.setText(d)

    def accept(self):
        c = self.cfg
        own = self.own_key.isChecked()
        c["provider"] = self.provider.currentData()
        c["klipy_key"] = self.klipy.text().strip() if own else ""
        c["giphy_key"] = self.giphy.text().strip()
        c["content_filter"] = self.filter.currentData()
        c["copy_quality"] = self.quality.currentData()
        c["copy_mode"] = self.mode.currentData()
        c["auto_hide"] = self.auto_hide.isChecked()
        c["emoji_command"] = self.emoji.text().strip()
        c["save_memes"] = self.save_memes.isChecked()
        c["memes_dir"] = self.memes_dir.text().strip()
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
        self.setObjectName("root")
        # Frameless popup with a frosted (KWin blur) rounded surface, like Win+.
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.frosted = False
        self.frost_timer = QTimer(self, singleShot=True, interval=300)
        self.frost_timer.timeout.connect(self._frost_check)
        self.resize(*GIF_SIZE)

        fid = QFontDatabase.addApplicationFont(str(ASSETS / "Anton-Regular.ttf"))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        meme_font = fams[0] if fams else QFont("DejaVu Sans").family()

        self.gifs = GifPage(cfg, self.net, self.recents)
        self.templates = TemplatePage(self.net, cfg)
        self.meme_from_gif = False   # captions on a GIF frame aren't kept (KLIPY terms)
        self.last_kept = None
        self.editor = MemeEditor(meme_font)
        self.stack = QStackedWidget()
        for w in (self.gifs, self.templates, self.editor):
            self.stack.addWidget(w)

        self.gifs.picked.connect(self.copy_gif)
        self.gifs.copy_link.connect(self.copy_link)
        self.gifs.caption.connect(self.caption_gif)
        self.gifs.need_key.connect(self.open_settings)
        self.templates.open_settings.connect(self.open_settings)
        self.templates.open_image.connect(self.open_editor)
        self.templates.copy_saved.connect(lambda p: self.copy_meme(QImage(p), keep=False))
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
        tabs = QFrame(objectName="tabs")
        tl = QHBoxLayout(tabs)
        tl.setContentsMargins(3, 3, 3, 3)
        tl.setSpacing(2)
        tl.addWidget(self.tab_gif)
        tl.addWidget(self.tab_meme)
        emoji = self._icon_button("face-smile", "😀", "Emoji picker", self.launch_emoji)
        gear = self._icon_button("configure", "⚙", "Settings (Ctrl+,)", self.open_settings)

        bar = QHBoxLayout()
        bar.setSpacing(2)
        bar.addWidget(tabs)
        bar.addStretch()
        bar.addWidget(emoji)
        bar.addWidget(gear)

        # Floating toast over the bottom of the window, fades out on its own.
        self.toast = QLabel(self, objectName="toast", alignment=Qt.AlignmentFlag.AlignCenter)
        self.toast.hide()
        self.toast_fx = QGraphicsOpacityEffect(self.toast)
        self.toast.setGraphicsEffect(self.toast_fx)
        self.toast_anim = QPropertyAnimation(self.toast_fx, b"opacity", self)
        self.toast_anim.setDuration(180)
        self.toast_timer = QTimer(self, singleShot=True, interval=1800)
        self.toast_timer.timeout.connect(lambda: self._fade_toast(False))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(8)
        lay.addLayout(bar)
        lay.addWidget(self.stack, 1)

        QShortcut(QKeySequence("Escape"), self, self.escape)
        QShortcut(QKeySequence("Ctrl+M"), self, lambda: self.show_page("meme"))
        QShortcut(QKeySequence("Ctrl+G"), self, lambda: self.show_page("gif"))
        QShortcut(QKeySequence("Ctrl+,"), self, self.open_settings)

        self.blur_timer = QTimer(self, singleShot=True, interval=200)
        self.blur_timer.timeout.connect(self._blur_check)
        self.show_page("gif")

    def _icon_button(self, icon, fallback, tip, fn):
        b = QToolButton(objectName="iconBtn", autoRaise=True, toolTip=tip)
        ic = QIcon.fromTheme(icon)
        if ic.isNull():
            b.setText(fallback)
        else:
            b.setIcon(ic)
        b.setFixedSize(30, 30)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(fn)
        return b

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
        self.toast.hide()

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

    def flash(self, msg, hide=False, sticky=False):
        self.toast.setText(msg)
        self._place_toast()
        if self.toast.isHidden():
            self._fade_toast(True)
        if sticky:
            self.toast_timer.stop()
        else:
            self.toast_timer.start()
        if hide and self.cfg["auto_hide"]:
            QTimer.singleShot(550, self.hide)

    def _place_toast(self):
        self.toast.setMaximumWidth(self.width() - 40)
        self.toast.adjustSize()
        self.toast.move((self.width() - self.toast.width()) // 2,
                        self.height() - self.toast.height() - 38)
        self.toast.raise_()

    def _fade_toast(self, show):
        self.toast_anim.stop()
        self.toast_anim.setStartValue(self.toast_fx.opacity() if self.toast.isVisible() else 0.0)
        self.toast_anim.setEndValue(1.0 if show else 0.0)
        try:
            self.toast_anim.finished.disconnect()
        except TypeError:
            pass
        if show:
            self.toast.show()
        else:
            self.toast_anim.finished.connect(self.toast.hide)
        self.toast_anim.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self._place_toast()
        if self.isVisible():
            theme.set_blur(self)

    # ---- frosted surface -----------------------------------------------
    def paintEvent(self, e):
        theme.paint_surface(self, self.frosted)

    def showEvent(self, e):
        super().showEvent(e)
        theme.set_blur(self)
        self.frost_timer.start()  # KWin only reports blur support once we're mapped

    def _frost_check(self):
        frosted = theme.blur_possible()
        if frosted != self.frosted:
            self.frosted = frosted
            self.update()

    def mousePressEvent(self, e):
        # No title bar: drag empty space (the header) to move the window.
        if e.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()

    # ---- clipboard -----------------------------------------------------
    def _set_clipboard(self, mime):
        QGuiApplication.clipboard().setMimeData(mime)

    def copy_gif(self, gif):
        if self.cfg["copy_mode"] == "link":
            self.copy_link(gif)
            return
        self.flash("Downloading…", sticky=True)

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

    def caption_gif(self, gif):
        self.flash("Opening first frame in the meme maker…")
        self.net.get(gif.full, lambda d: self.open_editor(QImage.fromData(d), 2, from_gif=True),
                     lambda m: self.flash(f"Download failed: {m}"), store=False)

    def open_editor(self, image, boxes, from_gif=False):
        if image.isNull():
            self.flash("Couldn't open that image.")
            return
        self.meme_from_gif = from_gif
        self.tab_meme.setChecked(True)
        self.stack.setCurrentWidget(self.editor)
        self.resize(*MEME_SIZE)
        self.editor.load(image, boxes)
        self.toast.clear()

    def keep_meme(self, image):
        """Copy into the My memes folder (once per distinct image). Returns the path or None."""
        if not self.cfg["save_memes"] or self.meme_from_gif:
            return None
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        digest = hashlib.sha1(bytes(data)).hexdigest()
        if digest == self.last_kept:
            return None
        folder = self.cfg.memes_dir
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"meme-{time.strftime('%Y%m%d-%H%M%S')}.png"
            path.write_bytes(bytes(data))
        except OSError as e:
            self.flash(f"Couldn't keep a copy: {e.strerror}")
            return None
        self.last_kept = digest
        self.templates.refresh_saved()
        return path

    def copy_meme(self, image, keep=True):
        kept = self.keep_meme(image) if keep else None
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
        self.flash("Meme copied — press Ctrl+V to paste"
                   + (" (kept in My memes)" if kept else ""), hide=True)

    def save_meme(self, image):
        path, _ = QFileDialog.getSaveFileName(self, "Save meme", os.path.expanduser("~/meme.png"),
                                              "PNG (*.png);;JPEG (*.jpg)")
        if path:
            image.save(path)
            self.keep_meme(image)
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
    apply_theme(app)
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
