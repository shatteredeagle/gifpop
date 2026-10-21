"""Meme maker: blank-template browser (imgflip + your own folder) and a text editor."""
import json
import time

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath,
                         QPen, QPixmap)
from PyQt6.QtWidgets import (QCheckBox, QColorDialog, QFileDialog, QFormLayout,
                             QGraphicsItem, QGraphicsObject, QGraphicsScene, QGraphicsView,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                             QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from .config import CACHE_DIR, TEMPLATES_DIR

IMGFLIP = "https://api.imgflip.com/get_memes"
TEMPLATE_CACHE = CACHE_DIR / "imgflip.json"
COLUMNS = 3
THUMB = QSize(140, 120)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


# ---------------------------------------------------------------- browser
class TemplateTile(QWidget):
    clicked = pyqtSignal(object)

    def __init__(self, tpl, net):
        super().__init__()
        self.tpl = tpl
        self.setFixedSize(THUMB.width(), THUMB.height() + 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tpl["name"])
        self.img = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.img.setObjectName("tile")
        self.img.setFixedSize(THUMB)
        name = QLabel(tpl["name"])
        name.setObjectName("caption")
        name.setFixedWidth(THUMB.width())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.img)
        lay.addWidget(name)
        if tpl.get("path"):
            self._show(QPixmap(tpl["path"]))
            self.reply = None
        else:
            self.reply = net.get(tpl["url"], self._loaded)

    def _loaded(self, data):
        self.reply = None
        pm = QPixmap()
        pm.loadFromData(data)
        self._show(pm)

    def _show(self, pm):
        if not pm.isNull():
            self.img.setPixmap(pm.scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))

    def abort(self):
        if self.reply:
            self.reply.abort()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.tpl)


class TemplatePage(QWidget):
    open_image = pyqtSignal(object, int)  # QImage, suggested box count

    def __init__(self, net):
        super().__init__()
        self.net = net
        self.templates = []
        self.tiles = []
        self.filter = QLineEdit(placeholderText="Filter templates")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._populate)
        own = QPushButton("Open image…")
        own.setToolTip(f"Use any image. Files in {TEMPLATES_DIR} show up here too.")
        own.clicked.connect(self._open_file)
        top = QHBoxLayout()
        top.addWidget(self.filter, 1)
        top.addWidget(own)

        host = QWidget()
        self.grid = QGridLayout(host)
        self.grid.setSpacing(6)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setWidget(host)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.status = QLabel(objectName="status")
        attrib = QLabel("Templates from imgflip", objectName="attrib")
        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)
        bottom.addWidget(attrib)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self.scroll, 1)
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
        self.status.setText("")
        self._populate()

    def _populate(self):
        for t in self.tiles:
            t.abort()
            t.deleteLater()
        self.tiles = []
        f = self.filter.text().strip().lower()
        for tpl in self.templates:
            if f and f not in tpl["name"].lower():
                continue
            t = TemplateTile(tpl, self.net)
            t.clicked.connect(self._pick)
            n = len(self.tiles)
            self.grid.addWidget(t, n // COLUMNS, n % COLUMNS)
            self.tiles.append(t)

    def _pick(self, tpl):
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

        # side panel
        self.edit = QPlainTextEdit(placeholderText="Type caption…")
        self.edit.setFixedHeight(80)
        self.edit.textChanged.connect(lambda: self._apply(text=self.edit.toPlainText()))
        self.size_sl = QSlider(Qt.Orientation.Horizontal, minimum=8, maximum=300)
        self.size_sl.valueChanged.connect(lambda v: self._apply(size=v))
        self.width_sl = QSlider(Qt.Orientation.Horizontal, minimum=10, maximum=100)
        self.width_sl.valueChanged.connect(
            lambda v: self._apply(box_w=self.image.width() * v / 100))
        self.caps = QCheckBox("ALL CAPS")
        self.caps.toggled.connect(lambda v: self._apply(caps=v))
        self.outline = QCheckBox("Outline")
        self.outline.toggled.connect(lambda v: self._apply(outline=v))
        self.fill_btn = QPushButton("Text colour")
        self.fill_btn.clicked.connect(lambda: self._pick_color("fill"))
        self.stroke_btn = QPushButton("Outline colour")
        self.stroke_btn.clicked.connect(lambda: self._pick_color("stroke"))
        self.del_btn = QPushButton("Remove box")
        self.del_btn.clicked.connect(self._delete)

        props = QWidget()
        form = QFormLayout(props)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow(self.edit)
        form.addRow("Size", self.size_sl)
        form.addRow("Width", self.width_sl)
        row = QHBoxLayout()
        row.addWidget(self.caps)
        row.addWidget(self.outline)
        form.addRow(row)
        form.addRow(self.fill_btn)
        form.addRow(self.stroke_btn)
        form.addRow(self.del_btn)
        self.props = props

        add = QPushButton("+ Add text")
        add.clicked.connect(lambda: self._add_box("free"))
        hint = QLabel("Click a caption to edit it. Drag to move.", objectName="status")
        hint.setWordWrap(True)
        side = QVBoxLayout()
        side.addWidget(add)
        side.addWidget(props)
        side.addStretch()
        side.addWidget(hint)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setFixedWidth(230)

        back = QPushButton("← Templates")
        back.clicked.connect(self.back)
        save = QPushButton("Save…")
        save.clicked.connect(lambda: self.save_image.emit(self.render()))
        copy = QPushButton("Copy")
        copy.setObjectName("primary")
        copy.setDefault(True)
        copy.clicked.connect(lambda: self.copy_image.emit(self.render()))
        actions = QHBoxLayout()
        actions.addWidget(back)
        actions.addStretch()
        actions.addWidget(save)
        actions.addWidget(copy)

        body = QHBoxLayout()
        body.addWidget(self.view, 1)
        body.addWidget(side_w)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(body, 1)
        lay.addLayout(actions)

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
            self.edit.setFocus()
        return item

    def _selection(self):
        sel = [i for i in self.scene.selectedItems() if isinstance(i, MemeText)]
        self.cur = sel[0] if sel else None
        self.props.setEnabled(bool(self.cur))
        if not self.cur:
            return
        c = self.cur
        for wdg, val in ((self.size_sl, int(c.size)),
                         (self.width_sl, round(100 * c.box_w / max(1, self.image.width()))),
                         (self.caps, c.caps), (self.outline, c.outline)):
            wdg.blockSignals(True)
            wdg.setValue(val) if isinstance(wdg, QSlider) else wdg.setChecked(val)
            wdg.blockSignals(False)
        self.edit.blockSignals(True)
        self.edit.setPlainText(c.text)
        self.edit.blockSignals(False)
        self.size_sl.setMaximum(max(300, int(self.image.height() / 2)))

    def _apply(self, **kw):
        if self.cur:
            self.cur.set(**kw)

    def _pick_color(self, attr):
        if not self.cur:
            return
        col = QColorDialog.getColor(getattr(self.cur, attr), self, "Pick colour")
        if col.isValid():
            self._apply(**{attr: col})

    def _delete(self):
        if self.cur:
            self.items.remove(self.cur)
            self.scene.removeItem(self.cur)
            self.cur = None
            self.props.setEnabled(False)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete and self.cur and not self.edit.hasFocus():
            self._delete()
        else:
            super().keyPressEvent(e)

    def render(self):
        was = self.cur
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
        return out
