"""Basic spectral index generation on the light stack.

NDVI, EVI, SAVI and NDWI are delegated to the vendored engine implementation
(:mod:`data_engine._vendor.geospatial_core.spectral`) so the GUI and the
scientific engine can never drift apart.  OPTRAM is re-implemented here with
plain numpy, mirroring :class:`data_engine.surface.optram.OPTRAM` (which needs
the xarray-based ``DataCube``), because it is a light-stack product for
Sentinel-2 in the GUI.

Only ``numpy`` and ``rasterio`` are imported, both lazily.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import BASIC_INDICES, SENTINEL2, SENTINEL_ONLY_INDICES
from .engine_loader import engine_module
from .layout import (
    build_product_metadata,
    product_metadata_path,
    product_raster_path,
    write_product_metadata,
)

#: Bands each index needs, expressed with the engine's internal band names.
INDEX_BANDS: dict[str, tuple[str, ...]] = {
    "NDVI": ("nir08", "red"),
    "EVI": ("nir08", "red", "blue"),
    "SAVI": ("nir08", "red"),
    "NDWI": ("green", "nir08"),
    "OPTRAM": ("red", "nir08"),
}

#: Scene band names differ from the engine's spectral helper names.
ENGINE_BAND_ALIASES: dict[str, str] = {"nir08": "nir"}

#: Human readable formulas, used by the help dialog and the metadata files.
INDEX_FORMULAS: dict[str, str] = {
    "NDVI": "(NIR - RED) / (NIR + RED)",
    "EVI": "2.5 * (NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1)",
    "SAVI": "((NIR - RED) / (NIR + RED + L)) * (1 + L), L = 0.5",
    "NDWI": "(GREEN - NIR) / (GREEN + NIR)",
    "OPTRAM": "sqrt(NIR / RED) * (1 - RED / NIR), clipped to [0, 1]",
}

INDEX_DESCRIPTIONS: dict[str, str] = {
    "NDVI": "Normalized Difference Vegetation Index — canopy greenness (-1 to 1).",
    "EVI": "Enhanced Vegetation Index — atmosphere-corrected biomass signal.",
    "SAVI": "Soil Adjusted Vegetation Index — NDVI corrected for bare soil.",
    "NDWI": "Normalized Difference Water Index — open water and wet surfaces.",
    "OPTRAM": "Soil moisture proxy from the OPTRAM reflectance model (Sentinel-2).",
}

DEFAULT_SAVI_L = 0.5
DEFAULT_EVI = {"g": 2.5, "c1": 6.0, "c2": 7.5, "light": 1.0}


class SceneIndexError(ValueError):
    """Raised when an index cannot be generated for a scene."""


class UnsupportedIndexError(SceneIndexError):
    """Raised when an index is not available for the selected satellite."""


@dataclass
class GeneratedProduct:
    """A product written to ``products/<name>/``."""

    index: str
    scene_id: str
    raster_path: Path
    metadata_path: Path
    statistics: dict[str, float] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.index} → {self.raster_path.name}"


@dataclass
class SceneInfo:
    """Minimal description of a downloaded scene folder."""

    scene_id: str
    directory: Path
    date: str = ""
    satellite: str = ""
    bands: dict[str, Path] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.directory.name


# ----------------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------------
def discover_bands(scene_dir: Path | str) -> dict[str, Path]:
    """Map internal band names to the GeoTIFFs inside ``scene_dir``."""
    scene_dir = Path(scene_dir)
    if not scene_dir.is_dir():
        raise SceneIndexError(f"Scene directory does not exist: {scene_dir}")
    bands: dict[str, Path] = {}
    for path in sorted(scene_dir.glob("*.tif")):
        bands.setdefault(path.stem.lower(), path)
    return bands


def _read_mtl(scene_dir: Path) -> dict[str, Any]:
    for candidate in sorted(scene_dir.glob("MTL*.json")):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _satellite_from_mtl(mtl: dict[str, Any], scene_dir: Path) -> str:
    platform = str(mtl.get("platform") or "").lower()
    if "sentinel" in platform or scene_dir.name.startswith("sentinel"):
        return SENTINEL2
    return platform


def scene_from_directory(scene_dir: Path | str) -> SceneInfo:
    """Build a :class:`SceneInfo` from a downloaded scene folder."""
    scene_dir = Path(scene_dir)
    mtl = _read_mtl(scene_dir)
    scene_id = (
        mtl.get("item_id")
        or mtl.get("landsat:scene_id")
        or (mtl.get("METADATA", {}).get("PRODUCT_METADATA", {}) or {}).get("LANDSAT_PRODUCT_ID")
        or scene_dir.name
    )
    date = str(mtl.get("datetime") or "")[:10]
    return SceneInfo(
        scene_id=str(scene_id),
        directory=scene_dir,
        date=date,
        satellite=_satellite_from_mtl(mtl, scene_dir),
        bands=discover_bands(scene_dir),
    )


def list_scenes(scenes_root: Path | str) -> list[SceneInfo]:
    """All scene folders under ``<output>/scenes`` that hold band files."""
    scenes_root = Path(scenes_root)
    if not scenes_root.is_dir():
        return []
    scenes: list[SceneInfo] = []
    for sub in sorted(p for p in scenes_root.iterdir() if p.is_dir()):
        if any(sub.glob("*.tif")):
            scenes.append(scene_from_directory(sub))
    return scenes


# ----------------------------------------------------------------------------
# Index availability
# ----------------------------------------------------------------------------
def available_indices(satellite: str) -> list[str]:
    """Indices that can be generated for a satellite."""
    if satellite == SENTINEL2:
        return list(BASIC_INDICES)
    return [name for name in BASIC_INDICES if name not in SENTINEL_ONLY_INDICES]


def validate_index(name: str, satellite: str) -> str:
    """Return the canonical index name, raising if unsupported."""
    upper = str(name).strip().upper()
    if upper not in INDEX_BANDS:
        raise UnsupportedIndexError(
            f"Unknown index '{name}'. Supported: {', '.join(BASIC_INDICES)}"
        )
    if upper in SENTINEL_ONLY_INDICES and satellite != SENTINEL2:
        raise UnsupportedIndexError(f"{upper} is only available for Sentinel-2 scenes")
    return upper


def missing_bands(index: str, bands: dict[str, Path] | dict[str, Any]) -> list[str]:
    """Bands required by ``index`` that are absent from ``bands``."""
    return [band for band in INDEX_BANDS[index.upper()] if band not in bands]


# ----------------------------------------------------------------------------
# Math
# ----------------------------------------------------------------------------
def optram(red: Any, nir: Any, nodata: float = float("nan")) -> Any:
    """OPTRAM soil-moisture proxy, matching ``data_engine.surface.optram``."""
    import numpy as np

    red_arr = np.asarray(red, dtype=np.float64)
    nir_arr = np.asarray(nir, dtype=np.float64)
    if red_arr.shape != nir_arr.shape:
        raise SceneIndexError(
            f"OPTRAM requires equal-shaped inputs, got {red_arr.shape} and {nir_arr.shape}"
        )

    out = np.full_like(red_arr, nodata, dtype=np.float64)
    valid = (
        np.isfinite(red_arr)
        & np.isfinite(nir_arr)
        & (red_arr != 0)
        & (nir_arr != 0)
    )
    np.divide(nir_arr, red_arr, out=out, where=valid)
    result = np.full_like(red_arr, nodata, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        values = np.sqrt(np.abs(out)) * (1.0 - red_arr / np.where(nir_arr == 0, np.nan, nir_arr))
    result[valid] = np.clip(values[valid], 0.0, 1.0)
    return result


def compute_index(
    name: str,
    bands: dict[str, Any],
    *,
    nodata: float = float("nan"),
    params: dict[str, Any] | None = None,
) -> Any:
    """Compute index ``name`` from a ``{band_name: 2-D array}`` mapping."""
    params = params or {}
    upper = str(name).strip().upper()

    if upper == "OPTRAM":
        if "red" not in bands or "nir08" not in bands:
            raise SceneIndexError("OPTRAM requires 'red' and 'nir08' bands")
        return optram(bands["red"], bands["nir08"], nodata=nodata)

    missing = [band for band in INDEX_BANDS.get(upper, ()) if band not in bands]
    if upper not in INDEX_BANDS:
        raise UnsupportedIndexError(f"Unknown index '{name}'")
    if missing:
        raise SceneIndexError(
            f"{upper} requires band(s) {', '.join(missing)} which are not in the scene"
        )

    spectral = engine_module("data_engine._vendor.geospatial_core.spectral")

    engine_bands = {
        ENGINE_BAND_ALIASES.get(key, key): bands[key] for key in INDEX_BANDS[upper]
    }
    kwargs = dict(DEFAULT_EVI) if upper == "EVI" else {}
    if upper == "SAVI":
        kwargs["light_coeff"] = float(params.get("light_coeff", DEFAULT_SAVI_L))
    kwargs.update({k: v for k, v in params.items() if k in kwargs or upper == "EVI"})
    return spectral.compute_spectral_index(upper, engine_bands, nodata=nodata, **kwargs)


# ----------------------------------------------------------------------------
# Raster IO
# ----------------------------------------------------------------------------
def _read_band(path: Path) -> tuple[Any, dict[str, Any]]:
    """Read a single band as float64 with nodata mapped to NaN."""
    import numpy as np
    import rasterio  # noqa: PLC0415

    with rasterio.open(path) as src:
        data = src.read(1, masked=True)
        profile = {
            "crs": src.crs,
            "transform": src.transform,
            "width": src.width,
            "height": src.height,
            "nodata": src.nodata,
        }
    array = np.array(data.filled(np.nan), dtype=np.float64)
    return array, profile


def read_scene_bands(scene: SceneInfo, names: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the requested bands, checking that their grids agree."""
    arrays: dict[str, Any] = {}
    reference: dict[str, Any] | None = None
    for name in names:
        path = scene.bands.get(name)
        if path is None:
            raise SceneIndexError(f"Band '{name}' is missing from scene {scene.scene_id}")
        array, profile = _read_band(path)
        if reference is None:
            reference = profile
        elif array.shape != reference["height"] and array.shape != (
            reference["height"],
            reference["width"],
        ):
            raise SceneIndexError(
                f"Band '{name}' in {scene.scene_id} has grid {array.shape}, "
                f"expected {(reference['height'], reference['width'])}"
            )
        arrays[name] = array
    if reference is None:
        raise SceneIndexError("No bands were requested")
    return arrays, reference


