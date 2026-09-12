"""data_engine — remote-sensing data engine for Landsat and Sentinel."""

from __future__ import annotations

__version__ = "0.1.0"

# Shared core modules (importable as data_engine.<module>)
from data_engine import (
    calibration,  # noqa: F401
    core,  # noqa: F401
    energy_balance,  # noqa: F401
    et,  # noqa: F401
    io,  # noqa: F401
    output,  # noqa: F401
    preprocess,  # noqa: F401
    radiation,  # noqa: F401
    settings,  # noqa: F401
    surface,  # noqa: F401
    utils,  # noqa: F401
    validation,  # noqa: F401
    weather,  # noqa: F401
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

try:
    from data_engine.landsat import (
        METRICPipeline as LandsatMETRICPipeline,  # noqa: F401
    )
except ImportError:  # sentinel only — landsat is an alias
    pass

__all__ = [
    "SENTINEL_ROOT",
    "Albedo",
    "CloudMask",
    "DataCube",
    "Emissivity",
    "LandsatReader",
    "LatentHeatFlux",
    "LongwaveRadiation",
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
    "constants",
]
