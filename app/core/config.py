"""Application paths and session state.

Everything the GUI persists lives next to the application in ``config.json``;
everything it produces lives under the user selected output directory in a
``scenes/`` + ``products/`` layout.  Both are defined here so the rest of the
core can stay free of path arithmetic.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.json"
VENV_DIRNAME = ".venv"
SCENES_DIRNAME = "scenes"
PRODUCTS_DIRNAME = "products"
METADATA_DIRNAME = "metadata"

#: Satellite identifiers understood by the GUI.
LANDSAT8 = "landsat-8"
LANDSAT9 = "landsat-9"
SENTINEL2 = "sentinel-2"

SATELLITES: tuple[str, ...] = (LANDSAT8, LANDSAT9, SENTINEL2)

#: Presets exposed in the Indices tab (mirrors ``OUTPUT_PRESETS`` in
#: ``data_engine.config.settings`` but duplicated so the GUI never needs the
#: heavy stack to render a label).
PRESET_NAMES: tuple[str, ...] = ("minimal", "standard", "full")

#: Basic indices that work on the light stack.
BASIC_INDICES: tuple[str, ...] = ("NDVI", "EVI", "SAVI", "NDWI", "OPTRAM")

#: Indices restricted to a single satellite.
SENTINEL_ONLY_INDICES: tuple[str, ...] = ("OPTRAM",)

#: Sorting options offered in the Search tab.
SORT_OPTIONS: tuple[str, ...] = ("date", "cloud_cover")

DEFAULT_MIRROR_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"


def app_dir() -> Path:
    """Directory the app runs from.

    For a PyInstaller build this is the folder holding the executable (the
    portable-folder distribution), otherwise the repository/app folder.
    """
    import sys

    if getattr(sys, "frozen", False):  # pragma: no cover - packaging specific
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def default_output_dir() -> Path:
    """Default location for downloaded scenes and generated products."""
    return app_dir() / "GeoDataEngine_out"


@dataclass
class AppConfig:
    """Persisted session settings.

    Unknown keys found in ``config.json`` are preserved on save so newer
    versions of the app never lose a setting when an older build writes the
    file (the migration plan calls for forward-compatible additive keys).
    """

    roi_path: str = ""
    start_date: str = ""
    end_date: str = ""
    output_dir: str = field(default_factory=lambda: str(default_output_dir()))
    cloud_threshold: float = 20.0
    min_coverage_ratio: float = 0.55
    satellite: str = LANDSAT8
    sort_by: str = "date"
    mirror_url: str = DEFAULT_MIRROR_URL
    crs_override: str = ""
    selected_indices: list[str] = field(default_factory=lambda: list(BASIC_INDICES[:4]))
    preset: str = "minimal"
    mode: str = "lite"
    last_band: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def normalized(self) -> AppConfig:
        """Return a copy with out-of-range/invalid values coerced to defaults."""
        cfg = copy.deepcopy(self)
        try:
            cfg.cloud_threshold = min(100.0, max(0.0, float(cfg.cloud_threshold)))
        except (TypeError, ValueError):
            cfg.cloud_threshold = 20.0
        try:
            cfg.min_coverage_ratio = min(1.0, max(0.0, float(cfg.min_coverage_ratio)))
        except (TypeError, ValueError):
            cfg.min_coverage_ratio = 0.55
        if cfg.satellite not in SATELLITES:
            cfg.satellite = LANDSAT8
        if cfg.sort_by not in SORT_OPTIONS:
            cfg.sort_by = "date"
        if cfg.mode not in ("lite", "full"):
            cfg.mode = "lite"
        cfg.selected_indices = [i.upper() for i in cfg.selected_indices if i.upper() in BASIC_INDICES]
        if cfg.preset not in PRESET_NAMES:
            cfg.preset = "minimal"
        return cfg

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data = {
            "roi_path": self.roi_path,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "output_dir": self.output_dir,
            "cloud_threshold": self.cloud_threshold,
            "min_coverage_ratio": self.min_coverage_ratio,
            "satellite": self.satellite,
            "sort_by": self.sort_by,
            "mirror_url": self.mirror_url,
            "crs_override": self.crs_override,
            "selected_indices": list(self.selected_indices),
            "preset": self.preset,
            "mode": self.mode,
            "last_band": self.last_band,
        }
        data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AppConfig:
        data = dict(data or {})
        known = set(cls.__dataclass_fields__) - {"extra"}
        kwargs: dict[str, Any] = {}
        for key in known:
            if key in data:
                kwargs[key] = data[key]
        extra = {k: v for k, v in data.items() if k not in known}
        cfg = cls(**kwargs)
        cfg.extra = extra
        return cfg.normalized()

    # ------------------------------------------------------------------
    # Derived paths
    # ------------------------------------------------------------------
    @property
    def scenes_dir(self) -> Path:
        return Path(self.output_dir) / SCENES_DIRNAME

    @property
    def products_dir(self) -> Path:
        return Path(self.output_dir) / PRODUCTS_DIRNAME

    def date_range(self) -> tuple[str, str]:
        return (self.start_date, self.end_date)


class ConfigStore:
    """Load/save :class:`AppConfig` as JSON in the application directory."""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory is not None else app_dir()

    @property
    def path(self) -> Path:
        return self.directory / CONFIG_FILENAME

    def load(self) -> AppConfig:
        """Load config, falling back to defaults for missing/corrupt files."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return AppConfig().normalized()
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return AppConfig().normalized()
        if not isinstance(data, dict):
            return AppConfig().normalized()
        return AppConfig.from_dict(data)

    def save(self, config: AppConfig) -> Path:
        """Persist ``config`` atomically and return the written path."""
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(config.to_dict(), indent=2, ensure_ascii=False)
        tmp_path = self.path.with_suffix(".json.tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        tmp_path.replace(self.path)
        return self.path

    def venv_dir(self) -> Path:
        return self.directory / VENV_DIRNAME


def _is_windows() -> bool:
    return os.name == "nt"


def venv_python(venv_dir: Path | str) -> Path:
    """Path of the Python interpreter inside a virtual environment."""
    venv_dir = Path(venv_dir)
    if _is_windows():  # pragma: no cover - platform specific
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


__all__ = [
    "BASIC_INDICES",
    "CONFIG_FILENAME",
    "DEFAULT_MIRROR_URL",
    "LANDSAT8",
    "LANDSAT9",
    "METADATA_DIRNAME",
    "PRESET_NAMES",
    "PRODUCTS_DIRNAME",
    "SATELLITES",
    "SCENES_DIRNAME",
    "SENTINEL2",
    "SENTINEL_ONLY_INDICES",
    "SORT_OPTIONS",
    "AppConfig",
    "ConfigStore",
    "app_dir",
    "default_output_dir",
    "venv_python",
]
