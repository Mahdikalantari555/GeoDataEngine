"""In-app help content.

Kept as plain data so the same text feeds the scrollable Tkinter dialog, the
tests, and (should it ever be wanted) a static documentation page.
"""

from __future__ import annotations

from .core.indices import INDEX_DESCRIPTIONS, INDEX_FORMULAS
from .core.presets import preset_help_entries

APP_TITLE = "GeoDataEngine Desktop"

OVERVIEW = """\
GeoDataEngine Desktop downloads satellite scenes for a region of interest and \
turns them into ready-to-use products.

Workflow
  1. Settings   – pick the output folder, mirror URL and (optionally) a CRS override.
  2. Search     – choose a ROI file, a satellite and a date range, then search.
  3. Download   – tick the scenes you want and download them (clipped to the ROI).
  4. Indices    – generate spectral indices, or METRIC presets in Full mode.
"""

USAGE_SECTIONS: list[tuple[str, str]] = [
    (
        "Search tab",
        """\
• ROI file: GeoJSON (.geojson/.json) or ESRI Shapefile (.shp).
• Satellite: Landsat 8, Landsat 9 or Sentinel-2.
• Date range: YYYY-MM-DD, both days inclusive.
• Cloud threshold: scenes above this cloud cover are dropped.
• Min coverage: fraction of the ROI a scene footprint must cover.
  1.0 keeps fully covering scenes only; lower it to accept partial coverage.
• Sort: by acquisition date or by cloud cover (both ascending).
• Only scenes that satisfy every filter appear in the table.""",
    ),
    (
        "Download tab",
        """\
• Every required band of a selected scene is downloaded in full — there are no
  per-band checkboxes.
  Landsat 8/9 : blue, green, red, nir08, swir16, swir22, lwir11, qa_pixel
  Sentinel-2  : blue, green, red, nir08 (B02, B03, B04, B08)
• Bands are clipped to the ROI with HTTP range requests (only the ROI pixels
  are transferred).
• Scenes land in <output>/scenes/<scene>/ together with MTL.json.
• Already-downloaded scenes are skipped, so a second run is cheap.
• The progress bar advances once per scene; the log prints one line per band.""",
    ),
    (
        "Indices tab",
        """\
• Select one scene or several (batch), tick the indices, press Generate.
• Each index is written to <output>/products/<index>/<scene-id>.tif with a
  metadata JSON in <output>/products/<index>/metadata/.
• Basic indices run on the light stack (numpy + rasterio) and need no extra
  installation.
• METRIC presets need Full mode: press "Enable full processing" in Settings,
  which installs the heavy stack into the same .venv.""",
    ),
    (
        "Settings tab",
        """\
• Output folder, mirror URL, default date range, cloud threshold and coverage
  ratio are saved to config.json next to the application and restored on start.
• CRS override: used for shapefiles without a .prj (defaults to EPSG:4326).
• Environment status shows whether the venv is Lite or Full.
• If the default mirror is unreachable, point the mirror field at
  https://pypi.org/simple (or leave it empty) and press Save.""",
    ),
    (
        "Troubleshooting",
        """\
• First run takes 5–15 minutes: the app creates .venv and installs packages.
  Antivirus software can slow venv creation down; that is expected.
• "No qualifying scenes": widen the date range, raise the cloud threshold or
  lower the minimum coverage ratio.
• Shapefile without .prj: the app assumes EPSG:4326. If your polygon is in a
  projected CRS (e.g. UTM), set the override before loading it.
• Full-stack install interrupted: press "Enable full processing" again; pip
  resumes where it stopped.""",
    ),
]


def index_entries() -> list[tuple[str, str, str]]:
    """``[(name, formula, description)]`` for every basic index."""
    return [
        (name, INDEX_FORMULAS[name], INDEX_DESCRIPTIONS[name])
        for name in INDEX_FORMULAS
    ]


def build_help_text() -> str:
    """Full help document as plain text (used by the dialog and the tests)."""
    lines = [APP_TITLE, "=" * len(APP_TITLE), "", OVERVIEW]
    for title, body in USAGE_SECTIONS:
        lines.extend(["", title, "-" * len(title), body])

    lines.extend(["", "Basic indices", "-------------"])
    for name, formula, description in index_entries():
        lines.append(f"• {name}: {formula}")
        lines.append(f"    {description}")

    lines.extend(["", "METRIC presets (Full mode only)", "-------------------------------"])
    for preset, products in preset_help_entries():
        lines.append(f"• {preset}: {', '.join(products)}")

    lines.extend(
        [
            "",
            "Output layout",
            "-------------",
            "<output>/scenes/<scene>/                     downloaded bands + MTL.json",
            "<output>/products/<product>/<scene>.tif      generated raster",
            "<output>/products/<product>/metadata/<scene>.json",
        ]
    )
    return "\n".join(lines).strip() + "\n"


__all__ = [
    "APP_TITLE",
    "OVERVIEW",
    "USAGE_SECTIONS",
    "build_help_text",
    "index_entries",
]
