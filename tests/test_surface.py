"""
Unit tests for surface validation functions.

Tests NDVI, albedo, and temperature validation.
"""

import pytest
import numpy as np
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class TestNDVICalculation:
    """Test NDVI calculation validation."""
    
    def test_ndvi_calculation_basic(self):
        """Test NDVI from red and NIR."""
        red = 0.1
        nir = 0.5
        
        ndvi = (nir - red) / (nir + red)
        
        # NDVI = (NIR - Red) / (NIR + Red)
        expected = (0.5 - 0.1) / (0.5 + 0.1)
        assert abs(ndvi - expected) < 1e-10
    
    def test_ndvi_positive_values(self):
        """Test NDVI for vegetated pixels."""
        red = 0.1
        nir = 0.5
        
        ndvi = (nir - red) / (nir + red)
        assert 0 < ndvi < 1
    
    def test_ndvi_negative_values(self):
        """Test NDVI for water/non-vegetation."""
        red = 0.3
        nir = 0.1
        
        ndvi = (nir - red) / (nir + red)
        assert -1 < ndvi < 0
    
    def test_ndvi_zero_values(self):
        """Test NDVI when NIR equals Red."""
        red = 0.2
        nir = 0.2
        
        ndvi = (nir - red) / (nir + red)
        assert ndvi == 0
    
    def test_ndvi_range_check(self):
        """Test NDVI range validation."""
        from data_engine.utils.validation import check_ndvi_range
        
        # Valid NDVI
        valid_ndvi = np.random.uniform(-0.2, 0.9, (100, 100))
        is_valid, msg = check_ndvi_range(valid_ndvi)
        assert is_valid is True
        
        # Invalid NDVI (out of range)
        invalid_ndvi = np.array([1.5, 0.5, -0.5])
        is_valid, msg = check_ndvi_range(invalid_ndvi)
        assert is_valid is False


class TestAlbedoCalculation:
    """Test albedo validation."""
    
    def test_albedo_calculation_basic(self):
        """Test albedo calculation formula."""
        blue = 0.1
        red = 0.15
        nir = 0.4
        swir1 = 0.1
        swir2 = 0.05
        
        # Using TMAD coefficients (Collection 2)
        albedo = (0.254 * blue + 0.149 * red + 0.295 * nir + 
                  0.243 * swir1 + 0.091 * swir2 + 0.066)
        
        # Albedo should be between 0 and 1
        assert 0 <= albedo <= 1
    
    def test_albedo_range_check(self):
        """Test albedo range validation."""
        from data_engine.utils.validation import check_albedo_range
        
        # Valid albedo
        valid_albedo = np.random.uniform(0.1, 0.4, (100, 100))
        is_valid, msg = check_albedo_range(valid_albedo)
        assert is_valid is True
        
        # Invalid albedo (out of range)
        invalid_albedo = np.array([1.5, 0.5, 0.2])
        is_valid, msg = check_albedo_range(invalid_albedo)
        assert is_valid is False


class TestTemperatureValidation:
    """Test temperature validation."""
    
    def test_temperature_range_check_valid(self):
        """Test temperature range validation with valid data."""
        from data_engine.utils.validation import check_temperature_range
        
        # Valid temperature values
        valid_temp = np.random.uniform(280, 320, (100, 100))
        is_valid, msg = check_temperature_range(valid_temp)
        assert is_valid is True
    
    def test_temperature_range_check_low(self):
        """Test temperature range validation with too low values."""
        from data_engine.utils.validation import check_temperature_range
        
        # Too cold
        cold_temp = np.array([200, 250, 280])
        is_valid, msg = check_temperature_range(cold_temp)
        assert is_valid is False
    
    def test_temperature_range_check_high(self):
        """Test temperature range validation with too high values."""
        from data_engine.utils.validation import check_temperature_range
        
        # Too hot
        hot_temp = np.array([350, 400, 420])
        is_valid, msg = check_temperature_range(hot_temp)
        assert is_valid is False


