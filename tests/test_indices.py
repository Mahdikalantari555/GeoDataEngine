"""Unit tests for per-scene spectral and stress indices."""

import pytest
import numpy as np
import xarray as xr
from data_engine.core.datacube import DataCube


def _make_cube_with_all_bands(size=20):
    """Create a DataCube with all reflectance + thermal bands + ndvi + lst."""
    np.random.seed(42)
    cube = DataCube()
    shape = (size, size)
    cube.add("blue", np.random.rand(*shape) * 0.2)
    cube.add("green", np.random.rand(*shape) * 0.3 + 0.05)
    cube.add("red", np.random.rand(*shape) * 0.2 + 0.05)
    cube.add("nir08", np.random.rand(*shape) * 0.5 + 0.1)
    cube.add("swir16", np.random.rand(*shape) * 0.2 + 0.05)
    cube.add("swir22", np.random.rand(*shape) * 0.1 + 0.02)
    cube.add("lwir11", np.random.uniform(290, 330, shape))
    # Add ndvi (pre-computed, realistic range)
    red = cube.get("red")
    nir = cube.get("nir08")
    ndvi_vals = ((nir.values - red.values) / (nir.values + red.values)).clip(-1, 1)
    cube.add("ndvi", xr.DataArray(ndvi_vals, dims=nir.dims, coords=nir.coords))
    # Add lst (Kelvin)
    lst_vals = np.random.uniform(290, 330, shape)
    cube.add("lst", xr.DataArray(lst_vals, dims=["y", "x"]))
    return cube


class TestNDMI:
    def test_formula(self):
        from data_engine.surface.moisture import NDMI
        cube = _make_cube_with_all_bands()
        NDMI().compute(cube)
        result = cube.get("ndmi")
        nir = cube.get("nir08").values.astype(float)
        swir = cube.get("swir16").values.astype(float)
        expected = (nir - swir) / (nir + swir)
        assert result.name == "ndmi"
        assert np.allclose(result.values[np.isfinite(expected)],
                           expected[np.isfinite(expected)], rtol=1e-10)

    def test_missing_swir16_raises(self):
        from data_engine.surface.moisture import NDMI
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="swir16"):
            NDMI().compute(cube)

    def test_nan_on_both_zero(self):
        """When both nir and swir are zero, denominator is 0/0 → NaN."""
        from data_engine.surface.moisture import NDMI
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.zeros((5, 5)), dims=["y", "x"]))
        cube.add("swir16", xr.DataArray(np.zeros((5, 5)), dims=["y", "x"]))
        NDMI().compute(cube)
        result = cube.get("ndmi")
        assert np.all(np.isnan(result.values))


class TestMSI:
    def test_dry_soil_msi_gt_1(self):
        from data_engine.surface.moisture import MSI
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.full((10, 10), 0.08), dims=["y", "x"]))
        cube.add("swir16", xr.DataArray(np.full((10, 10), 0.15), dims=["y", "x"]))
        MSI().compute(cube)
        result = cube.get("msi")
        assert result.name == "msi"
        assert np.all(result.values > 1.0)

    def test_missing_swir16_raises(self):
        from data_engine.surface.moisture import MSI
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="swir16"):
            MSI().compute(cube)


class TestNMDI:
    def test_formula(self):
        from data_engine.surface.moisture import NMDI
        cube = _make_cube_with_all_bands()
        NMDI().compute(cube)
        result = cube.get("nmdi")
        nir = cube.get("nir08").values.astype(float)
        swir1 = cube.get("swir16").values.astype(float)
        swir2 = cube.get("swir22").values.astype(float)
        diff = swir1 - swir2
        expected = (nir - diff) / (nir + diff)
        finite = np.isfinite(expected)
        assert result.name == "nmdi"
        assert np.allclose(result.values[finite], expected[finite], rtol=1e-10)

    def test_missing_swir22_raises(self):
        from data_engine.surface.moisture import NMDI
        cube = _make_cube_with_all_bands()
        del cube.data["swir22"]
        with pytest.raises(ValueError, match="swir22"):
            NMDI().compute(cube)


class TestNIRv:
    def test_reads_existing_ndvi(self):
        from data_engine.surface.productivity import NIRv
        cube = _make_cube_with_all_bands()
        ndvi_before = cube.get("ndvi").values.copy()
        NIRv().compute(cube)
        result = cube.get("nirv")
        assert result.name == "nirv"
        assert np.allclose(result.values, ndvi_before * cube.get("nir08").values)
        # ndvi should be unchanged
        assert np.allclose(cube.get("ndvi").values, ndvi_before)

    def test_missing_ndvi_raises(self):
        from data_engine.surface.productivity import NIRv
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="ndvi"):
            NIRv().compute(cube)


