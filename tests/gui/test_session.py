"""Tests for ``app.core.session`` — the headless brain behind the GUI."""

from __future__ import annotations

import json

import pytest
from app.core import catalog, presets
from app.core.session import (
    DownloadResult,
    LiveEngineBridge,
    Session,
    SessionResult,
)

from tests.gui.conftest import (
    BAND_VALUES,
    SCENE_FOOTPRINT_FULL,
    SCENE_FOOTPRINT_PARTIAL,
)


class Emitter:
    """Records ``emit(...)`` calls with either signature."""

    def __init__(self):
        self.messages: list[str] = []
        self.progress: list[tuple[int, int, str]] = []

    def __call__(self, *args):
        if len(args) == 1:
            self.messages.append(str(args[0]))
        elif args and args[0] == "progress":
            self.progress.append((args[1], args[2], args[3] if len(args) > 3 else ""))


@pytest.fixture
def emitter():
    return Emitter()


@pytest.fixture
def ready_session(session, roi_geojson_file):
    session.load_roi(roi_geojson_file)
    session.update_config(start_date="2024-01-01", end_date="2024-12-31")
    return session


class TestConfiguration:
    def test_session_starts_with_saved_or_default_config(self, session):
        assert session.config.satellite == "landsat-8"
        assert session.log_history == []

    def test_update_config_persists_on_demand(self, session):
        session.update_config(output_dir="/data/out", cloud_threshold=42)
        assert not session.store.path.exists()
        session.save_config()
        assert json.loads(session.store.path.read_text())["cloud_threshold"] == 42.0

    def test_update_config_normalizes(self, session):
        assert session.update_config(cloud_threshold=900).cloud_threshold == 100.0

    def test_full_mode_flag_is_session_scoped(self, session):
        assert session.full_mode_enabled() is False
        session.set_full_mode(True)
        assert session.full_mode_enabled() is True
        session.set_full_mode(False)
        assert session.full_mode_enabled() is False

    def test_full_mode_falls_back_to_config(self, store, fake_bridge):
        store.save(store.load().__class__(mode="full"))
        fresh = Session(store=store, bridge=fake_bridge)
        assert fresh.full_mode_enabled() is True

    def test_status_line_mentions_mode(self, session):
        assert "Lite" in session.status_line()
        session.set_full_mode(True)
        assert "Full" in session.status_line()

    def test_status_line_includes_result(self, session):
        assert "done" in session.status_line("done")

    def test_log_history_is_bounded(self, session):
        for index in range(700):
            session.remember_log(f"line {index}")
        assert len(session.log_history) == 500
        assert session.log_history[-1] == "line 699"


class TestRoi:
    def test_load_roi_stores_it_and_updates_config(self, session, roi_geojson_file, emitter):
        roi = session.load_roi(roi_geojson_file, emit=emitter)
        assert roi.path == roi_geojson_file
        assert session.roi is roi
        assert session.config.roi_path == str(roi_geojson_file)
        assert any("ROI loaded" in message for message in emitter.messages)

    def test_warnings_are_emitted(self, session, roi_geojson_without_crs, emitter):
        session.load_roi(roi_geojson_without_crs, emit=emitter)
        assert any(message.startswith("WARNING:") for message in emitter.messages)

    def test_crs_override_from_config(self, session, shapefile_without_prj):
        session.update_config(crs_override="EPSG:32639")
        assert session.load_roi(shapefile_without_prj).crs == "EPSG:32639"

    def test_invalid_roi_raises(self, session, tmp_path):
        from app.core.roi import ROIError

        with pytest.raises(ROIError):
            session.load_roi(tmp_path / "nope.geojson")

    def test_require_roi(self, session):
        from app.core.roi import ROIError

        with pytest.raises(ROIError, match="Load a ROI"):
            session.require_roi()


