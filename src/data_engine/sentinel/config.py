"""Sentinel-2 processing configuration constants."""

from __future__ import annotations

SENTINEL_COLLECTION: str = "sentinel-2-l2a"
BAND_MAPPING: dict[str, str] = {
    "B02": "blue",
    "B03": "green",
    "B04": "red",
    "B08": "nir",
    "B11": "swir_1",
    "B12": "swir_2",
}
