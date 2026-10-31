"""Region-of-interest loading for the desktop GUI.

The GUI accepts the two formats an agronomist is likely to have at hand:

* GeoJSON (``.geojson``/``.json``) — read with the standard library.
* ESRI Shapefile (``.shp``) — converted to GeoJSON **in memory** with
  ``pyshp`` (pure Python) so the light stack never needs fiona/geopandas.

The loader returns a :class:`ROI` carrying a plain GeoJSON geometry dict,
the CRS that was assumed, whether that CRS was assumed implicitly, and any
messages the UI should surface in the log.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CRS = "EPSG:4326"

#: WGS84 / CRS84 aliases that need no reprojection.
_WGS84_EPSG = {4326, 4979}
_WGS84_NAMES = {"wgs84", "wgs 84", "crs84", "urn:ogc:def:crs:ogc:1.3:crs84", "epsg:4326", "epsg:4979"}

SHAPEFILE_SUFFIX = ".shp"
GEOJSON_SUFFIXES = (".geojson", ".json")


class ROIError(ValueError):
    """Raised when a ROI file cannot be loaded or does not contain geometry."""


@dataclass
class ROI:
    """A loaded region of interest."""

    path: Path
    geometry: dict[str, Any]
    crs: str = DEFAULT_CRS
    crs_assumed: bool = False
    format: str = "geojson"
    feature_count: int = 1
    warnings: list[str] = field(default_factory=list)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Bounding box as ``(minx, miny, maxx, maxy)``."""
        coords = list(_iter_positions(self.geometry))
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        if not xs or not ys:
            raise ROIError(f"ROI {self.path} contains no coordinates")
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def label(self) -> str:
        return f"{self.path.name} ({self.feature_count} feature(s), {self.crs})"


# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------
def _iter_positions(geometry: dict[str, Any]) -> Iterator[tuple[float, float]]:
    """Yield every ``(x, y)`` position of a GeoJSON geometry."""
    if not isinstance(geometry, dict):
        return
    geom_type = str(geometry.get("type", "")).lower()
    if geom_type == "geometrycollection":
        for sub in geometry.get("geometries") or []:
            yield from _iter_positions(sub)
        return
    coordinates = geometry.get("coordinates")
    yield from _iter_coords(coordinates)


def _iter_coords(node: Any) -> Iterator[tuple[float, float]]:
    if node is None:
        return
    if isinstance(node, (list, tuple)):
        if node and isinstance(node[0], (int, float)):
            if len(node) >= 2:
                yield (float(node[0]), float(node[1]))
            return
        for child in node:
            yield from _iter_coords(child)


