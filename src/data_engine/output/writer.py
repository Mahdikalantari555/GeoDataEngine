"""Output Writer for METRIC ETa pipeline.

This module provides functions for writing georeferenced output files
including GeoTIFF, NetCDF, CSV, and JSON formats.
"""

from typing import Dict, Optional, Any, Union
import re
import numpy as np
import xarray as xr
import rasterio
from rasterio.transform import from_bounds
import json
import csv
from datetime import datetime
from pathlib import Path
import logging


from data_engine.core.datacube import DataCube
from data_engine.calibration.dt_calibration import CalibrationResult


def write_geotiff(
    path: str,
    data: Union[np.ndarray, xr.DataArray],
    cube: DataCube,
    compression: str = "LZW",
    nodata: float = np.nan,
    dtype: Optional[str] = None
) -> None:
    """Write single-band GeoTIFF with CRS and transform from DataCube."""
    if isinstance(data, xr.DataArray):
        data = data.values
    
    nodata_value = nodata
    if np.issubdtype(dtype, np.integer) if dtype else False:
        data = np.where(np.isnan(data), 0, data)
        nodata_value = 0

    if dtype is None:
        dtype = 'float32' if data.dtype in [np.float32, np.float64] else data.dtype
    
    crs = cube.crs
    transform = cube.transform
    
    if crs is None or transform is None:
        raise ValueError("DataCube must have CRS and transform set")
    
    height, width = data.shape
    
    with rasterio.open(
        path, 'w', driver='GTiff', height=height, width=width, count=1,
        dtype=dtype, crs=crs, transform=transform, compress=compression, nodata=nodata_value
    ) as dst:
        dst.write(data.astype(dtype), 1)
        dst.update_tags(
            DATE=datetime.now().isoformat(),
            SENSOR=cube.metadata.get('sensor', 'Unknown'),
            PRODUCT='METRIC_ET'
        )


def write_rgb_geotiff(
    path: str,
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
    cube: DataCube,
    compression: str = "LZW",
    stretch_percentiles: tuple = (2, 98)
) -> None:
    """Write 3-band RGB GeoTIFF with CRS and transform from DataCube."""
    crs = cube.crs
    transform = cube.transform
    
    if crs is None or transform is None:
        raise ValueError("DataCube must have CRS and transform set")
    
    if red.shape != green.shape or red.shape != blue.shape:
        raise ValueError("All RGB bands must have the same shape")
    
    height, width = red.shape
    
    def stretch_band(band_data, lower_pct=2, upper_pct=98):
        valid_data = band_data[~np.isnan(band_data)]
        if len(valid_data) == 0:
            return np.zeros_like(band_data, dtype=np.uint8)
        p_low, p_high = np.percentile(valid_data, (lower_pct, upper_pct))
        if p_high - p_low == 0:
            return np.zeros_like(band_data, dtype=np.uint8)
        stretched = np.clip((band_data - p_low) / (p_high - p_low), 0, 1)
        stretched = np.where(np.isnan(band_data), 0, stretched)
        return (stretched * 255).astype(np.uint8)
    
    with rasterio.open(
        path, 'w', driver='GTiff', height=height, width=width, count=3,
        dtype='uint8', crs=crs, transform=transform, compress=compression, photometric='RGB'
    ) as dst:
        dst.write(stretch_band(red, *stretch_percentiles), 1)
        dst.write(stretch_band(green, *stretch_percentiles), 2)
        dst.write(stretch_band(blue, *stretch_percentiles), 3)
        dst.set_band_description(1, 'Red')
        dst.set_band_description(2, 'Green')
        dst.set_band_description(3, 'Blue')
        dst.update_tags(
            DATE=datetime.now().isoformat(),
            SENSOR=cube.metadata.get('sensor', 'Unknown'),
            PRODUCT='RGB_TrueColor',
            STRETCH=f'{stretch_percentiles[0]}-{stretch_percentiles[1]} percentile'
        )


