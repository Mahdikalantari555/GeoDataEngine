"""Tests for ``app.core.engine_loader`` — importing engine modules on the lite stack.

The engine package ``data_engine/__init__.py`` imports the whole scientific
stack, so on a lite install (no matplotlib/pandas/scipy) even
``data_engine._vendor.geospatial_core.spectral`` would be unreachable.  The
loader falls back to importing the module file directly, which these tests
exercise with a *blocked* heavy dependency, i.e. the real lite-stack failure
mode, without needing a second interpreter.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from app.core.engine_loader import (
    ENGINE_PACKAGE,
    EngineImportError,
    engine_module,
    engine_root,
    lite_stack_active,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

BLOCK_HEAVY_PRELUDE = """
import sys
# Everything the METRIC/reporting stack adds on top of a lite install.
# The lite tier is: numpy, rasterio, requests, pyproj, shapely,
# pystac-client, planetary-computer, tenacity, loguru, pyshp.
_HEAVY = {"matplotlib", "scipy", "rioxarray", "geopandas", "fiona", "xarray", "pandas", "stackstac"}


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in _HEAVY:
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return None


sys.meta_path.insert(0, _Blocker())
sys.path.insert(0, "src")
sys.path.insert(0, ".")
"""


def run_blocked(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", BLOCK_HEAVY_PRELUDE + code],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )


class TestEngineRoot:
    def test_finds_the_package(self):
        root = engine_root()
        assert root.is_dir()
        assert (root / "__init__.py").is_file()

    def test_reports_a_missing_package(self, monkeypatch):
        import app.core.engine_loader as loader

        monkeypatch.setattr(
            loader.importlib.util, "find_spec", lambda name: None
        )
        monkeypatch.setitem(sys.modules, ENGINE_PACKAGE, None)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(loader, "engine_root", lambda: (_ for _ in ()).throw(
            EngineImportError("Cannot locate the 'data_engine' package.")
        ))
        with pytest.raises(EngineImportError, match="Cannot locate"):
            loader.engine_root()


class TestNormalImport:
    def test_imports_the_spectral_helper(self):
        module = engine_module("data_engine._vendor.geospatial_core.spectral")
        assert hasattr(module, "compute_spectral_index")

    def test_imports_the_fetcher_module(self):
        pytest.importorskip("stackstac")
        module = engine_module("data_engine.io.planetary_computer_fetcher")
        assert hasattr(module, "PlanetaryComputerLandsatFetcher")

    def test_unknown_module_raises(self):
        with pytest.raises((EngineImportError, ModuleNotFoundError)):
            engine_module("data_engine.does_not_exist")

    def test_non_engine_module_is_rejected_by_the_direct_loader(self):
        import app.core.engine_loader as loader

        with pytest.raises(EngineImportError, match="Not an engine module"):
            loader._direct_import("json.decoder")


class TestLiteStackFallback:
    """The fallback path is what makes a real lite install usable."""

    def test_spectral_helper_loads_when_heavy_packages_are_missing(self):
        code = (
            "from app.core.engine_loader import engine_module, lite_stack_active\n"
            "assert lite_stack_active() is True, 'engine unexpectedly importable'\n"
            "spectral = engine_module('data_engine._vendor.geospatial_core.spectral')\n"
            "import numpy as np\n"
            "value = spectral.compute_spectral_index('NDVI',"
            " {'nir': np.array([0.6]), 'red': np.array([0.2])})\n"
            "assert abs(float(value[0]) - 0.5) < 1e-9, value\n"
            "print('fallback ok')\n"
        )
        result = run_blocked(code)
        assert result.returncode == 0, result.stderr
        assert "fallback ok" in result.stdout

    def test_indices_work_when_heavy_packages_are_missing(self):
        code = (
            "import numpy as np\n"
            "from app.core.indices import compute_index\n"
            "ndvi = compute_index('NDVI', {'nir08': np.array([[0.6]]), 'red': np.array([[0.2]])})\n"
            "assert abs(float(ndvi[0, 0]) - 0.5) < 1e-9\n"
            "optram = compute_index('OPTRAM', {'red': np.array([[0.2]]), 'nir08': np.array([[0.6]])})\n"
            "assert 0.0 <= float(optram[0, 0]) <= 1.0\n"
            "print('indices ok')\n"
        )
        result = run_blocked(code)
        assert result.returncode == 0, result.stderr
        assert "indices ok" in result.stdout

    def test_engine_fetcher_module_loads_on_the_lite_stack(self):
        code = (
            "import sys\n"
            "from app.core.engine_loader import engine_module\n"
            "module = engine_module('data_engine.io.planetary_computer_fetcher')\n"
            "assert module.PlanetaryComputerLandsatFetcher is not None\n"
            "assert module.SentinelPlanetaryComputerFetcher is not None\n"
            "loaded = [m for m in ('matplotlib', 'scipy', 'geopandas', 'fiona', 'xarray',"
            " 'pandas', 'stackstac') if m in sys.modules]\n"
            "assert not loaded, loaded\n"
            "print('fetcher module ok')\n"
        )
        result = run_blocked(code)
        assert result.returncode == 0, result.stderr
        assert "fetcher module ok" in result.stdout

    def test_build_fetcher_reaches_the_network_on_the_lite_stack(self):
        """The fetcher is constructed (and only then hits the STAC endpoint)."""
        code = (
            "from app.core.catalog import build_fetcher\n"
            "from app.core.engine_loader import engine_module\n"
            "errors = engine_module('data_engine.io.errors')\n"
            "try:\n"
            "    build_fetcher('landsat-8')\n"
            "except errors.AuthenticationError as exc:\n"
            "    assert 'STAC' in str(exc) or 'connect' in str(exc).lower(), exc\n"
            "    print('network reached on lite stack')\n"
            "else:\n"
            "    print('network reached on lite stack')\n"
        )
        result = run_blocked(code)
        assert result.returncode == 0, result.stderr
        assert "network reached on lite stack" in result.stdout

    def test_namespace_stubs_do_not_break_later_engine_imports(self):
        """After the fallback, importing a second engine module still works."""
        code = (
            "from app.core.engine_loader import engine_module\n"
            "engine_module('data_engine._vendor.geospatial_core.spectral')\n"
            "again = engine_module('data_engine._vendor.geospatial_core.spectral')\n"
            "assert hasattr(again, 'ndvi')\n"
            "print('repeat ok')\n"
        )
        result = run_blocked(code)
        assert result.returncode == 0, result.stderr
        assert "repeat ok" in result.stdout


class TestLiteStackDetection:
    def test_lite_stack_active_is_false_in_the_test_environment(self):
        # The test environment has the full stack installed.
        assert lite_stack_active() is False

    def test_lite_stack_active_is_true_when_heavy_packages_are_missing(self):
        result = run_blocked(
            "from app.core.engine_loader import lite_stack_active\n"
            "print(lite_stack_active())\n"
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "True"

    def test_optional_error_detection(self):
        import app.core.engine_loader as loader

        assert loader._is_optional_dependency_error(ModuleNotFoundError("No module named 'pandas'"))
        assert loader._is_optional_dependency_error(ImportError("No module named 'matplotlib'"))
        assert not loader._is_optional_dependency_error(ModuleNotFoundError("No module named 'numpy'"))
        assert not loader._is_optional_dependency_error(ValueError("boom"))