class TestSearch:
    def test_search_returns_only_full_coverage_scenes(self, ready_session, emitter):
        results = ready_session.search(emit=emitter)
        assert [scene.id for scene in results] == ["LC08_L2SP_166038_20240601"]

    def test_search_passes_filters_to_the_bridge(self, ready_session, fake_bridge):
        ready_session.update_config(cloud_threshold=25, min_coverage_ratio=1.0)
        ready_session.search()
        call = fake_bridge.search_calls[0]
        assert call["satellite"] == "landsat-8"
        assert call["max_cloud_cover"] == 25.0
        assert call["date_range"] == ("2024-01-01", "2024-12-31")

    def test_relaxed_coverage_keeps_partial_scenes(self, ready_session):
        ready_session.update_config(min_coverage_ratio=0.2)
        assert len(ready_session.search()) == 2

    def test_sort_order(self, ready_session):
        ready_session.update_config(min_coverage_ratio=0.2, sort_by="date")
        assert [s.id for s in ready_session.search()] == [
            "LC08_L2SP_166038_20240601",
            "LC08_L2SP_166038_20240605",
        ]

    def test_no_qualifying_scenes_message(self, ready_session, fake_bridge, emitter):
        fake_bridge.items = [
            {
                "id": "PARTIAL",
                "datetime": "2024-06-05T00:00:00Z",
                "cloud_cover": 1.0,
                "platform": "landsat-8",
                "geometry": SCENE_FOOTPRINT_PARTIAL,
            }
        ]
        assert ready_session.search(emit=emitter) == []
        assert any("No qualifying scenes" in message for message in emitter.messages)

    def test_search_without_roi_fails(self, session):
        with pytest.raises(Exception, match="Load a ROI"):
            session.search()

    def test_search_without_dates_fails(self, session, roi_geojson_file):
        session.load_roi(roi_geojson_file)
        with pytest.raises(ValueError, match="start and end date"):
            session.search()

    def test_search_error_is_propagated(self, ready_session, fake_bridge):
        fake_bridge.search_error = catalog.CatalogError("boom")
        with pytest.raises(catalog.CatalogError):
            ready_session.search()


class TestSelection:
    def test_toggle_and_count(self, ready_session):
        ready_session.update_config(min_coverage_ratio=0.2)
        results = ready_session.search()
        assert ready_session.toggle_selection(results[0].id) is True
        assert ready_session.selected_count == 1
        assert ready_session.toggle_selection(results[0].id) is False
        assert ready_session.selected_count == 0

    def test_explicit_selection(self, ready_session):
        scene_id = ready_session.search()[0].id
        assert ready_session.toggle_selection(scene_id, True) is True
        assert ready_session.toggle_selection(scene_id, True) is True
        assert ready_session.is_selected(scene_id)
        assert ready_session.toggle_selection(scene_id, False) is False

    def test_unknown_scene(self, ready_session):
        ready_session.search()
        with pytest.raises(KeyError):
            ready_session.toggle_selection("NOPE")

    def test_selection_survives_a_re_search(self, ready_session):
        scene_id = ready_session.search()[0].id
        ready_session.toggle_selection(scene_id, True)
        ready_session.search()
        assert ready_session.is_selected(scene_id)

    def test_selection_is_cleared_for_scenes_that_disappear(self, ready_session, fake_bridge):
        ready_session.update_config(min_coverage_ratio=0.2)
        results = ready_session.search()
        ready_session.toggle_selection(results[0].id, True)
        ready_session.toggle_selection(results[1].id, True)
        fake_bridge.items = [fake_bridge.items[1]]
        ready_session.search()
        assert ready_session.selected_count == 1

    def test_selected_ids_follow_table_order(self, ready_session):
        ready_session.update_config(min_coverage_ratio=0.2, sort_by="date")
        results = ready_session.search()
        for scene in reversed(results):
            ready_session.toggle_selection(scene.id, True)
        assert ready_session.selected_scene_ids() == [scene.id for scene in results]


