# libgifpopblur

A small native helper that asks the Wayland compositor to blur whatever is
behind a GifPop window (the frosted-glass look on KDE Plasma).

The release bundle ships its own Qt (PyQt6-Qt6, pinned in
`packaging/requirements-build.txt`). The system `libKF6WindowSystem` is built
against the system Qt and will not load next to an older bundled Qt, so GifPop
ships this helper instead, compiled against the same Qt version as the bundle.

## API

```c
extern "C" int gifpop_blur(void *qwindow, int enable, int radius);
```

- `qwindow`: a `QWindow*` (`sip.unwrapinstance(widget.windowHandle())`). The
  window must be shown, so that its `wl_surface` exists.
- `enable=1` requests blur behind the whole window as a rounded rectangle
  (logical pixels, corner radius `radius`, clamped to 0..32). Call it again
  after a resize: the region is recomputed from `window->size()`.
- `enable=0` removes the blur.
- Returns `1` when blur was requested or removed, `0` when it is not supported
  (not Wayland, or the compositor has neither protocol), and `-1` on error
  (null window, or no surface yet).

Blur state is double-buffered on `wl_surface.commit`; the helper calls
`QWindow::requestUpdate()` so Qt's next frame commits it.

## How it works

- Gets the `wl_display` from `QNativeInterface::QWaylandApplication` and the
  `wl_surface` from `QNativeInterface::Private::QWaylandWindow` (QtGui private
  header `qpa/qplatformwindow_p.h`; no QtWaylandClient private headers needed).
- Binds `wl_compositor` and the blur global once per process, on a private
  `wl_event_queue` through a display wrapper, so Qt's own queue is never
  dispatched.
- Protocols, in order of preference:
  1. `ext_background_effect_manager_v1` (wayland-protocols, staging), used when
     the compositor advertises the `blur` capability.
  2. `org_kde_kwin_blur_manager` (plasma-wayland-protocols).
  `GIFPOP_BLUR_PROTOCOL=kde` forces the second one (testing aid).
- Keeps one blur object per `QWindow` and destroys it when blur is disabled,
  when the `QWindow` is destroyed, or when Qt destroys the window's surface
  (hide); the next call after show creates a new one.
- The region is a rounded rect: a full-height middle band plus one 1px-high
  strip per row in the corner bands.

The private Qt API is version-locked. Rebuild the helper whenever the
PyQt6-Qt6 pin changes. Python must load it after PyQt6 (the bundle's Qt
libraries are already loaded, so the library has no rpath).

## Build

```sh
packaging/blurhelper/build.sh <QT_PREFIX> <OUT_SO>
# e.g.
packaging/blurhelper/build.sh ~/qt/6.11.2/gcc_64 build/libgifpopblur.so
```

`QT_PREFIX` is an aqtinstall Qt install of the same version as the PyQt6-Qt6
pin. Only the base install is needed (QtCore/QtGui headers, including
`include/<Module>/<version>/<Module>/private`):

```sh
pip install aqtinstall
aqt install-qt linux desktop 6.11.2 linux_gcc_64 -O "$HOME/qt"
```

Build dependencies (Ubuntu 22.04):

```sh
sudo apt-get install -y g++ pkg-config libwayland-dev libwayland-bin
```

`libwayland-bin` provides `wayland-scanner`, which generates the protocol
code from `protocols/*.xml` at build time.

## Test

`test_blur.py` opens a translucent frameless window for about 2 seconds and
exercises enable, resize + re-enable, and disable. Run it with the build
venv's Python (bundled Qt, not the system Qt):

```sh
WAYLAND_DEBUG=client python packaging/blurhelper/test_blur.py build/libgifpopblur.so 2>&1 \
  | grep -E 'background_effect|kwin_blur|set_blur_region|set_region|commit|^TEST'
QT_QPA_PLATFORM=offscreen python packaging/blurhelper/test_blur.py build/libgifpopblur.so  # expect 0s
```

## Licenses of vendored protocol files

- `protocols/ext-background-effect-v1.xml`: from
  [wayland-protocols](https://gitlab.freedesktop.org/wayland/wayland-protocols)
  (`staging/ext-background-effect/`). MIT (Expat) license; copyright Martin
  Gräßlin, Marco Martin, Vlad Zahorodnii, Xaver Hugl. The full notice is in the
  file.
- `protocols/blur.xml`: from
  [plasma-wayland-protocols](https://invent.kde.org/libraries/plasma-wayland-protocols)
  (`src/protocols/blur.xml`). LGPL-2.1-or-later; copyright Martin Gräßlin,
  Marco Martin. The SPDX header is in the file.

Both files are used unmodified. Only the generated protocol glue is linked into
the helper.