def write_multiband_geotiff(
    path: str,
    bands_dict: Dict[str, np.ndarray],
    cube: DataCube,
    compression: str = "LZW"
) -> None:
    """Write multi-band GeoTIFF with all ET products."""
    dtypes = [arr.dtype for arr in bands_dict.values()]
    dtype = 'float32' if any(dt == np.float64 for dt in dtypes) else (dtypes[0] if dtypes else 'float32')
    
    crs = cube.crs
    transform = cube.transform
    
    if crs is None or transform is None:
        raise ValueError("DataCube must have CRS and transform set")
    
    shapes = [arr.shape for arr in bands_dict.values()]
    if len(set(shapes)) > 1:
        raise ValueError("All bands must have the same shape")
    
    height, width = shapes[0]
    count = len(bands_dict)
    
    with rasterio.open(
        path, 'w', driver='GTiff', height=height, width=width, count=count,
        dtype=dtype, crs=crs, transform=transform, compress=compression
    ) as dst:
        for idx, (band_name, data) in enumerate(bands_dict.items(), start=1):
            dst.write(np.where(np.isnan(data), -9999.0, data).astype(dtype), idx)
            dst.set_band_description(idx, band_name)
        dst.update_tags(
            DATE=datetime.now().isoformat(),
            SENSOR=cube.metadata.get('sensor', 'Unknown'),
            PRODUCT='METRIC_ET_multiband',
            BANDS=','.join(bands_dict.keys())
        )


def write_netcdf(
    path: str,
    cube: DataCube,
    variables: Optional[Dict[str, xr.DataArray]] = None
) -> None:
    """Write DataCube to NetCDF with CF compliance."""
    import xarray as xr
    
    ds = xr.Dataset()
    
    for name, data in cube.data.items():
        ds[name] = data
        ds[name].attrs.update({
            'units': cube.metadata.get(f'{name}_units', '1'),
            'long_name': cube.metadata.get(f'{name}_long_name', name),
            'standard_name': cube.metadata.get(f'{name}_standard_name', None)
        })
    
    if variables:
        for name, data in variables.items():
            ds[name] = data
    
    if cube.transform is not None:
        transform = cube.transform
        if hasattr(transform, 'a'):
            ds.attrs['transform_a'] = transform.a
            ds.attrs['transform_b'] = transform.b
            ds.attrs['transform_c'] = transform.c
            ds.attrs['transform_d'] = transform.d
            ds.attrs['transform_e'] = transform.e
            ds.attrs['transform_f'] = transform.f
    
    ds.attrs.update({
        'title': 'METRIC Evapotranspiration Data',
        'institution': 'METRIC Remote Sensing',
        'source': cube.metadata.get('sensor', 'Landsat'),
        'history': f'Created {datetime.now().isoformat()}',
        'references': 'METRIC model for evapotranspiration estimation',
        'Conventions': 'CF-1.8'
    })
    
    ds.to_netcdf(path)
    ds.close()


def write_statistics_csv(path: str, stats_dict: Dict[str, Any]) -> None:
    """Write summary statistics to CSV."""
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Statistic', 'Value', 'Unit'])
        for key, value in stats_dict.items():
            if isinstance(value, (int, float)):
                unit = stats_dict.get(f'{key}_unit', '')
                writer.writerow([key, value, unit])


def _convert_to_serializable(value):
    """Convert values to JSON-serializable types."""
    import xarray as xr
    
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_convert_to_serializable(v) for v in value]
    if isinstance(value, dict):
        return {k: _convert_to_serializable(v) for k, v in value.items()}
    if isinstance(value, xr.DataArray):
        vals = value.values
        if np.isscalar(vals):
            return _convert_to_serializable(float(vals))
        return None
    if hasattr(value, 'item'):
        return value.item()
    if hasattr(value, 'tolist'):
        return value.tolist()
    return str(value)


