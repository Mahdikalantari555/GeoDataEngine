# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the GeoDataEngine desktop GUI.

Build (from the repository root)::

    pyinstaller app/GeoDataEngine.spec

Produces ``dist/GeoDataEngine/`` — the portable folder distribution:

    GeoDataEngine/
      GeoDataEngine.exe        entry point (main.py)
      requirements.txt         installed into .venv on first run
      requirements-full.txt    installed by "Enable full processing"
      app/                     GUI sources (kept runnable by .venv)
      data_engine/             engine modules the GUI reuses (light stack only)
      config.json              created on first run next to the exe
      .venv/                   created on first run

The spec deliberately bundles only the *GUI* (stdlib + tkinter).  The heavy
scientific stack is installed into ``.venv`` at run time, which keeps the zip
small and lets the first run pick the right binary wheels for the user's
machine.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = Path(SPECPATH).resolve().parent          # noqa: F821 - injected by PyInstaller
APP_DIR = REPO_ROOT / "app"
SRC_DIR = REPO_ROOT / "src"

# Engine modules the lite stack needs: fetchers, bandwidth helpers, geometry
# errors and the vendored spectral index implementation.
ENGINE_MODULES = [
    "data_engine.io.errors",
    "data_engine.io.planetary_computer_fetcher",
    "data_engine._vendor.geospatial_core.spectral",
]

DATA_FILES = [
    (str(APP_DIR / "requirements.txt"), "."),
    (str(APP_DIR / "requirements-full.txt"), "."),
    # Ship the engine source so engine_loader can fall back to direct imports
    # in a frozen build (PyInstaller otherwise only stores compiled modules).
    (str(SRC_DIR), "."),
    (str(APP_DIR), "app"),
]

# Collect rasterio fully: its submodules (e.g. rasterio.serde) and native
# binaries/data are required at runtime but are not always auto-detected.
_rasterio_datas, _rasterio_binaries, _rasterio_hidden = collect_all("rasterio")
_planetary_datas, _planetary_binaries, _planetary_hidden = collect_all("planetary_computer")

ANALYSIS = Analysis(  # noqa: F821 - injected by PyInstaller
    [str(REPO_ROOT / "main.py")],
    pathex=[str(REPO_ROOT), str(SRC_DIR)],
    binaries=_rasterio_binaries + _planetary_binaries,
    datas=DATA_FILES + _rasterio_datas + _planetary_datas,
    hiddenimports=ENGINE_MODULES + _rasterio_hidden + _planetary_hidden
    + [
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.ttk",
        "numpy",
        "rasterio",
        "pyproj",
        "shapely",
        "pystac",
        "pystac_client",
        "planetary_computer",
        "tenacity",
        "loguru",
        "shapefile",          # pyshp, pure python shapefile reader
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # heavy stack is installed into .venv at run time, never bundled
        "scipy",
        "pandas",
        "xarray",
        "rioxarray",
        "geopandas",
        "fiona",
        "matplotlib",
        "seaborn",
        "cartopy",
        "sklearn",
        "torch",
        "tensorflow",
        "PyQt5",
        "PyQt6",
        "PySide6",
        "IPython",
        "notebook",
    ],
    noarchive=False,
    optimize=0,
)

PYZ = PYZ(ANALYSIS.pure)  # noqa: F821 - injected by PyInstaller

EXE = EXE(  # noqa: F821 - injected by PyInstaller
    PYZ,
    ANALYSIS.scripts,
    [],
    exclude_binaries=True,
    name="GeoDataEngine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

COLLECT = COLLECT(  # noqa: F821 - injected by PyInstaller
    EXE,
    ANALYSIS.binaries,
    ANALYSIS.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GeoDataEngine",
)
