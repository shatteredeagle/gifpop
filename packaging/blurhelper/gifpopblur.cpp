// SPDX-License-Identifier: GPL-3.0-or-later
//
// libgifpopblur: asks the Wayland compositor to blur what is behind a QWindow.
//
// The release bundle ships its own Qt (6.11.x), so it cannot load the system
// KF6WindowSystem (built against the system Qt). This helper is compiled against
// the bundled Qt version and talks the blur protocols directly:
//   1. ext_background_effect_manager_v1 (wayland-protocols staging), when the
//      compositor advertises the "blur" capability;
//   2. org_kde_kwin_blur_manager (plasma-wayland-protocols) as a fallback.
//
// C ABI (used from Python via ctypes):
//   int gifpop_blur(void *qwindow, int enable, int radius);
//   qwindow: QWindow* (sip.unwrapinstance(widget.windowHandle())), already shown.
//   Returns 1 = blur requested/removed, 0 = not supported, -1 = error.

#include <QtCore/QHash>
#include <QtCore/QObject>
#include <QtCore/QPointer>
#include <QtGui/QGuiApplication>
#include <QtGui/QWindow>
#include <QtGui/qguiapplication_platform.h>
#include <QtGui/qpa/qplatformwindow_p.h>

#include <wayland-client.h>

#include <algorithm>
#include <cmath>
#include <cstring>

#include "blur-client-protocol.h"
#include "ext-background-effect-v1-client-protocol.h"