def _extract_geometries(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Return ``(geometries, crs)`` from a parsed GeoJSON payload."""
    if not isinstance(payload, dict):
        raise ROIError("GeoJSON root must be an object")

    crs = _crs_from_geojson(payload.get("crs"))
    obj_type = str(payload.get("type", "")).lower()

    if obj_type == "featurecollection":
        geoms = []
        for feature in payload.get("features") or []:
            if not isinstance(feature, dict):
                continue
            geom = feature.get("geometry")
            if isinstance(geom, dict):
                geoms.append(geom)
        if not geoms:
            raise ROIError("GeoJSON FeatureCollection contains no geometries")
        return geoms, crs

    if obj_type == "feature":
        geom = payload.get("geometry")
        if not isinstance(geom, dict):
            raise ROIError("GeoJSON Feature has no geometry")
        return [geom], crs

    if obj_type in {
        "point",
        "multipoint",
        "linestring",
        "multilinestring",
        "polygon",
        "multipolygon",
        "geometrycollection",
    }:
        return [payload], crs

    raise ROIError(f"Unsupported GeoJSON type: {payload.get('type')!r}")


def _crs_from_geojson(crs_block: Any) -> str | None:
    """Best-effort CRS extraction from the (deprecated) GeoJSON ``crs`` member."""
    if not isinstance(crs_block, dict):
        return None
    name = (crs_block.get("properties") or {}).get("name")
    if not isinstance(name, str):
        return None
    normalized = name.strip().lower()
    if normalized in _WGS84_NAMES:
        return DEFAULT_CRS
    if "epsg" in normalized:
        digits = "".join(ch if ch.isdigit() else " " for ch in normalized).split()
        if digits:
            return f"EPSG:{digits[-1]}"
    return None


def _merge_geometries(geometries: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge several geometries into a single GeoJSON geometry dict."""
    if len(geometries) == 1:
        return geometries[0]
    return {"type": "GeometryCollection", "geometries": geometries}


def _normalize_epsg(crs: str | int | None) -> str:
    if crs is None or crs == "":
        return DEFAULT_CRS
    if isinstance(crs, int):
        return f"EPSG:{crs}"
    text = str(crs).strip()
    if not text:
        return DEFAULT_CRS
    upper = text.upper()
    if upper.startswith("EPSG:"):
        return upper
    if upper.startswith("URN:OGC:DEF:CRS:EPSG::"):
        return "EPSG:" + upper.rsplit("::", 1)[-1]
    if text.isdigit():
        return f"EPSG:{text}"
    return text


def _is_wgs84(crs: str) -> bool:
    normalized = crs.strip().lower()
    if normalized in _WGS84_NAMES:
        return True
    return normalized.replace("epsg:", "").strip() in {str(code) for code in _WGS84_EPSG}


# ----------------------------------------------------------------------------
# Readers
# ----------------------------------------------------------------------------
def load_geojson(path: Path) -> ROI:
    """Load a GeoJSON file (FeatureCollection, Feature or bare geometry)."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ROIError(f"Cannot read {path.name}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ROIError(f"{path.name} is not valid GeoJSON: {exc}") from exc

    geometries, crs = _extract_geometries(payload)
    warnings: list[str] = []
    crs_assumed = crs is None
    if crs is None:
        crs = DEFAULT_CRS
        warnings.append(
            f"GeoJSON {path.name} declares no CRS; assuming {DEFAULT_CRS}."
        )
    geometry = _merge_geometries(geometries)
    roi = ROI(
        path=path,
        geometry=geometry,
        crs=crs,
        crs_assumed=crs_assumed,
        format="geojson",
        feature_count=len(geometries),
        warnings=warnings,
    )
    # Validate immediately: an empty geometry is useless downstream.
    _ = roi.bounds
    return roi


def _read_prj(path: Path) -> str | None:
    """Return the CRS declared by a ``.prj`` sidecar (``EPSG:xxxx`` when known)."""
    prj_path = path.with_suffix(".prj")
    if not prj_path.is_file():
        return None
    try:
        wkt = prj_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not wkt:
        return None
    # Fast path: GEOGCS["GCS_WGS_1984", ...] or plain AUTHORITY ids.
    lowered = wkt.lower()
    if (
        ("wgs_1984" in lowered or "wgs 84" in lowered)
        and "geogcs" in lowered
        and "utm" not in lowered
    ):
        return DEFAULT_CRS
    if "authority[\"epsg\"" in lowered:
        fragment = lowered.rsplit('authority["epsg","', 1)[-1]
        digits = "".join(ch for ch in fragment.split('"')[0] if ch.isdigit())
        if digits:
            return f"EPSG:{digits}"
    return wkt


def load_shapefile(path: Path, crs_override: str | int | None = None) -> ROI:
    """Load a shapefile and convert it to a GeoJSON geometry in memory."""
    try:
        import shapefile  # pyshp
    except ImportError as exc:  # pragma: no cover - covered by dependency test
        raise ROIError(
            "Reading Shapefiles requires the 'pyshp' package. "
            "Install it with: pip install pyshp"
        ) from exc

    warnings: list[str] = []
    declared_crs = _read_prj(path)
    override = _normalize_epsg(crs_override) if crs_override not in (None, "") else None

    if override is not None:
        crs = override
        crs_assumed = False
        if declared_crs and not _is_wgs84(declared_crs):
            warnings.append(
                f"CRS override {override} applied; the .prj file declares "
                f"{_short_crs(declared_crs)}."
            )
    elif declared_crs is None:
        crs = DEFAULT_CRS
        crs_assumed = True
        warnings.append(
            f"Shapefile {path.name} has no .prj file; assuming {DEFAULT_CRS}. "
            "Set a CRS override in Settings if the data is projected."
        )
    else:
        crs = declared_crs
        crs_assumed = False

    try:
        reader = shapefile.Reader(str(path))
        shp_geoms = list(reader.shapes())
    except Exception as exc:  # pyshp raises several exception types
        raise ROIError(f"Cannot read shapefile {path.name}: {exc}") from exc

    geometries: list[dict[str, Any]] = []
    for shp_shape in shp_geoms:
        geojson = shp_shape.__geo_interface__
        if not isinstance(geojson, dict):
            continue
        # Drop Z/M values: STAC and the clip window only need lon/lat pairs.
        geometry = _strip_z(geojson)
        if list(_iter_positions(geometry)):
            geometries.append(geometry)

    if not geometries:
        raise ROIError(f"Shapefile {path.name} contains no usable geometries")

    roi = ROI(
        path=path,
        geometry=_merge_geometries(geometries),
        crs=crs,
        crs_assumed=crs_assumed,
        format="shapefile",
        feature_count=len(geometries),
        warnings=warnings,
    )
    _ = roi.bounds
    return roi


def _short_crs(crs: str) -> str:
    return crs if crs.upper().startswith("EPSG:") else "a non-WGS84 CRS"


def _strip_z(geometry: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``geometry`` with only the x/y components kept."""
    geom_type = str(geometry.get("type", "")).lower()
    if geom_type == "geometrycollection":
        return {
            "type": "GeometryCollection",
            "geometries": [
                _strip_z(g) for g in geometry.get("geometries") or [] if isinstance(g, dict)
            ],
        }

    def _clean(node: Any) -> Any:
        if isinstance(node, (list, tuple)):
            if node and isinstance(node[0], (int, float)):
                return list(node[:2])
            return [_clean(child) for child in node]
        return node

    return {"type": geometry.get("type"), "coordinates": _clean(geometry.get("coordinates"))}


def load_roi(
    path: str | Path,
    crs_override: str | int | None = None,
) -> ROI:
    """Load a ROI from a GeoJSON or Shapefile path.

    Args:
        path: Path to a ``.geojson``/``.json``/``.shp`` file.
        crs_override: CRS to assume for shapefiles whose ``.prj`` is missing
            or unhelpful. Ignored for GeoJSON, which carries its own CRS
            hint.

    Raises:
        ROIError: If the file is missing, unreadable, or contains no geometry.
    """
    path = Path(path)
    if not path.exists():
        raise ROIError(f"ROI file not found: {path}")
    if not path.is_file():
        raise ROIError(f"ROI path is not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == SHAPEFILE_SUFFIX:
        return load_shapefile(path, crs_override=crs_override)
    if suffix in GEOJSON_SUFFIXES:
        return load_geojson(path)
    raise ROIError(
        f"Unsupported ROI format '{path.suffix or 'unknown'}'. "
        "Use GeoJSON (.geojson/.json) or Shapefile (.shp)."
    )


__all__ = [
    "DEFAULT_CRS",
    "ROI",
    "ROIError",
    "load_geojson",
    "load_roi",
    "load_shapefile",
]