def write_metadata(
    path: str,
    cube: DataCube,
    calibration: CalibrationResult,
    input_files: Optional[Dict[str, str]] = None,
    processing_params: Optional[Dict[str, Any]] = None,
    quality_info: Optional[Dict[str, Any]] = None
) -> None:
    """Write processing metadata to JSON."""
    def _to_float(val):
        if val is None:
            return None
        if isinstance(val, (int, float, np.integer, np.floating)):
            return None if np.isnan(val) else float(val)
        return None
    
    extent = cube.extent
    extent_serializable = _convert_to_serializable(extent) if extent is not None else None
    
    metadata = {
        'scene_id': _convert_to_serializable(cube.metadata.get('scene_id', 'Unknown')),
        'acquisition_time': cube.acquisition_time.isoformat() if cube.acquisition_time else None,
        'calibration': {
            'a_coefficient': _to_float(calibration.a_coefficient),
            'b_coefficient': _to_float(calibration.b_coefficient),
            'dT_cold': _to_float(calibration.dT_cold),
            'dT_hot': _to_float(calibration.dT_hot),
            'Ts_cold': _to_float(calibration.ts_cold),
            'Ts_hot': _to_float(calibration.ts_hot),
            'air_temperature': _to_float(calibration.air_temperature),
            'Rn_cold': _to_float(getattr(calibration, 'rn_cold', None)),
            'Rn_hot': _to_float(getattr(calibration, 'rn_hot', None)),
            'G_cold': _to_float(getattr(calibration, 'g_cold', None)),
            'G_hot': _to_float(getattr(calibration, 'g_hot', None)),
            'valid': calibration.valid,
            'errors': [str(e) for e in calibration.errors] if calibration.errors else []
        },
        'anchor_pixels': {
            'cold_pixel': {
                'x': _to_float(getattr(calibration, 'cold_pixel_x', None)),
                'y': _to_float(getattr(calibration, 'cold_pixel_y', None)),
                'ndvi': _to_float(getattr(calibration, 'cold_pixel_ndvi', None)),
                'albedo': _to_float(getattr(calibration, 'cold_pixel_albedo', None)),
                'Ts': _to_float(calibration.ts_cold),
                'dT': _to_float(calibration.dT_cold),
                'LAI': _to_float(getattr(calibration, 'cold_pixel_lai', None)),
                'emissivity': _to_float(getattr(calibration, 'cold_pixel_emissivity', None)),
                'Rn': _to_float(getattr(calibration, 'rn_cold', None)),
                'G': _to_float(getattr(calibration, 'g_cold', None)),
                'H': _to_float(getattr(calibration, 'h_cold', None)),
                'LE': _to_float(getattr(calibration, 'le_cold', None)),
                'ETrF': _to_float(getattr(calibration, 'cold_pixel_etrf', None))
            },
            'hot_pixel': {
                'x': _to_float(getattr(calibration, 'hot_pixel_x', None)),
                'y': _to_float(getattr(calibration, 'hot_pixel_y', None)),
                'ndvi': _to_float(getattr(calibration, 'hot_pixel_ndvi', None)),
                'albedo': _to_float(getattr(calibration, 'hot_pixel_albedo', None)),
                'Ts': _to_float(calibration.ts_hot),
                'dT': _to_float(calibration.dT_hot),
                'LAI': _to_float(getattr(calibration, 'hot_pixel_lai', None)),
                'emissivity': _to_float(getattr(calibration, 'hot_pixel_emissivity', None)),
                'Rn': _to_float(getattr(calibration, 'rn_hot', None)),
                'G': _to_float(getattr(calibration, 'g_hot', None)),
                'H': _to_float(getattr(calibration, 'h_hot', None)),
                'LE': _to_float(getattr(calibration, 'le_hot', None)),
                'ETrF': _to_float(getattr(calibration, 'hot_pixel_etrf', None))
            }
        },
        'quality': _convert_to_serializable(quality_info) if quality_info else {
            'scene_quality': _convert_to_serializable(cube.metadata.get('scene_quality', 'UNKNOWN')),
            'cloud_coverage': _to_float(cube.metadata.get('cloud_cover', None)),
            'valid_pixels': _to_float(cube.metadata.get('valid_pixels', None)),
            'ndvi_range': {
                'min': _to_float(cube.metadata.get('ndvi_min', None)),
                'max': _to_float(cube.metadata.get('ndvi_max', None)),
                'mean': _to_float(cube.metadata.get('ndvi_mean', None))
            },
            'temperature_range': {
                'min': _to_float(cube.metadata.get('ts_min', None)),
                'max': _to_float(cube.metadata.get('ts_max', None)),
                'mean': _to_float(cube.metadata.get('ts_mean', None))
            }
        },
        'scene_info': {
            'extent': extent_serializable,
            'shape': {
                'y': _convert_to_serializable(cube.y_dim),
                'x': _convert_to_serializable(cube.x_dim)
            },
            'crs': _convert_to_serializable(str(cube.crs)) if cube.crs else None,
            'sensor': _convert_to_serializable(cube.metadata.get('sensor', 'Unknown')),
            'sun_elevation': _to_float(cube.metadata.get('sun_elevation', None)),
            'sun_azimuth': _to_float(cube.metadata.get('sun_azimuth', None))
        },
        'input_files': _convert_to_serializable(input_files) if input_files else {},
        'processing_parameters': _convert_to_serializable(processing_params) if processing_params else {},
        'processing_info': {
            'timestamp': datetime.now().isoformat(),
            'software': 'METRIC ETa Pipeline',
            'version': '1.0.0'
        }
    }
    
    with open(path, 'w') as f:
        json.dump(metadata, f, indent=2)


