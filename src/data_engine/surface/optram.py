"""OPTRAM soil-moisture proxy from Sentinel-2 red/NIR bands."""

import numpy as np

from ..core.datacube import DataCube


class OPTRAM:
    """Optical-path-length-adjusted reflectance model for soil moisture.

    Simplified proxy (no wet-edge calibration):

        optram = sqrt(NIR08 / Red) * (1 - Red / NIR08)

    Clipped to ``[0, 1]``.  NaN for zero-crossing or non-finite inputs.
    """

    def compute(self, cube: DataCube) -> DataCube:
        if "red" not in cube.bands():
            raise ValueError("Missing required band 'red' for OPTRAM")
        if "nir08" not in cube.bands():
            raise ValueError("Missing required band 'nir08' for OPTRAM")

        red = cube.get("red").astype(float)
        nir = cube.get("nir08").astype(float)

        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = nir / red
            optram = np.sqrt(ratio) * (1.0 - red / nir)

        valid = np.isfinite(red) & np.isfinite(nir) & (red != 0) & (nir != 0)
        optram = optram.where(valid, np.nan)
        optram = optram.clip(0.0, 1.0)

        optram.name = "optram"
        optram.attrs = {
            "long_name": "OPTRAM Soil Moisture Proxy",
            "units": "dimensionless",
            "range": "[0, 1]",
            "formula": "sqrt(nir08/red) * (1 - red/nir08)",
        }
        cube.add("optram", optram)
        return cube
