"""Unit tests for data_engine.surface.optram.OPTRAM."""

import numpy as np
import pytest
import xarray as xr

from data_engine.core.datacube import DataCube
from data_engine.surface.optram import OPTRAM


class TestOPTRAM:
    def test_compute_valid_bands(self):
        cube = DataCube()
        red = np.full((10, 10), 0.30, dtype=float)
        nir = np.full((10, 10), 0.50, dtype=float)
        cube.add("red", xr.DataArray(red, dims=["y", "x"]))
        cube.add("nir08", xr.DataArray(nir, dims=["y", "x"]))
        result = OPTRAM().compute(cube)
        out = cube.get("optram")
        assert out.name == "optram"
        assert out.attrs["units"] == "dimensionless"
        assert out.attrs["long_name"] == "OPTRAM Soil Moisture Proxy"
        # All pixels identical: sqrt(5/3) * (1 - 3/5) ≈ 0.516
        expected = np.sqrt(0.50 / 0.30) * (1.0 - 0.30 / 0.50)
        assert np.allclose(out.values, expected)
        assert 0 <= out.min().values <= out.max().values <= 1

    def test_missing_red_raises(self):
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="Missing required band 'red'"):
            OPTRAM().compute(cube)

    def test_missing_nir08_raises(self):
        cube = DataCube()
        cube.add("red", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="Missing required band 'nir08'"):
            OPTRAM().compute(cube)

    def test_nan_handling_zero_red(self):
        """Zero red → division by zero → NaN output, no crash."""
        cube = DataCube()
        red = np.ones((5, 5)) * 0.2
        nir = np.ones((5, 5)) * 0.5
        red[:, 0] = 0.0  # first column all zeros
        cube.add("red", xr.DataArray(red, dims=["y", "x"]))
        cube.add("nir08", xr.DataArray(nir, dims=["y", "x"]))
        OPTRAM().compute(cube)
        out = cube.get("optram")
        assert np.isnan(out.isel(x=0).values).all()
        assert np.all(np.isfinite(out.isel(x=slice(1, None)).values))

    def test_nan_values_result_in_nan_output(self):
        """Input NaN propagates to output."""
        cube = DataCube()
        red = np.ones((5, 5)) * 0.2
        nir = np.ones((5, 5)) * 0.5
        red[2, 2] = np.nan
        cube.add("red", xr.DataArray(red, dims=["y", "x"]))
        cube.add("nir08", xr.DataArray(nir, dims=["y", "x"]))
        OPTRAM().compute(cube)
        out = cube.get("optram")
        assert np.isnan(out.values[2, 2])

    def test_range_clipped_to_0_1(self):
        """Extreme ratios are clipped; high NIR+low red gives near 1."""
        cube = DataCube()
        red = np.full((10, 10), 0.01, dtype=float)
        nir = np.full((10, 10), 0.60, dtype=float)
        cube.add("red", xr.DataArray(red, dims=["y", "x"]))
        cube.add("nir08", xr.DataArray(nir, dims=["y", "x"]))
        OPTRAM().compute(cube)
        out = cube.get("optram")
        assert float(out.max()) <= 1.0
        assert float(out.min()) >= 0.0


class TestVegetationIndicesOptram:
    """OPTRAM integration via VegetationIndices."""

    def _make_cube(self):
        np.random.seed(0)
        shape = (10, 10)
        cube = DataCube()
        cube.add("blue", np.random.rand(*shape) * 0.2)
        cube.add("green", np.random.rand(*shape) * 0.3 + 0.05)
        cube.add("red", np.random.rand(*shape) * 0.2 + 0.05)
        cube.add("nir08", np.random.rand(*shape) * 0.5 + 0.1)
        cube.add("swir16", np.random.rand(*shape) * 0.2 + 0.05)
        return cube

    def test_vegetation_indices_with_optram(self):
        from data_engine.surface.vegetation import VegetationIndices
        cube = self._make_cube()
        VegetationIndices(compute_optram=True).compute(cube)
        assert "optram" in cube.bands()
        assert "ndvi" in cube.bands()
        assert "savi" in cube.bands()

    def test_vegetation_indices_without_optram_default(self):
        from data_engine.surface.vegetation import VegetationIndices
        cube = self._make_cube()
        VegetationIndices().compute(cube)
        assert "optram" not in cube.bands()