class OutputWriter:
    """Main output writer class for METRIC ETa pipeline."""
    
    DEFAULT_PRODUCTS = {
        'required': [
            ('ETaDaily', 'ET_daily', 'float32'),
            ('ETinst', 'ET_inst', 'float32'),
            ('ETrF', 'ETrF', 'float32'),
            ('LE', 'LE', 'float32'),
            ('quality', 'quality_mask', 'uint8')
        ],
        'optional': [
            ('Rn', 'R_n', 'float32'),
            ('G', 'G', 'float32'),
            ('H', 'H', 'float32'),
            ('AirTemp', 'temperature_2m', 'float32'),
            ('dT', 'dT', 'float32')
        ],
        'quality': [
            ('ETqualityClass', 'ET_quality_class', 'uint8'),
            ('ETaClassified', 'ETa_class', 'uint8')
        ],
        'surface': [
            ('NDVI', 'ndvi', 'float32'),
            ('Albedo', 'albedo', 'float32'),
            ('EVI', 'evi', 'float32'),
            ('NDWI', 'ndwi', 'float32'),
            ('LAI', 'lai', 'float32'),
            ('FVC', 'fvc', 'float32'),
            ('SAVI', 'savi', 'float32'),
            ('LST', 'lst', 'float32'),
            ('CWSI_ET', 'CWSI_ET', 'float32'),
            ('CWSI_LST', 'cwsi_lst', 'float32'),
            ('TVDI', 'tvdi', 'float32'),
            ('RGB', 'red', 'uint8'),  # RGB is created separately via write_rgb_image
        ]
    }
    
    def __init__(
        self,
        output_dir: str = ".",
        compression: str = "LZW",
        nodata: float = np.nan,
        output_products: Optional[list] = None,
        output_categories: Optional[list] = None,
        aoi_name: str = "AOI"
    ):
        self.output_dir = Path(output_dir)
        self.compression = compression
        self.nodata = nodata
        self.output_files = []
        self._aoi_name = aoi_name

        if output_products is not None:
            self._output_products = output_products
        elif output_categories is not None:
            from ..config.settings import get_output_products
            self._output_products = get_output_products(output_categories)
        else:
            # Default: use standard preset categories
            from ..config.settings import get_output_products
            self._output_products = get_output_products(["et_core", "energy_balance", "surface_props"])

        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _make_filename(
        self,
        product: str,
        cube: DataCube,
        date: str,
        extension: str
    ) -> Path:
        """Generate output filename: {PRODUCT}_{PLATFORM}_{SENSOR}_{LEVEL}_{RESOLUTION}_{SCENEID}_{DATE}_{AOI}.{extension}"""
        import re
        import logging
        logger = logging.getLogger(__name__)
        
        metadata = cube.metadata
        
        # Get platform (e.g., 'S2', 'S2A', 'S2B', 'landsat-8', 'landsat-9')
        platform_raw = metadata.get('platform', 'unknown')
        platform = self._extract_platform(platform_raw)
        
        # Get sensor (e.g., 'MSI', 'OLI_TIRS')
        sensor = metadata.get('sensor', 'unknown')
        
        # Get processing level (e.g., 'L2A', 'L1C', 'L1GT')
        # LandsatReader maps landsat_correction -> metadata['correction']; also check processing_level
        level = metadata.get('processing_level') or metadata.get('correction', 'unknown')
        
        # Get resolution (e.g., '10', '20', '30')
        resolution = metadata.get('resolution', 'unknown')
        
        # Get scene_id (Landsat: landsat:scene_id; fallback to path_row as SCENEID)
        scene_id_raw = metadata.get('scene_id', 'unknown')
        path = metadata.get('path')
        row = metadata.get('row')
        if path is not None or row is not None:
            path_str = str(path).zfill(3) if path is not None else '000'
            row_str = str(row).zfill(3) if row is not None else '000'
            sceneid = f"{path_str}{row_str}"
        else:
            # Extract scene ID (numeric part like '454' from Sentinel scene IDs)
            sceneid = self._extract_sceneid(scene_id_raw)
        
        # Get date from cube.acquisition_time (most reliable)
        date_clean = 'unknown'
        if cube.acquisition_time:
            try:
                date_clean = cube.acquisition_time.strftime('%Y-%m-%d')
                logger.debug("_make_filename: date from acquisition_time='%s'", date_clean)
            except Exception as e:
                logger.warning("_make_filename: Failed to get date: %s", e)
        
        # Fallback: extract date from scene_id_raw
        if date_clean == 'unknown':
            date_match = re.search(r'(\d{4}-\d{2}-\d{2}|\d{8})', scene_id_raw)
            if date_match:
                date_str = date_match.group(1)
                # Convert YYYYMMDD to YYYY-MM-DD if needed
                if len(date_str) == 8 and '-' not in date_str:
                    date_clean = f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"
                else:
                    date_clean = date_str
                logger.debug("_make_filename: date from scene_id='%s'", date_clean)
        
        logger.debug("_make_filename: date_clean='%s'", date_clean)
        
        aoi = self._aoi_name
        filename = f"{product}_{platform}_{level}_{sceneid}_{date_clean}_{aoi}.{extension}"
        
        logger.debug("_make_filename: Generated '%s'", filename)
        
        return self.output_dir / filename
    
    def _extract_platform(self, platform_raw: str) -> str:
        """Extract platform code from platform string.
        
        Args:
            platform_raw: Raw platform string from metadata
            
        Returns:
            Platform code (e.g., 'S2', 'S2A', 'S2B', 'L8', 'L9')
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not platform_raw or platform_raw == 'unknown':
            return 'unknown'
        
        platform_str = str(platform_raw).lower().strip()
        
        # Sentinel-2 variants
        if 'sentinel-2' in platform_str or 'sentinel2' in platform_str or platform_str.startswith('s2'):
            if 's2a' in platform_str or 'sentinel-2a' in platform_str:
                return 'S2A'
            elif 's2b' in platform_str or 'sentinel-2b' in platform_str:
                return 'S2B'
            else:
                return 'S2'
        
        # Landsat variants
        elif 'landsat-9' in platform_str or 'landsat9' in platform_str or platform_str.endswith('9'):
            return 'L9'
        elif 'landsat-8' in platform_str or 'landsat8' in platform_str or platform_str.endswith('8'):
            return 'L8'
        elif 'landsat-7' in platform_str or 'landsat7' in platform_str or platform_str.endswith('7'):
            return 'L7'
        elif 'landsat-5' in platform_str or 'landsat5' in platform_str or platform_str.endswith('5'):
            return 'L5'
        else:
            # Fallback: try to extract first letter and number
            match = re.search(r'([A-Z]+[\d]+)', str(platform_raw))
            if match:
                return match.group(1)[:4]
            return str(platform_raw)[:4] if len(str(platform_raw)) >= 4 else str(platform_raw)
    
    def _extract_sceneid(self, scene_id_raw: str) -> str:
        """Extract scene ID (numeric identifier) from scene ID string.
        
        Args:
            scene_id_raw: Raw scene ID string
            
        Returns:
            Scene ID (e.g., '454' for Sentinel, 'LC08_170034_20220205' -> '170034')
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not scene_id_raw or scene_id_raw == 'unknown':
            return 'unknown'
        
        scene_id_str = str(scene_id_raw)
        
        # For Sentinel: extract the numeric part (e.g., '454' from scene ID)
        # Sentinel scene IDs often contain a unique numeric identifier
        match = re.search(r'[_-]([\d]{3,})[_-]', scene_id_str)
        if match:
            return match.group(1)
        
        # For Landsat: extract path-row (e.g., '170034' from 'LC08_170034_20220205')
        match = re.search(r'[_-]([\d]{6})[_-]', scene_id_str)
        if match:
            return match.group(1)
        
        # Fallback: try to find any 3+ digit number
        match = re.search(r'([\d]{3,})', scene_id_str)
        if match:
            return match.group(1)
        
        return 'unknown'
    
    def write_et_products(
        self,
        cube: DataCube,
        scene_id: str,
        date: str,
        calibration: Optional[CalibrationResult] = None,
        products: Optional[list] = None
    ) -> Dict[str, str]:
        """Write ET products to GeoTIFF files."""
        import logging
        logger = logging.getLogger(__name__)
        
        output_files = {}
        product_list = products if products is not None else self._output_products
        
        for product_name, band_name, dtype in product_list:
            if band_name in cube.data:
                filepath = self._make_filename(product_name, cube, date, 'tif')
                write_geotiff(
                    str(filepath), cube.data[band_name], cube,
                    compression=self.compression, nodata=self.nodata, dtype=dtype
                )
                output_files[product_name] = str(filepath)
                self.output_files.append(filepath)
                logger.info(f"write_et_products: Written {product_name} to {filepath}")
            else:
                logger.warning(f"write_et_products: Band '{band_name}' not found. Skipping {product_name}.")
        
        return output_files
    
    def write_custom_products(
        self,
        cube: DataCube,
        scene_id: str,
        date: str,
        products: list
    ) -> Dict[str, str]:
        return self.write_et_products(cube, scene_id, date, products=products)
    
    write_et_products_csv = write_statistics_csv
    
    def compute_statistics(self, cube: DataCube) -> Dict[str, Any]:
        stats = {}
        for band_name in ['ET_daily', 'ET_inst', 'ETrF', 'LE']:
            if band_name in cube.data:
                data = cube.data[band_name]
                if hasattr(data, 'values'):
                    data = data.values
                valid_data = data[~np.isnan(data)]
                if len(valid_data) > 0:
                    stats[f'{band_name}_mean'] = float(np.nanmean(valid_data))
                    stats[f'{band_name}_std'] = float(np.nanstd(valid_data))
                    stats[f'{band_name}_min'] = float(np.nanmin(valid_data))
                    stats[f'{band_name}_max'] = float(np.nanmax(valid_data))
                    stats[f'{band_name}_count'] = int(np.sum(~np.isnan(data)))
        return stats

    def write_scene_statistics(self, cube: DataCube, scene_id: str, date: str) -> str:
        stats = self.compute_statistics(cube)
        filepath = self._make_filename('statistics', cube, date, 'csv')
        write_statistics_csv(str(filepath), stats)
        self.output_files.append(filepath)
        return str(filepath)
    
    def write_metadata_file(
        self,
        cube: DataCube,
        calibration: CalibrationResult,
        scene_id: str,
        date: str,
        input_files: Optional[Dict[str, str]] = None,
        processing_params: Optional[Dict[str, Any]] = None,
        quality_info: Optional[Dict[str, Any]] = None
    ) -> str:
        filepath = self._make_filename('metadata', cube, date, 'json')
        write_metadata(str(filepath), cube, calibration, input_files, processing_params, quality_info)
        self.output_files.append(filepath)
        return str(filepath)
    
    def write_multiband_product(
        self,
        cube: DataCube,
        scene_id: str,
        date: str,
        bands: list,
        product_name: str = 'ET_products'
    ) -> str:
        bands_dict = {name: cube.data[name].values for name in bands if name in cube.data}
        if not bands_dict:
            raise ValueError("None of the specified bands are available")
        filepath = self._make_filename(product_name, cube, date, 'tif')
        write_multiband_geotiff(str(filepath), bands_dict, cube, self.compression)
        self.output_files.append(filepath)
        return str(filepath)
    
    def write_netcdf_output(
        self,
        cube: DataCube,
        scene_id: str,
        date: str,
        variables: Optional[Dict[str, xr.DataArray]] = None
    ) -> str:
        filepath = self._make_filename(f'{scene_id}_ET', cube, date, 'nc')
        write_netcdf(str(filepath), cube, variables)
        self.output_files.append(filepath)
        return str(filepath)
    
    def get_output_files(self) -> list:
        return self.output_files
    
    def write_rgb_image(
        self,
        cube: DataCube,
        scene_id: str,
        date: str,
        red_band: str = 'red',
        green_band: str = 'green',
        blue_band: str = 'blue'
    ) -> Optional[str]:
        red_data = cube.data.get(red_band)
        green_data = cube.data.get(green_band)
        blue_data = cube.data.get(blue_band)
        
        if red_data is None or green_data is None or blue_data is None:
            logger = logging.getLogger(__name__)
            logger.warning(f"RGB bands not available. Requested: {red_band}, {green_band}, {blue_band}")
            return None
        
        filepath = self._make_filename('RGB', cube, date, 'tif')
        write_rgb_geotiff(
            str(filepath),
            red_data.values if hasattr(red_data, 'values') else red_data,
            green_data.values if hasattr(green_data, 'values') else green_data,
            blue_data.values if hasattr(blue_data, 'values') else blue_data,
            cube, compression=self.compression
        )
        self.output_files.append(filepath)
        return str(filepath)


