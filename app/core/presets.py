"""METRIC output presets — gated behind "Enable full processing".

The presets mirror ``OUTPUT_PRESETS`` / ``OUTPUT_PRODUCTS`` from
``data_engine.config.settings``.  A local copy is kept so the GUI can render
the preset and product names without importing the heavy scientific stack;
``tests/gui/test_presets.py`` asserts the copy stays identical to the engine.

Execution goes through :class:`MetricRunner`, which the app binds to the real
``METRICPipeline`` once the heavy dependencies are installed. Tests inject a
fake runner, so nothing here needs scipy/pandas/xarray.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .indices import SceneInfo
from .layout import (
    build_product_metadata,
    product_raster_path,
    write_product_metadata,
)

# ---------------------------------------------------------------------------
# Mirrors of data_engine.config.settings (verified by tests)
# ---------------------------------------------------------------------------
OUTPUT_PRODUCT_NAMES: dict[str, tuple[str, ...]] = {
    "et_core": ("ETaDaily", "ETinst", "ETrF", "LE"),
    "energy_balance": ("Rn", "G", "H"),
    "quality": ("ETqualityClass", "ETaClassified"),
    "surface_props": ("NDVI", "EVI", "LAI", "FVC", "SAVI", "Albedo", "LST", "Emissivity"),
    "radiation": ("Rns", "Rnl", "RsDown", "RlDown", "RlUp"),
    "spectral_indices": (
        "NDVI",
        "SAVI",
        "EVI",
        "NDMI",
        "MSI",
        "NMDI",
        "MNDWI",
        "NIRv",
        "GCI",
        "NDSI",
        "SI_T",
    ),
    "stress_indices": ("CWSI_ET", "CWSI_LST", "TVDI", "VSWI", "TCI", "VCI", "VHI"),
}

#: Band-name-in-cube for every product, used to pull results out of the pipeline.
PRODUCT_BANDS: dict[str, str] = {
    "ETaDaily": "ET_daily",
    "ETinst": "ET_inst",
    "ETrF": "ETrF",
    "LE": "LE",
    "Rn": "R_n",
    "G": "G",
    "H": "H",
    "ETqualityClass": "ET_quality_class",
    "ETaClassified": "ETa_class",
    "NDVI": "ndvi",
    "EVI": "evi",
    "LAI": "lai",
    "FVC": "fvc",
    "SAVI": "savi",
    "Albedo": "albedo",
    "LST": "lst",
    "Emissivity": "emissivity",
    "Rns": "R_ns",
    "Rnl": "R_nl",
    "RsDown": "Rs_down",
    "RlDown": "R_l_down",
    "RlUp": "R_l_up",
    "NDMI": "ndmi",
    "MSI": "msi",
    "NMDI": "nmdi",
    "MNDWI": "mndwi",
    "NIRv": "nirv",
    "GCI": "gci",
    "NDSI": "ndsi",
    "SI_T": "si_t",
    "CWSI_ET": "CWSI_ET",
    "CWSI_LST": "cwsi_lst",
    "TVDI": "tvdi",
    "VSWI": "vswi",
    "TCI": "tci",
    "VCI": "vci",
    "VHI": "vhi",
}

PRESET_CATEGORIES: dict[str, tuple[str, ...]] = {
    "minimal": ("et_core",),
    "standard": ("et_core", "energy_balance", "surface_props"),
    "full": tuple(OUTPUT_PRODUCT_NAMES.keys()),
}

#: Integer dtypes for classification products.
INTEGER_PRODUCTS = {"ETqualityClass": "uint8", "ETaClassified": "uint8"}

METRIC_SATELLITES = ("landsat-8", "landsat-9")


class FullProcessingRequiredError(RuntimeError):
    """Raised when a METRIC preset is requested in lite mode."""


class PresetError(ValueError):
    """Raised for unknown presets or products."""


class MetricRunner(Protocol):
    """Callable that runs the engine pipeline for one scene."""

    def __call__(
        self, scene: SceneInfo, output_categories: list[str], destination: Path | str
    ) -> dict[str, Any]: ...


@dataclass
class PresetRun:
    """Outcome of a METRIC preset run."""

    preset: str
    scene_id: str
    categories: list[str]
    products: list[str]
    written: list[Path]

    @property
    def summary(self) -> str:
        return f"{self.preset}: {len(self.written)} product(s) from {len(self.products)} requested"


def engine_presets() -> dict[str, list[str]]:
    """Return ``OUTPUT_PRESETS`` from the engine when it is importable."""
    try:
        from data_engine.config.settings import OUTPUT_PRESETS  # noqa: PLC0415
    except Exception:  # heavy stack or partial install
        return {name: list(cats) for name, cats in PRESET_CATEGORIES.items()}
    return {name: list(cats) for name, cats in OUTPUT_PRESETS.items()}


def preset_categories(preset: str) -> list[str]:
    """Categories implied by a preset name."""
    name = str(preset).strip().lower()
    if name not in PRESET_CATEGORIES:
        raise PresetError(
            f"Unknown preset '{preset}'. Available: {', '.join(PRESET_CATEGORIES)}"
        )
    return list(PRESET_CATEGORIES[name])


def preset_products(preset: str) -> list[str]:
    """Output product names produced by a preset (flattened, ordered)."""
    products: list[str] = []
    for category in preset_categories(preset):
        for product in OUTPUT_PRODUCT_NAMES[category]:
            if product not in products:
                products.append(product)
    return products


def preset_product_map(preset: str) -> dict[str, str]:
    """``{output_product_name: cube_band_name}`` for a preset."""
    return {product: PRODUCT_BANDS[product] for product in preset_products(preset)}


def require_full_mode(enabled: bool) -> None:
    """Raise :class:`FullProcessingRequiredError` when METRIC is not enabled."""
    if not enabled:
        raise FullProcessingRequiredError(
            "Full processing is not enabled. Install the heavy dependencies with "
            "'Enable full processing' in the Settings tab to run METRIC presets."
        )


def validate_preset_request(preset: str, satellite: str, full_enabled: bool) -> list[str]:
    """Validate a preset request and return the categories to run."""
    categories = preset_categories(preset)
    require_full_mode(full_enabled)
    if satellite and satellite not in METRIC_SATELLITES:
        raise PresetError(
            "METRIC presets currently run on Landsat scenes only "
            f"(scene satellite: {satellite or 'unknown'})."
        )
    return categories


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def _array_and_profile(data: Any) -> tuple[Any, dict[str, Any]]:
    """Extract a 2-D array and raster profile from an xarray DataArray-like."""
    import numpy as np

    array = np.asarray(getattr(data, "values", data), dtype=np.float64)
    if array.ndim > 2:
        array = np.squeeze(array)
    profile: dict[str, Any] = {"crs": None, "transform": None}

    rio = getattr(data, "rio", None)
    if rio is not None:
        try:
            profile["crs"] = rio.crs
            profile["transform"] = rio.transform()
        except Exception:  # missing rio metadata on a synthetic array
            pass
    if profile["transform"] is None:
        attrs = getattr(data, "attrs", {}) or {}
        profile["transform"] = attrs.get("transform")
        profile["crs"] = attrs.get("crs") or profile["crs"]
    return array, profile


def write_product_raster(
    output_dir: Path | str,
    product: str,
    scene_id: str,
    data: Any,
) -> Path:
    """Write one pipeline product to ``products/<product>/<scene>.tif``."""
    import numpy as np
    import rasterio  # noqa: PLC0415

    array, profile = _array_and_profile(data)
    path = product_raster_path(output_dir, product, scene_id)
    dtype = INTEGER_PRODUCTS.get(product, "float32")
    overflow = float(np.nanmax(array)) if np.isfinite(array).any() else 0.0
    if dtype == "uint8" and overflow > 255:
        dtype = "float32"

    payload = array.astype(dtype)
    nodata = None if dtype == "uint8" else float("nan")
    if dtype == "uint8":
        payload = np.nan_to_num(payload, nan=0.0).astype("uint8")

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=payload.shape[0],
        width=payload.shape[1],
        count=1,
        dtype=dtype,
        crs=profile.get("crs"),
        transform=profile.get("transform"),
        nodata=nodata,
        compress="lzw",
    ) as dst:
        dst.write(payload, 1)
    return path


def write_preset_products(
    scene: SceneInfo,
    preset: str,
    results: dict[str, Any],
    output_dir: Path | str,
) -> list[Path]:
    """Persist the products present in ``results`` for ``preset``.

    Products the pipeline did not produce (e.g. quality layer without
    calibration) are skipped instead of aborting the whole preset.
    """
    product_map = preset_product_map(preset)
    written: list[Path] = []
    for product, band in product_map.items():
        data = results.get(band)
        if data is None:
            data = results.get(product)
        if data is None:
            continue
        path = write_product_raster(output_dir, product, scene.scene_id, data)
        array, profile = _array_and_profile(data)
        metadata = build_product_metadata(
            product=product,
            scene_id=scene.scene_id,
            scene_date=scene.date,
            source_bands=[band],
            crs=profile.get("crs"),
            transform=profile.get("transform"),
            width=int(array.shape[1]) if array.ndim == 2 else None,
            height=int(array.shape[0]) if array.ndim == 2 else None,
            params={"preset": preset},
            extra={
                "cube_band": band,
                "scene_directory": str(scene.directory),
                "generator": "METRIC preset",
            },
        )
        write_product_metadata(output_dir, product, scene.scene_id, metadata)
        written.append(path)
    return written


def run_preset(
    scene: SceneInfo,
    preset: str,
    output_dir: Path | str,
    *,
    full_enabled: bool,
    runner: MetricRunner | None = None,
    progress: Callable[[str], None] | None = None,
) -> PresetRun:
    """Run a METRIC preset for one scene.

    Args:
        scene: Scene to process.
        preset: ``minimal``, ``standard`` or ``full``.
        output_dir: Root output folder (products go under ``products/``).
        full_enabled: Whether heavy dependencies are installed.
        runner: Injected pipeline runner; defaults to :class:`DefaultMetricRunner`.
        progress: Optional log sink.

    Raises:
        FullProcessingRequiredError: In lite mode.
        PresetError: For unknown presets or non-Landsat scenes.
        PresetError: When no products could be written.
    """
    categories = validate_preset_request(preset, scene.satellite, full_enabled)
    member = runner if runner is not None else DefaultMetricRunner()

    if progress:
        progress(f"METRIC preset '{preset}': categories {', '.join(categories)}")
    results = member(scene, categories, output_dir)
    if not isinstance(results, dict):
        raise PresetError("METRIC runner returned no product dictionary")

    written = write_preset_products(scene, preset, results, output_dir)
    if progress:
        progress(f"METRIC preset '{preset}': wrote {len(written)} product(s)")
    if not written:
        raise PresetError(
            f"METRIC preset '{preset}' produced no products for scene {scene.scene_id}"
        )

    return PresetRun(
        preset=preset,
        scene_id=scene.scene_id,
        categories=categories,
        products=preset_products(preset),
        written=written,
    )


class DefaultMetricRunner:
    """Runs the real engine pipeline (requires the full dependency set)."""

    def __init__(
        self,
        *,
        meteo_path: str | Path | None = None,
        meteo_data: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        roi_path: str | None = None,
    ) -> None:
        self.meteo_path = Path(meteo_path) if meteo_path else None
        self.meteo_data = meteo_data
        self.config = config or {}
        self.roi_path = roi_path

    def _weather(self) -> dict[str, Any]:
        if self.meteo_data:
            return self.meteo_data
        if self.meteo_path is None:
            raise PresetError(
                "METRIC processing needs meteorological input. "
                "Select a weather CSV in the Settings tab."
            )
        try:
            from data_engine.io.meteo_reader import read_weather_data  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - full mode only
            raise PresetError(f"Cannot load the weather reader: {exc}") from exc
        reader = read_weather_data(str(self.meteo_path))
        return getattr(reader, "data", None) or getattr(reader, "interpolate", lambda *_: {})()

    def __call__(
        self, scene: SceneInfo, output_categories: list[str], destination: Path | str
    ) -> dict[str, Any]:
        try:
            from data_engine.pipeline import METRICPipeline  # noqa: PLC0415
        except Exception as exc:  # pragma: no cover - full mode only
            raise PresetError(
                f"METRIC pipeline is unavailable: {exc}. Enable full processing first."
            ) from exc

        pipeline = METRICPipeline(config=dict(self.config), roi_path=self.roi_path)
        results = pipeline.run(
            landsat_dir=str(scene.directory),
            meteo_data=self._weather(),
            output_dir=None,
            roi_path=self.roi_path,
            output_categories=list(output_categories),
        )
        return dict(results or {})


def preset_help_entries() -> list[tuple[str, list[str]]]:
    """``[(preset, [product names])]`` for the help dialog."""
    return [
        (preset, preset_products(preset))
        for preset in ("minimal", "standard", "full")
    ]


__all__ = [
    "INTEGER_PRODUCTS",
    "METRIC_SATELLITES",
    "OUTPUT_PRODUCT_NAMES",
    "PRESET_CATEGORIES",
    "PRODUCT_BANDS",
    "DefaultMetricRunner",
    "FullProcessingRequiredError",
    "MetricRunner",
    "PresetError",
    "PresetRun",
    "engine_presets",
    "preset_categories",
    "preset_help_entries",
    "preset_product_map",
    "preset_products",
    "require_full_mode",
    "run_preset",
    "validate_preset_request",
    "write_preset_products",
    "write_product_raster",
]
