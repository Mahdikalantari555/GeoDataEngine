"""Integration tests for the METRICPipeline stage 3b (spectral indices)."""

import pytest
import numpy as np
import xarray as xr
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from data_engine.core.datacube import DataCube
from data_engine.pipeline.metric_pipeline import METRICPipeline


def _make_test_cube(size=10):
    """Create a minimal DataCube with all bands needed for spectral indices."""
    np.random.seed(7)
    shape = (size, size)
    cube = DataCube()
    cube.add("blue", np.random.rand(*shape) * 0.2)
    cube.add("green", np.random.rand(*shape) * 0.3 + 0.05)
    cube.add("red", np.random.rand(*shape) * 0.2 + 0.05)
    cube.add("nir08", np.random.rand(*shape) * 0.5 + 0.1)
    cube.add("swir16", np.random.rand(*shape) * 0.2 + 0.05)
    cube.add("swir22", np.random.rand(*shape) * 0.1 + 0.02)
    cube.add("lwir11", np.random.uniform(290, 330, shape))
    # Pre-compute ndvi and lst
    red = cube.get("red")
    nir = cube.get("nir08")
    ndvi_vals = ((nir.values - red.values) / (nir.values + red.values)).clip(-1, 1)
    cube.add("ndvi", xr.DataArray(ndvi_vals, dims=nir.dims, coords=nir.coords))
    cube.add("lst", xr.DataArray(np.random.uniform(290, 330, shape), dims=["y", "x"]))
    return cube


class TestCalculateSpectralIndices:
    def test_all_indices_computed(self):
        """Stage 3b should add ndmi, msi, nmdi, nirv, gci, ndsi, si_t."""
        pipeline = METRICPipeline(config={'output_categories': ['spectral_indices']})
        pipeline.data = _make_test_cube()
        pipeline.calculate_spectral_indices()
        assert "ndmi" in pipeline.data.bands()
        assert "msi" in pipeline.data.bands()
        assert "nmdi" in pipeline.data.bands()
        assert "nirv" in pipeline.data.bands()
        assert "gci" in pipeline.data.bands()
        assert "ndsi" in pipeline.data.bands()
        assert "si_t" in pipeline.data.bands()

    def test_ndmi_formula(self):
        pipeline = METRICPipeline(config={'output_categories': ['spectral_indices']})
        pipeline.data = _make_test_cube()
        pipeline.calculate_spectral_indices()
        result = pipeline.data.get("ndmi")
        nir = pipeline.data.get("nir08").values.astype(float)
        swir = pipeline.data.get("swir16").values.astype(float)
        expected = (nir - swir) / (nir + swir)
        finite = np.isfinite(expected)
        assert np.allclose(result.values[finite], expected[finite], rtol=1e-10)

    def test_skip_on_missing_swir22(self, caplog):
        """NMDI should be skipped with a warning when swir22 is missing."""
        import logging
        pipeline = METRICPipeline(config={'output_categories': ['spectral_indices']})
        cube = _make_test_cube()
        del cube.data["swir22"]
        pipeline.data = cube
        pipeline.calculate_spectral_indices()
        assert "nmdi" not in pipeline.data.bands()

    def test_other_indices_still_run_without_swir22(self):
        """Other indices should still compute even if NMDI is skipped."""
        pipeline = METRICPipeline(config={'output_categories': ['spectral_indices']})
        cube = _make_test_cube()
        del cube.data["swir22"]
        pipeline.data = cube
        pipeline.calculate_spectral_indices()
        assert "ndmi" in pipeline.data.bands()
        assert "msi" in pipeline.data.bands()
        assert "nirv" in pipeline.data.bands()
        assert "gci" in pipeline.data.bands()
        assert "ndsi" in pipeline.data.bands()
        assert "si_t" in pipeline.data.bands()