def describe_stats(array: Any) -> dict[str, float]:
    """Compact statistics for the metadata file."""
    import numpy as np

    values = np.asarray(array, dtype=np.float64).ravel()
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"count": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0}
    return {
        "count": float(finite.size),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
    }


def write_raster(path: Path, array: Any, profile: dict[str, Any]) -> Path:
    """Write a float32 GeoTIFF with NaN nodata, matching the source grid."""
    import numpy as np
    import rasterio  # noqa: PLC0415

    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(array, dtype=np.float32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype="float32",
        crs=profile.get("crs"),
        transform=profile.get("transform"),
        nodata=float("nan"),
        compress="lzw",
    ) as dst:
        dst.write(data, 1)
    return path


# ----------------------------------------------------------------------------
# Product generation
# ----------------------------------------------------------------------------
ProgressCallback = Callable[[str], None]


def generate_index(
    scene: SceneInfo,
    index: str,
    output_dir: Path | str,
    *,
    params: dict[str, Any] | None = None,
    progress: ProgressCallback | None = None,
) -> GeneratedProduct:
    """Generate one index for one scene and persist raster + metadata."""
    canonical = validate_index(index, scene.satellite)
    missing = missing_bands(canonical, scene.bands)
    if missing:
        raise SceneIndexError(
            f"{canonical} requires band(s) {', '.join(missing)} which are not in "
            f"scene {scene.scene_id}"
        )

    if progress:
        progress(f"{canonical}: reading {', '.join(INDEX_BANDS[canonical])} from {scene.scene_id}")

    arrays, profile = read_scene_bands(scene, list(INDEX_BANDS[canonical]))
    if progress:
        progress(f"{canonical}: computing index for {scene.scene_id}")
    result = compute_index(canonical, arrays, params=params or {})

    raster_path = product_raster_path(output_dir, canonical.lower(), scene.scene_id)
    write_raster(raster_path, result, profile)
    if progress:
        progress(f"{canonical}: saved {raster_path}")

    stats = describe_stats(result)
    metadata = build_product_metadata(
        product=canonical,
        scene_id=scene.scene_id,
        scene_date=scene.date,
        source_bands=list(INDEX_BANDS[canonical]),
        crs=profile.get("crs"),
        transform=profile.get("transform"),
        width=profile.get("width"),
        height=profile.get("height"),
        params=params or {},
        extra={
            "formula": INDEX_FORMULAS[canonical],
            "statistics": stats,
            "scene_directory": str(scene.directory),
            "satellite": scene.satellite,
        },
    )
    metadata_path = write_product_metadata(
        output_dir, canonical.lower(), scene.scene_id, metadata
    )
    if progress:
        progress(f"{canonical}: metadata → {metadata_path}")

    return GeneratedProduct(
        index=canonical,
        scene_id=scene.scene_id,
        raster_path=raster_path,
        metadata_path=metadata_path,
        statistics=stats,
    )


