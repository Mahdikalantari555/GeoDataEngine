"""Unit tests for PlanetaryComputerLandsatFetcher."""
# ruff: noqa: DTZ001  # naive datetimes intentional — matches production _normalize_dates API

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from data_engine.io.errors import (
    DownloadError,
    GeometryError,
    NoSceneFoundError,
    PartialDataError,
)
from data_engine.io.planetary_computer_fetcher import PlanetaryComputerLandsatFetcher
from shapely.geometry import box


class TestPlanetaryComputerLandsatFetcher:
    """Test suite for PlanetaryComputerLandsatFetcher."""
    
    def test_init_default(self):
        """Test initialization with default parameters."""
        fetcher = PlanetaryComputerLandsatFetcher()
        assert fetcher.collection == "landsat-c2-l2"
        assert len(fetcher.bands) == 8
        assert fetcher.max_cloud_cover == 70.0
        assert fetcher.cache_dir is None
        assert fetcher.use_cache is True
    
    def test_init_custom(self):
        """Test initialization with custom parameters."""
        fetcher = PlanetaryComputerLandsatFetcher(
            collection="landsat-c2-l2",
            bands=['blue', 'green', 'red'],
            max_cloud_cover=50.0,
            cache_dir="/tmp/cache",
            use_cache=False
        )
        assert fetcher.collection == "landsat-c2-l2"
        assert fetcher.bands == ['blue', 'green', 'red']
        assert fetcher.max_cloud_cover == 50.0
        assert str(fetcher.cache_dir) == "/tmp/cache"
        assert fetcher.use_cache is False
    
    def test_init_invalid_band(self):
        """Test initialization with invalid band name."""
        with pytest.raises(ValueError, match="Unknown band"):
            PlanetaryComputerLandsatFetcher(bands=['invalid_band'])
    
    def test_normalize_geometry_from_geojson(self):
        """Test geometry normalization from GeoJSON dict."""
        fetcher = PlanetaryComputerLandsatFetcher()
        geojson = {
            "type": "Polygon",
            "coordinates": [[
                [48.0, 31.0],
                [48.5, 31.0],
                [48.5, 31.5],
                [48.0, 31.5],
                [48.0, 31.0]
            ]]
        }
        geom = fetcher._normalize_geometry(geojson)
        assert geom.is_valid
        assert geom.area > 0
    
    def test_normalize_geometry_from_shapely(self):
        """Test geometry normalization from shapely geometry."""
        fetcher = PlanetaryComputerLandsatFetcher()
        geom = box(48.0, 31.0, 48.5, 31.5)
        normalized = fetcher._normalize_geometry(geom)
        assert normalized.equals(geom)
    
    def test_normalize_geometry_empty(self):
        """Test geometry normalization with empty geometry."""
        fetcher = PlanetaryComputerLandsatFetcher()
        from shapely.geometry import Point
        empty_geom = Point()
        with pytest.raises(GeometryError, match="Geometry is empty"):
            fetcher._normalize_geometry(empty_geom)
    
    def test_normalize_geometry_invalid_type(self):
        """Test geometry normalization with invalid type."""
        fetcher = PlanetaryComputerLandsatFetcher()
        with pytest.raises(GeometryError, match="Geometry must be dict or shapely geometry"):
            fetcher._normalize_geometry("invalid")
    
    def test_normalize_dates_strings(self):
        """Test date normalization from strings."""
        fetcher = PlanetaryComputerLandsatFetcher()
        start = "2023-04-27"
        end = "2023-04-28"
        start_dt, end_dt = fetcher._normalize_dates((start, end))
        assert isinstance(start_dt, datetime)
        assert isinstance(end_dt, datetime)
        assert start_dt.date() == datetime(2023, 4, 27).date()
        assert end_dt.date() == datetime(2023, 4, 28).date()
    
    def test_normalize_dates_datetime(self):
        """Test date normalization from datetime objects."""
        fetcher = PlanetaryComputerLandsatFetcher()
        start = datetime(2023, 4, 27)
        end = datetime(2023, 4, 28)
        start_dt, end_dt = fetcher._normalize_dates((start, end))
        assert start_dt == start
        # End date is adjusted to end of day (23:59:59) if it's at midnight
        expected_end = datetime(2023, 4, 28, 23, 59, 59)
        assert end_dt == expected_end
    
    def test_normalize_dates_invalid_range(self):
        """Test date normalization with start after end."""
        fetcher = PlanetaryComputerLandsatFetcher()
        start = datetime(2023, 4, 28)
        end = datetime(2023, 4, 27)
        with pytest.raises(ValueError, match="Start date .* is after end date"):
            fetcher._normalize_dates((start, end))
    
    def _make_item(self, item_id, bounds):
        """Helper: mock STAC item with a box geometry covering bounds."""
        minx, miny, maxx, maxy = bounds
        item = Mock()
        item.id = item_id
        item.bbox = bounds
        item.geometry = {
            "type": "Polygon",
            "coordinates": [[
                [minx, miny], [maxx, miny], [maxx, maxy],
                [minx, maxy], [minx, miny],
            ]],
        }
        return item

    def test_filter_full_coverage(self):
        """Test full coverage filtering."""
        fetcher = PlanetaryComputerLandsatFetcher()

        # ROI bbox (implementation takes a bbox list, not a shapely geometry)
        roi_bbox = [48.0, 31.0, 48.5, 31.5]

        # Scene that intersects ROI
        item1 = self._make_item("scene1", [47.5, 30.5, 48.8, 31.8])

        # Scene that does not intersect ROI at all
        item2 = self._make_item("scene2", [50.0, 33.0, 50.5, 33.5])

        items = [item1, item2]
        filtered = fetcher._filter_full_coverage(roi_bbox, items)

        assert len(filtered) == 1
        assert filtered[0].id == "scene1"

    def test_filter_full_coverage_empty(self):
        """Test full coverage filtering with no full coverage scenes."""
        fetcher = PlanetaryComputerLandsatFetcher()
        roi = box(48.0, 31.0, 48.5, 31.5)
        
        # Scene that only partially overlaps
        scene_bbox = [48.2, 31.2, 48.7, 31.7]
        item = self._make_item("scene_partial", scene_bbox)

        items = [item]
        filtered = fetcher._filter_full_coverage(list(roi.bounds), items)
        assert len(filtered) == 1  # intersects -> kept (pixel check happens after download)

    def test_filter_no_intersection(self):
        """Scenes that miss the ROI entirely are filtered out."""
        fetcher = PlanetaryComputerLandsatFetcher()
        roi_bbox = [48.0, 31.0, 48.5, 31.5]
        item = self._make_item("scene_far", [50.0, 33.0, 50.5, 33.5])
        assert fetcher._filter_full_coverage(roi_bbox, [item]) == []

    def test_cache_dir_default(self):
        """Default fetcher has no cache_dir but caching enabled."""
        fetcher = PlanetaryComputerLandsatFetcher()
        assert fetcher.cache_dir is None
        assert fetcher.use_cache is True

    def test_cache_dir_custom(self):
        """Custom cache_dir is stored as a Path."""
        fetcher = PlanetaryComputerLandsatFetcher(cache_dir="/tmp/cache", use_cache=False)
        assert fetcher.cache_dir == Path("/tmp/cache")
        assert fetcher.use_cache is False
    
    def _make_landsat_item(self, item_id="LC08_L2SP_166038_20230427_20230428_02_T1"):
        """Helper: mock Landsat STAC item."""
        item = Mock()
        item.id = item_id
        item.datetime = datetime(2023, 4, 27, 10, 30, 0)
        item.geometry = {
            "type": "Polygon",
            "coordinates": [[[48.0, 31.0], [48.5, 31.0], [48.5, 31.5],
                             [48.0, 31.5], [48.0, 31.0]]],
        }
        item.bbox = [48.0, 31.0, 48.5, 31.5]
        item.collection_id = "landsat-c2-l2"
        item.assets = {}
        item.properties = {
            'datetime': '2023-04-27T10:30:00Z',
            'eo:cloud_cover': 15.5,
            'platform': 'landsat-8',
            'view:sun_elevation': 45.2,
            'view:sun_azimuth': 123.4,
            'landsat:wrs_path': 166,
            'landsat:wrs_row': 38,
            'landsat:correction': 'L2SP',
        }
        return item

    def test_create_mtl_metadata(self, tmp_path):
        """Test MTL.json creation from a STAC item."""
        fetcher = PlanetaryComputerLandsatFetcher()
        item = self._make_landsat_item()

        mtl_path = fetcher._create_mtl_metadata(item, tmp_path)

        assert mtl_path.is_file()
        mtl_data = json.loads(mtl_path.read_text())
        assert mtl_data["item_id"] == item.id
        assert mtl_data["cloud_cover"] == 15.5
        assert mtl_data["path"] == 166
        assert mtl_data["row"] == 38

    def test_find_existing_scene_complete(self, tmp_path):
        """A scene dir with all bands + MTL.json counts as downloaded."""
        fetcher = PlanetaryComputerLandsatFetcher()
        scene_dir = tmp_path / "landsat_20230427_166_38"
        scene_dir.mkdir()
        for band in fetcher.bands:
            (scene_dir / f"{band}.tif").touch()
        (scene_dir / "MTL.json").touch()

        found = fetcher._find_existing_scene(scene_dir)
        assert found is not None
        band_files, mtl_path = found
        assert len(band_files) == len(fetcher.bands)
        assert mtl_path.is_file()

    def test_find_existing_scene_incomplete(self, tmp_path):
        """A scene dir missing bands or metadata is NOT complete."""
        fetcher = PlanetaryComputerLandsatFetcher()
        scene_dir = tmp_path / "landsat_20230427_166_38"
        scene_dir.mkdir()
        (scene_dir / "blue.tif").touch()  # only one band, no MTL

        assert fetcher._find_existing_scene(scene_dir) is None
        assert fetcher._find_existing_scene(tmp_path / "does_not_exist") is None
    
    @patch('planetary_computer.sign')
    def test_download_clip_bands_no_assets(self, mock_sign, tmp_path):
        """download_and_clip_bands raises when the item has no usable bands."""
        mock_item = Mock()
        mock_item.id = "test_scene_nobands"
        mock_item.datetime = datetime(2023, 4, 27)
        mock_item.assets = {}  # no bands at all
        mock_sign.return_value = mock_item

        fetcher = PlanetaryComputerLandsatFetcher()
        with pytest.raises(DownloadError, match="No required bands"):
            fetcher.download_and_clip_bands(
                mock_item, [48.0, 31.0, 48.5, 31.5], tmp_path, 30.0
            )

    def test_fetch_scenes_skips_existing(self, tmp_path):
        """fetch_scenes does not re-download scenes already on disk."""
        fetcher = PlanetaryComputerLandsatFetcher()
        item = self._make_landsat_item()
        item.properties['datetime'] = '2023-04-27T10:30:00Z'
        item.properties['eo:cloud_cover'] = 15.5

        roi = {
            "type": "Polygon",
            "coordinates": [[[48.0, 31.0], [48.5, 31.0], [48.5, 31.5],
                             [48.0, 31.5], [48.0, 31.0]]],
        }
        date_range = ("2023-04-27", "2023-04-28")

        # Pre-create the scene dir as if a previous run downloaded it
        scene_dir = tmp_path / "landsat_20230427_166_38"
        scene_dir.mkdir(parents=True)
        for band in fetcher.bands:
            (scene_dir / f"{band}.tif").touch()
        (scene_dir / "MTL.json").touch()

        with patch.object(fetcher, '_search_scenes_by_bbox', return_value=[item]), \
             patch.object(fetcher, 'download_and_clip_bands') as mock_dl:
            results = fetcher.fetch_scenes(roi, date_range, str(tmp_path))

            mock_dl.assert_not_called()  # no re-download
            assert len(results) == 1
            assert results[0]["scene_id"] == item.id
            assert results[0]["directory"] == str(scene_dir)

    def test_fetch_scenes_downloads_missing(self, tmp_path):
        """fetch_scenes downloads scenes that are not on disk yet."""
        fetcher = PlanetaryComputerLandsatFetcher()
        item = self._make_landsat_item()
        item.properties['datetime'] = '2023-04-27T10:30:00Z'
        item.properties['eo:cloud_cover'] = 15.5

        roi = {
            "type": "Polygon",
            "coordinates": [[[48.0, 31.0], [48.5, 31.0], [48.5, 31.5],
                             [48.0, 31.5], [48.0, 31.0]]],
        }
        date_range = ("2023-04-27", "2023-04-28")
        fake_files = {b: tmp_path / f"{b}.tif" for b in fetcher.bands}

        with patch.object(fetcher, '_search_scenes_by_bbox', return_value=[item]), \
             patch.object(fetcher, 'download_and_clip_bands', return_value=fake_files) as mock_dl, \
             patch.object(fetcher, '_create_mtl_metadata', return_value=tmp_path / "MTL.json"):
            results = fetcher.fetch_scenes(roi, date_range, str(tmp_path))

            mock_dl.assert_called_once()  # downloaded because not on disk
            assert len(results) == 1
            assert results[0]["bands_downloaded"] == len(fetcher.bands)
    
    def test_search_scenes_no_auth(self):
        """Test search_scenes with mocked STAC client."""
        fetcher = PlanetaryComputerLandsatFetcher()
        
        # Mock the STAC client
        with patch.object(fetcher, 'client') as mock_client:
            # Create mock search result
            mock_item = Mock()
            mock_item.id = "test_scene"
            mock_item.datetime = datetime(2023, 4, 27)
            mock_item.bbox = [48.0, 31.0, 48.5, 31.5]
            mock_item.geometry = {"type": "Polygon", "coordinates": [[[48.0, 31.0], [48.5, 31.0], [48.5, 31.5], [48.0, 31.5], [48.0, 31.0]]]}
            mock_item.properties = {
                'cloud_cover': 15.0,
                'platform': 'landsat-8',
            }
            
            mock_search = Mock()
            mock_search.items.return_value = [mock_item]
            mock_client.search.return_value = mock_search
            
            roi = box(48.0, 31.0, 48.5, 31.5)
            date_range = (datetime(2023, 4, 27), datetime(2023, 4, 28))
            
            results = fetcher.search_scenes(roi, date_range)
            
            assert len(results) == 1
            assert results[0]['id'] == "test_scene"
            assert results[0]['cloud_cover'] == 15.0
            assert results[0]['platform'] == 'landsat-8'
    
    def test_get_scene_count(self):
        """Test get_scene_count method."""
        fetcher = PlanetaryComputerLandsatFetcher()
        
        with patch.object(fetcher, 'search_scenes') as mock_search:
            mock_search.return_value = [{'id': 'scene1'}, {'id': 'scene2'}, {'id': 'scene3'}]
            
            roi = box(48.0, 31.0, 48.5, 31.5)
            date_range = (datetime(2023, 4, 27), datetime(2023, 4, 28))
            
            count = fetcher.get_scene_count(roi, date_range)
            assert count == 3
    
    def test_fetch_scenes_no_results(self, tmp_path):
        """Test fetch_scenes with no matching scenes."""
        fetcher = PlanetaryComputerLandsatFetcher()

        with patch.object(fetcher, '_search_scenes_by_bbox', return_value=[]):
            roi = box(48.0, 31.0, 48.5, 31.5)
            date_range = (datetime(2023, 4, 27), datetime(2023, 4, 28))

            with pytest.raises(NoSceneFoundError, match="No scenes found"):
                fetcher.fetch_scenes(roi, date_range, str(tmp_path))

    def test_fetch_scenes_no_full_coverage(self, tmp_path):
        """Test fetch_scenes with only non-intersecting scenes."""
        fetcher = PlanetaryComputerLandsatFetcher()

        mock_item = self._make_item("far_scene", [50.0, 33.0, 50.5, 33.5])
        mock_item.datetime = datetime(2023, 4, 27)
        mock_item.properties = {'cloud_cover': 10.0}

        with patch.object(fetcher, '_search_scenes_by_bbox', return_value=[mock_item]):
            roi = box(48.0, 31.0, 48.5, 31.5)
            date_range = (datetime(2023, 4, 27), datetime(2023, 4, 28))

            with pytest.raises(NoSceneFoundError, match="No scenes found with full ROI coverage"):
                fetcher.fetch_scenes(roi, date_range, str(tmp_path))

    def test_fetch_scenes_sort_by_cloud_cover(self, tmp_path):
        """Test fetch_scenes sorting by cloud cover (dict results)."""
        fetcher = PlanetaryComputerLandsatFetcher()

        def make_item(item_id, cloud_cover):
            item = self._make_item(item_id, [47.5, 30.5, 48.8, 31.8])
            item.datetime = datetime(2023, 4, 27)
            item.properties = {
                'datetime': '2023-04-27T10:30:00Z',
                'cloud_cover': cloud_cover,
                'landsat:wrs_path': 166,
                'landsat:wrs_row': 38,
            }
            return item

        items = [
            make_item("scene_high_cc", 50.0),
            make_item("scene_low_cc", 10.0),
            make_item("scene_mid_cc", 30.0),
        ]

        with patch.object(fetcher, '_search_scenes_by_bbox', return_value=items), \
             patch.object(fetcher, 'download_and_clip_bands',
                          return_value={'blue': tmp_path / 'blue.tif'}), \
             patch.object(fetcher, '_create_mtl_metadata',
                          return_value=tmp_path / 'MTL.json'):
            roi = box(48.0, 31.0, 48.5, 31.5)
            date_range = (datetime(2023, 4, 27), datetime(2023, 4, 28))

            results = fetcher.fetch_scenes(roi, date_range, str(tmp_path),
                                           sort_by='cloud_cover')

            assert len(results) == 3
            # Sorted ascending by cloud cover
            assert [r["scene_id"] for r in results] == [
                "scene_low_cc", "scene_mid_cc", "scene_high_cc",
            ]


