"""Planetary Computer Landsat Fetcher for METRIC ETa model.

This module provides functionality to fetch Landsat scenes directly from
Microsoft Planetary Computer's STAC API at runtime.
"""

import json
import logging
import os
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

# --- NEP 50 compatibility: numpy 2.x can_cast no longer accepts Python ints/floats ---
# stackstac calls np.can_cast(1, dtype) with Python scalars which now raises TypeError.
# Patch globally so both stackstac.prepare and stackstac.to_dask work without pinning numpy.
_original_can_cast = np.can_cast

def _patched_can_cast(from_, to, casting="safe"):  # type: ignore
    try:
        return _original_can_cast(from_, to, casting=casting)
    except TypeError as _e:
        if "does not support Python ints" in str(_e):
            # Map Python scalar -> corresponding numpy dtype (value-agnostic, safe-cast semantics)
            if isinstance(from_, bool):
                from_dtype = np.dtype(bool)
            elif isinstance(from_, int):
                from_dtype = np.dtype("int64")
            elif isinstance(from_, float):
                from_dtype = np.dtype("float64")
            elif isinstance(from_, complex):
                from_dtype = np.dtype("complex128")
            else:
                try:
                    from_dtype = np.asarray(from_).dtype
                except Exception:
                    raise _e
            return _original_can_cast(from_dtype, to, casting=casting)
        raise

np.can_cast = _patched_can_cast  # type: ignore

# --- pandas 2.x compatibility: infer_datetime_format removed ---
try:
    import pandas as pd

    _orig_to_datetime = pd.to_datetime

    def _patched_to_datetime(*args, **kwargs):  # type: ignore
        kwargs.pop("infer_datetime_format", None)
        return _orig_to_datetime(*args, **kwargs)

    pd.to_datetime = _patched_to_datetime  # type: ignore
except Exception:
    pass

import rasterio
from rasterio.transform import from_bounds
import stackstac
import xarray as xr
from pystac_client import Client
from pyproj import Transformer
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform, unary_union
from ..core.datacube import DataCube
from .errors import (
    AuthenticationError,
    DownloadError,
    NoSceneFoundError,
    PartialDataError,
    GeometryError,
)
from .landsat_reader import LandsatReader

# Fix PROJ database conflict with PostgreSQL on Windows
# Remove PROJ_LIB to use rasterio's bundled PROJ database instead of PostgreSQL's older version
if 'PROJ_LIB' in os.environ:
    del os.environ['PROJ_LIB']

logger = logging.getLogger(__name__)

# Band mapping for MPC STAC assets - matches LandsatReader.DEFAULT_BAND_MAPPING
MPC_BAND_MAPPING = {
    'blue': 'blue',
    'green': 'green',
    'red': 'red',
    'nir08': 'nir08',
    'swir16': 'swir16',
    'swir22': 'swir22',
    'lwir11': 'lwir11',
    'qa_pixel': 'qa_pixel',
}

# Required bands for METRIC processing
REQUIRED_BANDS = ['blue', 'green', 'red', 'nir08', 'swir16', 'swir22', 'lwir11', 'qa_pixel']

# Sentinel-2 specific band mapping for MPC STAC assets
SENTINEL_BAND_MAPPING = {
    'blue': 'B02',
    'green': 'B03',
    'red': 'B04',
    'nir08': 'B08',
    'swir16': 'B11',
    'swir22': 'B12',
    'qa60': 'QA60',
    'scl': 'SCL'
}

# Required bands for Sentinel-2 METRIC processing
SENTINEL_REQUIRED_BANDS = ['blue', 'green', 'red', 'nir08', 'swir16', 'swir22', 'qa60', 'scl']


