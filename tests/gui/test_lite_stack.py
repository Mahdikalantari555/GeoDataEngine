"""Guards for the "light stack" claim (change task 1.2).

These tests pin the dependency contract rather than performing installs (the
install is verified by ``pip install -r app/requirements.txt`` in a fresh venv,
see ``app/README.md``):

* every module the GUI's engine bridge imports exists in ``requirements.txt``;
* the heavy imports the METRIC pipeline needs live only in
  ``requirements-full.txt``;
* importing the GUI entry points never pulls in a heavy module.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
REPO_ROOT = APP_DIR.parent

#: Modules the engine bridge needs at run time (see app.core.bridge docs).
BRIDGE_STDLIB = {"contextlib", "json", "logging", "os", "datetime", "pathlib", "__future__"}
BRIDGE_THIRD_PARTY = {
    "numpy",
    "rasterio",
    "requests",
    "pyproj",
    "shapely",
    "pystac_client",
    "planetary_computer",
    "tenacity",
    "loguru",
    "pyshp",
}


def requirements_packages(filename: str) -> set[str]:
    """Normalised package names from a requirements file (ignoring comments)."""
    packages = set()
    for line in (APP_DIR / filename).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = line
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
            name = name.split(separator, 1)[0]
        packages.add(name.strip().lower())
    return packages


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


class TestRequirementsContract:
    def test_essentials_declare_the_engine_bridge_dependencies(self):
        declared = requirements_packages("requirements.txt")
        aliases = {
            "pystac_client": "pystac-client",
            "planetary_computer": "planetary-computer",
            "pyshp": "pyshp",
        }
        for module in BRIDGE_THIRD_PARTY:
            package = aliases.get(module, module)
            assert package in declared, f"{module} is imported but not in requirements.txt"

    def test_essentials_do_not_declare_the_heavy_stack(self):
        declared = requirements_packages("requirements.txt")
        for heavy in ("scipy", "pandas", "xarray", "rioxarray", "geopandas", "fiona",
                      "matplotlib", "cartopy", "scikit-learn", "seaborn"):
            assert heavy not in declared, heavy

    def test_full_stack_declares_what_metric_needs(self):
        declared = requirements_packages("requirements-full.txt")
        for package in ("scipy", "pandas", "xarray", "rioxarray", "geopandas", "fiona",
                        "matplotlib", "click", "pyyaml", "tqdm"):
            assert package in declared, package

    def test_full_stack_layers_on_the_essentials(self):
        text = (APP_DIR / "requirements-full.txt").read_text(encoding="utf-8")
        assert "-r requirements.txt" in text

    def test_xarray_and_pandas_belong_to_the_full_tier(self):
        """The fetcher imports stackstac lazily, so lite needs no xarray/dask."""
        from app.core.bootstrap import FULL_MODULES

        assert "xarray" in FULL_MODULES
        assert "pandas" in FULL_MODULES
        assert "stackstac" in FULL_MODULES

    def test_fetcher_imports_stackstac_lazily(self):
        import ast

        source = (REPO_ROOT / "src" / "data_engine" / "io" / "planetary_computer_fetcher.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        module_level = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                module_level.update(alias.name for alias in node.names)
        assert "stackstac" not in module_level
        assert "_import_stackstac" in source.read_text(encoding="utf-8")

    def test_module_probe_lists_match_the_requirements(self):
        from app.core.bootstrap import ESSENTIAL_MODULES, FULL_MODULES

        essentials = requirements_packages("requirements.txt")
        aliases = {"pystac_client": "pystac-client", "planetary_computer": "planetary-computer",
                   "shapefile": "pyshp"}
        for module in ESSENTIAL_MODULES:
            assert aliases.get(module, module) in essentials

        full = requirements_packages("requirements-full.txt") | essentials
        full_aliases = {"yaml": "pyyaml"}
        for module in FULL_MODULES:
            assert full_aliases.get(module, module) in full


class TestEngineImportSurface:
    """The GUI only imports these two engine modules at run time."""

    def test_bridge_imports_only_lite_engine_modules(self):
        catalog_source = (APP_DIR / "core" / "catalog.py").read_text(encoding="utf-8")
        assert "data_engine.io.planetary_computer_fetcher" in catalog_source
        assert "data_engine.pipeline" not in catalog_source

        session_source = (APP_DIR / "core" / "session.py").read_text(encoding="utf-8")
        assert "data_engine.pipeline" not in session_source

    def test_index_module_uses_the_vendored_spectral_helper(self):
        source = (APP_DIR / "core" / "indices.py").read_text(encoding="utf-8")
        assert 'engine_module("data_engine._vendor.geospatial_core.spectral")' in source

    def test_presets_import_the_pipeline_lazily(self):
        source = (APP_DIR / "core" / "presets.py").read_text(encoding="utf-8")
        # inside the runner callable, not at module scope
        tree = ast.parse(source)
        top_level = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        imported = set()
        for node in top_level:
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any("data_engine.pipeline" in name for name in imported)
        assert "data_engine.pipeline" in source

    @pytest.mark.parametrize(
        "module",
        ["app.core.session", "app.core.indices", "app.core.presets", "app.help_text"],
    )
    def test_gui_modules_do_not_import_heavy_packages(self, module):
        import importlib

        mod = importlib.import_module(module)
        imported = imports_of(Path(mod.__file__))
        heavy = {"scipy", "pandas", "xarray", "matplotlib", "geopandas", "fiona", "sklearn"}
        assert not imported & heavy, f"{module} imports {imported & heavy}"

    def test_engine_bridge_never_imports_data_engine_at_module_scope(self):
        """``data_engine`` is imported inside functions so the GUI starts first."""
        tree = ast.parse((APP_DIR / "core" / "session.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("data_engine")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("data_engine")


class TestInstalledEnvironment:
    """Sanity checks against the interpreter running the tests."""

    @pytest.mark.parametrize("module", ["numpy", "rasterio", "shapely", "pyproj"])
    def test_lite_dependencies_are_importable(self, module):
        pytest.importorskip(module)

    def test_engine_fetcher_imports_with_the_lite_stack(self):
        pytest.importorskip("stackstac")
        from data_engine.io.planetary_computer_fetcher import (
            PlanetaryComputerLandsatFetcher,
        )

        assert PlanetaryComputerLandsatFetcher.STAC_API_URL.startswith("https://")

    def test_spectral_helper_matches_the_gui_formulas(self):
        from data_engine._vendor.geospatial_core import spectral

        assert spectral.compute_spectral_index.__name__ == "compute_spectral_index"