class TestDownload:
    def test_download_writes_into_scenes_folder(self, ready_session, fake_bridge, tmp_path, emitter):
        output = tmp_path / "output"
        ready_session.update_config(output_dir=str(output))
        scene_id = ready_session.search()[0].id
        ready_session.toggle_selection(scene_id, True)

        result = ready_session.download(emit=emitter)

        assert isinstance(result, SessionResult)
        assert len(result.scenes) == 1
        download = result.scenes[0]
        assert isinstance(download, DownloadResult)
        assert download.scene_id == scene_id
        assert download.directory.parent == output / "scenes"
        assert download.bands_downloaded == len(BAND_VALUES)
        assert download.mtl_file and download.mtl_file.exists()
        assert (output / "scenes").is_dir()

    def test_each_band_is_logged(self, ready_session, fake_bridge, tmp_path, emitter):
        ready_session.update_config(output_dir=str(tmp_path / "out"))
        ready_session.toggle_selection(ready_session.search()[0].id, True)
        ready_session.download(emit=emitter)
        for band in BAND_VALUES:
            assert any(f"saved {band}" in message for message in emitter.messages)

    def test_progress_is_reported_per_scene(self, ready_session, fake_bridge, tmp_path, emitter):
        ready_session.update_config(output_dir=str(tmp_path / "out"), min_coverage_ratio=0.2)
        results = ready_session.search()
        for scene in results:
            ready_session.toggle_selection(scene.id, True)
        ready_session.download(emit=emitter)
        assert emitter.progress[-1][:2] == (2, 2)

    def test_bridge_receives_only_selected_ids(self, ready_session, fake_bridge, tmp_path):
        ready_session.update_config(output_dir=str(tmp_path / "out"), min_coverage_ratio=0.2)
        results = ready_session.search()
        chosen = results[1].id
        ready_session.toggle_selection(chosen, True)
        ready_session.download()
        assert fake_bridge.download_calls[0]["selected_ids"] == [chosen]

    def test_download_requires_a_selection(self, ready_session):
        ready_session.search()
        with pytest.raises(ValueError, match="Select at least one scene"):
            ready_session.download()

    def test_config_is_saved_after_download(self, ready_session, tmp_path):
        ready_session.update_config(output_dir=str(tmp_path / "out"))
        ready_session.toggle_selection(ready_session.search()[0].id, True)
        ready_session.download()
        assert ready_session.store.path.exists()

    def test_download_error_propagates(self, ready_session, fake_bridge, tmp_path):
        ready_session.update_config(output_dir=str(tmp_path / "out"))
        ready_session.toggle_selection(ready_session.search()[0].id, True)
        fake_bridge.download_error = catalog.CatalogError("no network")
        with pytest.raises(catalog.CatalogError, match="no network"):
            ready_session.download()


class TestScenesOnDisk:
    def test_scene_infos(self, session, landsat_scene):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        scenes = session.scene_infos()
        assert [scene.name for scene in scenes] == [landsat_scene.name]

    def test_scene_infos_for_satellite(self, session, landsat_scene, sentinel_scene):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        assert [scene.name for scene in session.scene_infos_for("landsat-8")] == [landsat_scene.name]
        assert session.scene_infos_for("landsat-9") == []
        assert [scene.name for scene in session.scene_infos_for("sentinel-2")] == [sentinel_scene.name]

    def test_get_scene_by_folder_and_id(self, session, landsat_scene):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        assert session.get_scene(landsat_scene.name).scene_id == "LC08_L2SP_166038_20240601"
        assert session.get_scene("LC08_L2SP_166038_20240601").name == landsat_scene.name
        with pytest.raises(KeyError):
            session.get_scene("nope")

    def test_output_summary(self, session, landsat_scene):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        summary = session.output_summary()
        assert summary["scenes"] == [str(landsat_scene)]
        assert summary["products"] == {}


