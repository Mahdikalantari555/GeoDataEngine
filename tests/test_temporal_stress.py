"""Unit tests for temporal stress indices: TCI, VCI, VHI."""

import pytest
import numpy as np
import xarray as xr
from data_engine.surface.temporal_stress import TCI, VCI, VHI


@pytest.fixture
def sample_arrays():
    """Create sample min/max arrays for testing temporal indices."""
    np.random.seed(0)
    shape = (10, 10)
    ndvi_min = np.random.uniform(0.1, 0.3, shape)
    ndvi_max = ndvi_min + np.random.uniform(0.2, 0.4, shape)
    lst_min = np.random.uniform(285, 295, shape)
    lst_max = lst_min + np.random.uniform(10, 20, shape)
    # Current scene values — deliberately allow some outside [min, max] to test unclamped behavior
    ndvi_current = np.random.uniform(0.2, 0.6, shape)
    lst_current = np.random.uniform(293, 307, shape)

    dims = ["y", "x"]
    coords = {"y": np.arange(shape[0]), "x": np.arange(shape[1])}

    return {
        "ndvi_min": xr.DataArray(ndvi_min, dims=dims, coords=coords),
        "ndvi_max": xr.DataArray(ndvi_max, dims=dims, coords=coords),
        "lst_min": xr.DataArray(lst_min, dims=dims, coords=coords),
        "lst_max": xr.DataArray(lst_max, dims=dims, coords=coords),
        "ndvi_current": xr.DataArray(ndvi_current, dims=dims, coords=coords),
        "lst_current": xr.DataArray(lst_current, dims=dims, coords=coords),
    }


class TestTCI:
    def test_formula(self, sample_arrays):
        tci_calc = TCI()
        result = tci_calc.compute(
            sample_arrays["lst_current"],
            sample_arrays["lst_min"],
            sample_arrays["lst_max"],
        )
        lst = sample_arrays["lst_current"].values.astype(float)
        lst_min = sample_arrays["lst_min"].values.astype(float)
        lst_max = sample_arrays["lst_max"].values.astype(float)
        expected = (lst_max - lst) / (lst_max - lst_min)
        finite = np.isfinite(expected) & (np.abs(lst_max - lst_min) > 1e-12)
        assert result.name == "tci"
        assert np.allclose(result.values[finite], expected[finite], rtol=1e-10)

    def test_zero_denominator_gives_nan(self):
        """When lst_max == lst_min everywhere, TCI should be NaN."""
        shape = (5, 5)
        lst = xr.DataArray(np.full(shape, 300.0), dims=["y", "x"])
        lst_min = xr.DataArray(np.full(shape, 300.0), dims=["y", "x"])
        lst_max = xr.DataArray(np.full(shape, 300.0), dims=["y", "x"])
        result = TCI().compute(lst, lst_min, lst_max)
        assert np.all(np.isnan(result.values))

    def test_bounds_case_current_at_max(self, sample_arrays):
        """When current LST equals lst_max, TCI should be 0."""
        shape = (5, 5)
        lst_max = xr.DataArray(np.full(shape, 320.0), dims=["y", "x"])
        lst_min = xr.DataArray(np.full(shape, 290.0), dims=["y", "x"])
        lst_current = xr.DataArray(np.full(shape, 320.0), dims=["y", "x"])
        result = TCI().compute(lst_current, lst_min, lst_max)
        assert np.allclose(result.values, 0.0)

    def test_bounds_case_current_at_min(self, sample_arrays):
        """When current LST equals lst_min, TCI should be 1."""
        shape = (5, 5)
        lst_max = xr.DataArray(np.full(shape, 320.0), dims=["y", "x"])
        lst_min = xr.DataArray(np.full(shape, 290.0), dims=["y", "x"])
        lst_current = xr.DataArray(np.full(shape, 290.0), dims=["y", "x"])
        result = TCI().compute(lst_current, lst_min, lst_max)
        assert np.allclose(result.values, 1.0)


