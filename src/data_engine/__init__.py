"""data_engine — remote-sensing data engine for Landsat and Sentinel."""

from __future__ import annotations

import contextlib

__version__ = "0.1.0"

# Shared core modules (importable as data_engine.<module>)
from data_engine import (
    calibration,  # ruff: ignore[unused-import]
    core,  # ruff: ignore[unused-import]
    energy_balance,  # ruff: ignore[unused-import]
    et,  # ruff: ignore[unused-import]
    io,  # ruff: ignore[unused-import]
    output,  # ruff: ignore[unused-import]
    preprocess,  # ruff: ignore[unused-import]
    radiation,  # ruff: ignore[unused-import]
    settings,  # ruff: ignore[unused-import]
    surface,  # ruff: ignore[unused-import]
    utils,  # ruff: ignore[unused-import]
    validation,  # ruff: ignore[unused-import]
    weather,  # ruff: ignore[unused-import]
)

# Convenience re-exports
from data_engine.core import DataCube, constants
from data_engine.energy_balance import (
    LatentHeatFlux,
    SensibleHeatFlux,
    SoilHeatFlux,
)
from data_engine.io import LandsatReader, MeteoReader
from data_engine.pipeline import METRICPipeline
from data_engine.preprocess import CloudMask, Resampling
from data_engine.radiation import (
    LongwaveRadiation,
    NetRadiation,
    ShortwaveRadiation,
)
from data_engine.settings import SENTINEL_ROOT
from data_engine.surface import (
    Albedo,
    Emissivity,
    RoughnessLength,
    VegetationIndices,
)

with contextlib.suppress(ImportError):
    from data_engine.landsat import (
        METRICPipeline as LandsatMETRICPipeline,
    )

__all__ = [
    "SENTINEL_ROOT",
    "Albedo",
    "CloudMask",
    "DataCube",
    "Emissivity",
    "LandsatReader",
    "LatentHeatFlux",
    "LongwaveRadiation",
    "LandsatMETRICPipeline",
    "METRICPipeline",
    "MeteoReader",
    "NetRadiation",
    "Resampling",
    "RoughnessLength",
    "SensibleHeatFlux",
    "ShortwaveRadiation",
    "SoilHeatFlux",
    "VegetationIndices",
    "__version__",
    "calibration",
    "constants",
    "core",
    "energy_balance",
    "et",
    "io",
    "output",
    "preprocess",
    "radiation",
    "settings",
    "surface",
    "utils",
    "validation",
    "weather",
]
