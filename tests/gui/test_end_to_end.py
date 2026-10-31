"""End-to-end smoke test: search → download → NDVI (change task 9.1).

Drives the real ``DesktopApp`` with the real core, a real GeoTIFF-writing
"engine" (in place of the network fetcher) and the fake toolkit, then asserts
the documented output layout: ``scenes/`` plus ``products/ndvi/`` with
``products/ndvi/metadata/``.
"""

from __future__ import annotations

import json

import pytest
from app.core.config import ConfigStore
from app.core.session import Session
from app.ui.fake import FakeToolkit
from app.ui.views import DesktopApp, SyncJobRunner

from tests.gui.conftest import FakeBridge, FakePrompter, write_scene


@pytest.fixture
def e2e(tmp_path, roi_geojson_file):
    store = ConfigStore(tmp_path / "appdir")
    bridge = FakeBridge()
    session = Session(store=store, bridge=bridge)

    def runner(args, on_line=None):  # pragma: no cover - not used in this flow
        return 0

    from app.core.bootstrap import Bootstrapper

    bootstrapper = Bootstrapper(store, app_root=tmp_path / "appdir", probe=lambda m: True)
    bootstrapper.env_python.parent.mkdir(parents=True, exist_ok=True)
    bootstrapper.env_python.write_text("#!/bin/sh\n")
    for name in ("requirements.txt", "requirements-full.txt"):
        (tmp_path / "appdir" / name).write_text("numpy\n")

    toolkit = FakeToolkit()
    prompter = FakePrompter(open_file=str(roi_geojson_file), open_directory=str(tmp_path / "out"))
    app = DesktopApp(
        session, bootstrapper, toolkit=toolkit, prompter=prompter, job_runner=SyncJobRunner()
    ).build()
    return app, bridge, prompter, tmp_path


def test_smoke_search_download_ndvi(e2e):
    app, bridge, prompter, tmp_path = e2e

    # 1. ROI + search criteria
    app.browse_roi()
    app.browse_output_dir()
    app.start_entry.set("2024-01-01")
    app.end_entry.set("2024-12-31")
    app.coverage_entry.set("1.0")

    # 2. Search returns only fully covering scenes
    app.run_search()
    scene_ids = app.results_tree.get_children()
    assert scene_ids == ("LC08_L2SP_166038_20240601",)

    # 3. Select and download
    app.select_all_results()
    app.download_selected()
    assert "Download complete" in prompter.info_calls[-1][0]

    output = tmp_path / "out"
    scenes = list((output / "scenes").iterdir())
    assert len(scenes) == 1
    scene_dir = scenes[0]
    assert (scene_dir / "MTL.json").is_file()
    for band in ("blue", "green", "red", "nir08", "swir16", "swir22", "lwir11", "qa_pixel"):
        assert (scene_dir / f"{band}.tif").is_file()

    # 4. Generate NDVI
    app.refresh_scene_list()
    for name in app.index_vars:
        app.index_vars[name].set(name == "NDVI")
    app.generate_indices()

    ndvi_raster = output / "products" / "ndvi" / "LC08_L2SP_166038_20240601.tif"
    ndvi_metadata = output / "products" / "ndvi" / "metadata" / "LC08_L2SP_166038_20240601.json"
    assert ndvi_raster.is_file()
    assert ndvi_metadata.is_file()

    # 5. The raster is a readable GeoTIFF on the scene grid
    import numpy as np
    import rasterio

    with rasterio.open(ndvi_raster) as src:
        assert src.crs.to_epsg() == 32639
        assert src.count == 1
        values = src.read(1)
        expected = (0.62 - 0.20) / (0.62 + 0.20)
        np.testing.assert_allclose(values, expected, rtol=1e-4)

    # 6. Metadata records provenance
    metadata = json.loads(ndvi_metadata.read_text())
    assert metadata["product"] == "NDVI"
    assert metadata["scene_id"] == "LC08_L2SP_166038_20240601"
    assert metadata["source_bands"] == ["nir08", "red"]
    assert metadata["crs"] == "EPSG:32639"
    assert metadata["statistics"]["mean"] == pytest.approx(expected, rel=1e-4)

    # 7. Session state and the log tell the full story
    assert app.last_status.startswith("Mode:")
    content = app.log_text.content
    for fragment in (
        "ROI loaded",
        "Searching landsat-8",
        "qualifying scene(s)",
        "saved red",
        "Download complete",
        "Generated 1 product",
        "Index generation complete",
    ):
        assert fragment in content, fragment


def test_smoke_batch_indices_on_two_scenes(e2e):
    app, bridge, prompter, tmp_path = e2e
    app.browse_roi()
    app.browse_output_dir()
    app.start_entry.set("2024-01-01")
    app.end_entry.set("2024-12-31")
    app.run_search()
    app.select_all_results()
    app.download_selected()

    # A second, manually downloaded Sentinel scene appears in the folder
    write_scene(
        tmp_path / "out" / "scenes" / "sentinel_20240601",
        scene_id="S2B_MSIL2A_20240601_T39SXC",
        bands={"blue": 0.08, "green": 0.12, "red": 0.2, "nir08": 0.62},
        platform="sentinel-2",
    )
    app.refresh_scene_list()

    app.scene_listbox.selection_set(1)  # sentinel scene
    app.index_vars["NDVI"].set(True)
    app.index_vars["OPTRAM"].set(True)
    for name in ("EVI", "SAVI", "NDWI"):
        app.index_vars[name].set(False)
    app.generate_indices()

    products = tmp_path / "out" / "products"
    assert (products / "ndvi" / "S2B_MSIL2A_20240601_T39SXC.tif").is_file()
    optram_raster = products / "optram" / "S2B_MSIL2A_20240601_T39SXC.tif"
    assert optram_raster.is_file()

    import numpy as np
    import rasterio

    with rasterio.open(optram_raster) as src:
        values = src.read(1)
    expected = np.sqrt(0.62 / 0.2) * (1 - 0.2 / 0.62)
    np.testing.assert_allclose(np.clip(values, 0, 1), np.clip(expected, 0, 1), rtol=1e-4)


def test_output_layout_contract(e2e):
    """Requirement: layout created — scenes/ and products/<product>/metadata/."""
    app, bridge, prompter, tmp_path = e2e
    app.browse_roi()
    app.browse_output_dir()
    app.start_entry.set("2024-01-01")
    app.end_entry.set("2024-12-31")
    app.run_search()
    app.select_all_results()
    app.download_selected()

    output = tmp_path / "out"
    assert (output / "scenes").is_dir()
    app.refresh_scene_list()
    for name in app.index_vars:
        app.index_vars[name].set(name == "NDVI")
    app.generate_indices()

    product_folders = sorted(path.name for path in (output / "products").iterdir())
    assert product_folders == ["ndvi"]
    assert (output / "products" / "ndvi" / "metadata").is_dir()
    # rasters never live inside the metadata folder
    assert not list((output / "products" / "ndvi" / "metadata").glob("*.tif"))
