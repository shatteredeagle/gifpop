"""Prints the CHANGELOG.md section for a version (release notes). Fails if it's missing.
Usage: python3 scripts/changelog_section.py 0.2.0"""
import re
import sys
from pathlib import Path

version = sys.argv[1].lstrip("v")
text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text()
m = re.search(rf"^## \[?{re.escape(version)}\]?[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
if not m or not m.group(1).strip():
    sys.exit(f"CHANGELOG.md has no notes for {version}")
print(m.group(1).strip())
