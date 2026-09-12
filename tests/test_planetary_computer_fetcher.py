"""Unit tests for PlanetaryComputerLandsatFetcher."""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import xarray as xr
from pathlib import Path
from shapely.geometry import box

from data_engine.io.planetary_computer_fetcher import (
    PlanetaryComputerLandsatFetcher,
    NoSceneFoundError,
    AuthenticationError,
    DownloadError,
    PartialDataError,
    GeometryError,
)
from data_engine.core.datacube import DataCube


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
