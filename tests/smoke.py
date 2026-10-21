"""Headless smoke test: the package imports, the key scrambling round-trips, the main
window builds. Run from the repo (or a release folder): python3 tests/smoke.py [--expect-builtin]"""
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
tmp = tempfile.mkdtemp(prefix="gifpop-smoke-")
for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME"):
    os.environ[var] = os.path.join(tmp, var.lower())
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gifpop import keys  # noqa: E402

for sample in ("", "abc123", "x" * 64):
    assert keys.unscramble(keys.scramble(sample)) == sample
assert keys.redact("GET /v1/SECRET/gifs", "SECRET") == "GET /v1/…/gifs"

if "--expect-builtin" in sys.argv:
    assert keys.BUILTIN_KLIPY, "release build has no built-in KLIPY key"
    assert keys.BUILTIN_KLIPY not in (root / "gifpop" / "_builtin.py").read_text()

from PyQt6.QtWidgets import QApplication  # noqa: E402

from gifpop.app import MainWindow  # noqa: E402
from gifpop.config import Config  # noqa: E402

app = QApplication([])
cfg = Config()
assert cfg.klipy == keys.BUILTIN_KLIPY
win = MainWindow(cfg)
print("smoke ok, built-in key:", "yes" if keys.BUILTIN_KLIPY else "no")
