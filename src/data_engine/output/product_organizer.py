"""Product Organizer for METRIC ETa model.

This module provides functions to organize METRIC output products into
a structured directory hierarchy with metadata.

The expected output structure is:
    /products/
        /ETaDaily/
            ETaDaily_LC08_20200105_amirkabir.tif
            ETaDaily_LC08_20200105_amirkabir_metadata.json
            ...
        /ETrF/
            ETrF_LC08_20200105_amirkabir.tif
            ETrF_LC08_20200105_amirkabir_metadata.json
            ...
        /NDVI/
            NDVI_LC08_20200105_amirkabir.tif
            NDVI_LC08_20200105_amirkabir_metadata.json
            ...
"""

import os
import json
import shutil
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from loguru import logger


# Sentinel pipeline writes plain names like RGB.tif, NDVI.tif.
# METRIC pipeline writes complex names like NDVI_LC08_20200105_amirkabir.tif.
# PRODUCT_PATTERNS needs to handle both.
PLAIN_PRODUCT_PATTERNS = {
    'RGB': r'^RGB\.tif$',
    'NDVI': r'^NDVI\.tif$',
    'EVI': r'^EVI\.tif$',
    'SAVI': r'^SAVI\.tif$',
    'NDWI': r'^NDWI\.tif$',
}

# METRIC naming convention:
#   <PRODUCT>_<PLATFORM>_<SENSOR>_<LEVEL>_<SCENEID>_<DATE>_<AOI>.tif
# e.g. NDVI_L8_oli_tirs_L2SP_166039_2023-06-06_amirkabir.tif
# Patterns match 5 segments after the product prefix (PLATFORM SENSOR LEVEL SCENEID DATE)
# before the AOI suffix.
SEGMENTS = r'_[A-Za-z0-9]+_[A-Za-z0-9]+_[A-Za-z0-9]+_\d{4}-\d{2}-\d{2}'

METRIC_PRODUCT_PATTERNS = {
    'ETaDaily': r'^ETaDaily' + SEGMENTS + r'_',
    'ETinst': r'^ETinst' + SEGMENTS + r'_',
    'ETrF': r'^ETrF' + SEGMENTS + r'_',
    'LE': r'^LE' + SEGMENTS + r'_',
    'ETqualityClass': r'^ETqualityClass' + SEGMENTS + r'_',
    'ETaClassified': r'^ETaClassified' + SEGMENTS + r'_',
    'CWSI_ET': r'^CWSI_ET' + SEGMENTS + r'_',
    'CWSI': r'^CWSI_(ET)?' + SEGMENTS + r'_',
    'CWSI_LST': r'^CWSI_LST' + SEGMENTS + r'_',
    'TVDI': r'^TVDI' + SEGMENTS + r'_',
    'Rn': r'^Rn' + SEGMENTS + r'_',
    'G': r'^G' + SEGMENTS + r'_',
    'H': r'^H' + SEGMENTS + r'_',
    # Flexible patterns (variable number of segments) for remaining products
    'NDVI': r'^NDVI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'EVI': r'^EVI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'LAI': r'^LAI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'SAVI': r'^SAVI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'FVC': r'^FVC_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'LST': r'^LST_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'Albedo': r'^Albedo_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'Emissivity': r'^Emissivity_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'RGB': r'^RGB_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'AirTemp': r'^AirTemp_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'NDWI': r'^NDWI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'MSI': r'^MSI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'NDMI': r'^NDMI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'MNDWI': r'^MNDWI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'NMDI': r'^NMDI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'NIRv': r'^NIRv_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'GCI': r'^GCI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'NDSI': r'^NDSI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'SI_T': r'^SI_T_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'Rns': r'^Rns_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'Rnl': r'^Rnl_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'RsDown': r'^RsDown_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'RlDown': r'^RlDown_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'RlUp': r'^RlUp_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'VSWI': r'^VSWI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'TCI': r'^TCI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'VCI': r'^VCI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
    'VHI': r'^VHI_[A-Z0-9_]+_\d{4}-\d{2}-\d{2}',
}


