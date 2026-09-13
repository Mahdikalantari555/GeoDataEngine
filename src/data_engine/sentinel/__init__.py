"""Sentinel-2 processing domain."""

from __future__ import annotations

import os
from pathlib import Path


def _raise_sentinel_unavailable() -> None:
    raise ImportError(
        "data_engine.sentinel is not available. "
        "The sentinel source directory cannot be reached. "
        "Set DATA_ENGINE_SENTINEL_ROOT to a valid Sentinel asset path."
    )


_sentinel_root = Path(os.environ.get("DATA_ENGINE_SENTINEL_ROOT", ""))
if not _sentinel_root.is_dir():
    _raise_sentinel_unavailable()

if not (_sentinel_root / "pipeline.py").is_file() or not (_sentinel_root / "config.py").is_file():
    _raise_sentinel_unavailable()

# Import the copied Sentinel sources when the asset root is valid.
from .config import BAND_MAPPING, SENTINEL_COLLECTION
from .pipeline import SentinelFetcher, SentinelPipeline

__all__ = [
    "BAND_MAPPING",
    "SENTINEL_COLLECTION",
    "SentinelFetcher",
    "SentinelPipeline",
]
