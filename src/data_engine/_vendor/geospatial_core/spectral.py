"""Unified spectral index calculations and band statistics."""

from __future__ import annotations

from typing import Any

import numpy as np


def _check_shapes(a: np.ndarray, b: np.ndarray, name: str) -> None:
    if a.shape != b.shape:
        raise ValueError(f"{name} requires equal-shaped inputs, got {a.shape} and {b.shape}")


def ndvi(nir: np.ndarray, red: np.ndarray, nodata: float = np.nan) -> np.ndarray:
    """Normalized Difference Vegetation Index: (NIR - RED) / (NIR + RED)."""
    nir_arr = np.asarray(nir, dtype=np.float64)
    red_arr = np.asarray(red, dtype=np.float64)
    _check_shapes(nir_arr, red_arr, "NDVI")

    denominator = nir_arr + red_arr
    out = np.full_like(denominator, nodata, dtype=np.float64)
    valid_mask = (denominator != 0) & np.isfinite(nir_arr) & np.isfinite(red_arr)
    np.divide(nir_arr - red_arr, denominator, out=out, where=valid_mask)
    return out


def evi(
    nir: np.ndarray,
    red: np.ndarray,
    blue: np.ndarray,
    *,
    g: float = 2.5,
    c1: float = 6.0,
    c2: float = 7.5,
    light: float = 1.0,
    nodata: float = np.nan,
) -> np.ndarray:
    """Enhanced Vegetation Index: G * (NIR - RED) / (NIR + C1 * RED - C2 * BLUE + L)."""
    nir_arr = np.asarray(nir, dtype=np.float64)
    red_arr = np.asarray(red, dtype=np.float64)
    blue_arr = np.asarray(blue, dtype=np.float64)
    _check_shapes(nir_arr, red_arr, "EVI")
    _check_shapes(nir_arr, blue_arr, "EVI")

    denominator = nir_arr + c1 * red_arr - c2 * blue_arr + light
    out = np.full_like(denominator, nodata, dtype=np.float64)
    valid_mask = (
        (denominator != 0)
        & np.isfinite(nir_arr)
        & np.isfinite(red_arr)
        & np.isfinite(blue_arr)
    )
    np.divide(g * (nir_arr - red_arr), denominator, out=out, where=valid_mask)
    return out


def ndwi(green: np.ndarray, nir: np.ndarray, nodata: float = np.nan) -> np.ndarray:
    """Normalized Difference Water Index: (GREEN - NIR) / (GREEN + NIR)."""
    green_arr = np.asarray(green, dtype=np.float64)
    nir_arr = np.asarray(nir, dtype=np.float64)
    _check_shapes(green_arr, nir_arr, "NDWI")

    denominator = green_arr + nir_arr
    out = np.full_like(denominator, nodata, dtype=np.float64)
    valid_mask = (denominator != 0) & np.isfinite(green_arr) & np.isfinite(nir_arr)
    np.divide(green_arr - nir_arr, denominator, out=out, where=valid_mask)
    return out


def savi(
    nir: np.ndarray,
    red: np.ndarray,
    light_coeff: float = 0.5,
    nodata: float = np.nan,
) -> np.ndarray:
    """Soil-Adjusted Vegetation Index: ((NIR - RED) / (NIR + RED + L)) * (1 + L)."""
    nir_arr = np.asarray(nir, dtype=np.float64)
    red_arr = np.asarray(red, dtype=np.float64)
    _check_shapes(nir_arr, red_arr, "SAVI")

    denominator = nir_arr + red_arr + light_coeff
    out = np.full_like(denominator, nodata, dtype=np.float64)
    valid_mask = (denominator != 0) & np.isfinite(red_arr) & np.isfinite(nir_arr)
    np.divide((1.0 + light_coeff) * (nir_arr - red_arr), denominator, out=out, where=valid_mask)
    return out


def compute_spectral_index(
    name: str,
    bands: dict[str, np.ndarray],
    nodata: float = np.nan,
    **kwargs: Any,
) -> np.ndarray:
    """Compute spectral index by name from a dictionary of band arrays."""
    upper = name.upper()
    if upper == "NDVI":
        return ndvi(bands["nir"], bands["red"], nodata=nodata)
    if upper == "EVI":
        return evi(
            bands["nir"],
            bands["red"],
            bands["blue"],
            g=float(kwargs.get("g", 2.5)),
            c1=float(kwargs.get("c1", 6.0)),
            c2=float(kwargs.get("c2", 7.5)),
            light=float(kwargs.get("light", 1.0)),
            nodata=nodata,
        )
    if upper == "NDWI":
        return ndwi(bands["green"], bands["nir"], nodata=nodata)
    if upper == "SAVI":
        light_coeff = float(kwargs.get("light_coeff", kwargs.get("savi_l", 0.5)))
        return savi(bands["nir"], bands["red"], light_coeff=light_coeff, nodata=nodata)
    raise ValueError(f"Unsupported spectral index: '{name}'. Supported: NDVI, EVI, NDWI, SAVI")


def band_statistics(array: np.ndarray) -> dict[str, float]:
    """Compute descriptive statistics for a single-band array."""
    values = np.asarray(array, dtype=np.float64).ravel()
    if values.size == 0:
        return {"count": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0, "p05": 0.0, "p95": 0.0}
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"count": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0, "p05": 0.0, "p95": 0.0}
    return {
        "count": float(finite.size),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "p05": float(np.percentile(finite, 5)),
        "p95": float(np.percentile(finite, 95)),
    }