class PlanetaryComputerLandsatFetcher:
    """Fetcher for Landsat scenes from Microsoft Planetary Computer.
    
    This class handles authentication, searching, and downloading Landsat
    Collection 2 Level-2 scenes from Planetary Computer's STAC API.
    
    The fetcher downloads bands as GeoTIFF files clipped to the ROI,
    and generates MTL.json metadata files compatible with METRIC processing.
    
    Attributes:
        collection: STAC collection ID (default: landsat-c2-l2)
        bands: List of band names to fetch
        max_cloud_cover: Maximum cloud cover percentage (0-100)
        source_crs: CRS of input ROI geometry (default: EPSG:4326 for WGS84 lat/lon).
                   If your ROI is in a different CRS (e.g., UTM), specify it here
                   and the fetcher will transform it to WGS84 for STAC queries.
    """
    
    # Planetary Computer STAC endpoint
    STAC_API_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
    
    def __init__(
        self,
        collection: str = "landsat-c2-l2",
        bands: List[str] = None,
        max_cloud_cover: float = 70.0,
        source_crs: str = "EPSG:4326",
        cache_dir: str = None,
        use_cache: bool = True
    ) -> None:
        """Initialize the fetcher.
        
        Args:
            collection: STAC collection ID (default: landsat-c2-l2)
            bands: List of band names to fetch (default: standard METRIC bands)
            max_cloud_cover: Maximum cloud cover percentage (0-100)
            source_crs: CRS of input ROI geometry (default: EPSG:4326 for WGS84 lat/lon).
                       If your ROI is in a different CRS (e.g., UTM), specify it here
                       and the fetcher will transform it to WGS84 for STAC queries.
        """
        self.collection = collection
        self.bands = bands or REQUIRED_BANDS.copy()
        self.max_cloud_cover = max_cloud_cover
        self.source_crs = source_crs
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.use_cache = use_cache
        
        # Validate bands
        for band in self.bands:
            if band not in MPC_BAND_MAPPING:
                raise ValueError(f"Unknown band: {band}. Supported bands: {list(MPC_BAND_MAPPING.keys())}")
        
        # Initialize STAC client
        try:
            self.client = Client.open(self.STAC_API_URL)
            logger.info(f"Connected to Planetary Computer STAC API: {self.STAC_API_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to STAC API: {e}")
            raise AuthenticationError(f"Failed to connect to STAC API: {e}") from e
    
    def fetch_scenes(
        self,
        roi_geometry: Union[dict, BaseGeometry],
        date_range: Tuple[Union[str, datetime], Union[str, datetime]],
        output_dir: str,
        min_cloud_cover: float = 0.0,
        resolution: float = 30.0,
        sort_by: str = 'date',
        min_coverage_ratio: float = 1
    ) -> List[Dict]:
        """
        Fetch and download Landsat scenes clipped to ROI.
        
        Args:
            roi_geometry: GeoJSON geometry dict or shapely geometry for the area of interest
            date_range: Tuple of (start_date, end_date) - both inclusive
            output_dir: Directory to save output files
            min_cloud_cover: Minimum cloud cover percentage (0-100) to filter out clear scenes
            resolution: Output resolution in meters (default: 30.0 for Landsat)
            sort_by: Sort results by 'date' (default) or 'cloud_cover'
            min_coverage_ratio: Minimum valid pixel coverage ratio (default: 0.55 = 55%)
            
        Returns:
            List of dicts with scene info and file paths:
                {
                    "scene_id": str,
                    "date": str (YYYY-MM-DD),
                    "cloud_cover": float,
                    "path": str,
                    "row": str,
                    "directory": str,
                    "bands_downloaded": int,
                    "mtl_file": str (path),
                    "band_files": Dict[str, Path] (band name -> file path)
                }
            Sorted by date (ascending) or cloud cover (ascending) based on sort_by param
            
        Raises:
            NoSceneFoundError: No suitable scenes found
            AuthenticationError: MPC authentication failed
            DownloadError: Band download failed for one or more scenes
            GeometryError: Invalid ROI geometry
        """
        # Normalize ROI geometry
        roi_geometry = self._normalize_geometry(roi_geometry)
        roi_bbox = list(roi_geometry.bounds)
        
        # Normalize dates
        start_date, end_date = self._normalize_dates(date_range)
        
        # Ensure output directory exists
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Search using bbox
        items = self._search_scenes_by_bbox(roi_bbox, start_date, end_date, min_cloud_cover)
        
        # Filter for full ROI coverage
        full_coverage_items = self._filter_full_coverage(roi_bbox, items)
        
        if not full_coverage_items:
            raise NoSceneFoundError("No scenes found with full ROI coverage")
        if sort_by == 'cloud_cover':
            full_coverage_items.sort(key=lambda item: item.properties.get('cloud_cover', 100.0))
        else:
            full_coverage_items.sort(key=lambda item: item.datetime)
        
        logger.info(f"Found {len(full_coverage_items)} qualifying scenes with full coverage")
        
        # Download each scene
        results = []
        for item in full_coverage_items:
            scene_date = item.properties["datetime"][:10]
            path = item.properties.get('landsat:wrs_path')
            row = item.properties.get('landsat:wrs_row')

            # Create scene directory
            scene_dir = output_path / f"landsat_{scene_date.replace('-', '')}_{path}_{row}"
            scene_dir.mkdir(parents=True, exist_ok=True)

            # Skip download if scene already exists on disk
            existing = self._find_existing_scene(scene_dir)
            if existing is not None:
                downloaded_files, mtl_path = existing
                logger.info(f"Scene {item.id} already downloaded, skipping: {scene_dir}")
            else:
                # Download and clip bands
                try:
                    downloaded_files = self.download_and_clip_bands(
                        item, roi_bbox, scene_dir, resolution, min_coverage_ratio
                    )
                except DownloadError as e:
                    # Scene has insufficient coverage, try next scene
                    logger.warning(f"Skipping scene {item.id}: {e}")
                    # Clean up the scene directory
                    try:
                        for f in scene_dir.iterdir():
                            if f.is_file():
                                f.unlink()
                        scene_dir.rmdir()
                    except Exception:
                        pass
                    continue

                # Create MTL.json
                mtl_path = self._create_mtl_metadata(item, scene_dir)

            results.append({
                "scene_id": item.id,
                "date": scene_date,
                "cloud_cover": item.properties.get('eo:cloud_cover'),
                "path": path,
                "row": row,
                "directory": str(scene_dir),
                "bands_downloaded": len(downloaded_files),
                "mtl_file": str(mtl_path),
                "band_files": downloaded_files
            })
        
        if not results:
            raise NoSceneFoundError(
                "No scenes found with sufficient valid pixel coverage. "
                f"Tried {len(full_coverage_items)} scene(s) but all had coverage < {min_coverage_ratio*100:.0f}%"
            )

        return results

    def _find_existing_scene(self, scene_dir: Path) -> Optional[Tuple[Dict[str, Path], Path]]:
        """Check if a scene was already downloaded.

        A scene counts as complete when its directory contains all
        required band .tif files plus an MTL.json metadata file.

        Args:
            scene_dir: Scene output directory to inspect

        Returns:
            (band_files, mtl_path) tuple if complete, else None
        """
        if not scene_dir.is_dir():
            return None
        band_files = {}
        for band in self.bands:
            band_path = scene_dir / f"{band}.tif"
            if not band_path.is_file():
                return None
            band_files[band] = band_path
        mtl_candidates = list(scene_dir.glob("MTL*.json")) + list(scene_dir.glob("*.json"))
        if not mtl_candidates:
            return None
        return band_files, mtl_candidates[0]

    def search_scenes(
        self,
        roi_geometry: Union[dict, BaseGeometry],
        date_range: Tuple[Union[str, datetime], Union[str, datetime]]
    ) -> List[Dict]:
        """Search for available scenes (returns metadata only, no download).
        
        Args:
            roi_geometry: GeoJSON geometry dict or shapely geometry
            date_range: Tuple of (start_date, end_date) as strings or datetime
            
        Returns:
            List of scene metadata dictionaries
        """
        roi_geometry = self._normalize_geometry(roi_geometry)
        start_date, end_date = self._normalize_dates(date_range)
        
        # Get bbox from ROI geometry
        bbox = list(roi_geometry.bounds)
        
        # Search with bbox
        search_params = {
            "collections": [self.collection],
            "bbox": bbox,
            "datetime": f"{start_date.isoformat()}/{end_date.isoformat()}",
            "limit": 100,
        }
        
        try:
            items = list(self.client.search(**search_params).items())
        except Exception as e:
            logger.error(f"STAC search failed: {e}")
            raise
        
        # Convert to metadata dicts
        results = []
        for item in items:
            cloud_cover = item.properties.get('cloud_cover', 0.0)
            if cloud_cover <= self.max_cloud_cover:
                results.append({
                    'id': item.id,
                    'datetime': item.datetime,
                    'cloud_cover': cloud_cover,
                    'platform': item.properties.get('platform'),
                    'bbox': item.bbox,
                    'geometry': item.geometry,
                })
        
        return results
    
    def get_scene_count(
        self,
        roi_geometry: Union[dict, BaseGeometry],
        date_range: Tuple[Union[str, datetime], Union[str, datetime]]
    ) -> int:
        """Get count of available scenes without downloading.
        
        Args:
            roi_geometry: GeoJSON geometry dict or shapely geometry
            date_range: Tuple of (start_date, end_date) as strings or datetime
            
        Returns:
            Number of scenes that match the criteria (including partial overlaps)
        """
        try:
            results = self.search_scenes(roi_geometry, date_range)
            return len(results)
        except Exception as e:
            logger.error(f"Failed to get scene count: {e}")
            return 0
    
    def _search_scenes_by_bbox(
        self,
        bbox: List[float],
        start_date: datetime,
        end_date: datetime,
        min_cloud_cover: float
    ) -> List:
        """Internal method to search STAC API for scenes using bbox.
        
        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat] in WGS84
            start_date: Start datetime
            end_date: End datetime
            min_cloud_cover: Minimum cloud cover percentage
            
        Returns:
            List of STAC items that intersect with bbox and meet cloud cover criteria
        """
        # Build search parameters
        search_params = {
            "collections": [self.collection],
            "bbox": bbox,
            "datetime": f"{start_date.isoformat()}/{end_date.isoformat()}",
            "limit": 100,
        }
        
        try:
            search = self.client.search(**search_params)
            items = list(search.items())
        except Exception as e:
            logger.error(f"STAC search request failed: {e}")
            raise AuthenticationError(f"STAC search failed: {e}") from e
        
        # Filter by cloud cover - ensure we don't exceed max_cloud_cover
        filtered = []
        for item in items:
            cloud_cover = item.properties.get('cloud_cover', 0.0)
            if cloud_cover <= self.max_cloud_cover:
                filtered.append(item)
            else:
                logger.debug(f"Scene {item.id} filtered out: cloud cover {cloud_cover}% > {self.max_cloud_cover}%")
        
        logger.info(f"Found {len(filtered)} scenes with cloud cover <= {self.max_cloud_cover}%")
        return filtered
    
    def _filter_full_coverage(
        self,
        roi_bbox: List[float],
        items: List,
    ) -> List:
        """Filter items to only those that fully contain the ROI geometry.
        
        This method provides an initial filter based on scene footprint geometry.
        Note: Final validation of actual pixel coverage happens AFTER downloading
        in the download_and_clip_bands method.
        
        Args:
            roi_bbox: [min_lon, min_lat, max_lon, max_lat] in WGS84
            items: List of STAC items
            
        Returns:
            List of items where ROI bbox intersects with scene footprint
        """
        from shapely.geometry import shape
        
        roi_box = box(roi_bbox[0], roi_bbox[1], roi_bbox[2], roi_bbox[3])
        candidates = []
        
        for item in items:
            # Use the scene footprint geometry
            try:
                scene_footprint = shape(item.geometry)
            except Exception as e:
                logger.warning(f"Could not parse scene geometry for {item.id}: {e}")
                continue
            
            # Check if there's any intersection (looser filter at this stage)
            # Final validation will be done after download
            if roi_box.intersects(scene_footprint):
                candidates.append(item)
            else:
                logger.debug(f"Scene {item.id} does not intersect with ROI at all")
        
        logger.info(f"Initial filter: {len(candidates)} scenes intersect with ROI (final validation after download)")
        
        return candidates
    
    def download_and_clip_bands(
        self,
        item,
        bbox: List[float],
        output_dir: Path,
        resolution: float = 30.0,
        min_coverage_ratio: float = 0.55
    ) -> Dict[str, Path]:
        """Download and clip bands to GeoTIFF files using stackstac.
        
        Args:
            item: STAC item (signed or unsigned)
            bbox: [min_lon, min_lat, max_lon, max_lat] in WGS84
            output_dir: Directory to save output files
            resolution: Output resolution in meters
            min_coverage_ratio: Minimum valid pixel coverage ratio (default: 0.55 = 55%)
            
        Returns:
            Dictionary mapping band names to file paths
            
        Raises:
            DownloadError: If scene has insufficient valid pixel coverage
        """
        # Sign the item
        try:
            import planetary_computer
            signed_item = planetary_computer.sign(item)
            logger.debug(f"Successfully signed item: {item.id}")
        except Exception as e:
            logger.error(f"Failed to sign item {item.id}: {e}")
            raise AuthenticationError(f"MPC authentication failed for item {item.id}: {e}") from e
        
        # Calculate UTM EPSG for the bbox
        utm_epsg = self._get_utm_epsg(bbox)
        
        # Transform bbox to UTM coordinates
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        min_x, min_y = transformer.transform(bbox[0], bbox[1])
        max_x, max_y = transformer.transform(bbox[2], bbox[3])
        utm_bounds = (min_x, min_y, max_x, max_y)
        
        # Use stackstac for efficient streaming and clipping
        asset_keys = [b for b in self.bands if b in signed_item.assets]
        
        if not asset_keys:
            raise DownloadError(f"No required bands found in item {item.id}")
        
        stack = stackstac.stack(
            signed_item,
            assets=asset_keys,
            resolution=resolution,
            epsg=utm_epsg,
            bounds=utm_bounds,
            chunksize=256 * 1024 * 1024  # 256 MB
        )
        
        # Compute and save each band as GeoTIFF using rasterio
        stack = stack.compute()
        
        downloaded_files = {}
        date_str = item.datetime.strftime('%Y%m%d')
        
        # Get the transform and shape from the stack
        # stackstac returns (band, y, x) or (time, band, y, x)
        if 'band' in stack.dims:
            band_dim = 'band'
        elif 'x' in stack.dims and 'y' in stack.dims:
            # Single band case - need to check
            band_dim = None
        
        # Get the crs and transform
        # Stackstac should have these as attributes
        if hasattr(stack, 'crs') and stack.crs is not None:
            crs = stack.crs
        else:
            crs = f"EPSG:{utm_epsg}"
        
        # Get transform from stack's transform attribute or compute it
        if hasattr(stack, 'transform') and stack.transform is not None:
            transform = stack.transform
        else:
            # Compute transform from bounds and shape
            # Handle different possible dimension names
            height = stack.sizes.get('y') or stack.sizes.get('latitude') or stack.sizes.get('band')
            width = stack.sizes.get('x') or stack.sizes.get('longitude')
            
            # If we have band dimension, we need y and x specifically
            if 'y' in stack.sizes:
                height = stack.sizes['y']
            elif 'latitude' in stack.sizes:
                height = stack.sizes['latitude']
            else:
                # Use the last dimension size as height
                height = list(stack.sizes.values())[-1]
            
            if 'x' in stack.sizes:
                width = stack.sizes['x']
            elif 'longitude' in stack.sizes:
                width = stack.sizes['longitude']
            else:
                # Use the second to last dimension size as width
                width = list(stack.sizes.values())[-2]
            
            if height and width:
                transform = rasterio.transform.from_bounds(
                    utm_bounds[0], utm_bounds[1],  # left, bottom
                    utm_bounds[2], utm_bounds[3],  # right, top
                    width, height
                )
            else:
                raise DownloadError(f"Could not determine stack dimensions: {stack.sizes}")
        
        for band in stack.band.values:
            band_data = stack.sel(band=band)
            
            # Get the data as numpy array
            data = band_data.values
            
            # Handle multi-dimensional data - squeeze to 2D if needed
            # stackstac may return (y, x) or could have extra dimensions
            if data.ndim > 2:
                # Squeeze any single-dimensional axes (like time=1)
                data = np.squeeze(data)
                # If still more than 2D, take the last 2 dimensions
                if data.ndim > 2:
                    data = data.reshape(-1, data.shape[-1])
            
            filename = f"{band}.tif"
            output_path = output_dir / filename
            
            # Write using rasterio directly
            height, width = data.shape
            with rasterio.open(
                output_path,
                'w',
                driver='GTiff',
                height=height,
                width=width,
                count=1,
                dtype=data.dtype,
                crs=crs,
                transform=transform,
                compress='lzw'
            ) as dst:
                dst.write(data, 1)
            
            downloaded_files[str(band)] = output_path
            logger.info(f"Saved {band} to {output_path}")
        
        # ------------------------------------------------------------
        # CHECK AOI COVERAGE RATIO AFTER DOWNLOAD
        # ------------------------------------------------------------
        # Verify that the downloaded scene actually covers the ROI with valid pixels
        # This handles cases where STAC geometry says it covers but actual pixels are nodata
        
        # Use red band to check coverage (commonly available and representative)
        red_band_path = downloaded_files.get('red')
        if red_band_path and red_band_path.exists():
            with rasterio.open(red_band_path) as src:
                red_data = src.read(1)
                nodata_value = src.nodata if src.nodata is not None else -9999
                
                # Create mask of valid pixels (not nodata)
                valid_mask = (red_data != nodata_value)
                
                # Also check for zero or negative values which may indicate no data
                # Landsat Collection 2 Level-2 surface reflectance should be positive
                valid_mask = valid_mask & (red_data > 0)
                
                total_pixels = valid_mask.size
                valid_pixels = np.count_nonzero(valid_mask)
                
                if total_pixels > 0:
                    coverage_ratio = valid_pixels / total_pixels
                    logger.info(f"Valid coverage ratio for {item.id}: {coverage_ratio:.3f} ({valid_pixels}/{total_pixels} pixels)")
                    
                    if coverage_ratio < min_coverage_ratio:
                        logger.warning(
                            f"Scene {item.id} skipped: insufficient AOI coverage "
                            f"({coverage_ratio:.1%} < {min_coverage_ratio:.1%})"
                        )
                        # Clean up downloaded files
                        for f in downloaded_files.values():
                            if f and f.exists():
                                try:
                                    f.unlink()
                                except:
                                    pass
                        raise DownloadError(
                            f"Scene {item.id} has insufficient valid pixel coverage "
                            f"({coverage_ratio:.1%} < {min_coverage_ratio:.1%})"
                        )
                else:
                    logger.warning(f"Could not determine coverage for {item.id}: no pixels found")
        else:
            logger.warning(f"Could not check coverage: red band not available")
        
        return downloaded_files
    
    def _create_mtl_metadata(self, item, output_dir: Path) -> Path:
        """Create MTL.json from STAC item properties.
        
        Args:
            item: STAC item
            output_dir: Directory to save MTL.json
            
        Returns:
            Path to the created MTL.json file
        """
        scene_id = item.id
        scene_date = item.properties["datetime"][:10]
        cloud_cover = item.properties.get('eo:cloud_cover', 0.0)
        path = item.properties.get('landsat:wrs_path')
        row = item.properties.get('landsat:wrs_row')
        sun_elevation = item.properties.get("view:sun_elevation")
        sun_azimuth = item.properties.get("view:sun_azimuth")

        # Derive platform and instruments from the Landsat scene_id prefix
        # (e.g. LC08 -> landsat-8 / oli_tirs; LC09 -> landsat-9 / oli_tirs)
        platform = "unknown"
        instruments = []
        if scene_id:
            prefix = scene_id.split('_')[0].upper()
            if prefix in ("LC08", "LO08"):
                platform = "landsat-8"
                instruments = ["oli", "tirs"]
            elif prefix in ("LC09", "LO09"):
                platform = "landsat-9"
                instruments = ["oli", "tirs"]
            elif prefix in ("LC07",):
                platform = "landsat-7"
                instruments = ["etm"]

        # Derive processing level (L2SP/L1TP/...) if present in properties
        correction = item.properties.get("landsat:correction") or item.properties.get("landsat:processing_level")

        # Use the Landsat product scene_id if available
        landsat_scene_id = item.properties.get("landsat:scene_id", scene_id)

        mtl_data = {
            "item_id": scene_id,
            "landsat:scene_id": landsat_scene_id,
            "datetime": scene_date,
            "platform": platform,
            "instruments": instruments,
            "landsat_correction": correction,
            "cloud_cover": cloud_cover,
            "path": path,
            "row": row,
            "cloud_cover": cloud_cover,
            "path": path,
            "row": row,
            "sun_elevation": sun_elevation,
            "sun_azimuth": sun_azimuth,
            "geometry": item.geometry,
            "bbox": item.bbox,
            "collection": item.collection_id,
            "properties": item.properties,
            "assets": list(item.assets.keys()),
        }
        
        # Add MTL-compatible structure
        mtl_data["METADATA"] = {
            "PRODUCT_METADATA": {
                "LANDSAT_PRODUCT_ID": scene_id,
                "ACQUISITION_DATE": scene_date,
                "WRS Path": str(path).zfill(3) if path else "N/A",
                "WRS Row": str(row).zfill(3) if row else "N/A",
                "CLOUD_COVER": cloud_cover,
            },
            "SUN_PARAMETERS": {
                "SUN_ELEVATION": sun_elevation,
                "SUN_AZIMUTH": sun_azimuth
            }
        }
        
        mtl_path = output_dir / "MTL.json"
        with open(mtl_path, 'w') as f:
            json.dump(mtl_data, f, indent=2, default=str)
        
        logger.info(f"Created MTL.json at {mtl_path}")
        return mtl_path
    
    def _get_utm_epsg(self, bbox: List[float]) -> int:
        """Determine UTM EPSG code for a given bbox in WGS84.
        
        Args:
            bbox: [min_lon, min_lat, max_lon, max_lat] in WGS84
            
        Returns:
            EPSG code for the appropriate UTM zone
        """
        # Calculate centroid
        lon_center = (bbox[0] + bbox[2]) / 2
        lat_center = (bbox[1] + bbox[3]) / 2
        
        # UTM zone number
        zone_number = int((lon_center + 180) / 6) + 1
        
        # Northern or Southern hemisphere
        if lat_center >= 0:
            epsg = 32600 + zone_number  # Northern hemisphere
        else:
            epsg = 32700 + zone_number  # Southern hemisphere
        
        return epsg
    
    def _normalize_geometry(
        self,
        geometry: Union[dict, BaseGeometry],
        target_crs: str = None
    ) -> BaseGeometry:
        """Normalize input geometry to shapely geometry and transform to WGS84.
        
        Args:
            geometry: GeoJSON dict or shapely geometry in source_crs
            target_crs: Override source CRS detection. If provided, use this CRS.
                       If not provided, will try to detect from geometry or use self.source_crs.
        
        Returns:
            Shapely geometry in WGS84 (EPSG:4326)
            
        Raises:
            GeometryError: If geometry is invalid or transformation fails
        """
        from shapely.geometry import shape
        from pyproj import CRS

        if isinstance(geometry, dict):
            geom_type = geometry.get("type")
            geom_type_lower = geom_type.lower() if isinstance(geom_type, str) else None
            # Handle GeoJSON FeatureCollection -> union of all feature geometries
            if geom_type_lower == "featurecollection":
                features = geometry.get("features", [])
                if not features:
                    raise GeometryError("FeatureCollection has no features")
                geoms = []
                for feat in features:
                    if not isinstance(feat, dict):
                        continue
                    ftype = feat.get("type")
                    ftype_lower = ftype.lower() if isinstance(ftype, str) else None
                    if ftype_lower == "feature":
                        g = feat.get("geometry")
                        if g is None:
                            continue
                        try:
                            geoms.append(shape(g))
                        except Exception as e:
                            raise GeometryError(f"Invalid GeoJSON geometry in Feature: {e}") from e
                    else:
                        # FeatureCollection containing bare geometries (non-standard but handle)
                        try:
                            geoms.append(shape(feat))
                        except Exception as e:
                            raise GeometryError(f"Invalid GeoJSON geometry in FeatureCollection: {e}") from e
                if not geoms:
                    raise GeometryError("FeatureCollection contains no valid geometries")
                geom = unary_union(geoms) if len(geoms) > 1 else geoms[0]
            elif geom_type_lower == "feature":
                g = geometry.get("geometry")
                if g is None:
                    raise GeometryError("Feature has no geometry")
                try:
                    geom = shape(g)
                except Exception as e:
                    raise GeometryError(f"Invalid GeoJSON geometry: {e}") from e
            else:
                # Plain geometry dict (Polygon, MultiPolygon, GeometryCollection, etc.)
                try:
                    geom = shape(geometry)
                except Exception as e:
                    raise GeometryError(f"Invalid GeoJSON geometry: {e}") from e
        elif isinstance(geometry, BaseGeometry):
            geom = geometry
        else:
            raise GeometryError(
                f"Geometry must be dict or shapely geometry, got {type(geometry)}"
            )
        
        if geom.is_empty:
            raise GeometryError("Geometry is empty")
        
        # Determine source CRS
        source_crs = target_crs or self.source_crs
        
        # Try to detect CRS from geometry if it has a CRS (e.g., from GeoJSON with CRS info)
        if target_crs is None and hasattr(geom, 'crs') and geom.crs:
            source_crs = str(geom.crs)
            logger.debug(f"Detected CRS from geometry: {source_crs}")
        
        # If still not determined, check if bounds are in WGS84 range
        if target_crs is None and source_crs.upper() == "EPSG:4326":
            bounds = geom.bounds  # (minx, miny, maxx, maxy)
            # Check if bounds are outside WGS84 range (lon: -180 to 180, lat: -90 to 90)
            if bounds[0] < -180 or bounds[1] < -90 or bounds[2] > 180 or bounds[3] > 90:
                # Bounds are outside WGS84 range, likely in a projected CRS
                logger.warning(f"Geometry bounds {bounds} are outside WGS84 range, attempting to detect UTM zone")
                # Try to determine UTM zone from centroid
                centroid = geom.centroid
                lon, lat = centroid.x, centroid.y
                if lat >= 0:
                    zone = int((lon + 180) / 6) + 1
                    source_crs = f"EPSG:326{zone:02d}"  # Northern hemisphere UTM
                else:
                    zone = int((lon + 180) / 6) + 1
                    source_crs = f"EPSG:327{zone:02d}"  # Southern hemisphere UTM
                logger.info(f"Auto-detected source CRS as {source_crs} based on geometry bounds")
        
        # Transform to WGS84 if needed
        if source_crs.upper() != "EPSG:4326":
            try:
                transformer = Transformer.from_crs(
                    source_crs, "EPSG:4326", always_xy=True
                )
                geom = shapely_transform(transformer.transform, geom)
                logger.debug(f"Transformed geometry from {source_crs} to WGS84")
            except Exception as e:
                raise GeometryError(
                    f"Failed to transform geometry from {source_crs} to WGS84: {e}"
                ) from e
        
        return geom
    
    def _normalize_dates(
        self,
        date_range: Tuple[Union[str, datetime], Union[str, datetime]]
    ) -> Tuple[datetime, datetime]:
        """Normalize date range to datetime objects.
        
        Args:
            date_range: Tuple of (start_date, end_date) as strings or datetime
            
        Returns:
            Tuple of (start_datetime, end_datetime)
        """
        start, end = date_range
        
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        
        # Ensure end date includes the full day
        if end.time() == datetime.min.time():
            end = end + timedelta(days=1) - timedelta(seconds=1)
        
        if start > end:
            raise ValueError(f"Start date {start} is after end date {end}")
        
        return start, end


