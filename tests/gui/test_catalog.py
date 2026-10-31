"""Tests for ``app.core.catalog`` — STAC search, coverage filter, sorting."""

from __future__ import annotations

from datetime import datetime

import pytest
from app.core import catalog
from app.core.roi import load_roi
from shapely.geometry import box

from tests.gui.conftest import SCENE_FOOTPRINT_FULL, SCENE_FOOTPRINT_PARTIAL


@pytest.fixture
def roi(roi_geojson_file):
    return load_roi(roi_geojson_file)


def scene_item(scene_id="SCENE", geometry=None, cloud=10.0, when="2024-06-01T08:30:00Z"):
    return {
        "id": scene_id,
        "datetime": when,
        "cloud_cover": cloud,
        "platform": "landsat-8",
        "path": 166,
        "row": 38,
        "geometry": geometry or SCENE_FOOTPRINT_FULL,
    }


class RecordingFetcher:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def search_scenes(self, geometry, date_range):
        self.calls.append((geometry, date_range))
        return list(self.items)


class ExplodingFetcher:
    def search_scenes(self, geometry, date_range):
        raise RuntimeError("network down")


class TestCollectionFor:
    def test_landsat_collections(self):
        assert catalog.collection_for("landsat-8") == "landsat-c2-l2"
        assert catalog.collection_for("landsat-9") == "landsat-c2-l2"

    def test_sentinel_collection(self):
        assert catalog.collection_for("sentinel-2") == "sentinel-2-l2a"

    def test_unknown_satellite(self):
        with pytest.raises(catalog.CatalogError, match="Unsupported satellite"):
            catalog.collection_for("modis")


class TestCoverageRatio:
    def test_full_coverage_is_one(self, roi):
        assert catalog.coverage_ratio(roi.geometry, SCENE_FOOTPRINT_FULL) == pytest.approx(1.0)

    def test_partial_coverage_is_between_zero_and_one(self, roi):
        ratio = catalog.coverage_ratio(roi.geometry, SCENE_FOOTPRINT_PARTIAL)
        assert 0.0 < ratio < 1.0

    def test_disjoint_footprint_is_zero(self, roi):
        far_away = box(10.0, 10.0, 11.0, 11.0).__geo_interface__
        assert catalog.coverage_ratio(roi.geometry, far_away) == 0.0

    def test_missing_geometry_is_zero(self, roi):
        assert catalog.coverage_ratio(roi.geometry, None) == 0.0

    def test_identical_geometry_is_one(self, roi):
        assert catalog.coverage_ratio(roi.geometry, roi.geometry) == pytest.approx(1.0)

    def test_malformed_geometry_raises_roi_error(self, roi):
        from app.core.roi import ROIError

        with pytest.raises(ROIError, match="Cannot evaluate coverage"):
            catalog.coverage_ratio(roi.geometry, {"type": "Bogus"})

    def test_empty_scene_geometry_is_zero(self, roi):
        assert catalog.coverage_ratio(roi.geometry, {"type": "Polygon", "coordinates": []}) == 0.0


class TestSummarizeAndFilter:
    def test_summary_fields(self, roi):
        summary = catalog.summarize_scene(scene_item(), "landsat-8", roi)
        assert summary.id == "SCENE"
        assert summary.date == "2024-06-01"
        assert summary.cloud_cover == 10.0
        assert summary.platform == "landsat-8"
        assert summary.path == 166
        assert summary.row == 38
        assert summary.full_coverage is True

    def test_summary_handles_datetime_objects(self, roi):
        item = scene_item(when=datetime(2024, 6, 2, 8, 30))
        assert catalog.summarize_scene(item, "landsat-8", roi).date == "2024-06-02"

    def test_summary_handles_missing_cloud_cover(self, roi):
        item = scene_item()
        item.pop("cloud_cover")
        assert catalog.summarize_scene(item, "landsat-8", roi).cloud_cover == 0.0

    def test_full_coverage_threshold_keeps_only_covering_scenes(self, roi):
        items = [
            scene_item("FULL", SCENE_FOOTPRINT_FULL),
            scene_item("PARTIAL", SCENE_FOOTPRINT_PARTIAL),
        ]
        summaries = [catalog.summarize_scene(i, "landsat-8", roi) for i in items]
        kept = catalog.filter_by_coverage(summaries, 1.0)
        assert [scene.id for scene in kept] == ["FULL"]

    def test_relaxed_threshold_keeps_partial_scenes(self, roi):
        items = [
            scene_item("FULL", SCENE_FOOTPRINT_FULL),
            scene_item("PARTIAL", SCENE_FOOTPRINT_PARTIAL),
        ]
        summaries = [catalog.summarize_scene(i, "landsat-8", roi) for i in items]
        # The partial footprint covers a quarter of the ROI.
        assert len(catalog.filter_by_coverage(summaries, 0.2)) == 2
        assert len(catalog.filter_by_coverage(summaries, 0.5)) == 1

    def test_threshold_is_clamped(self, roi):
        summaries = [catalog.summarize_scene(scene_item(), "landsat-8", roi)]
        assert catalog.filter_by_coverage(summaries, 5.0)
        assert catalog.filter_by_coverage(summaries, -2.0)

    def test_distance_to_full_coverage(self):
        assert catalog.distance_to_full_coverage(1.0) == 0.0
        assert catalog.distance_to_full_coverage(0.6) == pytest.approx(0.4)


