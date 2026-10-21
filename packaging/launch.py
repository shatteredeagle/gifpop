"""PyInstaller entry point for the bundled app (same as `python3 -m gifpop`)."""
import sys

from gifpop.app import main

sys.exit(main())
