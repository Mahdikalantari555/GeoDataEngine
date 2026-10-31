"""Tests for ``app.core.roi`` — GeoJSON and Shapefile ROI loading."""

from __future__ import annotations

import json

import pytest
from app.core.roi import DEFAULT_CRS, ROI, ROIError, load_roi

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[48.2, 30.9], [48.3, 30.9], [48.3, 31.0], [48.2, 31.0], [48.2, 30.9]]],
}


class TestGeoJSON:
    def test_loads_feature_collection(self, roi_geojson_file):
        roi = load_roi(roi_geojson_file)
        assert roi.format == "geojson"
        assert roi.feature_count == 1
        assert roi.geometry["type"] == "Polygon"
        assert roi.crs == DEFAULT_CRS

    def test_bounds_are_the_polygon_extent(self, roi_geojson_file):
        roi = load_roi(roi_geojson_file)
        assert roi.bounds == pytest.approx((48.2, 30.9, 48.3, 31.0))

    def test_crs84_hint_is_understood(self, roi_geojson_file):
        roi = load_roi(roi_geojson_file)
        assert roi.crs_assumed is False
        assert roi.warnings == []

    def test_missing_crs_is_assumed_with_warning(self, roi_geojson_without_crs):
        roi = load_roi(roi_geojson_without_crs)
        assert roi.crs == DEFAULT_CRS
        assert roi.crs_assumed is True
        assert any("no CRS" in warning for warning in roi.warnings)

    def test_loads_bare_geometry_object(self, tmp_path):
        path = tmp_path / "bare.geojson"
        path.write_text(json.dumps(SQUARE), encoding="utf-8")
        roi = load_roi(path)
        assert roi.bounds == pytest.approx((48.2, 30.9, 48.3, 31.0))

    def test_loads_feature_object(self, tmp_path):
        path = tmp_path / "feature.json"
        path.write_text(
            json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}),
            encoding="utf-8",
        )
        assert load_roi(path).geometry["type"] == "Polygon"

    def test_multiple_features_become_a_collection(self, tmp_path):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": SQUARE},
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[49.0, 31.0], [49.1, 31.0], [49.1, 31.1], [49.0, 31.0]]
                        ],
                    },
                },
            ],
        }
        path = tmp_path / "multi.geojson"
        path.write_text(json.dumps(payload), encoding="utf-8")
        roi = load_roi(path)
        assert roi.feature_count == 2
        assert roi.geometry["type"] == "GeometryCollection"
        assert roi.bounds == pytest.approx((48.2, 30.9, 49.1, 31.1))

    def test_epsg_crs_member_is_read(self, tmp_path):
        payload = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32639"}},
            "features": [{"type": "Feature", "properties": {}, "geometry": SQUARE}],
        }
        path = tmp_path / "utm.geojson"
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert load_roi(path).crs == "EPSG:32639"

    def test_empty_feature_collection_is_rejected(self, tmp_path):
        path = tmp_path / "empty.geojson"
        path.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        with pytest.raises(ROIError, match="no geometries"):
            load_roi(path)

    def test_invalid_json_is_rejected(self, tmp_path):
        path = tmp_path / "broken.geojson"
        path.write_text("{this is not json")
        with pytest.raises(ROIError, match="not valid GeoJSON"):
            load_roi(path)

    def test_unsupported_geojson_type_is_rejected(self, tmp_path):
        path = tmp_path / "weird.geojson"
        path.write_text(json.dumps({"type": "Circle"}))
        with pytest.raises(ROIError, match="Unsupported GeoJSON type"):
            load_roi(path)

    def test_utf8_bom_is_tolerated(self, tmp_path):
        path = tmp_path / "bom.geojson"
        path.write_text(json.dumps(SQUARE), encoding="utf-8-sig")
        assert load_roi(path).bounds[0] == pytest.approx(48.2)

    def test_sample_repository_geojson_loads(self):
        from pathlib import Path

        sample = Path(__file__).resolve().parents[2] / "sample" / "sample.geojson"
        if not sample.is_file():  # pragma: no cover - sample removed
            pytest.skip("sample/sample.geojson missing")
        roi = load_roi(sample)
        minx, miny, maxx, maxy = roi.bounds
        assert -180 <= minx <= 180 and -90 <= miny <= 90
        assert maxx > minx and maxy > miny