class TestGenerate:
    def test_generates_for_every_scene_by_default(self, session, landsat_scene, emitter):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        result = session.generate(emit=emitter, index_names=["NDVI", "NDWI"])
        assert len(result.products) == 2
        assert {product.index for product in result.products} == {"NDVI", "NDWI"}

    def test_generates_for_selected_scenes(self, session, landsat_scene, sentinel_scene):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        result = session.generate(scene_names=[sentinel_scene.name], index_names=["OPTRAM"])
        assert [product.scene_id for product in result.products] == ["S2B_MSIL2A_20240601_T39SXC"]

    def test_uses_config_indices_by_default(self, session, landsat_scene):
        session.update_config(
            output_dir=str(landsat_scene.parent.parent), selected_indices=["NDVI"]
        )
        assert len(session.generate().products) == 1

    def test_selection_is_remembered(self, session, landsat_scene):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        session.generate(index_names=["ndwi"])
        assert session.config.selected_indices == ["NDWI"]
        assert session.store.load().selected_indices == ["NDWI"]

    def test_no_scenes_is_an_error(self, session, tmp_path):
        session.update_config(output_dir=str(tmp_path))
        with pytest.raises(ValueError, match="No downloaded scenes"):
            session.generate()

    def test_no_indices_is_an_error(self, session, landsat_scene):
        session.update_config(output_dir=str(landsat_scene.parent.parent), selected_indices=[])
        with pytest.raises(Exception, match="at least one index"):
            session.generate(index_names=[])

    def test_progress_counts_every_job(self, session, landsat_scene, emitter):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        session.generate(emit=emitter, index_names=["NDVI", "EVI", "SAVI"])
        assert emitter.progress[-1][:2] == (3, 3)


class TestPresetRuns:
    def test_blocked_in_lite_mode(self, session, landsat_scene):
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        with pytest.raises(presets.FullProcessingRequiredError):
            session.generate_preset()

    def test_runs_in_full_mode(self, session, landsat_scene, fake_bridge):
        fake_bridge.preset_results = {
            "ET_daily": _array(), "ET_inst": _array(), "ETrF": _array(), "LE": _array()
        }
        session.set_full_mode(True)
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        result = session.generate_preset(preset="minimal")
        assert len(result.preset_runs) == 1
        assert len(result.preset_runs[0].written) == 4
        assert fake_bridge.preset_runner_calls[0]["categories"] == ["et_core"]

    def test_preset_choice_is_persisted(self, session, landsat_scene, fake_bridge):
        fake_bridge.preset_results = {"ET_daily": _array()}
        session.set_full_mode(True)
        session.update_config(output_dir=str(landsat_scene.parent.parent))
        session.generate_preset(preset="standard")
        assert session.config.preset == "standard"
        assert session.store.load().preset == "standard"

    def test_sentinel_only_downloads_are_ignored(self, store, fake_bridge, tmp_path, sentinel_scene):
        fake_bridge.preset_results = {"ET_daily": _array()}
        session = Session(store=store, bridge=fake_bridge, full_mode=True)
        session.update_config(output_dir=str(sentinel_scene.parent.parent))
        with pytest.raises(presets.PresetError, match="No Landsat scene"):
            session.generate_preset()

    def test_metric_products_land_in_products_folder(self, session, landsat_scene, fake_bridge):
        fake_bridge.preset_results = {"ET_daily": _array(), "R_n": _array()}
        session.set_full_mode(True)
        output = landsat_scene.parent.parent
        session.update_config(output_dir=str(output))
        session.generate_preset(preset="standard")
        assert (output / "products" / "ETaDaily").is_dir()
        assert (output / "products" / "ETaDaily" / "metadata").is_dir()


class TestHelpers:
    def test_sentinel_only_notice(self, session):
        assert "Sentinel-2" in session.sentinel_only_notice("OPTRAM")
        assert session.sentinel_only_notice("NDVI") is None

    def test_sentinel_only_notice_is_silent_for_sentinel(self, session):
        session.update_config(satellite="sentinel-2")
        assert session.sentinel_only_notice("OPTRAM") is None

    def test_status_line_counts_selection(self, ready_session):
        ready_session.toggle_selection(ready_session.search()[0].id, True)
        assert "Selected: 1" in ready_session.status_line()


