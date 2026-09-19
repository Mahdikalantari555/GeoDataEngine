## Purpose

Orchestrate an end-to-end AOI → satellite fetch → index computation workflow using data-engine, reading a GeoJSON boundary, downloading Landsat/Sentinel scenes for 3 dates from Planetary Computer, computing spectral indices (NDVI, SAVI, EVI, LAI, FVC, NDMI, MSI), stress indices (TVDI, CWSI_LST, VSWI), and ET products (ETaDaily) clipped to the AOI, then writing all outputs as GeoTIFFs into `sample/output/`.

## ADDED Requirements

### Requirement: Landsat scene fetch and pipeline execution
The script SHALL read a GeoJSON FeatureCollection from `--input`, extract the first polygon's bounds, search Planetary Computer for Landsat Collection 2 Level-2 scenes at 3 user-specified dates (with ±15 day tolerance), download-and-clip bands to UTM via stackstac, run `METRICPipeline.run()` with `output_categories=["surface_props", "stress_indices", "spectral_indices"]` (no radiation, energy balance, or quality bands), and write all resulting GeoTIFFs to `sample/output/<scene_id>/`.

#### Scenario: Successful Landsat run for 3 dates
- **WHEN** `scripts/compute_sample_indices.py --input sample/sasmple.geojson --dates 2023-07-01 2023-08-15 2023-10-01` is executed
- **THEN** three scene directories are created under `sample/output/`, each containing `ETaDaily_*.tif`, `tvdi_*.tif`, `lst_*.tif`, `ndvi_*.tif`, `savi_*.tif`, `evi_*.tif`, `lai_*.tif`, `fvc_*.tif`, `ndmi_*.tif`, `msi_*.tif`, and corresponding `_metadata.json` files

#### Scenario: Missing scene on a date
- **WHEN** no Landsat scene matching the date range is found for one of the three requested dates
- **THEN** the script logs a warning, skips that date, and proceeds with the remaining two dates without failing

#### Scenario: AOI outside scene footprint
- **WHEN** the GeoJSON AOI does not intersect any scene footprint
- **THEN** the script exits with code 1 and prints an error message listing the searched dates and the nearest scene found

### Requirement: Sentinel-2 fetch and index computation
When `--sentinel` flag is set, the script SHALL search Sentinel-2 L2A scenes from Planetary Computer for the same 3 dates, download-and-clip bands, compute NDVI, SAVI, EVI, LAI, FVC, NDMI, and MSI via `VegetationIndices.compute()`, compute OPTRAM soil-moisture proxy if the `OPTRAM` class is available, and write outputs to `sample/output/<scene_id>-s2/`.

#### Scenario: Sentinel run with vegetation indices
- **WHEN** `--sentinel --input sample/sasmple.geojson --dates 2023-07-01 2023-08-15 2023-10-01` is executed
- **THEN** three scene directories are created, each containing `ndvi_*.tif`, `savi_*.tif`, `evi_*.tif`, `lai_*.tif`, `fvc_*.tif`, `ndmi_*.tif`, `msi_*.tif`, and `optram_*.tif` (if available)

#### Scenario: Sentinel-only mode without Landsat
- **WHEN** only `--sentinel` is passed (no `--landsat`)
- **THEN** only Sentinel processing runs; Landsat search is skipped entirely

### Requirement: Output directory management
Outputs SHALL be written to `<input-dir>/output/` relative to the GeoJSON file's parent directory. The output directory SHALL be created automatically. Existing outputs SHALL be overwritten without prompting.

#### Scenario: Output path structure
- **WHEN** `--input /home/asus/Projects/GeoFoundation/sample/sasmple.geojson` is used
- **THEN** outputs are written to `/home/asus/Projects/GeoFoundation/sample/output/`

#### Scenario: Idempotent re-run
- **WHEN** the script is run a second time with identical arguments
- **THEN** existing files in `sample/output/` are overwritten and the script completes successfully
