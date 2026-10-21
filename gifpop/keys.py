"""The KLIPY key that release builds ship with.

Release builds get a generated `_builtin.py` (see scripts/embed_key.py, never committed).
The key is XOR-scrambled there so it isn't a plain string for scrapers to grep. That only
stops bots, not people: anyone can still pull it out of the app, which is normal for GIF
API keys (they identify the app; they don't guard anything private).
A key typed into Settings always wins over the built-in one.
"""
import base64
from urllib.parse import quote

SALT = b"gifpop: not a secret, just not greppable"


def scramble(text):
    raw = bytes(b ^ SALT[i % len(SALT)] for i, b in enumerate(text.encode()))
    return base64.b64encode(raw).decode()


def unscramble(blob):
    raw = base64.b64decode(blob)
    return bytes(b ^ SALT[i % len(SALT)] for i, b in enumerate(raw)).decode()


def builtin_klipy_key():
    try:
        from ._builtin import KLIPY
    except ImportError:
        return ""
    try:
        return unscramble(KLIPY)
    except ValueError:
        return ""


BUILTIN_KLIPY = builtin_klipy_key()


def redact(text, *keys):
    """Keep API keys out of error messages (Qt puts the request URL in them)."""
    for k in (BUILTIN_KLIPY, *keys):
        if k:
            text = text.replace(k, "…").replace(quote(k, safe=""), "…")
    return text