class TestVCI:
    def test_formula(self, sample_arrays):
        vci_calc = VCI()
        result = vci_calc.compute(
            sample_arrays["ndvi_current"],
            sample_arrays["ndvi_min"],
            sample_arrays["ndvi_max"],
        )
        ndvi = sample_arrays["ndvi_current"].values.astype(float)
        ndvi_min = sample_arrays["ndvi_min"].values.astype(float)
        ndvi_max = sample_arrays["ndvi_max"].values.astype(float)
        expected = (ndvi - ndvi_min) / (ndvi_max - ndvi_min)
        finite = np.isfinite(expected) & (np.abs(ndvi_max - ndvi_min) > 1e-12)
        assert result.name == "vci"
        assert np.allclose(result.values[finite], expected[finite], rtol=1e-10)

    def test_zero_variation_gives_nan(self):
        """When ndvi_max == ndvi_min, VCI should be NaN."""
        shape = (5, 5)
        ndvi = xr.DataArray(np.full(shape, 0.5), dims=["y", "x"])
        ndvi_min = xr.DataArray(np.full(shape, 0.5), dims=["y", "x"])
        ndvi_max = xr.DataArray(np.full(shape, 0.5), dims=["y", "x"])
        result = VCI().compute(ndvi, ndvi_min, ndvi_max)
        assert np.all(np.isnan(result.values))

    def test_bounds_case_current_at_max(self, sample_arrays):
        """When current NDVI equals ndvi_max, VCI should be 1."""
        shape = (5, 5)
        ndvi_max = xr.DataArray(np.full(shape, 0.8), dims=["y", "x"])
        ndvi_min = xr.DataArray(np.full(shape, 0.2), dims=["y", "x"])
        ndvi_current = xr.DataArray(np.full(shape, 0.8), dims=["y", "x"])
        result = VCI().compute(ndvi_current, ndvi_min, ndvi_max)
        assert np.allclose(result.values, 1.0)

    def test_bounds_case_current_at_min(self, sample_arrays):
        """When current NDVI equals ndvi_min, VCI should be 0."""
        shape = (5, 5)
        ndvi_max = xr.DataArray(np.full(shape, 0.8), dims=["y", "x"])
        ndvi_min = xr.DataArray(np.full(shape, 0.2), dims=["y", "x"])
        ndvi_current = xr.DataArray(np.full(shape, 0.2), dims=["y", "x"])
        result = VCI().compute(ndvi_current, ndvi_min, ndvi_max)
        assert np.allclose(result.values, 0.0)


class TestVHI:
    def test_formula(self, sample_arrays):
        vhi_calc = VHI(alpha=0.5)
        vci_result = VCI().compute(
            sample_arrays["ndvi_current"],
            sample_arrays["ndvi_min"],
            sample_arrays["ndvi_max"],
        )
        tci_result = TCI().compute(
            sample_arrays["lst_current"],
            sample_arrays["lst_min"],
            sample_arrays["lst_max"],
        )
        result = vhi_calc.compute(vci_result, tci_result)
        expected = 0.5 * vci_result.values + 0.5 * tci_result.values
        finite = np.isfinite(expected)
        assert result.name == "vhi"
        assert np.allclose(result.values[finite], expected[finite], rtol=1e-10)

    def test_vhi_nan_where_either_input_nan(self):
        """VHI should be NaN wherever VCI or TCI is NaN."""
        shape = (5, 5)
        vci = xr.DataArray(np.ones(shape), dims=["y", "x"])
        tci = xr.DataArray(np.ones(shape), dims=["y", "x"])
        vci.values[0, 0] = np.nan
        tci.values[1, 1] = np.nan
        result = VHI(alpha=0.5).compute(vci, tci)
        assert np.isnan(result.values[0, 0])
        assert np.isnan(result.values[1, 1])
        assert np.isfinite(result.values[2, 2])

    def test_default_alpha_is_0_5(self):
        assert VHI().alpha == 0.5

    def test_custom_alpha(self):
        vhi_calc = VHI(alpha=0.3)
        shape = (5, 5)
        vci = xr.DataArray(np.ones(shape), dims=["y", "x"])
        tci = xr.DataArray(np.ones(shape) * 2, dims=["y", "x"])
        result = vhi_calc.compute(vci, tci)
        expected = 0.3 * 1.0 + 0.7 * 2.0
        assert np.allclose(result.values, expected)
