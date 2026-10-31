# Proposal

## Why

GeoDataEngine is a capable remote-sensing data engine (Landsat METRIC ETa, Sentinel-2, spectral indices), but every operation today requires command-line fluency and a pre-configured conda environment. End users (researchers, friends) cannot search the Planetary Computer STAC catalog, download ROI-clipped scenes, or generate indices without writing Python or click commands. A lightweight desktop GUI with self-bootstrapping Python environment removes that barrier while keeping the heavy METRIC stack optional.

## What Changes

- New Tkinter desktop GUI (Windows) with tabs: Search, Download, Indices, Settings.
- STAC search over Planetary Computer for Landsat 8/9 and Sentinel-2, showing only scenes with full ROI coverage; user selects scenes and downloads them (raw bands always downloaded fully).
- Post-download index generation: basic spectral indices (NDVI, EVI, SAVI, NDWI, OPTRAM for Sentinel) on the light stack; METRIC presets (minimal/standard/full) gated behind an "Enable full processing" action that installs heavy dependencies on demand.
- ROI input accepts GeoJSON and Shapefile (shapefile converted to GeoJSON in memory via pyshp).
- Bootstrap launcher: creates a `.venv` next to the exe on first run, installs essentials from the Tuna mirror; upgrades the same venv when full processing is enabled.
- Output layout split into `scenes/` (downloaded scenes) and `products/` folders, with products organized per product type (e.g. `products/ndvi/`) each containing a `metadata/` subfolder; session settings persisted to `config.json`.
- In-app help dialog documenting app usage, METRIC presets (product lists), and index formulas.
- Per-scene progress bar plus scrolling log for download and generation.

## Capabilities

### New Capabilities
- `gui-desktop`: desktop GUI for STAC search, ROI-clipped download, index generation, settings, bootstrap environment, and in-app help.

### Modified Capabilities
<!-- none -->

## Impact

- Affected code: new `app/` package (GUI, bootstrap, help text) plus a launcher entry point; reuses existing `data_engine.io.planetary_computer_fetcher` and `_vendor.geospatial_core.spectral`. No changes to engine internals.
- Dependencies: essentials (numpy, rasterio, requests, pyproj, shapely, pystac-client, planetary-computer, tenacity, loguru, pyshp) installed on first run; heavy set (scipy, pandas, xarray, rioxarray, geopandas, fiona, matplotlib, stackstac) installed only when full processing is enabled.
- Systems: Windows desktop; portable folder distribution; GitHub releases (with domestic mirror fallback noted).
- Breaking: none.
