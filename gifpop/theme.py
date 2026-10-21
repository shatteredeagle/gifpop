"""GifPop's look: palette-driven QSS (dark and light) and a frosted window background.

The blur comes from one of two places:
- libgifpopblur.so next to this file (the release bundle ships it in _internal/gifpop/):
  a small helper built against the bundled Qt that speaks KWin's blur protocol on Wayland.
- Otherwise (source installs on the system Qt), KDE's KWindowEffects from
  libKF6WindowSystem, called through ctypes. Never inside the frozen bundle: that library
  would drag the system Qt into a process already running the bundled one.
If neither works (not KDE, not Wayland, missing library) the window is drawn near-opaque."""
import ctypes
import sys
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QRegion

from .config import TILING_WM

RADIUS = 12

_HELPER_PATH = Path(__file__).with_name("libgifpopblur.so")
_helper = None      # gifpop_blur() once loaded, False if it can't be
_granted = False    # the helper's last blur request on a shown window succeeded

_blur = _avail = None
if not getattr(sys, "frozen", False) and not _HELPER_PATH.exists():
    try:
        _kws = ctypes.CDLL("libKF6WindowSystem.so.6")
        _blur = _kws["_ZN14KWindowEffects16enableBlurBehindEP7QWindowbRK7QRegion"]
        _blur.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_void_p]
        _blur.restype = None
        _avail = _kws["_ZN14KWindowEffects17isEffectAvailableENS_6EffectE"]
        _avail.argtypes = [ctypes.c_int]
        _avail.restype = ctypes.c_bool
    except (OSError, AttributeError, TypeError):
        _blur = _avail = None


def _load_helper():
    """The helper's gifpop_blur(), loaded on first use, or None.

    Only on the Wayland platform (it speaks Wayland protocols). Its Qt6Gui/Core deps resolve
    to the copies already loaded in the process (the bundled Qt), never the system's."""
    global _helper
    if _helper is None:
        _helper = False
        if _HELPER_PATH.exists() and QGuiApplication.platformName().startswith("wayland"):
            try:
                fn = ctypes.CDLL(str(_HELPER_PATH))["gifpop_blur"]
                fn.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
                fn.restype = ctypes.c_int
                _helper = fn
            except (OSError, AttributeError, TypeError):
                pass
    return _helper or None


def is_dark():
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme != Qt.ColorScheme.Unknown:
        return scheme == Qt.ColorScheme.Dark
    return QGuiApplication.palette().window().color().lightness() < 128


def blur_possible():
    """True once the compositor has granted/advertised blur (False before first show).
    Hyprland blurs translucent windows by itself (decoration:blur), no request needed."""
    if TILING_WM == "hyprland":
        return True
    if _HELPER_PATH.exists():
        return _granted
    try:
        return bool(_avail and _avail(7))
    except Exception:
        return False


def set_blur(widget, on=True, radius=RADIUS):
    """Ask KWin to blur behind `widget` (must be shown; call again after a resize).

    Helper: returns its result (1 blur requested, 0 unsupported, -1 error).
    KWindowEffects: True if the request was sent. Never raises."""
    global _granted
    try:
        win = widget.windowHandle()
        if win is None:
            return False
        if _HELPER_PATH.exists():
            fn = _load_helper()
            if fn is None:
                return 0
            result = fn(sip.unwrapinstance(win), 1 if on else 0, int(radius))
            if on:
                _granted = result == 1
            return result
        if not _blur:
            return False
        path = QPainterPath()
        path.addRoundedRect(QRectF(widget.rect()), radius, radius)
        region = QRegion(path.toFillPolygon().toPolygon())
        _blur(sip.unwrapinstance(win), on, sip.unwrapinstance(region))
        return True
    except Exception:
        return False