def write_product_metadata_geojson(
    path: str,
    product_name: str,
    data: np.ndarray,
    cube: DataCube,
    aoi_id: str = "AOI",
    masked_pixels_count: int = 0,
    cloud_cover_percent: Optional[float] = None,
    theoretical_range: tuple = (-1, 1)
) -> None:
    """Write product metadata to GeoJSON format."""
    valid_data = data[~np.isnan(data)]
    
    min_val = float(np.nanmin(valid_data)) if len(valid_data) > 0 else np.nan
    max_val = float(np.nanmax(valid_data)) if len(valid_data) > 0 else np.nan
    mean_val = float(np.nanmean(valid_data)) if len(valid_data) > 0 else np.nan
    
    resolution_m = 30.0
    if cube.transform is not None:
        transform = cube.transform
        resolution_m = abs(transform.a) if hasattr(transform, 'a') else abs(transform[0])
    
    projection = str(cube.crs) if cube.crs else "EPSG:4326"
    
    acquisition_date = cube.acquisition_time.strftime("%Y-%m-%d") if cube.acquisition_time else datetime.now().strftime("%Y-%m-%d")
    
    scene_id_raw = cube.metadata.get('scene_id', 'Unknown')
    scene_id_short = scene_id_raw.split('_')[0] if '_' in scene_id_raw else (scene_id_raw[:6] if len(scene_id_raw) >= 6 else scene_id_raw)
    
    platform_raw = cube.metadata.get('platform', None)
    sensor_raw = cube.metadata.get('sensor', None)
    
    platform = str(platform_raw).lower().replace(' ', '-') if platform_raw else None
    sensor = str(sensor_raw).lower().replace(' ', '_') if sensor_raw else None
    
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "MultiPoint", "coordinates": []},
            "id": "0",
            "properties": {
                "product_name": product_name,
                "platform": platform,
                "sensor": sensor,
                "sceneID": scene_id_short,
                "acquisition_date": acquisition_date,
                "min_value": min_val,
                "max_value": max_val,
                "mean_value": mean_val,
                "masked_pixels": masked_pixels_count,
                "projection": projection,
                "spatial_resolution_m": resolution_m,
                "AOI_ID": aoi_id,
                "cloud_cover_percent": cloud_cover_percent,
                "theoretical_range": f"{theoretical_range[0]} to {theoretical_range[1]}"
            }
        }]
    }
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2)


