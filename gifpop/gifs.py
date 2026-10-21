"""GIF tab: search box, quick chips, animated masonry grid with infinite scroll."""
from PyQt6.QtCore import QBuffer, QByteArray, QEvent, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QMovie, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
                             QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from .keys import redact
from .providers import Gif, make_provider

COLUMNS = 3
GAP = 6
RADIUS = 8
CHIPS = ["lol", "yes", "no", "thank you", "wow", "facepalm", "love", "sad",
         "happy dance", "shrug", "mind blown", "applause"]
SKELETON = [0.75, 1.1, 0.6, 1.0, 0.7, 1.25, 0.9, 0.65, 1.05]   # height/width of loading tiles
PRELOAD = 200   # px beyond the viewport where GIFs keep playing


def placeholder_color(w):
    c = QColor(w.palette().color(QPalette.ColorRole.Mid))
    c.setAlpha(70)
    return c


def rounded(rect):
    p = QPainterPath()
    p.addRoundedRect(QRectF(rect), RADIUS, RADIUS)
    return p


class Skeleton(QWidget):
    ratio = 1.0

    def __init__(self, ratio):
        super().__init__()
        self.ratio = ratio

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillPath(rounded(self.rect()), placeholder_color(self))


class GifTile(QWidget):
    clicked = pyqtSignal(object)
    menu = pyqtSignal(object, object)

    def __init__(self, gif, net):
        super().__init__()
        self.gif = gif
        self.movie = self.buf = None
        self.hover = self.pressed = self.selected = self.bad = False
        self.active = True
        self.ratio = max(0.5, min(2.0, gif.h / gif.w)) if gif.w and gif.h else 1.0
        self.setObjectName("tile")
        self.setToolTip(gif.title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reply = net.get(gif.preview, self._loaded)

    def _loaded(self, data):
        self.reply = None
        self.buf = QBuffer(self)
        self.buf.setData(QByteArray(data))
        self.buf.open(QBuffer.OpenModeFlag.ReadOnly)
        self.movie = QMovie(self.buf, QByteArray(), self)
        if not self.movie.isValid():
            self.movie, self.bad = None, True
            self.update()
            return
        self.movie.jumpToFrame(0)
        self.src = self.movie.currentImage().size()
        self._scale()
        self.movie.frameChanged.connect(self.update)
        self.movie.start()
        self.movie.setPaused(not self.active)

    def _scale(self):
        if self.movie and not self.src.isEmpty():
            self.movie.setScaledSize(self.src.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding))

    def set_active(self, on):
        if on != self.active:
            self.active = on
            if self.movie:
                self.movie.setPaused(not on)

    def set_selected(self, on):
        self.selected = on
        self.update()

    def abort(self):
        if self.reply:
            self.reply.abort()

    def resizeEvent(self, e):
        self._scale()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.rect()
        path = rounded(r)
        p.fillPath(path, placeholder_color(self))
        p.setClipPath(path)
        pix = self.movie.currentPixmap() if self.movie else None
        if pix and not pix.isNull():
            p.drawPixmap((r.width() - pix.width()) // 2, (r.height() - pix.height()) // 2, pix)
        elif self.bad:
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "?")
        if self.pressed:
            p.fillRect(r, QColor(0, 0, 0, 80))
        p.setClipping(False)
        if self.selected or self.hover:
            w = 3 if self.selected else 2
            p.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), w))
            p.drawPath(rounded(QRectF(r).adjusted(w / 2, w / 2, -w / 2, -w / 2)))

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = self.pressed = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.pressed = True
            self.update()

    def mouseReleaseEvent(self, e):
        was, self.pressed = self.pressed, False
        self.update()
        if e.button() == Qt.MouseButton.LeftButton and was and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.gif)
        elif e.button() == Qt.MouseButton.RightButton:
            self.menu.emit(self.gif, e.globalPosition().toPoint())


