"""GIF tab: search box, quick chips, animated grid with infinite scroll."""
from PyQt6.QtCore import QBuffer, QByteArray, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .keys import redact
from .providers import Gif, make_provider

COLUMNS = 3
TILE = QSize(140, 110)
CHIPS = ["lol", "yes", "no", "thank you", "wow", "facepalm", "love", "sad"]


class GifTile(QLabel):
    clicked = pyqtSignal(object)
    menu = pyqtSignal(object, object)

    def __init__(self, gif, net):
        super().__init__()
        self.gif = gif
        self.movie = self.buf = None
        self.setFixedSize(TILE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
            self.setText("?")
            return
        self.movie.jumpToFrame(0)
        sz = self.movie.currentImage().size()
        if not sz.isEmpty():
            self.movie.setScaledSize(sz.scaled(TILE, Qt.AspectRatioMode.KeepAspectRatio))
        self.setMovie(self.movie)
        self.movie.start()

    def abort(self):
        if self.reply:
            self.reply.abort()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.gif)
        elif e.button() == Qt.MouseButton.RightButton:
            self.menu.emit(self.gif, e.globalPosition().toPoint())


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

        self.search = QLineEdit(placeholderText=f"Search {self.provider.name}")
        self.search.setClearButtonEnabled(True)
        self.debounce = QTimer(self, singleShot=True, interval=350)
        self.debounce.timeout.connect(self._run_search)
        self.search.textChanged.connect(lambda _: self.debounce.start())
        self.search.returnPressed.connect(self._enter)

        chips = QHBoxLayout()
        chips.setSpacing(4)
        self.btn_recent = self._chip("Recent", lambda: self.show_mode("recent"))
        self.btn_trend = self._chip("Trending", lambda: self.show_mode("trending"))
        chips.addWidget(self.btn_recent)
        chips.addWidget(self.btn_trend)
        for c in CHIPS[:5]:
            chips.addWidget(self._chip(c, lambda _=False, c=c: self.search.setText(c)))
        chips.addStretch()

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(6)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setWidget(self.grid_host)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_more)

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
        lay.addLayout(chips)
        lay.addWidget(self.scroll, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.attrib)
        lay.addLayout(bottom)

    def _chip(self, text, fn):
        b = QPushButton(text)
        b.setObjectName("chip")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(fn)
        return b

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
        self.btn_recent.setProperty("active", mode == "recent")
        self.btn_trend.setProperty("active", mode == "trending")
        for b in (self.btn_recent, self.btn_trend):
            b.style().unpolish(b)
            b.style().polish(b)
        if mode == "recent":
            self._clear()
            self._add([Gif(**g) for g in self.recents.items])
            self.has_next = False
            self.status.setText("" if self.recents.items else "No recent GIFs yet. Search for one.")
        else:
            self._fetch(reset=True)

    def _run_search(self):
        q = self.search.text().strip()
        if not q:
            self.show_mode(self.mode)
            return
        self.query = q
        self._fetch(reset=True)

    def _enter(self):
        # Enter copies the first result, like picking it with the keyboard.
        self.debounce.stop()
        if self.search.text().strip() != self.query:
            self._run_search()
        elif self.tiles:
            self.picked.emit(self.tiles[0].gif)

    def _fetch(self, reset):
        self.attrib.setText(f"Powered by {self.provider.name}")
        self.search.setPlaceholderText(f"Search {self.provider.name}")  # KLIPY requires this
        if not self.cfg.api_key:
            self._clear()
            self.status.setText(
                f'Add a free {self.provider.name} API key in Settings (⚙) to search. '
                f'Get one at <a href="{self.provider.signup}">{self.provider.signup}</a>.')
            self.need_key.emit()
            return
        if self.loading:
            self.loading.abort()
        if reset:
            self.page = 1
            self._clear()
        self.status.setText("Loading…")
        query = self.query if self.mode != "recent" or self.query else ""
        url = self.provider.url(query, self.page)
        self.loading = self.net.get(url, self._got, self._err, prefer_cache=False)

    def _got(self, raw):
        self.loading = None
        try:
            gifs, self.has_next = self.provider.parse(raw)
        except (ValueError, KeyError, TypeError) as e:
            self.status.setText(f"Couldn't read results: {e}")
            return
        self._add(gifs)
        self.status.setText("" if self.tiles else "No results.")

    def report_share(self, gif):
        if (self.mode == "recent" and not self.query) or not self.cfg.api_key:
            return
        ping = self.provider.share(gif, self.query)
        if ping:
            self.net.post_json(*ping)

    def _err(self, msg):
        self.loading = None
        msg = redact(msg, self.cfg["klipy_key"], self.cfg["giphy_key"])
        hint = " Check the API key in Settings." if any(c in msg for c in ("401", "403")) else ""
        self.status.setText(f"Search failed: {msg}.{hint}")

    def _maybe_more(self, value):
        bar = self.scroll.verticalScrollBar()
        if self.has_next and not self.loading and value > bar.maximum() - 300:
            self.page += 1
            self._fetch(reset=False)

    # ---- grid ------------------------------------------------------------
    def _clear(self):
        for t in self.tiles:
            t.abort()
            t.deleteLater()
        self.tiles = []
        self.scroll.verticalScrollBar().setValue(0)

    def _add(self, gifs):
        for g in gifs:
            if not g.preview or not g.full:
                continue
            t = GifTile(g, self.net)
            t.clicked.connect(self.picked)
            t.menu.connect(self._menu)
            n = len(self.tiles)
            self.grid.addWidget(t, n // COLUMNS, n % COLUMNS)
            self.tiles.append(t)

    def _menu(self, gif, pos):
        m = QMenu(self)
        m.addAction("Copy GIF", lambda: self.picked.emit(gif))
        m.addAction("Copy link", lambda: self.copy_link.emit(gif))
        m.addAction("Caption in meme maker", lambda: self.caption.emit(gif))
        m.exec(pos)