def _array(shape=(4, 4)):
    import numpy as np

    class _A:
        values = np.ones(shape, dtype="float32")
        attrs: dict = {}

    return _A()


class TestLiveBridge:
    def test_search_uses_injected_fetcher(self, roi_geojson_file):
        from app.core.roi import load_roi

        calls = []

        class Fetcher:
            def search_scenes(self, geometry, date_range):
                calls.append((geometry, date_range))
                return [{"id": "X", "datetime": "2024-06-01T00:00:00Z", "geometry": SCENE_FOOTPRINT_FULL}]

        bridge = LiveEngineBridge(fetcher_factory=lambda satellite: Fetcher())
        roi = load_roi(roi_geojson_file)
        items = bridge.search("landsat-8", roi, ("2024-01-01", "2024-12-31"), max_cloud_cover=10)
        assert items[0]["id"] == "X"
        assert calls[0][1] == ("2024-01-01", "2024-12-31")

    def test_search_errors_are_wrapped(self, roi_geojson_file):
        from app.core.roi import load_roi

        class Fetcher:
            def search_scenes(self, geometry, date_range):
                raise RuntimeError("offline")

        bridge = LiveEngineBridge(fetcher_factory=lambda satellite: Fetcher())
        with pytest.raises(catalog.CatalogError, match="offline"):
            bridge.search("landsat-8", load_roi(roi_geojson_file), ("2024-01-01", "2024-12-31"),
                          max_cloud_cover=10)

    def test_download_filters_to_selected_ids(self, roi_geojson_file, tmp_path):
        from app.core.roi import load_roi

        class Fetcher:
            def fetch_scenes(self, geometry, date_range, output_dir, **kwargs):
                return [
                    {"scene_id": "A", "directory": output_dir, "band_files": {}},
                    {"scene_id": "B", "directory": output_dir, "band_files": {}},
                ]

        bridge = LiveEngineBridge(fetcher_factory=lambda satellite: Fetcher())
        results = bridge.download(
            "landsat-8", load_roi(roi_geojson_file), ("2024-01-01", "2024-12-31"),
            ["B"], tmp_path / "scenes", max_cloud_cover=10, min_coverage_ratio=1.0, sort_by="date",
        )
        assert [item["scene_id"] for item in results] == ["B"]

    def test_download_with_empty_selection(self, roi_geojson_file, tmp_path):
        from app.core.roi import load_roi

        bridge = LiveEngineBridge(fetcher_factory=lambda satellite: object())
        assert bridge.download(
            "landsat-8", load_roi(roi_geojson_file), ("2024-01-01", "2024-12-31"),
            [], tmp_path, max_cloud_cover=10, min_coverage_ratio=1.0, sort_by="date",
        ) == []

    def test_download_errors_are_wrapped(self, roi_geojson_file, tmp_path):
        from app.core.roi import load_roi

        class Fetcher:
            def fetch_scenes(self, *args, **kwargs):
                raise RuntimeError("quota")

        bridge = LiveEngineBridge(fetcher_factory=lambda satellite: Fetcher())
        with pytest.raises(catalog.CatalogError, match="quota"):
            bridge.download(
                "landsat-8", load_roi(roi_geojson_file), ("2024-01-01", "2024-12-31"),
                ["A"], tmp_path, max_cloud_cover=10, min_coverage_ratio=1.0, sort_by="date",
            )


def test_download_result_band_count(tmp_path):
    result = DownloadResult(
        scene_id="X", date="2024-06-01", directory=tmp_path,
        bands={"red": tmp_path / "red.tif", "nir08": tmp_path / "nir08.tif"},
    )
    assert result.bands_downloaded == 2


def test_session_result_ok_flag():
    assert SessionResult("x").ok is False
    assert SessionResult("x", scenes=[DownloadResult("s", "", Path())]).ok is True


from pathlib import Path  # noqa: E402  (used above)
