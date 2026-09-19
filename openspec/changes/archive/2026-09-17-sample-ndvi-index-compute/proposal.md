## Why

Researchers need a reproducible, end-to-end workflow that takes a GeoJSON AOI (e.g. `sample/sasmple.geojson`), fetches satellite scenes for 3 dates from Planetary Computer, runs the data-engine pipeline to compute all available spectral and stress indices (ETaDaily, TVDI, LST, NDVI, SAVI, EVI, LAI, FVC, NDMI, MSI, CWSI_LST, VSWI, etc.), and writes clipped outputs directly into the same folder. This turns the library's theoretical capability into a practical daily-use script.

## What Changes

1. Add a reusable Python module `scripts/compute_sample_indices.py` that reads a GeoJSON AOI, searches Planetary Computer for Landsat 8/9 scenes at 3 specified dates, downloads-and-clips bands to UTM, runs the METRIC pipeline with output categories limited to `["surface_props", "stress_indices", "spectral_indices"]` (no radiation, energy balance, or quality bands), and writes all products as GeoTIFFs into `sample/output/`.
2. Add a Sentinel-2 path in the same module: search Sentinel-2 L2A scenes for the same dates, clip bands, compute NDVI/SAVI/EVI/LAI/FVC via `VegetationIndices`, and optionally compute OPTRAM soil-moisture proxy via new `data_engine.surface.optram.OPTRAM` class.
3. Add `sample/output/` to `.gitignore`; keep `sample/sasmple.geojson` tracked.
4. Add `OPTRAM` class to `data_engine.surface.optram` (new file) implementing the optical-path-length-adjusted reflectance model for soil moisture estimation from Sentinel-2 bands.

## Capabilities

### New Capabilities
- `sample-pipeline`: End-to-end AOI → satellite fetch → index computation → GeoTIFF output workflow using data-engine libraries; supports both Landsat and Sentinel-2 inputs with configurable dates and output categories.
- `optram-surface-index`: New OPTRAM soil-moisture proxy class in `data_engine.surface.optram` for Sentinel-2 red/NIR band analysis.

### Modified Capabilities
*(none — all new files)*

## Impact

- **New files**: `scripts/compute_sample_indices.py`, `libs/data_engine/src/data_engine/surface/optram.py`, `libs/data_engine/tests/test_optram.py`, `sample/output/` (gitignored), `.gitignore` update
- **Modified files**: `.gitignore` (add `sample/output/`), `libs/data_engine/src/data_engine/surface/__init__.py` (export OPTRAM)
- **Deps**: no new hard deps; uses existing `planetary-computer`, `stackstac`, `rasterio`, `xarray` already in `[rs]` extra
- **Tests**: unit tests for OPTRAM class; integration test for `compute_sample_indices` with mocked STAC responses