def surface_color(widget, blurred):
    # NOT widget.palette(): a QSS "background" rule rewrites that to transparent
    c = QColor(QGuiApplication.palette().window().color())
    if blurred:
        c.setAlphaF(0.62 if is_dark() else 0.74)
    else:
        c.setAlphaF(0.97)  # no blur: translucent text-over-desktop is unreadable
    return c


def paint_surface(widget, blurred, radius=RADIUS):
    """Call from paintEvent of the top-level (WA_TranslucentBackground) widget."""
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.fillPath(path, surface_color(widget, blurred))
    p.setPen(QColor(255, 255, 255, 28) if is_dark() else QColor(0, 0, 0, 40))
    p.drawPath(path)


def _chevron(dark):
    """QSS can't take inline images, so the dropdown arrow is written to the cache dir."""
    from .config import CACHE_DIR
    path = CACHE_DIR / f"chevron-{'dark' if dark else 'light'}.svg"
    if not path.exists():
        colour = "#d0d0d4" if dark else "#505055"
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6">'
                        f'<path d="M1 1l4 4 4-4" fill="none" stroke="{colour}" '
                        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return path.as_posix()


def style():
    """Build QSS. Call again on colorSchemeChanged / paletteChanged."""
    dark = is_dark()
    chevron = _chevron(dark)
    # rgba overlays on top of the frosted surface; accent comes from palette(highlight)
    fill = "rgba(255,255,255,0.06)" if dark else "rgba(0,0,0,0.045)"
    fill_hover = "rgba(255,255,255,0.11)" if dark else "rgba(0,0,0,0.08)"
    fill_press = "rgba(255,255,255,0.16)" if dark else "rgba(0,0,0,0.12)"
    stroke = "rgba(255,255,255,0.10)" if dark else "rgba(0,0,0,0.12)"
    field = "rgba(0,0,0,0.28)" if dark else "rgba(255,255,255,0.75)"
    handle = "rgba(255,255,255,0.22)" if dark else "rgba(0,0,0,0.25)"
    handle_hover = "rgba(255,255,255,0.38)" if dark else "rgba(0,0,0,0.42)"
    toast_bg = "rgba(20,20,22,0.92)" if dark else "rgba(250,250,252,0.96)"
    return f"""
* {{ font-size: 10pt; }}
QWidget#root, QStackedWidget, QScrollArea, #qt_scrollarea_viewport, #gridHost,
#qt_scrollarea_vcontainer, #qt_scrollarea_hcontainer,
QScrollArea > QWidget > QWidget, MasonryHost, #emptyState
    {{ background: transparent; border: none; }}

/* header tabs: pill segmented control */
QFrame#tabs, QWidget#segmented {{ background: {fill}; border: 1px solid {stroke}; border-radius: 10px; }}
QPushButton#segment {{ padding: 4px 12px; border: none; border-radius: 7px;
    background: transparent; color: palette(text); }}
QPushButton#segment:hover {{ background: {fill_hover}; }}
QPushButton#segment:checked {{ background: {fill_press}; color: palette(text); font-weight: 600; border-bottom: 2px solid palette(highlight); }}
QToolButton#iconBtn, QToolButton#tileAction, QToolButton#danger, QToolButton#swatchCustom {{
    border: none; border-radius: 8px; background: transparent; padding: 3px; }}
QToolButton#iconBtn:hover, QToolButton#tileAction:hover, QToolButton#swatchCustom:hover
    {{ background: {fill_hover}; }}
QToolButton#danger:hover {{ background: rgba(229,57,53,0.25); }}
QWidget#tileActions {{ background: {toast_bg}; border-radius: 8px; }}
QToolButton#swatch {{ border: 2px solid {stroke}; border-radius: 12px; padding: 0; }}
QToolButton#swatch:checked {{ border: 2px solid palette(highlight); }}
QLabel#sectionTitle {{ font-weight: 600; color: palette(placeholder-text); font-size: 8.5pt;
    padding-top: 8px; }}
QLabel#hint {{ color: palette(placeholder-text); font-size: 8.5pt; }}
#emptyState QLabel {{ color: palette(placeholder-text); }}
QLineEdit#search {{ min-height: 22px; padding: 6px 12px; }}
QCheckBox {{ spacing: 8px; }}
QSlider::groove:horizontal {{ height: 4px; background: {fill_press}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: palette(highlight); border-radius: 2px; }}
QSlider::handle:horizontal {{ background: palette(highlight); width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{ background: palette(window); border: 1px solid {stroke};
    border-radius: 8px; selection-background-color: palette(highlight); }}
QDialog {{ background: palette(window); }}
QPushButton#tab {{ padding: 5px 14px; border: none; border-radius: 8px;
    background: transparent; color: palette(text); font-weight: 600; }}
QPushButton#tab:hover {{ background: {fill_hover}; }}
QPushButton#tab:checked {{ background: {fill_press}; color: palette(text); border-bottom: 2px solid palette(highlight); }}

/* icon buttons (emoji / gear / back) */
QPushButton[flat="true"] {{ border: none; border-radius: 8px; padding: 4px 8px;
    background: transparent; min-width: 22px; min-height: 22px; }}
QPushButton[flat="true"]:hover {{ background: {fill_hover}; }}
QPushButton[flat="true"]:pressed {{ background: {fill_press}; }}

/* generic buttons */
QPushButton {{ background: {fill}; border: 1px solid {stroke}; border-radius: 8px;
    padding: 5px 12px; color: palette(text); }}
QPushButton:hover {{ background: {fill_hover}; }}
QPushButton:pressed {{ background: {fill_press}; }}
QPushButton:focus {{ border: 1px solid palette(highlight); }}
QPushButton#primary {{ background: palette(highlight); color: palette(highlighted-text);
    border: none; padding: 6px 20px; font-weight: 600; }}
QPushButton#primary:hover {{ background: palette(highlight); border: 1px solid {stroke}; }}

/* category chips */
QPushButton#chip {{ padding: 3px 11px; border-radius: 13px; min-height: 20px;
    background: {fill}; border: 1px solid {stroke}; }}
QPushButton#chip:hover {{ background: {fill_hover}; }}
QPushButton#chip[active="true"] {{ background: palette(highlight);
    color: palette(highlighted-text); border-color: transparent; }}

/* search / text fields */
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {field}; border: 1px solid {stroke}; border-radius: 10px;
    padding: 6px 10px; selection-background-color: palette(highlight); }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid palette(highlight); }}

/* tiles: rounded, outline-on-hover (no fill flash over the GIF) */
#tile {{ background: {fill}; border: 2px solid transparent; border-radius: 10px; }}
#tile:hover {{ border: 2px solid palette(highlight); background: {fill_hover}; }}
#caption, #status, #attrib {{ color: palette(placeholder-text); font-size: 8.5pt; }}

/* toast: floating pill */
QLabel#toast {{ background: {toast_bg}; color: palette(text); border: 1px solid {stroke};
    border-radius: 14px; padding: 6px 14px; font-weight: 600; }}

/* overlay scrollbars */
QAbstractScrollArea::corner {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; border: none; width: 10px; margin: 4px 2px 4px 0; }}
QScrollBar::handle:vertical {{ background: {handle}; border-radius: 3px; min-height: 32px;
    margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {handle_hover}; margin: 0; border-radius: 4px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; border: none; height: 10px; margin: 0 4px 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {handle}; border-radius: 3px; min-width: 32px;
    margin: 2px 0; }}

QToolTip {{ background: palette(window); color: palette(text); border: 1px solid {stroke};
    border-radius: 6px; padding: 4px 8px; }}
QMenu {{ background: palette(window); border: 1px solid {stroke}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 5px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: palette(highlight); color: palette(highlighted-text); }}

#canvas {{ background: rgba(0,0,0,0.55); border-radius: 10px; }}
"""