class TestShapefile:
    def test_converts_to_geojson_in_memory(self, shapefile_path):
        roi = load_roi(shapefile_path)
        assert roi.format == "shapefile"
        assert roi.geometry["type"] == "Polygon"
        assert roi.bounds == pytest.approx((48.2, 30.9, 48.3, 31.0))

    def test_missing_prj_assumes_wgs84_and_warns(self, shapefile_without_prj):
        roi = load_roi(shapefile_without_prj)
        assert roi.crs == DEFAULT_CRS
        assert roi.crs_assumed is True
        assert any("no .prj" in warning for warning in roi.warnings)

    def test_prj_is_used_when_present(self, shapefile_with_prj):
        roi = load_roi(shapefile_with_prj)
        assert roi.crs == DEFAULT_CRS
        assert roi.crs_assumed is False

    def test_crs_override_wins_over_prj(self, shapefile_with_prj):
        roi = load_roi(shapefile_with_prj, crs_override="EPSG:32639")
        assert roi.crs == "EPSG:32639"
        assert roi.crs_assumed is False

    def test_crs_override_is_normalized(self, shapefile_without_prj):
        assert load_roi(shapefile_without_prj, crs_override="32639").crs == "EPSG:32639"
        assert load_roi(shapefile_without_prj, crs_override=32639).crs == "EPSG:32639"

    def test_crs_override_with_missing_prj_does_not_warn_about_assumption(
        self, shapefile_without_prj
    ):
        roi = load_roi(shapefile_without_prj, crs_override="EPSG:32639")
        assert roi.crs_assumed is False
        assert not any("no .prj" in warning for warning in roi.warnings)

    def test_unreadable_shapefile_raises(self, tmp_path):
        broken = tmp_path / "broken.shp"
        broken.write_bytes(b"\x00\x01\x02not-a-shapefile")
        with pytest.raises(ROIError, match="Cannot read shapefile"):
            load_roi(broken)

    def test_z_values_are_dropped(self):
        """Shapefile Z/M values are stripped so the geometry stays lon/lat."""
        from app.core.roi import _strip_z

        geometry = {
            "type": "Polygon",
            "coordinates": [[[48.2, 30.9, 1.0], [48.3, 30.9, 2.0], [48.3, 31.0, 3.0]]],
        }
        stripped = _strip_z(geometry)
        assert stripped["coordinates"] == [[[48.2, 30.9], [48.3, 30.9], [48.3, 31.0]]]

    def test_geometry_collection_z_values_are_dropped(self):
        from app.core.roi import _strip_z

        stripped = _strip_z(
            {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "Point", "coordinates": [48.2, 30.9, 5.0]},
                    {"type": "MultiPoint", "coordinates": [[48.3, 31.0, 7.0]]},
                ],
            }
        )
        assert stripped["geometries"][0]["coordinates"] == [48.2, 30.9]
        assert stripped["geometries"][1]["coordinates"] == [[48.3, 31.0]]


class TestLoadRoiDispatch:
    def test_missing_file(self, tmp_path):
        with pytest.raises(ROIError, match="not found"):
            load_roi(tmp_path / "nope.geojson")

    def test_directory_instead_of_file(self, tmp_path):
        with pytest.raises(ROIError, match="not a file"):
            load_roi(tmp_path)

    def test_unsupported_extension(self, tmp_path):
        path = tmp_path / "roi.kml"
        path.write_text("<kml/>")
        with pytest.raises(ROIError, match="Unsupported ROI format"):
            load_roi(path)

    def test_uppercase_extension_still_works(self, tmp_path):
        path = tmp_path / "ROI.GEOJSON"
        path.write_text(json.dumps(SQUARE))
        assert load_roi(path).geometry["type"] == "Polygon"

    def test_accepts_string_path(self, roi_geojson_file):
        assert isinstance(load_roi(str(roi_geojson_file)), ROI)

    def test_label_mentions_name_features_and_crs(self, roi_geojson_file):
        label = load_roi(roi_geojson_file).label
        assert "roi.geojson" in label
        assert "1 feature" in label
        assert DEFAULT_CRS in label
