# Runtime hook: programs GifPop starts (the emoji picker, xdg-open, ...) get the user's own
# environment, not the bundle's. PyInstaller points LD_LIBRARY_PATH at the bundled libraries
# and its PyQt6 hook sets QT_PLUGIN_PATH / QML2_IMPORT_PATH to the bundled Qt; a system Qt app
# such as plasma-emojier inheriting those would load the wrong Qt and fail.
# The bundled app doesn't need them: the dynamic loader read LD_LIBRARY_PATH when the process
# started, the bundled libraries find each other via RPATH, and Qt finds its plugins through
# the qt.conf that PyQt6 embeds at import time (prefix = the bundle's PyQt6/Qt6).
import os

for _var in ("LD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
    _orig = os.environ.pop(_var + "_ORIG", None)
    if _orig is not None:
        os.environ[_var] = _orig
    else:
        os.environ.pop(_var, None)
del _var, _orig
