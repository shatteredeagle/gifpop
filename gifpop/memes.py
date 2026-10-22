"""Meme maker: blank-template browser (imgflip + your own folder) and a text editor."""
import json
import shutil
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QFontMetricsF, QIcon, QImage, QKeySequence,
                         QPainter, QPainterPath, QPen, QPixmap, QShortcut)
from PyQt6.QtWidgets import (QBoxLayout, QButtonGroup, QCheckBox, QColorDialog, QFileDialog,
                             QFormLayout, QGraphicsItem, QGraphicsObject, QGraphicsScene,
                             QGraphicsView, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QPlainTextEdit, QPushButton, QScrollArea, QSlider, QStackedWidget,
                             QToolButton, QVBoxLayout, QWidget)

from .config import CACHE_DIR, TEMPLATES_DIR

IMGFLIP = "https://api.imgflip.com/get_memes"
TEMPLATE_CACHE = CACHE_DIR / "imgflip.json"
THUMB = QSize(140, 120)
SPACING = 6
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
TRASH = Path(tempfile.gettempdir()) / "gifpop-trash"
SWATCHES = ["white", "black", "#ffd400", "#e53935"]
SIDE_W = 200
NARROW = 640


def themed(btn, name, fallback):
    """Theme icon when there is one (offscreen/odd themes may lack it), else fallback text."""
    icon = QIcon.fromTheme(name)
    if icon.isNull():
        btn.setText(fallback)
    else:
        btn.setIcon(icon)
    return btn


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


def shortcut(widget, keys, fn):
    for k in keys if isinstance(keys, (list, tuple)) else [keys]:
        QShortcut(QKeySequence(k), widget, fn, context=Qt.ShortcutContext.WidgetWithChildrenShortcut)


# ---------------------------------------------------------------- browser
class TemplateTile(QWidget):
    clicked = pyqtSignal(object)
    menu = pyqtSignal(object, object)  # tpl, global pos
    action = pyqtSignal(str, object)   # "copy" / "edit" / "delete", tpl

    def __init__(self, tpl, net):
        super().__init__()
        self.tpl = tpl
        self.setFixedSize(THUMB.width(), THUMB.height() + 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tpl["name"])
        self.img = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.img.setObjectName("tile")
        self.img.setFixedSize(THUMB)
        name = QLabel(objectName="caption")
        name.setFixedWidth(THUMB.width())
        name.setText(name.fontMetrics().elidedText(tpl["name"], Qt.TextElideMode.ElideRight,
                                                   THUMB.width()))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.img)
        lay.addWidget(name)
        self.actions = None
        if tpl.get("saved"):
            self.actions = QWidget(self, objectName="tileActions")
            row = QHBoxLayout(self.actions)
            row.setContentsMargins(2, 2, 2, 2)
            row.setSpacing(2)
            for key, icon, fb, tip in (("copy", "edit-copy", "⧉", "Copy"),
                                       ("edit", "document-edit", "✎", "Add more captions"),
                                       ("delete", "edit-delete", "✕", "Delete")):
                b = themed(QToolButton(objectName="tileAction", toolTip=tip), icon, fb)
                b.setFixedSize(24, 24)
                b.setCursor(Qt.CursorShape.ArrowCursor)
                b.clicked.connect(lambda _=False, k=key: self.action.emit(k, self.tpl))
                row.addWidget(b)
            self.actions.adjustSize()
            self.actions.move(THUMB.width() - self.actions.width() - 2, 2)
            self.actions.hide()
        self.net = net
        self.reply = None
        self.loaded = False

    def showEvent(self, e):
        # Load on first show, so filtering down to a few tiles only fetches those.
        if not self.loaded:
            self.loaded = True
            if self.tpl.get("path"):
                self._show(QPixmap(self.tpl["path"]))
            else:
                self.reply = self.net.get(self.tpl["url"], self._loaded, self._failed)
        super().showEvent(e)

    def _loaded(self, data):
        self.reply = None
        pm = QPixmap()
        pm.loadFromData(data)
        self._show(pm)

    def _failed(self, _msg):
        self.reply = None  # net deletes the reply; don't abort() it later

    def _show(self, pm):
        if not pm.isNull():
            self.img.setPixmap(pm.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))

    def abort(self):
        if self.reply:
            try:
                self.reply.abort()
            except RuntimeError:
                pass  # already finished and deleted
            self.reply = None

    def _hover(self, on):
        self.img.setProperty("hover", on)
        repolish(self.img)
        if self.actions:
            self.actions.setVisible(on)
            self.actions.raise_()

    def enterEvent(self, e):
        self._hover(True)

    def leaveEvent(self, e):
        self._hover(False)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.tpl)
        elif e.button() == Qt.MouseButton.RightButton:
            self.menu.emit(self.tpl, e.globalPosition().toPoint())


