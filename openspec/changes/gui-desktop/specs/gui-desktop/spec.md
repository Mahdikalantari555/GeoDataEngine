# Spec Delta

## Purpose

Provide a Windows desktop GUI for GeoDataEngine that lets non-CLI users search the Planetary Computer STAC catalog, download ROI-clipped Landsat/Sentinel scenes, generate spectral indices and optional METRIC ETa outputs, and bootstrap its own Python environment, without managing Python manually.

## ADDED Requirements

### Requirement: STAC search returns only full-coverage scenes
The system SHALL search Planetary Computer for Landsat 8/9 and Sentinel-2 scenes intersecting the ROI and SHALL return only scenes whose footprint fully covers the ROI, respecting the user-configured minimum coverage ratio.

#### Scenario: Full-coverage filtering
- **WHEN** the user runs a search with a valid ROI and minimum coverage ratio of 0.5
- **THEN** every returned scene covers at least 50% valid pixels of the ROI and no partial-coverage scene is listed

#### Scenario: No qualifying scenes
- **WHEN** no scene meets the coverage threshold
- **THEN** the system shows an empty result table and a "no qualifying scenes" message instead of downloading

### Requirement: Search results table with metadata and selection
The system SHALL display search results in a table with columns scene id, date, cloud cover, platform, path, and row (Landsat), each row selectable, and SHALL allow selecting a subset for download.

#### Scenario: Select subset
- **WHEN** the user checks 2 of 5 listed scenes
- **THEN** only the 2 selected scenes are downloaded

### Requirement: ROI input supports GeoJSON and Shapefile
The system SHALL accept an ROI file in GeoJSON or Shapefile (.shp) format, converting Shapefile to GeoJSON in memory before processing, and SHALL warn when no CRS (.prj) is present, defaulting to WGS84.

#### Scenario: Shapefile input
- **WHEN** the user selects a .shp file without a .prj
- **THEN** the system converts it to GeoJSON, warns about missing CRS, and defaults to EPSG:4326

#### Scenario: Invalid ROI file
- **WHEN** the user selects a file that is neither valid GeoJSON nor a readable Shapefile
- **THEN** the system shows an error and does not start the search

### Requirement: Raw bands always download fully
The system SHALL download the complete required band set for the selected satellite (all Landsat required bands or Sentinel blue/green/red/nir08 at minimum) for every selected scene, clipped to the ROI, and SHALL NOT expose per-band download checkboxes.

#### Scenario: Landsat download
- **WHEN** a Landsat scene is downloaded
- **THEN** blue, green, red, nir08, swir16, swir22, lwir11, and qa_pixel are saved clipped to the ROI with an MTL.json

### Requirement: Basic index generation on the light stack
The system SHALL generate NDVI, EVI, SAVI, NDWI, and (Sentinel only) OPTRAM from downloaded bands using only numpy and rasterio, without requiring heavy dependencies, and SHALL save each as a GeoTIFF under products/<index>/ with per-product metadata under products/<index>/metadata/.

#### Scenario: Basic indices for Sentinel
- **WHEN** the user selects NDVI and OPTRAM for a downloaded Sentinel scene
- **THEN** products/ndvi/<scene>.tif and products/optram/<scene>.tif are written using the scene's transform and CRS, and matching metadata JSON files are written under products/ndvi/metadata/ and products/optram/metadata/

#### Scenario: Heavy index gated
- **WHEN** the user requests a METRIC preset while heavy dependencies are not installed
- **THEN** the system prompts to enable full processing instead of attempting the run

### Requirement: METRIC presets when full processing enabled
When heavy dependencies are installed, the system SHALL offer METRIC output presets minimal, standard, and full, each mapping to the existing OUTPUT_PRESETS categories, and SHALL write each resulting product under products/<product_name>/ with metadata under products/<product_name>/metadata/.

#### Scenario: Standard preset
- **WHEN** full processing is enabled and the user selects the standard preset
- **THEN** et_core, energy_balance, and surface_props products are generated for the scene

### Requirement: Bootstrap environment on first run
The system SHALL create a `.venv` in its own directory on first run, install essential dependencies from the configured mirror (default Tuna), and reuse that venv on subsequent runs without re-downloading.

#### Scenario: First run bootstrap
- **WHEN** no `.venv` exists
- **THEN** the system creates the venv, installs essentials, and shows progress; later runs skip installation

#### Scenario: Enable full processing
- **WHEN** the user clicks "Enable full processing"
- **THEN** heavy dependencies are installed into the same venv and the status changes to Full

### Requirement: Progress and status visibility
The system SHALL show a per-scene progress indicator, a scrolling log of operations (including per-band save messages), and a status bar reflecting venv mode and last operation result.

#### Scenario: Download progress
- **WHEN** scenes are downloading
- **THEN** the progress bar advances per scene and the log shows each band saved

### Requirement: Session persistence
The system SHALL persist the last used ROI path, date range, output directory, cloud threshold, and min coverage ratio to config.json in its own directory and SHALL restore them on startup.

#### Scenario: Restore settings
- **WHEN** the app starts with an existing config.json
- **THEN** the Search tab fields are populated from the saved values

### Requirement: Output folder layout
The system SHALL store downloaded scenes under `<output>/scenes/` and generated products under `<output>/products/`, with each product type in its own subfolder (e.g. `products/ndvi/`) containing a `metadata/` subfolder for per-product JSON metadata.

#### Scenario: Layout created
- **WHEN** a download completes
- **THEN** the scene directory exists under scenes/ and any later index output goes under products/<product>/ with metadata under products/<product>/metadata/

### Requirement: In-app help dialog
The system SHALL provide an in-app help dialog documenting app usage, the METRIC presets with their product lists, and the basic indices with their formulas.

#### Scenario: Help opened
- **WHEN** the user opens help
- **THEN** a scrollable dialog shows usage, preset product lists, and index formulas including OPTRAM

### Requirement: Shapefile CRS handling
The system SHALL allow overriding the assumed CRS for a Shapefile without .prj and SHALL display the assumed CRS in the log.

#### Scenario: CRS override
- **WHEN** the user sets a CRS override before loading a .shp without .prj
- **THEN** that CRS is used for the conversion
