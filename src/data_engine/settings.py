"""Shared settings for data_engine."""

from __future__ import annotations

import os
from pathlib import Path

SENTINEL_ROOT: Path = Path(
    os.environ.get(
        "DATA_ENGINE_SENTINEL_ROOT",
        r"D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel",
    )
)

__all__ = ["SENTINEL_ROOT"]