class Segment(QPushButton):
    """Segmented-control button. In an exclusive group setChecked(False) is a no-op,
    so unchecking one checks its partner instead."""
    partner = None

    def setChecked(self, on):
        if not on and self.partner and self.isChecked():
            self.partner.setChecked(True)
        else:
            super().setChecked(on)


class TemplatePage(QWidget):
    open_image = pyqtSignal(object, int)  # QImage, suggested box count
    copy_saved = pyqtSignal(str)          # path of a meme you made earlier
    open_settings = pyqtSignal()          # empty My memes with saving off

    def __init__(self, net, cfg):
        super().__init__()
        self.net = net
        self.cfg = cfg
        self.templates = []
        self.tiles = []
        self.shown = []  # tiles matching the filter, in grid order
        self.cols = 3
        self.filters = {False: "", True: ""}
        self.undo = None  # (trash path, original path)
        self.undo_timer = QTimer(self, singleShot=True, interval=5000)
        self.undo_timer.timeout.connect(self._drop_undo)

        seg = QWidget(objectName="segmented")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(0, 0, 0, 0)
        seg_lay.setSpacing(0)
        self.seg_tpl = Segment("Templates", checkable=True, checked=True, objectName="segment")
        self.mine = Segment("My memes", checkable=True, objectName="segment")
        self.mine.setToolTip("Memes you made. Click to copy, right-click for more.")
        self.seg_tpl.partner, self.mine.partner = self.mine, self.seg_tpl
        group = QButtonGroup(self, exclusive=True)
        for b, pos in ((self.seg_tpl, "first"), (self.mine, "last")):
            b.setProperty("pos", pos)
            group.addButton(b)
            seg_lay.addWidget(b)
        self.mine.toggled.connect(self._toggle_mine)

        self.filter = QLineEdit(placeholderText="Filter templates")
        self.filter.setClearButtonEnabled(True)
        self.filter_timer = QTimer(self, singleShot=True, interval=120)
        self.filter_timer.timeout.connect(self._apply_filter)
        self.filter.textChanged.connect(lambda _: self.filter_timer.start())
        self.filter.returnPressed.connect(self._enter)
        own = themed(QToolButton(objectName="iconBtn"), "document-open", "Open…")
        own.setToolTip(f"Open any image. Files in {TEMPLATES_DIR} show up here too.")
        own.clicked.connect(self._open_file)
        top = QHBoxLayout()
        top.addWidget(seg)
        top.addWidget(self.filter, 1)
        top.addWidget(own)
        shortcut(self, QKeySequence.StandardKey.Find,
                 lambda: (self.filter.setFocus(), self.filter.selectAll()))

        host = QWidget()
        self.grid = QGridLayout(host)
        self.grid.setSpacing(SPACING)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setWidget(host)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().installEventFilter(self)

        self.empty = QWidget(objectName="emptyState")
        icon = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(QIcon.fromTheme("folder-pictures").pixmap(48))
        self.empty_text = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self.empty_btn = QPushButton()
        self.empty_btn.clicked.connect(lambda: self.seg_tpl.setChecked(True) if self.cfg["save_memes"]
                                       else self.open_settings.emit())
        e_lay = QVBoxLayout(self.empty)
        e_lay.addStretch()
        e_lay.addWidget(icon)
        e_lay.addWidget(self.empty_text)
        e_lay.addWidget(self.empty_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        e_lay.addStretch()
        self.body = QStackedWidget()
        self.body.addWidget(self.scroll)
        self.body.addWidget(self.empty)

        self.status = QLabel(objectName="status")
        self.status.linkActivated.connect(self._undo_delete)
        attrib = self.attrib = QLabel("Templates from imgflip", objectName="attrib")
        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(attrib)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self.body, 1)
        lay.addLayout(bottom)

    def ensure_loaded(self):
        if self.templates:
            return
        try:
            if time.time() - TEMPLATE_CACHE.stat().st_mtime < 86400:
                self._set(json.loads(TEMPLATE_CACHE.read_text()))
                return
        except (OSError, ValueError):
            pass
        self.status.setText("Loading templates…")
        self.net.get(IMGFLIP, self._got, self._err, prefer_cache=False)

    def _got(self, raw):
        try:
            memes = json.loads(raw)["data"]["memes"]
        except (ValueError, KeyError) as e:
            self._err(str(e))
            return
        TEMPLATE_CACHE.write_text(json.dumps(memes))
        self._set(memes)

    def _err(self, msg):
        self.status.setText(f"Couldn't load templates: {msg}")
        try:
            self._set(json.loads(TEMPLATE_CACHE.read_text()))  # stale beats nothing
        except (OSError, ValueError):
            self._set([])

    def _set(self, memes):
        local = [{"name": p.stem.replace("_", " "), "path": str(p), "box_count": 2}
                 for p in sorted(TEMPLATES_DIR.iterdir()) if p.suffix.lower() in IMAGE_EXT]
        self.templates = local + memes
        if not self.undo:
            self.status.setText("")
        self._populate()

    def saved_memes(self):
        try:
            files = [p for p in self.cfg.memes_dir.iterdir() if p.suffix.lower() in IMAGE_EXT]
        except OSError:
            return []
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"name": p.stem, "path": str(p), "saved": True, "box_count": 2} for p in files]

    def _toggle_mine(self, on):
        self.filters[not on] = self.filter.text()  # each mode keeps its own filter
        self.filter.blockSignals(True)
        self.filter.setText(self.filters[on])
        self.filter.blockSignals(False)
        self.filter.setPlaceholderText("Filter my memes" if on else "Filter templates")
        self.attrib.setText("My memes" if on else "Templates from imgflip")
        self.attrib.setToolTip(str(self.cfg.memes_dir) if on else "")
        self._populate()

    def refresh_saved(self):
        if self.mine.isChecked():
            self._populate()

    def _enter(self):
        self._apply_filter()
        if self.shown:
            self._pick(self.shown[0].tpl)

    def _populate(self):
        """Rebuild the tiles for the current mode. Typing only re-filters them (_apply_filter)."""
        self.filter_timer.stop()
        for t in self.tiles:
            t.abort()
            t.hide()  # out of the layout now, not whenever deleteLater gets to it
            self.grid.removeWidget(t)
            t.deleteLater()
        self.tiles = []
        self.shown = []
        mine = self.mine.isChecked()
        items = self.saved_memes() if mine else self.templates
        if mine and not items:
            on = self.cfg["save_memes"]
            self.empty_text.setText("Memes you copy show up here" if on else
                                    "Saving memes is off, so nothing lands here")
            self.empty_btn.setText("Browse templates" if on else "Turn on in Settings")
        self.body.setCurrentWidget(self.empty if mine and not items else self.scroll)
        for tpl in items:
            t = TemplateTile(tpl, self.net)
            t.hide()
            t.clicked.connect(self._pick)
            t.menu.connect(self._menu)
            t.action.connect(self._action)
            self.tiles.append(t)
        self._apply_filter()

    def _apply_filter(self):
        f = self.filter.text().strip().lower()
        for t in self.shown:
            self.grid.removeWidget(t)
        self.shown = [t for t in self.tiles if not f or f in t.tpl["name"].lower()]
        keep = set(map(id, self.shown))
        for t in self.tiles:
            if id(t) not in keep:
                t.hide()
        self._layout_tiles()
        for t in self.shown:
            t.show()
        self.scroll.verticalScrollBar().setValue(0)

    def _layout_tiles(self):
        for i, t in enumerate(self.shown):
            self.grid.addWidget(t, i // self.cols, i % self.cols)
    def eventFilter(self, obj, e):
        # The viewport's resize, not ours: it's the width tiles actually get (minus scrollbar).
        if obj is self.scroll.viewport() and e.type() == QEvent.Type.Resize:
            self._reflow(e.size().width())
        return super().eventFilter(obj, e)

    def _reflow(self, w):
        cols = max(2, (w + SPACING) // (THUMB.width() + SPACING))
        if cols != self.cols:
            self.cols = cols
            for t in self.shown:
                self.grid.removeWidget(t)
            self._layout_tiles()

    def _action(self, key, tpl):
        path = tpl["path"]
        if key == "copy":
            self.copy_saved.emit(path)
        elif key == "edit":
            self.open_image.emit(QImage(path), 1)
        elif key == "delete":
            self._delete(path)

    def _menu(self, tpl, pos):
        if not tpl.get("saved"):
            return
        m = QMenu(self)
        m.addAction("Copy", lambda: self._action("copy", tpl))
        m.addAction("Add more captions", lambda: self._action("edit", tpl))
        m.addAction("Open folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(Path(tpl["path"]).parent))))
        m.addSeparator()
        m.addAction("Delete", lambda: self._action("delete", tpl))
        m.exec(pos)

    def _delete(self, path):
        """Move to a temp trash so the 5 s Undo link can bring it back."""
        self._drop_undo()
        dest = TRASH / f"{time.time_ns()}-{Path(path).name}"
        try:
            TRASH.mkdir(exist_ok=True)
            shutil.move(path, dest)
        except OSError as e:
            self.status.setText(f"Couldn't delete: {e}")
            return
        self.undo = (dest, path)
        self.status.setText(f'Deleted {Path(path).stem}. <a href="undo">Undo</a>')
        self.undo_timer.start()
        self._populate()

    def _undo_delete(self):
        if self.undo:
            dest, path = self.undo
            self.undo = None
            self.undo_timer.stop()
            try:
                shutil.move(dest, path)
            except OSError as e:
                self.status.setText(f"Couldn't restore: {e}")
                return
            self.status.setText("")
            self._populate()

    def _drop_undo(self):
        self.undo_timer.stop()
        if self.undo:
            self.undo[0].unlink(missing_ok=True)
            self.undo = None
            self.status.setText("")

    def _pick(self, tpl):
        if tpl.get("saved"):
            self.copy_saved.emit(tpl["path"])
            return
        boxes = tpl.get("box_count", 2)
        if tpl.get("path"):
            self.open_image.emit(QImage(tpl["path"]), boxes)
            return
        self.status.setText(f"Opening {tpl['name']}…")

        def ok(data):
            self.status.setText("")
            self.open_image.emit(QImage.fromData(data), boxes)
        self.net.get(tpl["url"], ok, lambda m: self.status.setText(f"Download failed: {m}"))

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image", "", "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)")
        if path:
            self.open_image.emit(QImage(path), 2)


# ----------------------------------------------------------------- editor
class MemeText(QGraphicsObject):
    """Classic outlined meme caption. pos() is the top-centre of the text box;
    'bottom' boxes grow upward so bottom text stays on the image."""
    changed = pyqtSignal()

    def __init__(self, family, img_w, img_h, anchor="top", placeholder="TEXT"):
        super().__init__()
        self.family = family
        self.text = ""
        self.placeholder = placeholder
        self.anchor = anchor
        self.size = max(16, round(img_h / 10))
        self.box_w = img_w * 0.94
        self.fill = QColor("white")
        self.stroke = QColor("black")
        self.outline = True
        self.caps = True
        self.exporting = False
        self._path = QPainterPath()
        self._h = 0
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._relayout()

    def font(self):
        f = QFont(self.family)
        f.setPixelSize(int(self.size))
        return f

    def shown_text(self):
        t = self.text or ("" if self.exporting else self.placeholder)
        return t.upper() if self.caps else t

    def _wrap(self, fm, text):
        lines = []
        for para in text.split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = f"{cur} {word}" if cur else word
                if cur and fm.horizontalAdvance(trial) > self.box_w:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
        return lines

    def _relayout(self):
        self.prepareGeometryChange()
        bottom = self.pos().y() + self._h
        font = self.font()
        fm = QFontMetricsF(font)
        path = QPainterPath()
        y = fm.ascent()
        lines = self._wrap(fm, self.shown_text())
        for line in lines:
            path.addText(QPointF(-fm.horizontalAdvance(line) / 2, y), font, line)
            y += fm.lineSpacing() * 0.92
        self._path = path
        old_h, self._h = self._h, max(fm.height(), fm.lineSpacing() * 0.92 * len(lines) + fm.descent() * 0.3)
        if self.anchor == "bottom" and old_h:
            self.setY(bottom - self._h)
        self.update()
        self.changed.emit()

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self._relayout()

    def set_exporting(self, on):
        self.exporting = on
        self._relayout()

    def boundingRect(self):
        pad = self.size * 0.1 + 4
        return QRectF(-self.box_w / 2 - pad, -pad, self.box_w + 2 * pad, self._h + 2 * pad)

    def paint(self, p, option, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        faint = not self.text and not self.exporting
        if self.outline:
            pen = QPen(QColor(self.stroke) if not faint else QColor(0, 0, 0, 90),
                       max(2.0, self.size * 0.12))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.strokePath(self._path, pen)
        fill = QColor(self.fill)
        if faint:
            fill.setAlpha(110)
        p.fillPath(self._path, fill)
        if not self.exporting and (self.isSelected() or faint):
            pen = QPen(QColor("#4da3ff") if self.isSelected() else QColor(255, 255, 255, 120),
                       0, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(QRectF(-self.box_w / 2, 0, self.box_w, self._h))


class MemeView(QGraphicsView):
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


def swatch_icon(color):
    """Square filled with the colour; None draws the 'no outline' slash."""
    pm = QPixmap(16, 16)
    pm.fill(QColor(color) if color else Qt.GlobalColor.white)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(0, 0, 0, 90), 1))
    p.drawRect(QRectF(0.5, 0.5, 15, 15))
    if not color:
        p.setPen(QPen(QColor("#e53935"), 2))
        p.drawLine(2, 14, 14, 2)
    p.end()
    return QIcon(pm)


class SwatchRow(QWidget):
    """Preset colour swatches + '…' for a custom colour. Emits QColor, or None for 'none'."""
    picked = pyqtSignal(object)

    def __init__(self, none=False):
        super().__init__()
        self.value = QColor("white")
        self.group = QButtonGroup(self, exclusive=True)
        self.buttons = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        for c in ([None] if none else []) + SWATCHES:
            b = self._button(swatch_icon(c), "No outline" if c is None else QColor(c).name())
            b.clicked.connect(lambda _=False, c=c: self._emit(QColor(c) if c else None))
            self.buttons[QColor(c).name() if c else None] = b
            lay.addWidget(b)
        self.custom = self._button(None, "Custom colour…")
        self.custom.setText("…")
        self.custom.clicked.connect(self._choose)
        lay.addWidget(self.custom)
        lay.addStretch()

    def _button(self, icon, tip):
        b = QToolButton(objectName="swatch", checkable=True, toolTip=tip)
        b.setFixedSize(22, 22)
        if icon:
            b.setIcon(icon)
        self.group.addButton(b)
        return b

    def _emit(self, color):
        self.set_value(color)
        self.picked.emit(color)

    def _choose(self):
        col = QColorDialog.getColor(self.value or QColor("white"), self, "Pick colour")
        if col.isValid():
            self._emit(col)
        else:
            self.set_value(self.value)

    def set_value(self, color):
        self.value = QColor(color) if color else None
        key = self.value.name() if self.value else None
        b = self.buttons.get(key, self.custom)
        b.setChecked(True)
        self.custom.setIcon(swatch_icon(self.value) if b is self.custom else QIcon())
        self.custom.setText("" if b is self.custom else "…")


def section(title, extra=None):
    row = QHBoxLayout()
    row.setContentsMargins(0, 6, 0, 0)
    row.addWidget(QLabel(title, objectName="sectionTitle"))
    row.addStretch()
    if extra:
        row.addWidget(extra)
    return row


class MemeEditor(QWidget):
    back = pyqtSignal()
    copy_image = pyqtSignal(object)   # QImage
    save_image = pyqtSignal(object)

    def __init__(self, family):
        super().__init__()
        self.family = family
        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._selection)
        self.view = MemeView(self.scene)
        self.view.setRenderHints(QPainter.RenderHint.Antialiasing
                                 | QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setObjectName("canvas")
        self.image = QImage()
        self.items = []
        self.cur = None
        self.rendering = False

        # side panel
        self.edit = QPlainTextEdit(placeholderText="Type caption…")
        self.edit.setFixedHeight(64)
        self.edit.textChanged.connect(lambda: self._apply(text=self.edit.toPlainText()))
        self.edit.installEventFilter(self)
        self.size_sl = QSlider(Qt.Orientation.Horizontal, minimum=8, maximum=300)
        self.size_sl.valueChanged.connect(lambda v: self._apply(size=v))
        self.width_sl = QSlider(Qt.Orientation.Horizontal, minimum=10, maximum=100)
        self.width_sl.valueChanged.connect(
            lambda v: self._apply(box_w=self.image.width() * v / 100))
        self.caps = QCheckBox("ALL CAPS")
        self.caps.toggled.connect(lambda v: self._apply(caps=v))
        self.fill_row = SwatchRow()
        self.fill_row.picked.connect(lambda c: self._apply(fill=c))
        self.stroke_row = SwatchRow(none=True)
        self.stroke_row.picked.connect(
            lambda c: self._apply(outline=False) if c is None else self._apply(outline=True, stroke=c))
        remove = themed(QToolButton(objectName="danger", autoRaise=True), "edit-delete", "Remove")
        remove.setToolTip("Remove this caption")
        remove.clicked.connect(self._delete)

        props = QWidget()
        col = QVBoxLayout(props)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        col.addLayout(section("Text", remove))
        col.addWidget(self.edit)
        col.addWidget(self.caps)
        col.addLayout(section("Size"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Size", self.size_sl)
        form.addRow("Width", self.width_sl)
        col.addLayout(form)
        col.addLayout(section("Colour"))
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)  # swatches need the width
        form.addRow("Fill", self.fill_row)
        form.addRow("Outline", self.stroke_row)
        col.addLayout(form)
        col.addStretch()
        hint = QLabel("Click a caption or + Add text\n\nDrag captions to move them.",
                      objectName="status", alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self.props = QStackedWidget()
        self.props.addWidget(hint)
        self.props.addWidget(props)

        add = QPushButton("+ Add text", objectName="addText")
        add.clicked.connect(lambda: self._add_box("free"))
        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(add)
        side.addWidget(self.props, 1)
        self.side = QWidget()
        self.side.setLayout(side)
        self.side.setFixedWidth(SIDE_W)

        back = QPushButton("← Templates", toolTip="Back to templates (Esc)")
        back.clicked.connect(self.back)
        save = QPushButton("Save…", toolTip="Save to a file (Ctrl+S)")
        save.clicked.connect(self._save)
        copy = QPushButton("Copy", objectName="primary", toolTip="Copy to clipboard (Ctrl+↵)")
        copy.setDefault(True)
        copy.clicked.connect(self._copy)
        actions = QHBoxLayout()
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(save)
        actions.addWidget(copy)
        shortcut(self, ["Ctrl+Return", "Ctrl+Enter"], self._copy)
        shortcut(self, QKeySequence.StandardKey.Copy, self._copy)
        shortcut(self, QKeySequence.StandardKey.Save, self._save)

        self.body = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.body.addWidget(self.view, 1)
        self.body.addWidget(self.side)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self.body, 1)
        lay.addLayout(actions)

    def _copy(self):
        self.copy_image.emit(self.render())

    def _save(self):
        self.save_image.emit(self.render())

    def eventFilter(self, obj, e):
        # Ctrl+C in the caption box copies the meme unless there's text selected to copy.
        if (obj is self.edit and e.type() == QEvent.Type.ShortcutOverride
                and e.matches(QKeySequence.StandardKey.Copy)
                and not self.edit.textCursor().hasSelection()):
            e.ignore()
            return True
        return super().eventFilter(obj, e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < NARROW
        self.body.setDirection(QBoxLayout.Direction.TopToBottom if narrow
                               else QBoxLayout.Direction.LeftToRight)
        if narrow:
            self.side.setMinimumWidth(0)
            self.side.setMaximumWidth(16777215)
        else:
            self.side.setFixedWidth(SIDE_W)

    def load(self, image, boxes=2):
        self.scene.clear()
        self.items = []
        self.image = image.convertToFormat(QImage.Format.Format_ARGB32)
        w, h = self.image.width(), self.image.height()
        self.scene.addPixmap(QPixmap.fromImage(self.image)).setZValue(-1)
        self.scene.setSceneRect(0, 0, w, h)
        boxes = max(2, min(boxes, 5))
        for i in range(boxes):
            if i == 0:
                self._add_box("top", "TOP TEXT")
            elif i == boxes - 1:
                self._add_box("bottom", "BOTTOM TEXT")
            else:
                self._add_box("free", f"TEXT {i + 1}", y=h * i / (boxes - 1))
        self.items[0].setSelected(True)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.edit.setFocus()

    def _add_box(self, where, placeholder="TEXT", y=None):
        w, h = self.image.width(), self.image.height()
        if not w:
            return
        item = MemeText(self.family, w, h, anchor="bottom" if where == "bottom" else "top",
                        placeholder=placeholder)
        margin = h * 0.02
        if where == "top":
            item.setPos(w / 2, margin)
        elif where == "bottom":
            item.setPos(w / 2, h - margin - item._h)
        else:
            item.setPos(w / 2, y if y is not None else h / 2 - item._h / 2)
        self.scene.addItem(item)
        self.items.append(item)
        if where == "free" and y is None:
            self.scene.clearSelection()
            item.setSelected(True)
        return item

    def _selection(self):
        if self.rendering:
            return
        sel = [i for i in self.scene.selectedItems() if isinstance(i, MemeText)]
        self.cur = sel[0] if sel else None
        self.props.setCurrentIndex(1 if self.cur else 0)
        if not self.cur:
            return
        c = self.cur
        self.size_sl.setMaximum(max(300, int(self.image.height() / 2)))
        for wdg, val in ((self.size_sl, int(c.size)),
                         (self.width_sl, round(100 * c.box_w / max(1, self.image.width()))),
                         (self.caps, c.caps)):
            wdg.blockSignals(True)
            wdg.setValue(val) if isinstance(wdg, QSlider) else wdg.setChecked(val)
            wdg.blockSignals(False)
        self.fill_row.set_value(c.fill)
        self.stroke_row.set_value(c.stroke if c.outline else None)
        self.edit.blockSignals(True)
        self.edit.setPlainText(c.text)
        self.edit.blockSignals(False)
        self.edit.setFocus()
        self.edit.selectAll()  # typing replaces the caption

    def _apply(self, **kw):
        if self.cur:
            self.cur.set(**kw)

    def _delete(self):
        if self.cur:
            self.items.remove(self.cur)
            self.scene.removeItem(self.cur)
            self.cur = None
            self.props.setCurrentIndex(0)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete and self.cur and not self.edit.hasFocus():
            self._delete()
        else:
            super().keyPressEvent(e)

    def render(self):
        was = self.cur
        self.rendering = True
        self.scene.clearSelection()
        for i in self.items:
            i.set_exporting(True)
        out = QImage(self.image.size(), QImage.Format.Format_ARGB32)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHints(QPainter.RenderHint.Antialiasing
                         | QPainter.RenderHint.SmoothPixmapTransform
                         | QPainter.RenderHint.TextAntialiasing)
        r = QRectF(out.rect())
        self.scene.render(p, r, r)
        p.end()
        for i in self.items:
            i.set_exporting(False)
        if was in self.items:
            was.setSelected(True)
        self.rendering = False
        return out
