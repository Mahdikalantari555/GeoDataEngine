"""Portable-folder launcher for GeoDataEngine Desktop.

Double-clicking ``main.pyw``/``main.py`` (or running the PyInstaller exe built
from this file) starts the GUI.  The heavy import work lives in ``app.main``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
