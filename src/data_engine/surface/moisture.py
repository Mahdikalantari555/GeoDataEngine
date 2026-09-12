"""Moisture spectral indices: NDMI, MSI, NMDI."""

import logging
import numpy as np
import xarray as xr

from ..core.datacube import DataCube

logger = logging.getLogger(__name__)


class NDMI:
    """Normalized Difference Moisture Index.

    Formula: NDMI = (nir08 - swir16) / (nir08 + swir16)
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "swir16" not in cube.bands():
            raise ValueError("Missing required band 'swir16' for NDMI")
        nir = cube.get("nir08").astype(float)
        swir = cube.get("swir16").astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            ndmi = (nir - swir) / (nir + swir)
        ndmi = ndmi.where((np.isfinite(nir)) & (np.isfinite(swir)) & ((nir + swir) != 0), np.nan)
        ndmi.name = "ndmi"
        ndmi.attrs = {
            "long_name": "Normalized Difference Moisture Index",
            "units": "dimensionless",
            "range": "[-1, 1]",
            "formula": "(nir08 - swir16) / (nir08 + swir16)",
        }
        cube.add("ndmi", ndmi)
        return cube


class MSI:
    """Moisture Stress Index.

    Formula: MSI = swir16 / nir08
    Higher values indicate stronger moisture stress.
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "swir16" not in cube.bands():
            raise ValueError("Missing required band 'swir16' for MSI")
        nir = cube.get("nir08").astype(float)
        swir = cube.get("swir16").astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            msi = swir / nir
        msi = msi.where(np.isfinite(nir) & np.isfinite(swir) & (nir != 0), np.nan)
        msi.name = "msi"
        msi.attrs = {
            "long_name": "Moisture Stress Index",
            "units": "dimensionless",
            "interpretation": "Higher values indicate stronger moisture stress",
            "formula": "swir16 / nir08",
        }
        cube.add("msi", msi)
        return cube


class NMDI:
    """Normalized Multi-band Drought Index.

    Formula: NMDI = (nir08 - (swir16 - swir22)) / (nir08 + (swir16 - swir22))
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "swir22" not in cube.bands():
            raise ValueError("Missing required band 'swir22' for NMDI")
        nir = cube.get("nir08").astype(float)
        swir1 = cube.get("swir16").astype(float)
        swir2 = cube.get("swir22").astype(float)
        diff = swir1 - swir2
        with np.errstate(divide="ignore", invalid="ignore"):
            nmdi = (nir - diff) / (nir + diff)
        nmdi = nmdi.where(
            np.isfinite(nir) & np.isfinite(swir1) & np.isfinite(swir2) & ((nir + diff) != 0),
            np.nan
        )
        nmdi.name = "nmdi"
        nmdi.attrs = {
            "long_name": "Normalized Multi-band Drought Index",
            "units": "dimensionless",
            "range": "[-1, 1]",
            "formula": "(nir08 - (swir16 - swir22)) / (nir08 + (swir16 - swir22))",
        }
        cube.add("nmdi", nmdi)
        return cube


class MNDWI:
    """Modified Normalized Difference Water Index.

    Formula: MNDWI = (green - swir16) / (green + swir16)
    Improves water detection, especially in urban areas.
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "green" not in cube.bands():
            raise ValueError("Missing required band 'green' for MNDWI")
        if "swir16" not in cube.bands():
            raise ValueError("Missing required band 'swir16' for MNDWI")
        green = cube.get("green").astype(float)
        swir = cube.get("swir16").astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            mndwi = (green - swir) / (green + swir)
        valid = np.isfinite(green) & np.isfinite(swir) & ((green + swir) != 0)
        mndwi = mndwi.where(valid, np.nan)
        mndwi = mndwi.clip(-1.0, 1.0)
        mndwi.name = "mndwi"
        mndwi.attrs = {
            "long_name": "Modified Normalized Difference Water Index",
            "units": "dimensionless",
            "range": "[-1, 1]",
            "formula": "(green - swir16) / (green + swir16)",
        }
        cube.add("mndwi", mndwi)
        return cube
