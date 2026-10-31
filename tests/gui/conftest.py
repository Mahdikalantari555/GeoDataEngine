"""Shared fixtures for the GeoDataEngine desktop GUI tests.

The GUI is exercised without Tk (``FakeToolkit``) and without the network
(fake engine bridge) so the suite runs anywhere, including CI containers that
ship no Tk libraries.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


# ---------------------------------------------------------------------------
# ROI payloads
# ---------------------------------------------------------------------------
ROI_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [48.20, 30.90],
            [48.30, 30.90],
            [48.30, 31.00],
            [48.20, 31.00],
            [48.20, 30.90],
        ]
    ],
}

#: Footprint that fully contains :data:`ROI_POLYGON`.
SCENE_FOOTPRINT_FULL = {
    "type": "Polygon",
    "coordinates": [
        [
            [48.00, 30.80],
            [48.60, 30.80],
            [48.60, 31.20],
            [48.00, 31.20],
            [48.00, 30.80],
        ]
    ],
}

#: Footprint covering roughly a quarter of :data:`ROI_POLYGON`.
SCENE_FOOTPRINT_PARTIAL = {
    "type": "Polygon",
    "coordinates": [
        [
            [48.25, 30.95],
            [48.60, 30.95],
            [48.60, 31.20],
            [48.25, 31.20],
            [48.25, 30.95],
        ]
    ],
}


@pytest.fixture
def roi_geojson_file(tmp_path: Path) -> Path:
    """A GeoJSON FeatureCollection with one polygon and CRS84 metadata."""
    payload = {
        "type": "FeatureCollection",
        "name": "test-roi",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [
            {
                "type": "Feature",
                "properties": {"id": 1},
                "geometry": ROI_POLYGON,
            }
        ],
    }
    path = tmp_path / "roi.geojson"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def roi_geojson_without_crs(tmp_path: Path) -> Path:
    payload = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": ROI_POLYGON}],
    }
    path = tmp_path / "roi_nocrs.geojson"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def shapefile_path(tmp_path: Path) -> Path:
    """A minimal shapefile with one polygon (pyshp writes it)."""
    shapefile = pytest.importorskip("shapefile")
    path = tmp_path / "roi.shp"
    writer = shapefile.Writer(str(path))
    writer.field("id", "N")
    writer.poly([[[48.20, 30.90], [48.30, 30.90], [48.30, 31.00], [48.20, 31.00], [48.20, 30.90]]])
    writer.record(1)
    writer.close()
    return path


@pytest.fixture
def shapefile_with_prj(shapefile_path: Path) -> Path:
    """Same shapefile, plus a WGS84 ``.prj`` sidecar."""
    prj = shapefile_path.with_suffix(".prj")
    prj.write_text(
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]',
        encoding="utf-8",
    )
    return shapefile_path


@pytest.fixture
def shapefile_without_prj(shapefile_path: Path) -> Path:
    shapefile_path.with_suffix(".prj").unlink(missing_ok=True)
    return shapefile_path


# ---------------------------------------------------------------------------
# Scene builders
# ---------------------------------------------------------------------------
BAND_VALUES = {
    "blue": 0.08,
    "green": 0.12,
    "red": 0.20,
    "nir08": 0.62,
    "swir16": 0.30,
    "swir22": 0.18,
    "lwir11": 305.0,
    "qa_pixel": 21824.0,
}

SENTINEL_BANDS = {"blue": 0.08, "green": 0.12, "red": 0.20, "nir08": 0.62}


def _write_tif(path: Path, value: float, shape: tuple[int, int] = (16, 16)) -> Path:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=shape[0],
        width=shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:32639",
        transform=from_origin(210000.0, 3430000.0, 30.0, 30.0),
    ) as dst:
        dst.write(np.full(shape, value, dtype="float32"), 1)
    return path


def write_scene(
    directory: Path,
    scene_id: str = "LC08_L2SP_166038_20240601",
    *,
    bands: dict[str, float] | None = None,
    date: str = "2024-06-01",
    platform: str = "landsat-8",
) -> Path:
    """Create a downloaded-looking scene folder (bands + MTL.json)."""
    directory.mkdir(parents=True, exist_ok=True)
    for band, value in (bands or BAND_VALUES).items():
        _write_tif(directory / f"{band}.tif", value)
    (directory / "MTL.json").write_text(
        json.dumps(
            {
                "item_id": scene_id,
                "datetime": date,
                "platform": platform,
                "cloud_cover": 3.0,
            }
        ),
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def landsat_scene(tmp_path: Path) -> Path:
    return write_scene(tmp_path / "scenes" / "landsat_20240601_166_038")


@pytest.fixture
def sentinel_scene(tmp_path: Path) -> Path:
    return write_scene(
        tmp_path / "scenes" / "sentinel_20240601",
        scene_id="S2B_MSIL2A_20240601_T39SXC",
        bands=SENTINEL_BANDS,
        platform="sentinel-2",
    )


# ---------------------------------------------------------------------------
# Application doubles
# ---------------------------------------------------------------------------
class FakePrompter:
    """Records dialog calls instead of opening modal windows."""

    def __init__(self, open_file: str = "", open_directory: str = "") -> None:
        self.next_file = open_file
        self.next_directory = open_directory
        self.files: list[str] = []
        self.directories: list[str] = []
        self.info_calls: list[tuple[str, str]] = []
        self.error_calls: list[tuple[str, str]] = []
        self.warning_calls: list[tuple[str, str]] = []
        self.help_calls: list[str] = []

    def open_file(self, title: str = "Select a file", kind: str = "roi") -> str:
        self.files.append(kind)
        return self.next_file

    def open_directory(self, title: str = "Select a folder") -> str:
        self.directories.append(title)
        return self.next_directory

    def info(self, title: str, message: str) -> None:
        self.info_calls.append((title, message))

    def error(self, title: str, message: str) -> None:
        self.error_calls.append((title, message))

    def warning(self, title: str, message: str) -> None:
        self.warning_calls.append((title, message))

    def help(self, body: str) -> None:
        self.help_calls.append(body)


class FakeBridge:
    """Engine bridge double: STAC search + download without any network."""

    def __init__(self, items: list[dict] | None = None) -> None:
        self.items = items if items is not None else default_search_items()
        self.search_calls: list[dict] = []
        self.download_calls: list[dict] = []
        self.preset_runner_calls: list[dict] = []
        self.preset_results: dict = {}
        self.download_error: Exception | None = None
        self.search_error: Exception | None = None

    # -- protocol ------------------------------------------------------
    def search(self, satellite, roi, date_range, *, max_cloud_cover):
        self.search_calls.append(
            {
                "satellite": satellite,
                "roi": roi,
                "date_range": date_range,
                "max_cloud_cover": max_cloud_cover,
            }
        )
        if self.search_error:
            raise self.search_error
        return list(self.items)

    def download(
        self, satellite, roi, date_range, selected_ids, output_dir, *, max_cloud_cover,
        min_coverage_ratio, sort_by, emit=None,
    ):
        self.download_calls.append(
            {
                "satellite": satellite,
                "selected_ids": list(selected_ids),
                "output_dir": Path(output_dir),
                "min_coverage_ratio": min_coverage_ratio,
                "sort_by": sort_by,
            }
        )
        if self.download_error:
            raise self.download_error

        results = []
        for scene_id in selected_ids:
            directory = Path(output_dir) / "landsat_20240601_166_038"
            write_scene(directory, scene_id=scene_id)
            results.append(
                {
                    "scene_id": scene_id,
                    "date": "2024-06-01",
                    "directory": str(directory),
                    "bands_downloaded": len(BAND_VALUES),
                    "mtl_file": str(directory / "MTL.json"),
                    "band_files": {
                        band: directory / f"{band}.tif" for band in BAND_VALUES
                    },
                }
            )
            if emit:
                emit(f"{scene_id}: downloaded {len(BAND_VALUES)} bands")
        return results

    def metric_runner(self):
        def runner(scene, categories, destination):
            self.preset_runner_calls.append(
                {"scene": scene, "categories": list(categories), "destination": destination}
            )
            return dict(self.preset_results)

        return runner


def default_search_items() -> list[dict]:
    """One fully covering scene and one partial scene, newest first."""
    return [
        {
            "id": "LC08_L2SP_166038_20240605",
            "datetime": "2024-06-05T08:30:00Z",
            "cloud_cover": 2.0,
            "platform": "landsat-8",
            "path": 166,
            "row": 38,
            "geometry": SCENE_FOOTPRINT_PARTIAL,
        },
        {
            "id": "LC08_L2SP_166038_20240601",
            "datetime": "2024-06-01T08:30:00Z",
            "cloud_cover": 5.0,
            "platform": "landsat-8",
            "path": 166,
            "row": 38,
            "geometry": SCENE_FOOTPRINT_FULL,
        },
    ]


@pytest.fixture
def fake_bridge() -> FakeBridge:
    return FakeBridge()


@pytest.fixture
def store(tmp_path: Path):
    from app.core.config import ConfigStore

    return ConfigStore(tmp_path / "appdir")


@pytest.fixture
def session(store, fake_bridge):
    from app.core.session import Session

    return Session(store=store, bridge=fake_bridge)


@pytest.fixture
def bootstrapper(store, tmp_path):
    """Bootstrapper whose environment looks like a completed first run.

    The ``.venv`` interpreter marker and both requirements files exist and the
    import probe reports the lite stack as installed (the heavy stack is
    still missing, so the app starts in Lite mode).
    """
    from app.core.bootstrap import FULL_MODULES, Bootstrapper

    app_root = tmp_path / "appdir"
    app_root.mkdir(parents=True, exist_ok=True)
    for name in ("requirements.txt", "requirements-full.txt"):
        (app_root / name).write_text("-r requirements.txt\nnumpy\n", encoding="utf-8")
    boot = Bootstrapper(
        store,
        app_root=app_root,
        probe=lambda module: module not in FULL_MODULES,
    )
    boot.env_python.parent.mkdir(parents=True, exist_ok=True)
    boot.env_python.write_text("#!/bin/sh\n", encoding="utf-8")
    return boot


@pytest.fixture
def fake_toolkit():
    from app.ui.fake import FakeToolkit

    return FakeToolkit()


@pytest.fixture
def prompter():
    return FakePrompter()


@pytest.fixture
def app(session, bootstrapper, fake_toolkit, prompter):
    """A built ``DesktopApp`` wired to fakes and a synchronous job runner."""
    from app.ui.views import DesktopApp, SyncJobRunner

    application = DesktopApp(
        session,
        bootstrapper,
        toolkit=fake_toolkit,
        prompter=prompter,
        job_runner=SyncJobRunner(),
    )
    application.build()
    return application