class TestGCI:
    def test_dense_vegetation_gci_gt_2(self):
        from data_engine.surface.productivity import GCI
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.full((10, 10), 0.50), dims=["y", "x"]))
        cube.add("green", xr.DataArray(np.full((10, 10), 0.03), dims=["y", "x"]))
        GCI().compute(cube)
        result = cube.get("gci")
        assert result.name == "gci"
        assert np.all(result.values > 2.0)

    def test_zero_green_gives_nan(self):
        from data_engine.surface.productivity import GCI
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.full((5, 5), 0.4), dims=["y", "x"]))
        cube.add("green", xr.DataArray(np.zeros((5, 5)), dims=["y", "x"]))
        GCI().compute(cube)
        result = cube.get("gci")
        assert np.all(np.isnan(result.values))

    def test_missing_green_raises(self):
        from data_engine.surface.productivity import GCI
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="green"):
            GCI().compute(cube)


class TestNDSI:
    def test_saline_soil_positive(self):
        from data_engine.surface.salinity import NDSI
        cube = DataCube()
        cube.add("red", xr.DataArray(np.full((10, 10), 0.30), dims=["y", "x"]))
        cube.add("nir08", xr.DataArray(np.full((10, 10), 0.10), dims=["y", "x"]))
        NDSI().compute(cube)
        result = cube.get("ndsi")
        assert result.name == "ndsi"
        assert np.all(result.values > 0)

    def test_vegetation_negative(self):
        from data_engine.surface.salinity import NDSI
        cube = DataCube()
        cube.add("red", xr.DataArray(np.full((10, 10), 0.05), dims=["y", "x"]))
        cube.add("nir08", xr.DataArray(np.full((10, 10), 0.50), dims=["y", "x"]))
        NDSI().compute(cube)
        result = cube.get("ndsi")
        assert np.all(result.values < 0)

    def test_missing_red_raises(self):
        from data_engine.surface.salinity import NDSI
        cube = DataCube()
        cube.add("nir08", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="red"):
            NDSI().compute(cube)


class TestSIT:
    def test_positive_output(self):
        from data_engine.surface.salinity import SI_T
        cube = DataCube()
        cube.add("red", xr.DataArray(np.full((10, 10), 0.20), dims=["y", "x"]))
        cube.add("swir16", xr.DataArray(np.full((10, 10), 0.15), dims=["y", "x"]))
        SI_T().compute(cube)
        result = cube.get("si_t")
        expected = np.sqrt(0.20 * 0.15)
        assert np.allclose(result.values, expected)
        assert result.name == "si_t"

    def test_non_negative_for_positive_inputs(self):
        from data_engine.surface.salinity import SI_T
        cube = _make_cube_with_all_bands()
        SI_T().compute(cube)
        result = cube.get("si_t")
        valid = np.isfinite(result.values)
        assert np.all(result.values[valid] >= 0)

    def test_missing_swir16_raises(self):
        from data_engine.surface.salinity import SI_T
        cube = DataCube()
        cube.add("red", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="swir16"):
            SI_T().compute(cube)


class TestVSWI:
    def test_formula(self):
        from data_engine.surface.stress import VSWI
        cube = _make_cube_with_all_bands()
        VSWI().compute(cube)
        result = cube.get("vswi")
        ndvi = cube.get("ndvi").values.astype(float)
        lst = cube.get("lst").values.astype(float)
        expected = ndvi / lst
        finite = np.isfinite(expected) & (lst != 0)
        assert result.name == "vswi"
        assert np.allclose(result.values[finite], expected[finite], rtol=1e-10)
        assert result.attrs.get("lst_units") == "K"

    def test_zero_lst_gives_nan(self):
        from data_engine.surface.stress import VSWI
        cube = DataCube()
        cube.add("ndvi", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        cube.add("lst", xr.DataArray(np.zeros((5, 5)), dims=["y", "x"]))
        VSWI().compute(cube)
        result = cube.get("vswi")
        assert np.all(np.isnan(result.values))

    def test_missing_ndvi_raises(self):
        from data_engine.surface.stress import VSWI
        cube = DataCube()
        cube.add("lst", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="ndvi"):
            VSWI().compute(cube)
