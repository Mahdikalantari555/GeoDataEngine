"""STAC search helpers for the Search tab.

The engine fetchers (:mod:`data_engine.io.planetary_computer_fetcher`) already
talk to the Planetary Computer STAC API and clip downloads to a region of
interest.  This module adds the two things the GUI needs on top of them:

* a satellite → fetcher factory, and
* a coverage filter that keeps only scenes whose footprint covers at least
  ``min_coverage_ratio`` of the ROI (the requirement behind "show only scenes
  with full ROI coverage").
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .config import LANDSAT8, LANDSAT9, SENTINEL2
from .engine_loader import engine_module
from .roi import ROI, ROIError

#: Minimum acceptable value for the coverage ratio exposed in the UI.
MIN_COVERAGE_FLOOR = 0.5


@dataclass
class SceneSummary:
    """One row of the search results table."""

    id: str
    date: str
    cloud_cover: float
    platform: str
    path: str | int | None
    row: str | int | None
    coverage_ratio: float
    satellite: str
    geometry: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def full_coverage(self) -> bool:
        return self.coverage_ratio >= 1.0

    def as_row(self) -> tuple[str, str, str, str, str, str]:
        """Values for the table columns (id, date, cloud%, platform, path, row)."""
        return (
            self.id,
            self.date,
            f"{self.cloud_cover:.1f}",
            self.platform,
            "" if self.path is None else str(self.path),
            "" if self.row is None else str(self.row),
        )


TABLE_COLUMNS: tuple[str, ...] = ("Scene ID", "Date", "Cloud %", "Platform", "Path", "Row")
ROW_INDEX = {"id": 0, "date": 1, "cloud_cover": 2, "platform": 3, "path": 4, "row": 5}


class CatalogError(RuntimeError):
    """Raised when the catalog cannot be queried."""


def collection_for(satellite: str) -> str:
    """STAC collection id for a satellite identifier."""
    if satellite in (LANDSAT8, LANDSAT9):
        return "landsat-c2-l2"
    if satellite == SENTINEL2:
        return "sentinel-2-l2a"
    raise CatalogError(f"Unsupported satellite: {satellite}")


def build_fetcher(
    satellite: str,
    *,
    max_cloud_cover: float = 70.0,
    source_crs: str = "EPSG:4326",
    fetcher_factory: Any | None = None,
) -> Any:
    """Create the engine fetcher for ``satellite``.

    ``fetcher_factory`` lets tests (and callers that already hold a fetcher)
    bypass the import of the engine, which requires the full download stack.
    The import is deliberately lazy: the GUI must be importable — and the
    tests runnable — without rasterio/stackstac.
    """
    if fetcher_factory is not None:
        return fetcher_factory(satellite)

    fetchers = engine_module("data_engine.io.planetary_computer_fetcher")

    if satellite == SENTINEL2:
        return fetchers.SentinelPlanetaryComputerFetcher(max_cloud_cover=max_cloud_cover)
    return fetchers.PlanetaryComputerLandsatFetcher(
        collection=collection_for(satellite),
        max_cloud_cover=max_cloud_cover,
        source_crs=source_crs,
    )


def _parse_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    text = str(value or "")
    return text[:10]


def coverage_ratio(roi_geometry: dict[str, Any], scene_geometry: dict[str, Any] | None) -> float:
    """Fraction of the ROI covered by a scene footprint (0.0 – 1.0)."""
    if not scene_geometry:
        return 0.0
    try:
        from shapely.geometry import shape  # noqa: PLC0415
        from shapely.validation import make_valid  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - shapely is core to the app
        raise CatalogError("shapely is required to evaluate ROI coverage") from exc

    try:
        roi = shape(roi_geometry)
        scene = shape(scene_geometry)
    except Exception as exc:  # shapely raises GeometryTypeError, KeyError, …
        raise ROIError(f"Cannot evaluate coverage for scene geometry: {exc}") from exc

    if not roi.is_valid:
        roi = make_valid(roi)
    if not scene.is_valid:
        scene = make_valid(scene)
    roi_area = float(roi.area)
    if roi_area <= 0:
        return 0.0
    if scene.is_empty or roi.is_empty:
        return 0.0
    try:
        intersection_area = float(roi.intersection(scene).area)
    except Exception:  # topology errors on malformed footprints
        return 0.0
    return max(0.0, min(1.0, intersection_area / roi_area))


def summarize_scene(
    item: dict[str, Any],
    satellite: str,
    roi: ROI,
) -> SceneSummary:
    """Convert a fetcher metadata dict into a :class:`SceneSummary`."""
    geometry = item.get("geometry")
    ratio = coverage_ratio(roi.geometry, geometry)
    cloud = item.get("cloud_cover")
    return SceneSummary(
        id=str(item.get("id", "unknown")),
        date=_parse_date(item.get("datetime")),
        cloud_cover=float(cloud) if cloud is not None else 0.0,
        platform=str(item.get("platform") or ""),
        path=item.get("path"),
        row=item.get("row"),
        coverage_ratio=ratio,
        satellite=satellite,
        geometry=geometry,
        raw=item,
    )


def sort_scenes(scenes: list[SceneSummary], sort_by: str = "date") -> list[SceneSummary]:
    """Sort scenes by acquisition date or cloud cover (both ascending)."""
    if sort_by == "cloud_cover":
        return sorted(scenes, key=lambda s: (s.cloud_cover, s.date, s.id))
    return sorted(scenes, key=lambda s: (s.date, s.id))


def filter_by_coverage(
    scenes: Iterable[SceneSummary],
    min_coverage_ratio: float,
) -> list[SceneSummary]:
    """Keep scenes covering at least ``min_coverage_ratio`` of the ROI.

    The spec asks for scenes that fully cover the ROI but exposes the minimum
    coverage ratio to the user, so a ratio of 1.0 means "fully covered" and
    lower values relax the requirement to partial coverage.
    """
    threshold = min(1.0, max(0.0, float(min_coverage_ratio)))
    return [scene for scene in scenes if scene.coverage_ratio >= threshold]


def distance_to_full_coverage(min_coverage_ratio: float) -> float:
    """Gap between the requested coverage and total coverage (for UI hints)."""
    return max(0.0, 1.0 - min(1.0, max(0.0, float(min_coverage_ratio))))


def search_scenes(
    fetcher: Any,
    roi: ROI,
    date_range: tuple[str, str],
    *,
    satellite: str,
    sort_by: str = "date",
    min_coverage_ratio: float = 1.0,
) -> list[SceneSummary]:
    """Run a STAC search and apply the coverage/sorting pipeline.

    Args:
        fetcher: Object exposing ``search_scenes(geometry, date_range)``
            (an engine fetcher or a test double).
        roi: Loaded ROI whose geometry is sent to the catalog.
        date_range: ``(start, end)`` ISO dates.
        satellite: Satellite identifier used for labelling/summaries.
        sort_by: ``"date"`` or ``"cloud_cover"``.
        min_coverage_ratio: Minimum fraction of the ROI a scene must cover.

    Returns:
        Sorted list of scenes meeting the coverage threshold. An empty list
        means "no qualifying scenes".
    """
    if not roi.geometry:
        raise ROIError("ROI has no geometry")
    try:
        items = fetcher.search_scenes(roi.geometry, date_range)
    except Exception as exc:  # network/auth errors from the engine
        raise CatalogError(f"STAC search failed: {exc}") from exc

    summaries = [summarize_scene(item, satellite, roi) for item in items or []]
    return sort_scenes(filter_by_coverage(summaries, min_coverage_ratio), sort_by=sort_by)


__all__ = [
    "MIN_COVERAGE_FLOOR",
    "ROW_INDEX",
    "TABLE_COLUMNS",
    "CatalogError",
    "SceneSummary",
    "build_fetcher",
    "collection_for",
    "coverage_ratio",
    "distance_to_full_coverage",
    "filter_by_coverage",
    "search_scenes",
    "sort_scenes",
    "summarize_scene",
]