class TestSorting:
    def _summaries(self, roi):
        return [
            catalog.summarize_scene(
                scene_item("B", SCENE_FOOTPRINT_FULL, cloud=30.0, when="2024-06-03T00:00:00Z"),
                "landsat-8",
                roi,
            ),
            catalog.summarize_scene(
                scene_item("A", SCENE_FOOTPRINT_FULL, cloud=5.0, when="2024-06-01T00:00:00Z"),
                "landsat-8",
                roi,
            ),
            catalog.summarize_scene(
                scene_item("C", SCENE_FOOTPRINT_FULL, cloud=12.0, when="2024-06-02T00:00:00Z"),
                "landsat-8",
                roi,
            ),
        ]

    def test_sort_by_date(self, roi):
        assert [s.id for s in catalog.sort_scenes(self._summaries(roi), "date")] == ["A", "C", "B"]

    def test_sort_by_cloud_cover(self, roi):
        assert [s.id for s in catalog.sort_scenes(self._summaries(roi), "cloud_cover")] == [
            "A",
            "C",
            "B",
        ]

    def test_unknown_sort_key_falls_back_to_date(self, roi):
        assert [s.id for s in catalog.sort_scenes(self._summaries(roi), "price")] == ["A", "C", "B"]


class TestSearchScenes:
    def test_filters_by_coverage_and_sorts(self, roi):
        fetcher = RecordingFetcher(
            [
                scene_item("PARTIAL", SCENE_FOOTPRINT_PARTIAL, when="2024-06-09T00:00:00Z"),
                scene_item("FULL_LATE", SCENE_FOOTPRINT_FULL, when="2024-06-05T00:00:00Z"),
                scene_item("FULL_EARLY", SCENE_FOOTPRINT_FULL, when="2024-06-01T00:00:00Z"),
            ]
        )
        results = catalog.search_scenes(
            fetcher, roi, ("2024-01-01", "2024-12-31"), satellite="landsat-8"
        )
        assert [scene.id for scene in results] == ["FULL_EARLY", "FULL_LATE"]

    def test_no_qualifying_scenes_returns_empty_list(self, roi):
        fetcher = RecordingFetcher([scene_item("PARTIAL", SCENE_FOOTPRINT_PARTIAL)])
        assert catalog.search_scenes(fetcher, roi, ("2024-01-01", "2024-12-31"), satellite="landsat-8") == []

    def test_fetcher_receives_roi_geometry_and_dates(self, roi):
        fetcher = RecordingFetcher([])
        catalog.search_scenes(fetcher, roi, ("2024-01-01", "2024-02-01"), satellite="landsat-8")
        geometry, date_range = fetcher.calls[0]
        assert geometry == roi.geometry
        assert date_range == ("2024-01-01", "2024-02-01")

    def test_fetcher_error_is_wrapped(self, roi):
        with pytest.raises(catalog.CatalogError, match="STAC search failed"):
            catalog.search_scenes(
                ExplodingFetcher(), roi, ("2024-01-01", "2024-12-31"), satellite="landsat-8"
            )

    def test_empty_roi_geometry_is_rejected(self, roi):
        roi.geometry = {}
        with pytest.raises(Exception, match="no geometry"):
            catalog.search_scenes(RecordingFetcher([]), roi, ("2024-01-01", "2024-12-31"),
                                  satellite="landsat-8")


class TestSceneSummaryRow:
    def test_as_row_matches_table_columns(self, roi):
        summary = catalog.summarize_scene(scene_item(), "landsat-8", roi)
        row = summary.as_row()
        assert len(row) == len(catalog.TABLE_COLUMNS)
        assert row[0] == "SCENE"
        assert row[2] == "10.0"
        assert row[4] == "166"
        assert row[5] == "38"

    def test_missing_path_and_row_render_empty(self, roi):
        item = scene_item()
        item.pop("path")
        item.pop("row")
        row = catalog.summarize_scene(item, "landsat-8", roi).as_row()
        assert row[4] == "" and row[5] == ""


class TestBuildFetcher:
    def test_injected_factory_is_used(self):
        calls = []

        def factory(satellite):
            calls.append(satellite)
            return "fetcher"

        assert catalog.build_fetcher("sentinel-2", fetcher_factory=factory) == "fetcher"
        assert calls == ["sentinel-2"]

    def test_real_factory_builds_engine_fetchers(self):
        """The lazy import produces the real engine classes."""
        try:
            from data_engine.io.planetary_computer_fetcher import (
                PlanetaryComputerLandsatFetcher,
                SentinelPlanetaryComputerFetcher,
            )
        except ImportError:  # pragma: no cover - lite test environment
            pytest.skip("engine download stack not installed")

        assert PlanetaryComputerLandsatFetcher is not None
        assert issubclass(SentinelPlanetaryComputerFetcher, PlanetaryComputerLandsatFetcher)
