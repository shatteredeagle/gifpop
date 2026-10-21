"""Writes gifpop/_builtin.py with the KLIPY key from $KLIPY_API_KEY, scrambled.
Release builds only; _builtin.py is gitignored and must never be committed.
Usage: KLIPY_API_KEY=... python3 scripts/embed_key.py [output path]"""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from gifpop.keys import scramble, unscramble  # noqa: E402

key = os.environ.get("KLIPY_API_KEY", "").strip()
if not key:
    sys.exit("KLIPY_API_KEY is empty")
blob = scramble(key)
assert unscramble(blob) == key
out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "gifpop" / "_builtin.py"
out.write_text(f'KLIPY = "{blob}"\n')
print(f"wrote {out}")
