# PyInstaller spec for the self-contained GifPop bundle (onedir). Run via scripts/build.sh,
# which sets GIFPOP_SRC to a staged copy of the source (with the generated _builtin.py).
#   GIFPOP_SRC=/path/to/src pyinstaller --distpath DIST --workpath WORK packaging/gifpop.spec
import os
import re

from PyInstaller.depend.bindepend import get_imports

src = os.path.abspath(os.environ.get("GIFPOP_SRC") or os.path.join(SPECPATH, ".."))

# PyQt6 modules GifPop doesn't use. PyInstaller only collects what's imported, but listing
# them keeps a stray import (or a hook) from dragging in WebEngine, QML, Multimedia and co.
qt_unused = [
    "Qt3DAnimation", "Qt3DCore", "Qt3DExtras", "Qt3DInput", "Qt3DLogic", "Qt3DRender",
    "QtBluetooth", "QtCharts", "QtDataVisualization", "QtDesigner", "QtGraphs", "QtHelp",
    "QtMultimedia", "QtMultimediaWidgets", "QtNfc", "QtOpenGL", "QtOpenGLWidgets", "QtPdf",
    "QtPdfWidgets", "QtPositioning", "QtPrintSupport", "QtQml", "QtQuick", "QtQuick3D",
    "QtQuickWidgets", "QtRemoteObjects", "QtSensors", "QtSerialPort", "QtSpatialAudio",
    "QtSql", "QtStateMachine", "QtSvgWidgets", "QtTest", "QtTextToSpeech", "QtWebChannel",
    "QtWebEngineCore", "QtWebEngineQuick", "QtWebEngineWidgets", "QtWebSockets", "QtWebView",
    "QtXml", "uic", "lupdate",
]
excludes = [f"PyQt6.{m}" for m in qt_unused] + [
    "tkinter", "_tkinter", "unittest", "pydoc", "doctest", "xmlrpc", "lib2to3", "sqlite3",
    "PySide6", "PySide2", "PyQt5",
]

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[src],
    datas=[(os.path.join(src, "gifpop", "assets"), "gifpop/assets")],
    # keys.py imports the generated key module lazily inside a try; make sure it's frozen in.
    hiddenimports=["gifpop._builtin"] if os.path.exists(os.path.join(src, "gifpop", "_builtin.py")) else [],
    excludes=excludes,
    runtime_hooks=[os.path.join(SPECPATH, "rthook_env.py")],
    noarchive=False,
)

# Plugins / data the PyQt6 hooks collect that GifPop never loads. Kept: platforms wayland,
# xcb, offscreen, minimal; wayland shell / decoration / graphics integration; xcb GL
# integration; imageformats gif, webp, jpeg, png (built in), svg, ico; iconengines (svg);
# tls (OpenSSL); platformthemes xdg-desktop-portal; input contexts (ibus, compose);
# networkinformation (NetworkManager). Dropped: the gtk3 platform theme (it alone pulls in
# ~100 MB of GTK/ICU/glib libraries), eglfs/vnc/linuxfb, Qt translations.
drop = re.compile(
    r"PyQt6/Qt6/("
    r"translations/"
    r"|plugins/platforms/lib(qeglfs|qlinuxfb|qminimalegl|qvnc|qvkkhrdisplay)\.so"
    r"|plugins/platformthemes/libqgtk3\.so"
    r"|plugins/networkinformation/lib(qglib|qconnman)\.so"
    r"|plugins/egldeviceintegrations/"
    r"|plugins/generic/"
    r"|plugins/imageformats/lib(qpdf|qicns|qtga|qtiff|qwbmp)\.so"
    r")"
)


def dest(entry):
    return entry[0].replace(os.sep, "/")


binaries = [e for e in a.binaries if not drop.search(dest(e))]
a.datas = [e for e in a.datas if not drop.search(dest(e))]

# Dropping plugins leaves the libraries only they needed (GTK, glib, a second ICU, QtPdf...).
# Keep a shared library only if something we still ship links to it (ldd is transitive).
# Qt's TLS plugin dlopen()s OpenSSL, so libssl/libcrypto stay regardless.
def is_root(e):
    d = dest(e)
    return e[2] == "EXTENSION" or "/plugins/" in d or os.path.basename(d).startswith("libpython")


needed = set()
for e in binaries:
    if is_root(e) and e[2] != "SYMLINK":
        needed.update(os.path.basename(name) for name, _ in get_imports(e[1]))
always = re.compile(r"lib(ssl|crypto)\.so")
a.binaries = [e for e in binaries
              if is_root(e) or os.path.basename(dest(e)) in needed or always.match(os.path.basename(dest(e)))]

# Base desktop libraries every target system has in a newer version than the build host
# (ubuntu-22.04). Bundling the old copies does harm: an old libstdc++ stops newer Mesa GL
# drivers from loading, an old fontconfig chokes on newer fonts.conf, and glib/dbus/systemd
# get loaded alongside the system's copies by other system libraries. Use the system's.
system_libs = re.compile(
    r"lib(stdc\+\+|gcc_s|fontconfig|freetype|glib-2\.0|gobject-2\.0|gio-2\.0|gmodule-2\.0"
    r"|gthread-2\.0|dbus-1|systemd)\.so"
)
a.binaries = [e for e in a.binaries
              if "/" in dest(e) or not system_libs.match(os.path.basename(dest(e)))]
# PyInstaller also lists top-level symlinks to the Qt libraries; drop the ones left dangling.
kept = {os.path.basename(dest(e)) for e in a.binaries if e[2] != "SYMLINK"}
a.binaries = [e for e in a.binaries if e[2] != "SYMLINK" or os.path.basename(dest(e)) in kept]
a.datas = [e for e in a.datas if e[2] != "SYMLINK" or os.path.basename(dest(e)) in kept]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gifpop",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,  # mostly libpython's debug symbols; the Qt wheels ship stripped already
    upx=False,
    name="app",
)