class ProductOrganizer:
    """
    Organize METRIC ETa products into structured directories.
    
    This class handles:
    - Scanning output directories for products
    - Creating product-specific subdirectories
    - Moving products to appropriate folders
    - Generating metadata for each product
    """
    
    # Combined: plain patterns (Sentinel pipeline) + METRIC patterns (full naming)
    PRODUCT_PATTERNS = {**PLAIN_PRODUCT_PATTERNS, **METRIC_PRODUCT_PATTERNS}
    
    def __init__(
        self,
        output_dir: str,
        aoi_name: str = "AOI",
        create_metadata: bool = True,
        metadata_in_product_folder: bool = True,
        allowed_products: Optional[List[str]] = None
    ):
        """
        Initialize ProductOrganizer.

        Args:
            output_dir: Base output directory containing products
            aoi_name: Area of Interest name for file naming
            create_metadata: Whether to create metadata JSON files
            metadata_in_product_folder: If True, save metadata in each product's folder.
                                                If False, save in a central metadata folder.
            allowed_products: If provided, only organize products whose band-name
                              appears in this list. Prevents empty folders for
                              unselected product categories.
        """
        self.output_dir = Path(output_dir)
        self.aoi_name = aoi_name
        self.create_metadata = create_metadata
        self.metadata_in_product_folder = metadata_in_product_folder
        self.allowed_products = allowed_products
        self.products_dir = self.output_dir / "products"
        self.metadata_dir = self.products_dir / "metadata" if not metadata_in_product_folder else None
    
    def organize(self) -> Dict[str, List[str]]:
        """
        Organize all products in the output directory.
        
        Returns:
            Dictionary mapping product types to lists of organized file paths
        """
        logger.info(f"Starting product organization in {self.output_dir}")
        
        # Create products directory structure
        self._create_directory_structure()
        
        # Scan for products
        products = self._scan_products()
        
        if not products:
            logger.warning(f"No products found in {self.output_dir}")
            logger.warning("DEBUG: Check if .tif files exist in subdirectories")
            # Debug: list all tif files found
            all_tifs = list(self.output_dir.rglob("*.tif"))
            logger.warning(f"DEBUG: Total .tif files found in output_dir: {len(all_tifs)}")
            for tif in all_tifs[:10]:  # Show first 10
                logger.warning(f"  - {tif}")
            return {}
        
        logger.info(f"Found {sum(len(v) for v in products.values())} products to organize")
        
        # Organize each product type
        organized = {}
        for product_type, files in products.items():
            organized[product_type] = self._organize_product_type(product_type, files)
        
        # Create summary metadata
        if self.create_metadata:
            self._create_summary_metadata(organized)
        
        logger.info(f"Product organization complete. Products saved to {self.products_dir}")
        logger.info(f"Organized products: {list(organized.keys())}")
        for pt, files in organized.items():
            logger.info(f"  {pt}: {len(files)} files")
        
        return organized
    
    def _create_directory_structure(self) -> None:
        """Create the products directory structure."""
        # Create main products directory
        self.products_dir.mkdir(parents=True, exist_ok=True)

        # Create metadata directory (only if not using per-product folders)
        if self.create_metadata and not self.metadata_in_product_folder:
            self.metadata_dir.mkdir(parents=True, exist_ok=True)

        # Per-product directories are created lazily in _organize_product_type()
        # only when matching files are actually found, avoiding empty dirs.
    
    def _scan_products(self) -> Dict[str, List[Path]]:
        """
        Scan output directory for product files.

        Returns:
            Dictionary mapping product types to lists of file paths
        """
        products = {}

        # Debug: Count all tif files first
        all_tif_files = list(self.output_dir.rglob("*.tif"))
        logger.debug(f"Total .tif files found: {len(all_tif_files)}")

        # Build allowed-set when a filter is provided
        allowed_set: Optional[set] = None
        if self.allowed_products:
            allowed_set = {p.lower() for p in self.allowed_products}
            logger.info(f"Product filter active: {sorted(allowed_set)}")

        # Scan all .tif files in output directory and subdirectories
        for tif_file in self.output_dir.rglob("*.tif"):
            # Skip files already in products directory
            if "products" in tif_file.parts:
                continue

            # Skip PNG and JSON files
            if tif_file.suffix.lower() != '.tif':
                continue

            # Identify product type
            product_type = self._identify_product_type(tif_file.name)

            if product_type:
                if allowed_set is not None and product_type.lower() not in allowed_set:
                    logger.debug(f"Filtered out {product_type}: {tif_file.name}")
                    continue
                if product_type not in products:
                    products[product_type] = []
                products[product_type].append(tif_file)
                logger.debug(f"Found {product_type}: {tif_file.name}")
            else:
                logger.debug(f"Unrecognized product file: {tif_file.name}")

        # Summary log
        if products:
            logger.info(f"Scan complete: Found products in {len(products)} categories")
            for pt, files in products.items():
                logger.info(f"  {pt}: {len(files)} files")
        else:
            logger.warning("No recognizable products found during scan")

        return products
    
    def _identify_product_type(self, filename: str) -> Optional[str]:
        """
        Identify the product type from filename.
        
        First tries plain patterns (Sentinel: RGB.tif, NDVI.tif), then
        falls back to METRIC naming convention.
        
        Args:
            filename: Name of the file
            
        Returns:
            Product type string or None if not recognized
        """
        # First try plain patterns (Sentinel pipeline: RGB.tif, NDVI.tif, etc.)
        for product_type, pattern in PLAIN_PRODUCT_PATTERNS.items():
            if re.match(pattern, filename, re.IGNORECASE):
                return product_type
        
        # Then try METRIC naming convention
        for product_type, pattern in METRIC_PRODUCT_PATTERNS.items():
            if re.match(pattern, filename, re.IGNORECASE):
                return product_type
        
        return None
    
    def _organize_product_type(self, product_type: str, files: List[Path]) -> List[str]:
        """
        Organize files for a specific product type.
        
        Args:
            product_type: Type of product (e.g., 'NDVI', 'ETrF')
            files: List of file paths to organize
            
        Returns:
            List of organized file paths
        """
        organized_files = []
        product_dir = self.products_dir / product_type
        
        # Ensure product directory exists
        product_dir.mkdir(parents=True, exist_ok=True)
        
        for src_file in files:
            try:
                # Skip if file doesn't exist (might have been moved already)
                if not src_file.exists():
                    logger.warning(f"File already moved or doesn't exist: {src_file}")
                    continue
                
                dst_file = product_dir / src_file.name
                
                # Handle case where destination already exists
                if dst_file.exists():
                    logger.warning(f"Destination already exists, skipping: {dst_file.name}")
                    continue
                
                # Move file to product directory
                shutil.move(str(src_file), str(dst_file))
                organized_files.append(str(dst_file))
                
                logger.info(f"Moved {src_file.name} -> products/{product_type}/")
                
                # Create metadata if enabled
                if self.create_metadata:
                    self._create_product_metadata(dst_file, product_type)
                    
            except Exception as e:
                logger.error(f"Failed to organize {src_file}: {e}")
                continue
        
        return organized_files
    
    def _create_product_metadata(self, product_file: Path, product_type: str) -> None:
        """
        Create metadata JSON for a product file.
        
        Args:
            product_file: Path to the product file
            product_type: Type of product
        """
        try:
            import rasterio
            import numpy as np
            
            metadata = {
                'product_name': product_file.stem,
                'product_type': product_type,
                'file_path': str(product_file),
                'file_size_bytes': product_file.stat().st_size,
                'creation_date': datetime.now().isoformat(),
            }
            
            # Read raster metadata using rasterio
            with rasterio.open(str(product_file)) as src:
                metadata['width'] = src.width
                metadata['height'] = src.height
                metadata['crs'] = str(src.crs)
                metadata['bounds'] = {
                    'left': src.bounds.left,
                    'bottom': src.bounds.bottom,
                    'right': src.bounds.right,
                    'top': src.bounds.top,
                }
                metadata['transform'] = src.transform.to_gdal()
                metadata['dtype'] = src.dtypes[0]
                metadata['nodata'] = src.nodata
                
                # Calculate statistics if possible
                try:
                    data = src.read(1)
                    if np.issubdtype(data.dtype, np.floating):
                        valid = data[~np.isnan(data)]
                    else:
                        valid = data[data != src.nodata] if src.nodata else data.flatten()
                    
                    if len(valid) > 0:
                        metadata['statistics'] = {
                            'min': float(np.min(valid)),
                            'max': float(np.max(valid)),
                            'mean': float(np.mean(valid)),
                            'std': float(np.std(valid)),
                            'valid_pixels': len(valid),
                            'total_pixels': data.size,
                        }
                except Exception:
                    pass
            
            # Write metadata file into the product's metadata/ subfolder
            # with a META_ prefix and .geojson extension.
            product_dir = product_file.parent
            metadata_dir = product_dir / "metadata"
            metadata_dir.mkdir(parents=True, exist_ok=True)
            meta_path = metadata_dir / f"META_{product_file.stem}.geojson"
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            logger.debug(f"Created metadata for {product_file.name}")
            
        except Exception as e:
            logger.warning(f"Failed to create metadata for {product_file}: {e}")
    
    def _create_summary_metadata(self, organized: Dict[str, List[str]]) -> None:
        """
        Create summary metadata for organized products.
        
        Args:
            organized: Dictionary of product type -> list of file paths
        """
        try:
            summary = {
                'created': datetime.now().isoformat(),
                'aoi_name': self.aoi_name,
                'output_dir': str(self.output_dir),
                'products_dir': str(self.products_dir),
                'products': {}
            }
            
            for product_type, files in organized.items():
                summary['products'][product_type] = {
                    'count': len(files),
                    'files': files,
                    'directory': str(self.products_dir / product_type),
                }
            
            summary_path = self.products_dir / "summary_metadata.json"
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2)
            
            logger.info(f"Created summary metadata at {summary_path}")
            
        except Exception as e:
            logger.warning(f"Failed to create summary metadata: {e}")
    
    def get_product_statistics(self) -> Dict[str, Dict]:
        """
        Get statistics for all organized products.
        
        Returns:
            Dictionary mapping product types to their statistics
        """
        stats = {}
        
        for product_dir in self.products_dir.iterdir():
            if product_dir.is_dir():
                tif_files = list(product_dir.glob("*.tif"))
                if tif_files:
                    stats[product_dir.name] = {
                        'count': len(tif_files),
                        'total_size_mb': sum(f.stat().st_size for f in tif_files) / (1024 * 1024),
                        'files': [f.name for f in tif_files],
                    }
        
        return stats


def organize_products(
    output_dir: str,
    aoi_name: str = "AOI",
    create_metadata: bool = True,
    metadata_in_product_folder: bool = True,
    allowed_products: Optional[List[str]] = None
) -> Dict[str, List[str]]:
    """
    Convenience function to organize products in a single call.

    Args:
        output_dir: Base output directory containing products
        aoi_name: Area of Interest name for file naming
        create_metadata: Whether to create metadata JSON files
        metadata_in_product_folder: If True, save metadata in each product's folder
        allowed_products: If provided, only organize matching products.
                         Pass band-names (e.g. ['ndvi', 'et_daily']) or product
                         display names (e.g. ['NDVI', 'ETaDaily']).

    Returns:
        Dictionary mapping product types to lists of organized file paths
    """
    organizer = ProductOrganizer(
        output_dir=output_dir,
        aoi_name=aoi_name,
        create_metadata=create_metadata,
        metadata_in_product_folder=metadata_in_product_folder,
        allowed_products=allowed_products
    )
    return organizer.organize()