class SentinelPlanetaryComputerFetcher(PlanetaryComputerLandsatFetcher):
    """Fetcher for Sentinel-2 scenes from Microsoft Planetary Computer.

    This class handles authentication, searching, and downloading Sentinel-2
    L2A scenes from Planetary Computer's STAC API. It reuses geometry and
    date normalization methods from the parent Landsat fetcher but uses the
    ``sentinel-2-l2a`` STAC collection and maps internal band names
    (blue, green, red, nir08, …) to Sentinel‑2 asset keys (B02, B03, B04, B08, …).
    """

    # Band mapping from internal (METRIC) names to Sentinel‑2 STAC asset keys
    SENTINEL_BAND_MAPPING = {
        'blue': 'B02',
        'green': 'B03',
        'red': 'B04',
        'nir08': 'B08',
        'swir16': 'B11',
        'swir22': 'B12',
    }

    def __init__(
        self,
        collection: str = "sentinel-2-l2a",
        bands: List[str] = None,
        max_cloud_cover: float = 70.0,
        source_crs: str = "EPSG:4326",
    ) -> None:
        # Use internal band names (blue, green, …) as the primary band list.
        required = ['blue', 'green', 'red', 'nir08']
        super().__init__(
            collection=collection,
            bands=bands or required,
            max_cloud_cover=max_cloud_cover,
            source_crs=source_crs,
        )

    def search_scenes(
        self,
        roi_geometry: Union[dict, BaseGeometry],
        date_range: Tuple[Union[str, datetime], Union[str, datetime]],
    ) -> List[Dict]:
        """Search for available Sentinel-2 scenes.

        Returns metadata dicts with ``id``, ``datetime``, ``cloud_cover``,
        ``platform``, and ``geometry``.
        """
        roi_geometry = self._normalize_geometry(roi_geometry)
        start_date, end_date = self._normalize_dates(date_range)

        bbox = list(roi_geometry.bounds)
        search_params = {
            "collections": [self.collection],
            "bbox": bbox,
            "datetime": f"{start_date.isoformat()}/{end_date.isoformat()}",
            "limit": 100,
        }
        try:
            items = list(self.client.search(**search_params).items())
        except Exception as e:
            logger.error(f"STAC search failed: {e}")
            raise AuthenticationError(f"STAC search failed: {e}") from e

        results = []
        for item in items:
            cloud_cover = item.properties.get('cloud_cover', 0.0)
            if cloud_cover <= self.max_cloud_cover:
                results.append({
                    'id': item.id,
                    'datetime': item.datetime,
                    'cloud_cover': cloud_cover,
                    'platform': item.properties.get('platform'),
                    'bbox': item.bbox,
                    'geometry': item.geometry,
                })
        return results

    def download_and_clip_bands(
        self,
        item,
        bbox: List[float],
        output_dir: Path,
        resolution: float = 10.0,
        min_coverage_ratio: float = 0.55,
    ) -> Dict[str, Path]:
        """Download and clip Sentinel-2 bands using rasterio directly.

        Bands are saved as ``<internal_name>.tif`` (e.g. ``blue.tif``,
        ``green.tif``, …) so that the downstream pipeline can load them by
        their internal METRIC name.

        This method uses rasterio's windowed reading to avoid file handle
        issues that can occur with stackstac on Windows.
        """
        try:
            import planetary_computer
            signed_item = planetary_computer.sign(item)
        except Exception as e:
            raise AuthenticationError(
                f"MPC authentication failed for {item.id}: {e}"
            ) from e

        utm_epsg = self._get_utm_epsg(bbox)
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)
        min_x, min_y = transformer.transform(bbox[0], bbox[1])
        max_x, max_y = transformer.transform(bbox[2], bbox[3])
        utm_bounds = (min_x, min_y, max_x, max_y)

        # Resolve internal band names → Sentinel asset keys
        asset_keys = [
            self.SENTINEL_BAND_MAPPING[b]
            for b in self.bands
            if b in self.SENTINEL_BAND_MAPPING
            and self.SENTINEL_BAND_MAPPING[b] in signed_item.assets
        ]
        if not asset_keys:
            raise DownloadError(
                f"No required bands found in Sentinel-2 item {item.id}. "
                f"Available assets: {list(signed_item.assets.keys())}"
            )

        # Download and process each band individually to avoid file handle issues
        downloaded_files: Dict[str, Path] = {}
        asset_to_internal = {v: k for k, v in self.SENTINEL_BAND_MAPPING.items()}

        for asset_key in asset_keys:
            try:
                # Get the asset href
                asset_href = signed_item.assets[asset_key].href
                logger.info(f"Downloading band {asset_key} from {asset_href[:80]}...")

                import gc
                import urllib.request
                import tempfile
                import io

                # Download file to memory first using urllib (more reliable than rasterio for HTTP)
                req = urllib.request.Request(
                    asset_href,
                    headers={'User-Agent': 'METRIC-ETa/1.0'}
                )
                with urllib.request.urlopen(req) as response:
                    data_bytes = response.read()

                # Read from bytes buffer - this is the key to avoiding WinError 32
                # We never keep a file handle open from rasterio's perspective
                with rasterio.open(io.BytesIO(data_bytes)) as src:
                    src_crs = src.crs
                    src_transform = src.transform

                    from rasterio.windows import from_bounds
                    window = from_bounds(utm_bounds[0], utm_bounds[1],
                                        utm_bounds[2], utm_bounds[3], src_transform)

                    data = src.read(1, window=window)
                    out_transform = src.window_transform(window)
                    nodata_val = src.nodata

                # Delete the bytes to free memory
                del data_bytes
                gc.collect()

                # Reproject if needed
                out_crs = f"EPSG:{utm_epsg}"
                if str(src_crs) != out_crs:
                    from rasterio.warp import calculate_default_transform, reproject, Resampling
                    dst_transform, dst_width, dst_height = calculate_default_transform(
                        src_crs, out_crs,
                        data.shape[1], data.shape[0],
                        utm_bounds[0], utm_bounds[1], utm_bounds[2], utm_bounds[3]
                    )
                    dst_data = np.zeros((dst_height, dst_width), dtype=data.dtype)
                    reproject(
                        source=data, destination=dst_data,
                        src_transform=out_transform, src_crs=src_crs,
                        dst_transform=dst_transform, dst_crs=out_crs,
                        resampling=Resampling.bilinear
                    )
                    data = dst_data
                    out_transform = dst_transform

                internal_name = asset_to_internal.get(asset_key, asset_key)
                out_path = output_dir / f"{internal_name}.tif"

                with rasterio.open(
                    out_path, 'w',
                    driver='GTiff',
                    height=data.shape[0], width=data.shape[1],
                    count=1, dtype=data.dtype,
                    crs=out_crs, transform=out_transform,
                    compress='lzw', nodata=nodata_val,
                ) as dst:
                    dst.write(data.astype(data.dtype), 1)

                downloaded_files[internal_name] = out_path
                logger.info(f"Saved Sentinel-2 band {internal_name} → {out_path}")

                del data
                gc.collect()

            except Exception as e:
                logger.warning(f"Failed to download band {asset_key}: {e}")
                continue

        if not downloaded_files:
            raise DownloadError(f"No bands could be downloaded for {item.id}")

        # Coverage check (first downloaded band)
        if downloaded_files:
            first_name = list(downloaded_files.keys())[0]
            first_path = downloaded_files[first_name]
            if first_path.exists():
                with rasterio.open(str(first_path)) as src:
                    arr = src.read(1)
                    nodata = src.nodata if src.nodata is not None else -9999
                    valid = (arr != nodata) & (arr > 0)
                    total = valid.size
                    valid_count = int(np.count_nonzero(valid))
                    if total > 0:
                        ratio = valid_count / total
                        logger.info(
                            f"Valid coverage for {item.id}: {ratio:.3f} "
                            f"({valid_count}/{total} pixels)"
                        )
                        if ratio < min_coverage_ratio:
                            for f in downloaded_files.values():
                                f.unlink(missing_ok=True)
                            raise DownloadError(
                                f"Scene {item.id} coverage {ratio:.1%} "
                                f"< {min_coverage_ratio:.1%}"
                            )
        return downloaded_files

    def _create_mtl_metadata(self, item, output_dir: Path) -> Path:
        """Create an MTL.json from Sentinel-2 STAC properties."""
        scene_id = item.id
        scene_date = item.properties["datetime"][:10]
        cloud_cover = item.properties.get('cloud_cover', 0.0)
        platform = item.properties.get('platform', 'sentinel-2')
        sensor = item.properties.get('instruments', ['MSI'])[0] if item.properties.get('instruments') else 'MSI'
        sun_elev = item.properties.get("view:sun_elevation")
        sun_az = item.properties.get("view:sun_azimuth")

        mtl_data = {
            "item_id": scene_id,
            "datetime": scene_date,
            "platform": platform,
            "sensor": sensor,
            "processing_level": "L2A",
            "spacecraft": item.properties.get("constellation", "sentinel-2"),
            "cloud_cover": cloud_cover,
            "view:sun_elevation": sun_elev,
            "view:sun_azimuth": sun_az,
            "ggop:mgrs_grid": item.properties.get('mgrs:grid_code'),
            "geometry": item.geometry,
            "bbox": item.bbox,
            "collection": item.collection_id,
            "properties": item.properties,
            "assets": list(item.assets.keys()),
        }
        mtl_data["METADATA"] = {
            "PRODUCT_METADATA": {
                "PRODUCT_ID": scene_id,
                "ACQUISITION_DATE": scene_date,
                "CLOUD_COVER": cloud_cover,
                "PLATFORM": platform,
                "SENSOR": sensor,
                "PROCESSING_LEVEL": "L2A",
            },
            "SUN_PARAMETERS": {
                "SUN_ELEVATION": sun_elev,
                "SUN_AZIMUTH": sun_az,
            },
        }
        mtl_path = output_dir / "MTL.json"
        with open(mtl_path, 'w') as f:
            json.dump(mtl_data, f, indent=2, default=str)
        logger.info(f"Created Sentinel-2 MTL.json at {mtl_path}")
        return mtl_path

    def fetch_scenes(
        self,
        roi_geometry: Union[dict, BaseGeometry],
        date_range: Tuple[Union[str, datetime], Union[str, datetime]],
        output_dir: str,
        min_cloud_cover: float = 0.0,
        resolution: float = 10.0,
        sort_by: str = "date",
        min_coverage_ratio: float = 0.55,
    ) -> List[Dict]:
        """Fetch and download Sentinel-2 scenes from Planetary Computer.

        This overrides the parent's :meth:`fetch_scenes` to use Sentinel-2
        asset keys (B02, B03, …), write MTL.json with Sentinel-2 metadata,
        and name scene directories ``sentinel_<date>``.

        Args:
            roi_geometry: GeoJSON dict or shapely geometry.
            date_range: (start, end) tuple.
            output_dir: Directory for scene sub-directories.
            min_cloud_cover: Minimum cloud cover filter.
            resolution: Output spatial resolution (m).
            sort_by: ``'date'`` or ``'cloud_cover'``.
            min_coverage_ratio: Minimum valid-pixel coverage.

        Returns:
            List of scene metadata dicts.
        """
        roi_geometry = self._normalize_geometry(roi_geometry)
        roi_bbox = list(roi_geometry.bounds)
        start_date, end_date = self._normalize_dates(date_range)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Search using bbox (inherited method uses self.collection)
        items = self._search_scenes_by_bbox(roi_bbox, start_date, end_date, min_cloud_cover)
        full_coverage_items = self._filter_full_coverage(roi_bbox, items)

        if not full_coverage_items:
            raise NoSceneFoundError("No Sentinel-2 scenes found with full ROI coverage")

        if sort_by == "cloud_cover":
            full_coverage_items.sort(key=lambda it: it.properties.get("cloud_cover", 100.0))
        else:
            full_coverage_items.sort(key=lambda it: it.datetime)

        logger.info(f"Found {len(full_coverage_items)} qualifying Sentinel-2 scenes")

        results: List[Dict] = []
        for item in full_coverage_items:
            scene_date = item.datetime.strftime("%Y%m%d") if item.datetime else "unknown"
            scene_dir = output_path / f"sentinel_{scene_date}"
            scene_dir.mkdir(parents=True, exist_ok=True)

            try:
                downloaded_files = self.download_and_clip_bands(
                    item, roi_bbox, scene_dir, resolution, min_coverage_ratio,
                )
            except DownloadError as e:
                logger.warning(f"Skipping scene {item.id}: {e}")
                continue

            mtl_path = self._create_mtl_metadata(item, scene_dir)

            results.append({
                "scene_id": item.id,
                "date": item.datetime.strftime("%Y-%m-%d") if item.datetime else scene_date,
                "cloud_cover": item.properties.get("eo:cloud_cover") or item.properties.get("cloud_cover", 0.0),
                "directory": str(scene_dir),
                "bands_downloaded": len(downloaded_files),
                "mtl_file": str(mtl_path),
                "band_files": downloaded_files,
            })

        if not results:
            raise NoSceneFoundError(
                f"No Sentinel-2 scenes with sufficient coverage. "
                f"Tried {len(full_coverage_items)} scene(s)."
            )
        return results