class TestCWSILST:
    """Test CWSI_LST index."""

    def _make_cube(self, size=30, seed=0):
        import xarray as xr
        from data_engine.core.datacube import DataCube
        np.random.seed(seed)
        ndvi = np.random.uniform(0.2, 0.9, (size, size))
        lst = 300 - 10 * ndvi + np.random.randn(size, size) * 2
        cube = DataCube()
        cube.add("ndvi", xr.DataArray(ndvi, dims=["y", "x"]))
        cube.add("lst", xr.DataArray(lst, dims=["y", "x"]))
        return cube, ndvi, lst

    def test_cwsi_lst_basic(self):
        from data_engine.surface.stress import CWSILSTCalculator
        cube, _, _ = self._make_cube()
        calc = CWSILSTCalculator()
        result = calc.compute_cwsi_lst(cube.get("lst"), cube.get("ndvi"))
        assert result.name == "cwsi_lst"
        assert result.shape == (30, 30)
        vals = result.values[np.isfinite(result.values)]
        assert vals.size > 0
        assert np.all(vals >= 0) and np.all(vals <= 1)

    def test_cwsi_lst_via_cube(self):
        from data_engine.surface.stress import CWSILSTCalculator
        cube, _, _ = self._make_cube()
        CWSILSTCalculator().compute(cube)
        assert "cwsi_lst" in cube.bands()

    def test_cwsi_lst_missing_band(self):
        import xarray as xr
        from data_engine.core.datacube import DataCube
        from data_engine.surface.stress import CWSILSTCalculator
        cube = DataCube()
        cube.add("ndvi", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="lst"):
            CWSILSTCalculator().compute(cube)

    def test_cwsi_lst_clip_false(self):
        import xarray as xr
        from data_engine.core.datacube import DataCube
        from data_engine.surface.stress import CWSILSTCalculator
        np.random.seed(1)
        ndvi = np.random.uniform(0.2, 0.9, (20, 20))
        lst = 300 - 10 * ndvi + np.random.randn(20, 20) * 2
        # force a few extreme pixels to test clipping
        lst[0, 0] = 350
        lst[1, 1] = 250
        cube = DataCube()
        cube.add("ndvi", xr.DataArray(ndvi, dims=["y", "x"]))
        cube.add("lst", xr.DataArray(lst, dims=["y", "x"]))
        unclipped = CWSILSTCalculator(clip=False).compute_cwsi_lst(cube.get("lst"), cube.get("ndvi"))
        clipped = CWSILSTCalculator(clip=True).compute_cwsi_lst(cube.get("lst"), cube.get("ndvi"))
        # clipped stays in [0, 1]
        cvals = clipped.values[np.isfinite(clipped.values)]
        assert np.min(cvals) >= 0
        assert np.max(cvals) <= 1
        # unclipped has some values outside [0,1] due to extremes
        uvals = unclipped.values[np.isfinite(unclipped.values)]
        assert np.any((uvals < 0) | (uvals > 1))

    def test_cwsi_lst_not_enough_bins(self):
        import xarray as xr
        from data_engine.core.datacube import DataCube
        from data_engine.surface.stress import CWSILSTCalculator
        # ndvi single value -> only 1 bin
        cube = DataCube()
        cube.add("ndvi", xr.DataArray(np.full((5, 5), 0.25), dims=["y", "x"]))
        cube.add("lst", xr.DataArray(np.full((5, 5), 300.0), dims=["y", "x"]))
        with pytest.raises(ValueError, match="Not enough valid NDVI bins"):
            CWSILSTCalculator().compute(cube)


class TestTVDI:
    """Test TVDI index."""

    def _make_cube(self, size=30, seed=0):
        import xarray as xr
        from data_engine.core.datacube import DataCube
        np.random.seed(seed)
        ndvi = np.random.uniform(0.2, 0.9, (size, size))
        lst = 305 - 8 * ndvi + np.random.randn(size, size) * 2
        cube = DataCube()
        cube.add("ndvi", xr.DataArray(ndvi, dims=["y", "x"]))
        cube.add("lst", xr.DataArray(lst, dims=["y", "x"]))
        return cube

    def test_tvdi_basic(self):
        from data_engine.surface.stress import TVDICalculator
        cube = self._make_cube()
        calc = TVDICalculator()
        result = calc.compute_tvdi(cube.get("lst"), cube.get("ndvi"))
        assert result.name == "tvdi"
        assert result.shape == (30, 30)
        vals = result.values[np.isfinite(result.values)]
        assert vals.size > 0
        assert np.all(vals >= 0) and np.all(vals <= 1)
        assert "dry_edge_a" in result.attrs
        assert "dry_edge_b" in result.attrs
        assert "lst_min" in result.attrs

    def test_tvdi_via_cube(self):
        from data_engine.surface.stress import TVDICalculator
        cube = self._make_cube()
        TVDICalculator().compute(cube)
        assert "tvdi" in cube.bands()

    def test_tvdi_missing_band(self):
        import xarray as xr
        from data_engine.core.datacube import DataCube
        from data_engine.surface.stress import TVDICalculator
        cube = DataCube()
        cube.add("lst", xr.DataArray(np.ones((5, 5)), dims=["y", "x"]))
        with pytest.raises(ValueError, match="ndvi"):
            TVDICalculator().compute(cube)

    def test_tvdi_not_enough_bins(self):
        import xarray as xr
        from data_engine.core.datacube import DataCube
        from data_engine.surface.stress import TVDICalculator
        cube = DataCube()
        cube.add("ndvi", xr.DataArray(np.full((5, 5), 0.25), dims=["y", "x"]))
        cube.add("lst", xr.DataArray(np.full((5, 5), 300.0), dims=["y", "x"]))
        with pytest.raises(ValueError, match="Not enough valid NDVI bins"):
            TVDICalculator().compute(cube)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
