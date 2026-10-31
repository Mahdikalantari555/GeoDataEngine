"""GeoDataEngine desktop GUI (Tkinter).

The package is intentionally split in two layers:

``app.core``
    Dependency-light, framework-free logic: configuration, ROI loading,
    output layout, spectral index generation, METRIC preset mapping,
    environment bootstrap and the download/generate session controller.
    Nothing in ``app.core`` imports ``tkinter`` or any heavy scientific
    package, so the whole layer is unit testable on any machine.

``app.ui``
    Thin Tkinter views that render ``app.core`` state and forward user
    actions to the session controller. The toolkit is injected, which keeps
    the views testable without a display server.

Run the application with ``python -m app.main``.
"""

from __future__ import annotations

import sys
from pathlib import Path

__version__ = "0.1.0"

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
SRC_DIR = REPO_ROOT / "src"


def ensure_engine_on_path() -> Path | None:
    """Make ``src/`` importable when running from a source checkout.

    The GUI reuses engine modules (``data_engine._vendor.geospatial_core``,
    ``data_engine.io.planetary_computer_fetcher``).  In a PyInstaller build
    they are already bundled; in a source checkout they live under ``src/``.
    Returns the directory that was added, or ``None`` when nothing changed.
    """
    if not SRC_DIR.is_dir():
        return None
    resolved = str(SRC_DIR)
    if resolved in {str(Path(entry).resolve()) for entry in sys.path if entry}:
        return None
    sys.path.insert(0, resolved)
    return SRC_DIR


ensure_engine_on_path()

__all__ = ["PACKAGE_ROOT", "REPO_ROOT", "SRC_DIR", "ensure_engine_on_path", "__version__"]