def generate_indices(
    scene: SceneInfo,
    indices: list[str],
    output_dir: Path | str,
    *,
    params: dict[str, Any] | None = None,
    progress: ProgressCallback | None = None,
) -> list[GeneratedProduct]:
    """Generate each requested index.

    Indices are validated up-front; a failure while generating one aborts the
    whole run (fail-fast) rather than silently skipping it.

    Raises:
        UnsupportedIndexError: If an index is not valid for the scene's
            satellite (validated up-front, before any work is done).
        SceneIndexError: If a required band is missing or generation fails.
    """
    canonical = [validate_index(name, scene.satellite) for name in indices]
    if not canonical:
        raise SceneIndexError("Select at least one index to generate")

    products: list[GeneratedProduct] = []
    for name in canonical:
        products.append(
            generate_index(scene, name, output_dir, params=params, progress=progress)
        )
    return products


__all__ = [
    "DEFAULT_EVI",
    "ENGINE_BAND_ALIASES",
    "DEFAULT_SAVI_L",
    "INDEX_BANDS",
    "INDEX_DESCRIPTIONS",
    "INDEX_FORMULAS",
    "GeneratedProduct",
        "SceneInfo",
    "UnsupportedIndexError",
    "available_indices",
    "compute_index",
    "describe_stats",
    "discover_bands",
    "generate_index",
    "generate_indices",
    "list_scenes",
    "missing_bands",
    "optram",
    "product_metadata_path",
    "read_scene_bands",
    "scene_from_directory",
    "validate_index",
    "write_raster",
]