class TestSentinel1PlanetaryComputerFetcher:
    """Tests for ``Sentinel1PlanetaryComputerFetcher`` (GRD + GCP geolocation)."""

    def test_init_default(self):
        """Defaults target the GRD collection and the VV/VH polarisations."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        fetcher = Sentinel1PlanetaryComputerFetcher()
        assert fetcher.collection == "sentinel-1-grd"
        assert fetcher.bands == ["vv", "vh"]
        assert fetcher.instrument_mode is None
        assert fetcher.orbit_direction is None
        assert fetcher.resolution == 10.0

    def test_init_rejects_unknown_polarisation(self):
        """Only real GRD polarisation asset keys are accepted."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        with pytest.raises(ValueError, match="Unknown band"):
            Sentinel1PlanetaryComputerFetcher(bands=["blue"])

    def _s1_item(self, item_id="S1A_IW_GRDH_1SDV_20240101T000000", mode="IW", orbit="ascending"):
        """Helper: mock a Sentinel-1 GRD STAC item."""
        item = Mock()
        item.id = item_id
        item.datetime = datetime(2024, 1, 1, 0, 0, 0)
        item.bbox = [48.0, 31.0, 48.5, 31.5]
        item.collection_id = "sentinel-1-grd"
        item.geometry = {
            "type": "Polygon",
            "coordinates": [
                [[48.0, 31.0], [48.5, 31.0], [48.5, 31.5], [48.0, 31.5], [48.0, 31.0]]
            ],
        }
        item.assets = {
            "vv": Mock(href="https://example.invalid/vv.tif"),
            "vh": Mock(href="https://example.invalid/vh.tif"),
        }
        item.properties = {
            "datetime": "2024-01-01T00:00:00Z",
            "platform": "sentinel-1a",
            "constellation": "Sentinel-1",
            "sar:instrument_mode": mode,
            "sat:orbit_state": orbit,
            "sat:relative_orbit": 72,
            "sar:polarizations": ["VV", "VH"],
            "s1:product_identifier": "S1A_IW_GRDH_1SDV_20240101T000000_000001_0001",
        }
        return item

    def test_search_scenes_reports_no_cloud_cover(self):
        """GRD has no cloud property, so the summary says so rather than 0 %."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        fetcher = Sentinel1PlanetaryComputerFetcher()
        item = self._s1_item()
        with patch.object(fetcher, "client") as mock_client:
            mock_search = Mock()
            mock_search.items.return_value = [item]
            mock_client.search.return_value = mock_search
            results = fetcher.search_scenes(
                box(48.0, 31.0, 48.5, 31.5), (datetime(2024, 1, 1), datetime(2024, 1, 2))
            )

        assert len(results) == 1
        assert results[0]["cloud_cover"] is None
        assert results[0]["polarizations"] == ["vv", "vh"]
        assert results[0]["instrument_mode"] == "IW"
        assert results[0]["orbit_state"] == "ascending"

    def test_search_scenes_filters_on_acquisition_mode(self):
        """An ``instrument_mode`` filter keeps only matching scenes."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        fetcher = Sentinel1PlanetaryComputerFetcher(instrument_mode="IW")
        ewm = self._s1_item("S1A_EW_GRDH_1SDV_20240101T000000", mode="EW")
        with patch.object(fetcher, "client") as mock_client:
            mock_search = Mock()
            mock_search.items.return_value = [self._s1_item(), ewm]
            mock_client.search.return_value = mock_search
            results = fetcher.search_scenes(
                box(48.0, 31.0, 48.5, 31.5), (datetime(2024, 1, 1), datetime(2024, 1, 2))
            )

        assert [r["id"] for r in results] == [self._s1_item().id]

    def test_scene_dirname_distinguishes_orbit_passes(self):
        """Ascending and descending passes on one date must not collide."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        fetcher = Sentinel1PlanetaryComputerFetcher()
        asc = fetcher._scene_dirname(self._s1_item("asc", orbit="ascending"))
        desc = fetcher._scene_dirname(self._s1_item("desc", orbit="descending"))
        assert asc == "sentinel1_20240101_asc"
        assert desc == "sentinel1_20240101_desc"
        assert asc != desc

    def test_find_existing_scene_accepts_any_polarisation(self, tmp_path):
        """A single-polarisation scene is still complete (no fixed band list)."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        fetcher = Sentinel1PlanetaryComputerFetcher(bands=["vv", "vh"])
        scene_dir = tmp_path / "sentinel1_20240101_asc"
        scene_dir.mkdir()
        (scene_dir / "vv.tif").touch()
        (scene_dir / "MTL.json").touch()

        found = fetcher._find_existing_scene(scene_dir)
        assert found is not None
        assert list(found[0]) == ["vv"]

    def test_find_existing_scene_rejects_missing_metadata(self, tmp_path):
        """Band files alone are not enough to count as downloaded."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        fetcher = Sentinel1PlanetaryComputerFetcher()
        scene_dir = tmp_path / "sentinel1_20240101_asc"
        scene_dir.mkdir()
        (scene_dir / "vv.tif").touch()
        assert fetcher._find_existing_scene(scene_dir) is None

    def test_create_mtl_metadata_records_sar_fields(self, tmp_path):
        """MTL.json carries polarisations, orbit and the GCP geolocation note."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        fetcher = Sentinel1PlanetaryComputerFetcher()
        item = self._s1_item()
        mtl_path = fetcher._create_mtl_metadata(item, tmp_path)

        payload = json.loads(mtl_path.read_text())
        assert payload["item_id"] == item.id
        assert payload["polarizations"] == ["vv", "vh"]
        assert payload["instrument_mode"] == "IW"
        assert payload["orbit_state"] == "ascending"
        assert payload["relative_orbit"] == 72
        assert payload["geolocation"]["method"] == "gdal-tps"

    @patch("data_engine.io.planetary_computer_fetcher._configure_gdal_http")
    @patch("planetary_computer.sign")
    def test_download_clip_bands_requires_gdal(self, mock_sign, mock_gdal, tmp_path):
        """A failed GDAL warp skips the band instead of writing junk."""
        from data_engine.io.planetary_computer_fetcher import (
            DownloadError,
            Sentinel1PlanetaryComputerFetcher,
        )

        gdal = Mock()
        gdal.Warp.side_effect = RuntimeError("network down")
        mock_gdal.return_value = gdal

        item = self._s1_item()
        mock_sign.return_value = item
        fetcher = Sentinel1PlanetaryComputerFetcher()

        with pytest.raises(DownloadError, match="No bands could be downloaded"):
            fetcher.download_and_clip_bands(
                item, [48.0, 31.0, 48.5, 31.5], tmp_path, 10.0
            )

    @patch("data_engine.io.planetary_computer_fetcher._configure_gdal_http")
    @patch("planetary_computer.sign")
    def test_download_clip_bands_writes_one_file_per_polarisation(
        self, mock_sign, mock_gdal, tmp_path
    ):
        """Each polarisation becomes ``<pol>.tif`` and the warp targets UTM."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        calls = []

        def fake_warp(dest, source, **kwargs):
            calls.append({"dest": dest, "source": source, **kwargs})
            # Emulate a non-empty output so the coverage check passes.
            import numpy as np
            import rasterio

            with rasterio.open(
                dest,
                "w",
                driver="GTiff",
                height=4,
                width=4,
                count=1,
                dtype="uint16",
                crs=kwargs["dstSRS"],
                transform=rasterio.Affine(10, 0, 0, 0, -10, 0),
                nodata=0,
            ) as dst:
                dst.write(np.full((4, 4), 100, dtype="uint16"), 1)

        gdal = Mock()
        gdal.Warp.side_effect = fake_warp
        mock_gdal.return_value = gdal

        item = self._s1_item()
        mock_sign.return_value = item
        fetcher = Sentinel1PlanetaryComputerFetcher()

        files = fetcher.download_and_clip_bands(
            item, [48.0, 31.0, 48.5, 31.5], tmp_path, 10.0
        )

        assert sorted(files) == ["vh", "vv"]
        assert all(path.name.endswith(".tif") for path in files.values())
        # ROI centred at 48.25E falls in UTM zone 39N.
        assert calls[0]["dstSRS"] == "EPSG:32639"
        assert calls[0]["tps"] is True
        assert calls[0]["source"].startswith("/vsicurl/")

    def test_fetch_scenes_uses_sentinel1_folder_names(self, tmp_path):
        """``fetch_scenes`` writes into ``sentinel1_<date>_<orbit>``."""
        from data_engine.io.planetary_computer_fetcher import (
            Sentinel1PlanetaryComputerFetcher,
        )

        fetcher = Sentinel1PlanetaryComputerFetcher()
        item = self._s1_item()
        fake_files = {"vv": tmp_path / "vv.tif", "vh": tmp_path / "vh.tif"}

        with patch.object(fetcher, "_search_scenes_by_bbox", return_value=[item]), patch.object(
            fetcher, "download_and_clip_bands", return_value=fake_files
        ), patch.object(
            fetcher, "_create_mtl_metadata", return_value=tmp_path / "MTL.json"
        ):
            results = fetcher.fetch_scenes(
                box(48.0, 31.0, 48.5, 31.5),
                ("2024-01-01", "2024-01-02"),
                str(tmp_path),
            )

        assert len(results) == 1
        assert Path(results[0]["directory"]).name == "sentinel1_20240101_asc"
        assert results[0]["polarizations"] == ["vv", "vh"]


class TestErrorClasses:
    """Test suite for custom error classes."""
    
    def test_no_scene_found_error_default(self):
        """Test NoSceneFoundError without partial count."""
        err = NoSceneFoundError("Test message")
        assert str(err) == "Test message"
        assert err.partial_count is None
    
    def test_no_scene_found_error_with_partial(self):
        """Test NoSceneFoundError with partial count."""
        err = NoSceneFoundError("Test message", partial_count=5)
        assert "partial overlaps: 5" in str(err)
        assert err.partial_count == 5
    
    def test_download_error_with_details(self):
        """Test DownloadError with band and URL."""
        err = DownloadError("Download failed", band_name="blue", url="https://example.com/blue.tif")
        assert "band: blue" in str(err)
        assert "url: https://example.com/blue.tif" in str(err)
    
    def test_download_error_without_details(self):
        """Test DownloadError without extra details."""
        err = DownloadError("Download failed")
        assert str(err) == "Download failed"
        assert err.band_name is None
        assert err.url is None
    
    def test_partial_data_error(self):
        """Test PartialDataError."""
        missing = ['blue', 'green']
        available = ['red', 'nir08']
        err = PartialDataError("Missing bands", missing_bands=missing, available_bands=available)
        assert "Missing bands: [blue, green]" in str(err)
        assert err.missing_bands == missing
        assert err.available_bands == available


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
