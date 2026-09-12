"""Temporal stress indices: TCI, VCI, VHI."""

import logging
import numpy as np
import xarray as xr

from ..core.datacube import DataCube

logger = logging.getLogger(__name__)


class TCI:
    """Temperature Condition Index.

    Formula: TCI = (LST_max - LST) / (LST_max - LST_min)
    Uses the last scene's LST as the instantaneous value.
    Higher values = cooler / less stressed.
    """

    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha

    def compute(self, lst: xr.DataArray, lst_min: xr.DataArray, lst_max: xr.DataArray) -> xr.DataArray:
        with np.errstate(divide="ignore", invalid="ignore"):
            denom = lst_max.values - lst_min.values
            denom = np.where(denom == 0, np.nan, denom)
            tci = (lst_max.values - lst.values) / denom
        tci = np.where(
            np.isfinite(lst.values) & np.isfinite(lst_min.values) & np.isfinite(lst_max.values),
            tci, np.nan
        )
        da = xr.DataArray(tci, dims=lst.dims, coords=lst.coords)
        da.name = "tci"
        da.attrs = {
            "long_name": "Temperature Condition Index",
            "units": "dimensionless",
            "range": "[0, 1]",
            "formula": "(LST_max - LST) / (LST_max - LST_min)",
            "interpretation": "Higher = cooler / less stressed",
        }
        return da

    def compute_from_cube(self, cube: DataCube, lst_current: xr.DataArray) -> DataCube:
        """Convenience: compute TCI using accumulated min/max already on the cube."""
        if "lst_min" not in cube.bands():
            raise ValueError("Missing 'lst_min' on cube")
        if "lst_max" not in cube.bands():
            raise ValueError("Missing 'lst_max' on cube")
        result = self.compute(lst_current, cube.get("lst_min"), cube.get("lst_max"))
        cube.add("tci", result)
        return cube


class VCI:
    """Vegetation Condition Index.

    Formula: VCI = (NDVI - NDVI_min) / (NDVI_max - NDVI_min)
    When NDVI_max == NDVI_min, result is NaN.
    """

    def compute(self, ndvi: xr.DataArray, ndvi_min: xr.DataArray, ndvi_max: xr.DataArray) -> xr.DataArray:
        with np.errstate(divide="ignore", invalid="ignore"):
            denom = ndvi_max.values - ndvi_min.values
            denom = np.where(denom == 0, np.nan, denom)
            vci = (ndvi.values - ndvi_min.values) / denom
        vci = np.where(
            np.isfinite(ndvi.values) & np.isfinite(ndvi_min.values) & np.isfinite(ndvi_max.values),
            vci, np.nan
        )
        da = xr.DataArray(vci, dims=ndvi.dims, coords=ndvi.coords)
        da.name = "vci"
        da.attrs = {
            "long_name": "Vegetation Condition Index",
            "units": "dimensionless",
            "range": "[0, 1]",
            "formula": "(NDVI - NDVI_min) / (NDVI_max - NDVI_min)",
            "interpretation": "0 = worst vegetation condition, 1 = best",
        }
        return da


class VHI:
    """Vegetation Health Index.

    Formula: VHI = alpha * VCI + (1 - alpha) * TCI, default alpha = 0.5.
    Both VCI and TCI must be valid at a pixel for VHI to be valid there.
    """

    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha

    def compute(self, vci: xr.DataArray, tci: xr.DataArray) -> xr.DataArray:
        vci_vals = vci.values.astype(float)
        tci_vals = tci.values.astype(float)
        # Where either is NaN, result is NaN
        with np.errstate(divide="ignore", invalid="ignore"):
            vhi = self.alpha * vci_vals + (1.0 - self.alpha) * tci_vals
        valid = np.isfinite(vci_vals) & np.isfinite(tci_vals)
        vhi = np.where(valid, vhi, np.nan)
        da = xr.DataArray(vhi, dims=vci.dims, coords=vci.coords)
        da.name = "vhi"
        da.attrs = {
            "long_name": "Vegetation Health Index",
            "units": "dimensionless",
            "range": "[0, 1]",
            "formula": f"{self.alpha} * VCI + ({1.0 - self.alpha}) * TCI",
            "alpha": self.alpha,
        }
        return da
