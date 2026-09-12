"""Productivity spectral indices: NIRv, GCI."""

import logging
import numpy as np
import xarray as xr

from ..core.datacube import DataCube

logger = logging.getLogger(__name__)


class NIRv:
    """Near-Infrared Reflectance of Vegetation.

    Formula: NIRv = ndvi * nir08
    Reads existing `ndvi` from the cube; does not recompute.
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "ndvi" not in cube.bands():
            raise ValueError("Missing required band 'ndvi' for NIRv")
        if "nir08" not in cube.bands():
            raise ValueError("Missing required band 'nir08' for NIRv")
        ndvi = cube.get("ndvi").astype(float)
        nir = cube.get("nir08").astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            nirv = ndvi * nir
        nirv = nirv.where(np.isfinite(ndvi) & np.isfinite(nir), np.nan)
        nirv.name = "nirv"
        nirv.attrs = {
            "long_name": "Near-Infrared Reflectance of Vegetation",
            "units": "dimensionless × reflectance",
            "range": "approx [0, 0.5]",
            "formula": "ndvi * nir08",
            "notes": "One of the strongest simple predictors of GPP and biomass",
        }
        cube.add("nirv", nirv)
        return cube


class GCI:
    """Green Chlorophyll Index.

    Formula: GCI = (nir08 / green) - 1
    Useful for chlorophyll and nitrogen status assessment.
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "green" not in cube.bands():
            raise ValueError("Missing required band 'green' for GCI")
        nir = cube.get("nir08").astype(float)
        green = cube.get("green").astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            gci = (nir / green) - 1.0
        gci = gci.where(np.isfinite(nir) & np.isfinite(green) & (green != 0), np.nan)
        gci.name = "gci"
        gci.attrs = {
            "long_name": "Green Chlorophyll Index",
            "units": "dimensionless",
            "formula": "(nir08 / green) - 1",
            "notes": "Useful for chlorophyll and nitrogen status assessment",
        }
        cube.add("gci", gci)
        return cube