class ProductMetadataWriter:
    """Helper class for writing product-specific metadata GeoJSON files."""
    
    PRODUCT_CONFIG = {
        'CWSI_ET': {'theoretical_range': (0, 1), 'product_key': 'cwsi_et'},
        'CWSI_LST': {'theoretical_range': (0, 1), 'product_key': 'cwsi_lst'},
        'TVDI': {'theoretical_range': (0, 1), 'product_key': 'tvdi'},
        'ETaDaily': {'theoretical_range': (0, 10), 'product_key': 'eta_daily'},
        'ETinst': {'theoretical_range': (0, 1), 'product_key': 'et_inst'},
        'ETrF': {'theoretical_range': (0, 1.5), 'product_key': 'etrf'},
        'NDVI': {'theoretical_range': (-1, 1), 'product_key': 'ndvi'},
        'LST': {'theoretical_range': (250, 400), 'product_key': 'lst'},
        'Albedo': {'theoretical_range': (0, 1), 'product_key': 'albedo'}
    }
    
    def __init__(self, output_dir: str = ".", aoi_name: str = "AOI"):
        self.output_dir = Path(output_dir)
        self.aoi_name = aoi_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _extract_platform(self, platform_raw: str) -> str:
        """Extract platform code from platform string.
        
        Args:
            platform_raw: Raw platform string from metadata
            
        Returns:
            Platform code (e.g., 'S2', 'S2A', 'S2B', 'L8', 'L9')
        """
        import re
        import logging
        logger = logging.getLogger(__name__)
        
        if not platform_raw or platform_raw == 'unknown':
            return 'unknown'
        
        platform_str = str(platform_raw).lower().strip()
        
        # Sentinel-2 variants
        if 'sentinel-2' in platform_str or 'sentinel2' in platform_str or platform_str.startswith('s2'):
            if 's2a' in platform_str or 'sentinel-2a' in platform_str:
                return 'S2A'
            elif 's2b' in platform_str or 'sentinel-2b' in platform_str:
                return 'S2B'
            else:
                return 'S2'
        
        # Landsat variants
        elif 'landsat-9' in platform_str or 'landsat9' in platform_str or platform_str.endswith('9'):
            return 'L9'
        elif 'landsat-8' in platform_str or 'landsat8' in platform_str or platform_str.endswith('8'):
            return 'L8'
        elif 'landsat-7' in platform_str or 'landsat7' in platform_str or platform_str.endswith('7'):
            return 'L7'
        elif 'landsat-5' in platform_str or 'landsat5' in platform_str or platform_str.endswith('5'):
            return 'L5'
        else:
            # Fallback: try to extract first letter and number
            match = re.search(r'([A-Z]+[\d]+)', str(platform_raw))
            if match:
                return match.group(1)[:4]
            return str(platform_raw)[:4] if len(str(platform_raw)) >= 4 else str(platform_raw)
    
    def _extract_sceneid(self, scene_id_raw: str) -> str:
        """Extract scene ID (numeric identifier) from scene ID string.
        
        Args:
            scene_id_raw: Raw scene ID string
            
        Returns:
            Scene ID (e.g., '454' for Sentinel, 'LC08_170034_20220205' -> '170034')
        """
        import re
        import logging
        logger = logging.getLogger(__name__)
        
        if not scene_id_raw or scene_id_raw == 'unknown':
            return 'unknown'
        
        scene_id_str = str(scene_id_raw)
        
        # For Sentinel: extract the numeric part (e.g., '454' from scene ID)
        # Sentinel scene IDs often contain a unique numeric identifier
        match = re.search(r'[_-]([\d]{3,})[_-]', scene_id_str)
        if match:
            return match.group(1)
        
        # For Landsat: extract path-row (e.g., '170034' from 'LC08_170034_20220205')
        match = re.search(r'[_-]([\d]{6})[_-]', scene_id_str)
        if match:
            return match.group(1)
        
        # Fallback: try to find any 3+ digit number
        match = re.search(r'([\d]{3,})', scene_id_str)
        if match:
            return match.group(1)
        
        return 'unknown'
    
    def _make_geojson_path(self, product: str, cube: DataCube, date: str) -> Path:
        metadata = cube.metadata
        
        # Get platform
        platform_raw = metadata.get('platform', 'unknown')
        platform = self._extract_platform(platform_raw)
        
        # Get processing level
        level = metadata.get('processing_level', 'unknown')
        
        # Get scene ID
        scene_id_raw = metadata.get('scene_id', 'unknown')
        sceneid = self._extract_sceneid(scene_id_raw)
        
        # Format date as YYYY-MM-DD if not already
        date_clean = date
        if len(date) == 8 and '-' not in date:
            date_clean = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
        
        filename = f"META_{product}_{platform}_{level}_{sceneid}_{date_clean}_{self.aoi_name}.geojson"
        return self.output_dir / filename
    
    def write_cwsi_metadata(self, data: np.ndarray, cube: DataCube, date: str, masked_pixels_count: int = 0, cloud_cover_percent: Optional[float] = None) -> str:
        path = self._make_geojson_path('CWSI_ET', cube, date)
        write_product_metadata_geojson(str(path), product_name='CWSI_ET', data=data, cube=cube, aoi_id=self.aoi_name, masked_pixels_count=masked_pixels_count, cloud_cover_percent=cloud_cover_percent, theoretical_range=self.PRODUCT_CONFIG['CWSI_ET']['theoretical_range'])
        return str(path)
    
    def write_eta_daily_metadata(self, data: np.ndarray, cube: DataCube, date: str, masked_pixels_count: int = 0, cloud_cover_percent: Optional[float] = None) -> str:
        path = self._make_geojson_path('ETa', cube, date)
        write_product_metadata_geojson(str(path), product_name='ETaDaily', data=data, cube=cube, aoi_id=self.aoi_name, masked_pixels_count=masked_pixels_count, cloud_cover_percent=cloud_cover_percent, theoretical_range=self.PRODUCT_CONFIG['ETaDaily']['theoretical_range'])
        return str(path)
    
    def write_custom_product_metadata(self, product_name: str, data: np.ndarray, cube: DataCube, date: str, masked_pixels_count: int = 0, cloud_cover_percent: Optional[float] = None, theoretical_range: tuple = (-1, 1)) -> str:
        path = self._make_geojson_path(product_name.upper(), cube, date)
        write_product_metadata_geojson(str(path), product_name=product_name, data=data, cube=cube, aoi_id=self.aoi_name, masked_pixels_count=masked_pixels_count, cloud_cover_percent=cloud_cover_percent, theoretical_range=theoretical_range)
        return str(path)