class MasonryHost(QWidget):
    """Absolute-positioned columns; each new item goes into the shortest column (API order kept)."""

    def __init__(self):
        super().__init__()
        self.items = []
        self.cols = [[] for _ in range(COLUMNS)]
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def add(self, w):
        w.setParent(self)
        self.items.append(w)
        w.show()

    def remove(self, w):
        self.items.remove(w)

    def relayout(self):
        colw = max(1, (self.width() - (COLUMNS - 1) * GAP) // COLUMNS)
        tops = [0] * COLUMNS
        self.cols = [[] for _ in range(COLUMNS)]
        for w in self.items:
            c = tops.index(min(tops))
            h = round(colw * w.ratio)
            w.setGeometry(c * (colw + GAP), tops[c], colw, h)
            w.col = c
            self.cols[c].append(w)
            tops[c] += h + GAP
        self.setMinimumHeight(max(0, max(tops) - GAP))

    def resizeEvent(self, e):
        if e.size().width() != e.oldSize().width():
            self.relayout()


class GifPage(QWidget):
    picked = pyqtSignal(object)        # Gif -> copy as file
    copy_link = pyqtSignal(object)
    caption = pyqtSignal(object)       # Gif -> open in meme editor (first frame)
    need_key = pyqtSignal()

    def __init__(self, cfg, net, recents):
        super().__init__()
        self.cfg, self.net, self.recents = cfg, net, recents
        self.provider = make_provider(cfg)
        self.query = ""
        self.mode = "recent" if recents.items else "trending"
        self.page = 1
        self.has_next = False
        self.loading = None
        self.tiles = []
        self.skeletons = []
        self.sel = None

        self.search = QLineEdit(placeholderText=f"Search {self.provider.name}")
        self.search.setObjectName("search")
        self.search.setMinimumHeight(34)
        self.search.setClearButtonEnabled(True)
        self.search.installEventFilter(self)
        self.debounce = QTimer(self, singleShot=True, interval=350)
        self.debounce.timeout.connect(self._run_search)
        self.search.textChanged.connect(lambda _: self.debounce.start())
        self.search.returnPressed.connect(self._enter)

        chip_host = QWidget()
        chips = QHBoxLayout(chip_host)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(4)
        self.btn_recent = self._chip("Recent", lambda: self.show_mode("recent"))
        self.btn_trend = self._chip("Trending", lambda: self.show_mode("trending"))
        chips.addWidget(self.btn_recent)
        chips.addWidget(self.btn_trend)
        for c in CHIPS:
            chips.addWidget(self._chip(c, lambda _=False, c=c: self.search.setText(c)))
        chips.addStretch()
        self.chip_strip = QScrollArea(widgetResizable=True)
        self.chip_strip.setObjectName("chipStrip")
        self.chip_strip.setFrameShape(QFrame.Shape.NoFrame)
        self.chip_strip.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chip_strip.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chip_strip.setWidget(chip_host)
        self.chip_strip.setFixedHeight(chip_host.sizeHint().height())
        self.chip_strip.viewport().installEventFilter(self)

        self.host = MasonryHost()
        self.host.installEventFilter(self)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setObjectName("gridScroll")
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidget(self.host)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_more)
        self.scroll.verticalScrollBar().valueChanged.connect(self._update_playing)

        self.empty = QWidget()
        self.empty.setObjectName("emptyState")
        self.empty_icon = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.empty_text = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self.empty_text.setOpenExternalLinks(True)
        self.empty_btn = QPushButton()
        self._empty_action = lambda: None
        self.empty_btn.clicked.connect(lambda: self._empty_action())
        el = QVBoxLayout(self.empty)
        el.addStretch()
        el.addWidget(self.empty_icon)
        el.addWidget(self.empty_text)
        el.addWidget(self.empty_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        el.addStretch(2)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.scroll)
        self.stack.addWidget(self.empty)

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status.setOpenExternalLinks(True)
        self.attrib = QLabel()
        self.attrib.setObjectName("attrib")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.search)
        lay.addWidget(self.chip_strip)
        lay.addWidget(self.stack, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.attrib, 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(bottom)

    def _chip(self, text, fn):
        b = QPushButton(text)
        b.setObjectName("chip")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    def _set_chips(self, mode):
        for b, m in ((self.btn_recent, "recent"), (self.btn_trend, "trending")):
            b.setProperty("active", mode == m)
            b.style().unpolish(b)
            b.style().polish(b)

    # ---- states ----------------------------------------------------------
    def _message(self, icons, text, button=None, action=None):
        icon = next((QIcon.fromTheme(i) for i in icons if QIcon.hasThemeIcon(i)), QIcon())
        if not icon.isNull():
            self.empty_icon.setPixmap(icon.pixmap(64, 64))
        self.empty_icon.setVisible(not icon.isNull())
        self.empty_text.setText(text)
        self.empty_btn.setText(button or "")
        self.empty_btn.setVisible(bool(button))
        self._empty_action = action or (lambda: None)
        self.stack.setCurrentWidget(self.empty)

    def _show_grid(self):
        self.stack.setCurrentWidget(self.scroll)

    # ---- data flow -------------------------------------------------------
    def reload_provider(self):
        self.provider = make_provider(self.cfg)
        self.refresh()

    def refresh(self):
        if self.query:
            self._run_search()
        else:
            self.show_mode(self.mode)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def show_mode(self, mode):
        self.mode = mode
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self.query = ""
        self._set_chips(mode)
        if mode == "recent":
            self._clear()
            self.status.clear()
            self._add([Gif(**g) for g in self.recents.items])
            self.has_next = False
            if self.recents.items:
                self._show_grid()
            else:
                self._message(["document-open-recent", "clock"], "No recent GIFs yet.",
                              "Show trending", lambda: self.show_mode("trending"))
        else:
            self._fetch(reset=True)

    def _run_search(self):
        q = self.search.text().strip()
        if not q:
            self.show_mode(self.mode)
            return
        self.query = q
        self._set_chips(None)
        self._fetch(reset=True)

    def _enter(self):
        # Enter copies the selected (or first) result, like picking it with the keyboard.
        self.debounce.stop()
        if self.search.text().strip() != self.query:
            self._run_search()
        elif self.tiles:
            self.picked.emit((self.sel or self.tiles[0]).gif)

    def _fetch(self, reset):
        self.attrib.setText(f"Powered by {self.provider.name}")
        self.search.setPlaceholderText(f"Search {self.provider.name}")  # KLIPY requires this
        if not self.cfg.api_key:
            self._clear()
            self.status.clear()
            self._message(["dialog-password", "security-high", "preferences-system"],
                          f"Add a free {self.provider.name} API key to search.<br>Get one at "
                          f'<a href="{self.provider.signup}">{self.provider.signup}</a>.',
                          "Open Settings", self.need_key.emit)
            return
        if self.loading:
            self.loading.abort()
        if reset:
            self.page = 1
            self._clear()
            self._skeletons()
            self._show_grid()
        self.status.setText("" if reset else "Loading more…")
        query = self.query if self.mode != "recent" or self.query else ""
        url = self.provider.url(query, self.page)
        self.loading = self.net.get(url, self._got, self._err, prefer_cache=False)

    def _got(self, raw):
        self.loading = None
        self._drop_skeletons()
        try:
            gifs, self.has_next = self.provider.parse(raw)
        except (ValueError, KeyError, TypeError) as e:
            self._fail(f"Couldn't read results: {e}")
            return
        self._add(gifs)
        self.status.clear()
        if self.tiles:
            self._show_grid()
        else:
            what = f"No GIFs for “{self.query}”." if self.query else "Nothing here right now."
            self._message(["edit-find", "system-search"], what)

    def report_share(self, gif):
        if (self.mode == "recent" and not self.query) or not self.cfg.api_key:
            return
        ping = self.provider.share(gif, self.query)
        if ping:
            self.net.post_json(*ping)

    def _err(self, msg):
        self.loading = None
        self._drop_skeletons()
        msg = redact(msg, self.cfg["klipy_key"], self.cfg["giphy_key"])
        if "429" in msg:
            shared = self.cfg["provider"] == "klipy" and not self.cfg["klipy_key"]
            self.status.setText(
                "GifPop's shared KLIPY key hit its hourly limit. Try again in a bit, or add "
                f'your own free key in Settings (⚙): <a href="{self.provider.signup}">'
                f"{self.provider.signup}</a>." if shared else
                f"{self.provider.name} says too many searches. Try again in a bit.")
            if not self.tiles:
                self._message(["dialog-warning"], "Too many searches right now.", "Retry", self.refresh)
            return
        hint = " Check the API key in Settings." if any(c in msg for c in ("401", "403")) else ""
        self._fail(f"Search failed: {msg}.{hint}")

    def _fail(self, text):
        if self.tiles:
            self.status.setText(text)
        else:
            self.status.clear()
            self._message(["network-error", "dialog-error", "dialog-warning"], text, "Retry", self.refresh)

    def _maybe_more(self, value):
        bar = self.scroll.verticalScrollBar()
        if self.has_next and not self.loading and value > bar.maximum() - 300:
            self.page += 1
            self._fetch(reset=False)

    # ---- grid ------------------------------------------------------------
    def _clear(self):
        self._select(None)
        self._drop_skeletons()
        for t in self.tiles:
            t.abort()
            self.host.remove(t)
            t.deleteLater()
        self.tiles = []
        self.host.relayout()
        self.scroll.verticalScrollBar().setValue(0)

    def _skeletons(self):
        for r in SKELETON:
            s = Skeleton(r)
            self.host.add(s)
            self.skeletons.append(s)
        self.host.relayout()

    def _drop_skeletons(self):
        for s in self.skeletons:
            self.host.remove(s)
            s.deleteLater()
        self.skeletons = []

    def _add(self, gifs):
        for g in gifs:
            if not g.preview or not g.full:
                continue
            t = GifTile(g, self.net)
            t.clicked.connect(self.picked)
            t.menu.connect(self._menu)
            self.host.add(t)
            self.tiles.append(t)
        self.host.relayout()
        QTimer.singleShot(0, self._update_playing)

    def _update_playing(self, *_):
        top = self.scroll.verticalScrollBar().value() - PRELOAD
        view = QRect(0, top, self.host.width(), self.scroll.viewport().height() + 2 * PRELOAD)
        shown = self.isVisible()
        for t in self.tiles:
            t.set_active(shown and t.geometry().intersects(view))

    def hideEvent(self, e):
        for t in self.tiles:
            t.set_active(False)

    def showEvent(self, e):
        QTimer.singleShot(0, self._update_playing)

    def _menu(self, gif, pos):
        m = QMenu(self)
        m.addAction("Copy GIF", lambda: self.picked.emit(gif))
        m.addAction("Copy link", lambda: self.copy_link.emit(gif))
        m.addAction("Caption in meme maker", lambda: self.caption.emit(gif))
        m.exec(pos)

    # ---- keyboard --------------------------------------------------------
    def _select(self, t):
        if self.sel:
            self.sel.set_selected(False)
        self.sel = t
        if t:
            t.set_selected(True)
            self.host.setFocus()
            self.scroll.ensureWidgetVisible(t, 0, GAP)

    def _move(self, key):
        t, cols = self.sel, self.host.cols
        col = cols[t.col]
        i = col.index(t)
        if key == Qt.Key.Key_Up:
            if i == 0:
                self._select(None)
                self.focus_search()
                return
            self._select(col[i - 1])
        elif key == Qt.Key.Key_Down:
            if i + 1 < len(col):
                self._select(col[i + 1])
        else:
            c = t.col + (1 if key == Qt.Key.Key_Right else -1)
            if 0 <= c < len(cols) and cols[c]:
                cy = t.geometry().center().y()
                self._select(min(cols[c], key=lambda o: abs(o.geometry().center().y() - cy)))

    def eventFilter(self, obj, e):
        et = e.type()
        if obj is self.chip_strip.viewport() and et == QEvent.Type.Wheel:
            d = e.angleDelta()
            bar = self.chip_strip.horizontalScrollBar()
            bar.setValue(bar.value() - (d.y() or d.x()))
            return True
        if et != QEvent.Type.KeyPress:
            return super().eventFilter(obj, e)
        k = e.key()
        if obj is self.search:
            if k in (Qt.Key.Key_Down, Qt.Key.Key_Tab) and self.tiles and self.stack.currentWidget() is self.scroll:
                self._select(self.tiles[0])
                return True
        elif obj is self.host:
            if not self.sel:
                if k in (Qt.Key.Key_Down, Qt.Key.Key_Tab) and self.tiles:
                    self._select(self.tiles[0])
                    return True
                return False
            if k in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
                self._move(k)
                return True
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.picked.emit(self.sel.gif)
                return True
            if k == Qt.Key.Key_Menu:
                self._menu(self.sel.gif, self.sel.mapToGlobal(self.sel.rect().center()))
                return True
            if e.text().isprintable() and e.text().strip():
                self._select(None)
                self.search.setFocus()
                self.search.insert(e.text())
                return True
        return super().eventFilter(obj, e)
