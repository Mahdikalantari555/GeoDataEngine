"""Salinity spectral indices: NDSI, SI_T."""

import logging
import numpy as np
import xarray as xr

from ..core.datacube import DataCube

logger = logging.getLogger(__name__)


class NDSI:
    """Normalized Difference Salinity Index.

    Formula: NDSI = (red - nir08) / (red + nir08)
    Positive values indicate saline/urban surfaces; negative values indicate healthy vegetation.
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "red" not in cube.bands():
            raise ValueError("Missing required band 'red' for NDSI")
        red = cube.get("red").astype(float)
        nir = cube.get("nir08").astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            ndsi = (red - nir) / (red + nir)
        ndsi = ndsi.where(np.isfinite(red) & np.isfinite(nir) & ((red + nir) != 0), np.nan)
        ndsi.name = "ndsi"
        ndsi.attrs = {
            "long_name": "Normalized Difference Salinity Index",
            "units": "dimensionless",
            "range": "[-1, 1]",
            "formula": "(red - nir08) / (red + nir08)",
            "interpretation": "Positive = saline/urban; Negative = healthy vegetation",
        }
        cube.add("ndsi", ndsi)
        return cube


class SI_T:
    """Soil Salinity Index (geometric mean variant).

    Formula: SI_T = sqrt(red * swir16)
    More useful for agricultural soils than NDSI.
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "swir16" not in cube.bands():
            raise ValueError("Missing required band 'swir16' for SI_T")
        red = cube.get("red").astype(float)
        swir = cube.get("swir16").astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            si_t = np.sqrt(red * swir)
        si_t = si_t.where(np.isfinite(red) & np.isfinite(swir), np.nan)
        si_t.name = "si_t"
        si_t.attrs = {
            "long_name": "Soil Salinity Index (geometric mean variant)",
            "units": "reflectance-scaled",
            "formula": "sqrt(red * swir16)",
            "interpretation": "More useful for agricultural soils than NDSI",
        }
        cube.add("si_t", si_t)
        return cube
