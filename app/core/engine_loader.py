"""Resilient imports of the engine modules the GUI reuses.

A clean "lite" install (``app/requirements.txt``) deliberately does **not**
contain matplotlib, pandas, xarray, scipy, geopandas or fiona.  Importing
``data_engine.<something>`` would normally execute ``data_engine/__init__.py``
first, which imports the whole scientific stack — so on a lite install the
vendored spectral helper and the Planetary Computer fetcher would be
unreachable even though *they* only need numpy/rasterio.

:func:`engine_module` solves that without touching the engine: it tries the
normal import first and, when the failure is caused by a missing heavy
package, loads the requested module file directly with lightweight namespace
stubs for its parent packages.  The engine therefore keeps its public import
behaviour while the GUI keeps working on the light stack.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ENGINE_PACKAGE = "data_engine"

#: Errors caused by an incomplete install (as opposed to a real bug).
_OPTIONAL_MISSING = (
    "matplotlib",
    "pandas",
    "xarray",
    "rioxarray",
    "scipy",
    "geopandas",
    "fiona",
    "cartopy",
    "seaborn",
    "sklearn",
    "dask",
)


class EngineImportError(ImportError):
    """Raised when an engine module cannot be imported even directly."""


def _is_optional_dependency_error(exc: BaseException) -> bool:
    """True when ``exc`` is an ImportError for one of the optional heavy packages."""
    missing = getattr(exc, "name", None) or ""
    if isinstance(exc, ModuleNotFoundError) and missing.split(".")[0] in _OPTIONAL_MISSING:
        return True
    if not isinstance(exc, ImportError):
        return False
    text = str(exc)
    return any(
        f"No module named '{package}" in text or f"No module named {package}" in text
        for package in _OPTIONAL_MISSING
    )


def engine_root() -> Path:
    """Directory that contains the ``data_engine`` package."""
    spec = importlib.util.find_spec(ENGINE_PACKAGE)
    if spec is not None and spec.submodule_search_locations:
        return Path(list(spec.submodule_search_locations)[0])

    candidates = [
        Path(sys._MEIPASS) / ENGINE_PACKAGE if hasattr(sys, "_MEIPASS") else None,
        Path(__file__).resolve().parents[2] / "src" / ENGINE_PACKAGE,
        Path(sys.executable).resolve().parent / ENGINE_PACKAGE if getattr(sys, "frozen", False) else None,
        Path(__file__).resolve().parents[2] / ENGINE_PACKAGE,
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate
    raise EngineImportError(
        f"Cannot locate the '{ENGINE_PACKAGE}' package. Install the engine with "
        "'pip install -e .' or run the GUI from the repository root."
    )


def _ensure_namespace(name: str, path: Path) -> None:
    """Register ``name`` as an importable package rooted at ``path`` (no __init__)."""
    if name in sys.modules:
        return
    spec = importlib.util.spec_from_loader(name, loader=None, is_package=True)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    module.__path__ = [str(path)]
    module.__package__ = name
    sys.modules[name] = module


def _direct_import(dotted: str) -> ModuleType:
    """Load ``dotted`` from its file, stubbing parent packages as namespaces."""
    root = engine_root()
    parts = dotted.split(".")
    if parts[0] != ENGINE_PACKAGE:
        raise EngineImportError(f"Not an engine module: {dotted}")

    _ensure_namespace(ENGINE_PACKAGE, root)
    current = root
    for index in range(1, len(parts) - 1):
        current = current / parts[index]
        _ensure_namespace(".".join(parts[: index + 1]), current)

    path = current / f"{parts[-1]}.py"
    if not path.is_file():
        package_init = current / parts[-1] / "__init__.py"
        if not package_init.is_file():
            raise EngineImportError(f"Engine module not found: {path}")
        path = package_init

    spec = importlib.util.spec_from_file_location(dotted, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise EngineImportError(f"Cannot build an import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(dotted, None)
        raise
    return module


def engine_module(dotted: str) -> ModuleType:
    """Import an engine module, tolerating a lite (partial) install.

    Args:
        dotted: Dotted module path, e.g.
            ``"data_engine.io.planetary_computer_fetcher"``.

    Returns:
        The imported module.

    Raises:
        EngineImportError: If the module cannot be imported either normally or
            directly from its file.
    """
    try:
        return importlib.import_module(dotted)
    except ImportError as exc:
        if not _is_optional_dependency_error(exc):
            raise
        try:
            return _direct_import(dotted)
        except ImportError as direct_exc:
            raise EngineImportError(
                f"Cannot import {dotted} on the light stack: {direct_exc}"
            ) from direct_exc


def lite_stack_active() -> bool:
    """Whether the engine package requires modules the lite stack does not ship."""
    try:
        importlib.import_module(ENGINE_PACKAGE)
    except ImportError as exc:
        return _is_optional_dependency_error(exc)
    return False


__all__ = [
    "ENGINE_PACKAGE",
    "EngineImportError",
    "engine_module",
    "engine_root",
    "lite_stack_active",
]