namespace {

enum class Backend { Unknown, None, Ext, Kde };

struct Globals {
    bool probed = false;
    Backend backend = Backend::Unknown;
    wl_display *display = nullptr;
    wl_event_queue *queue = nullptr;
    wl_display *displayWrapper = nullptr;
    wl_compositor *compositor = nullptr;
    ext_background_effect_manager_v1 *extManager = nullptr;
    uint32_t extCaps = 0;
    org_kde_kwin_blur_manager *kdeManager = nullptr;
};

Globals g;

struct SurfaceBlur {
    wl_surface *surface = nullptr;
    ext_background_effect_surface_v1 *ext = nullptr;
    org_kde_kwin_blur *kde = nullptr;
    QMetaObject::Connection destroyedConn;
    QMetaObject::Connection surfaceGoneConn;
};

QHash<QWindow *, SurfaceBlur> g_blurs;

void onGlobal(void *, wl_registry *registry, uint32_t name, const char *iface, uint32_t version)
{
    if (std::strcmp(iface, wl_compositor_interface.name) == 0 && !g.compositor) {
        g.compositor = static_cast<wl_compositor *>(
            wl_registry_bind(registry, name, &wl_compositor_interface, std::min<uint32_t>(version, 4)));
    } else if (std::strcmp(iface, ext_background_effect_manager_v1_interface.name) == 0 && !g.extManager) {
        g.extManager = static_cast<ext_background_effect_manager_v1 *>(
            wl_registry_bind(registry, name, &ext_background_effect_manager_v1_interface, 1));
    } else if (std::strcmp(iface, org_kde_kwin_blur_manager_interface.name) == 0 && !g.kdeManager) {
        g.kdeManager = static_cast<org_kde_kwin_blur_manager *>(
            wl_registry_bind(registry, name, &org_kde_kwin_blur_manager_interface, 1));
    }
}

void onGlobalRemove(void *, wl_registry *, uint32_t) {}

const wl_registry_listener kRegistryListener = {onGlobal, onGlobalRemove};

void onExtCaps(void *, ext_background_effect_manager_v1 *, uint32_t flags)
{
    g.extCaps = flags;
}

const ext_background_effect_manager_v1_listener kExtListener = {onExtCaps};

// Binds the globals once per process on a private event queue, so Qt's own
// queue is never dispatched from here.
Backend probe()
{
    if (g.probed)
        return g.backend;
    g.probed = true;
    g.backend = Backend::None;

    auto *app = qGuiApp ? qGuiApp->nativeInterface<QNativeInterface::QWaylandApplication>() : nullptr;
    if (!app)
        return g.backend;
    g.display = app->display();
    if (!g.display)
        return g.backend;

    g.queue = wl_display_create_queue(g.display);
    g.displayWrapper = static_cast<wl_display *>(wl_proxy_create_wrapper(g.display));
    if (!g.queue || !g.displayWrapper)
        return g.backend;
    wl_proxy_set_queue(reinterpret_cast<wl_proxy *>(g.displayWrapper), g.queue);

    wl_registry *registry = wl_display_get_registry(g.displayWrapper);
    wl_registry_add_listener(registry, &kRegistryListener, nullptr);
    if (wl_display_roundtrip_queue(g.display, g.queue) < 0) {
        wl_registry_destroy(registry);
        return g.backend;
    }
    if (g.extManager) {
        ext_background_effect_manager_v1_add_listener(g.extManager, &kExtListener, nullptr);
        // Second roundtrip delivers the capabilities event sent on bind.
        wl_display_roundtrip_queue(g.display, g.queue);
    }
    wl_registry_destroy(registry);

    if (!g.compositor)
        return g.backend;
    // GIFPOP_BLUR_PROTOCOL=kde forces the KWin fallback (testing aid).
    const bool forceKde = qgetenv("GIFPOP_BLUR_PROTOCOL") == "kde";
    if (!forceKde && g.extManager && (g.extCaps & EXT_BACKGROUND_EFFECT_MANAGER_V1_CAPABILITY_BLUR))
        g.backend = Backend::Ext;
    else if (g.kdeManager)
        g.backend = Backend::Kde;
    return g.backend;
}

// surfaceAlive: false when Qt already destroyed the wl_surface (then only the
// blur objects themselves may be destroyed, nothing may reference the surface).
void destroyBlurObjects(SurfaceBlur &b, bool surfaceAlive)
{
    if (b.ext) {
        ext_background_effect_surface_v1_destroy(b.ext);
        b.ext = nullptr;
    }
    if (b.kde) {
        if (surfaceAlive)
            org_kde_kwin_blur_manager_unset(g.kdeManager, b.surface);
        org_kde_kwin_blur_release(b.kde);
        b.kde = nullptr;
    }
    b.surface = nullptr;
}

void forget(QWindow *w, bool surfaceAlive)
{
    auto it = g_blurs.find(w);
    if (it == g_blurs.end())
        return;
    destroyBlurObjects(*it, surfaceAlive);
    QObject::disconnect(it->destroyedConn);
    QObject::disconnect(it->surfaceGoneConn);
    g_blurs.erase(it);
    if (g.display)
        wl_display_flush(g.display);
}

// Rounded rectangle as a wl_region: a full-height middle band plus horizontal
// strips in the corner columns (one strip per row of the corner arc).
wl_region *roundedRegion(int w, int h, int r)
{
    wl_region *region = wl_compositor_create_region(g.compositor);
    r = std::clamp(r, 0, 32);
    r = std::min({r, w / 2, h / 2});
    if (r <= 0) {
        wl_region_add(region, 0, 0, w, h);
        return region;
    }
    wl_region_add(region, 0, r, w, h - 2 * r);   // middle band, full width
    for (int y = 0; y < r; ++y) {
        // Inset of the arc at the vertical centre of this row.
        const double dy = r - (y + 0.5);
        const int inset = r - static_cast<int>(std::lround(std::sqrt(double(r) * r - dy * dy)));
        const int span = w - 2 * inset;
        if (span <= 0)
            continue;
        wl_region_add(region, inset, y, span, 1);             // top row
        wl_region_add(region, inset, h - 1 - y, span, 1);     // bottom row
    }
    return region;
}

int apply(QWindow *window, bool enable, int radius)
{
    if (!enable) {
        auto *native = window->nativeInterface<QNativeInterface::Private::QWaylandWindow>();
        forget(window, native && native->surface());
        window->requestUpdate();
        return 1;
    }

    auto *native = window->nativeInterface<QNativeInterface::Private::QWaylandWindow>();
    if (!native)
        return 0;
    wl_surface *surface = native->surface();
    if (!surface)
        return -1; // not mapped yet

    auto it = g_blurs.find(window);
    if (it != g_blurs.end() && it->surface != surface) {
        // Qt recreated the wl_surface (hide/show); start over.
        forget(window, false);
        it = g_blurs.end();
    }
    if (it == g_blurs.end()) {
        SurfaceBlur b;
        b.surface = surface;
        if (g.backend == Backend::Ext)
            b.ext = ext_background_effect_manager_v1_get_background_effect(g.extManager, surface);
        else
            b.kde = org_kde_kwin_blur_manager_create(g.kdeManager, surface);
        b.destroyedConn = QObject::connect(window, &QObject::destroyed, [window] { forget(window, false); });
        // Drop our object when Qt tears the surface down, so we never send
        // requests for a dead surface (a protocol error for ext_background_effect).
        b.surfaceGoneConn = QObject::connect(native, &QNativeInterface::Private::QWaylandWindow::surfaceDestroyed,
                                             window, [window] { forget(window, false); });
        it = g_blurs.insert(window, b);
    }

    const QSize size = window->size();
    wl_region *region = roundedRegion(size.width(), size.height(), radius);
    if (it->ext) {
        ext_background_effect_surface_v1_set_blur_region(it->ext, region);
    } else {
        org_kde_kwin_blur_set_region(it->kde, region);
        org_kde_kwin_blur_commit(it->kde);
    }
    wl_region_destroy(region);

    // Blur state is double-buffered: Qt's next frame commits the surface.
    window->requestUpdate();
    wl_display_flush(g.display);
    return 1;
}

} // namespace

extern "C" __attribute__((visibility("default"))) int gifpop_blur(void *qwindow, int enable, int radius)
{
    if (!qwindow || !qGuiApp)
        return -1;
    auto *window = static_cast<QWindow *>(qwindow);
    switch (probe()) {
    case Backend::Ext:
    case Backend::Kde:
        return apply(window, enable != 0, radius);
    default:
        return 0;
    }
}
