# Tasks

## 1. Setup and packaging

- [ ] 1.1 Create `app/` package with `__init__.py`, `bootstrap.py`, `config.py`, `roi.py`, `help_text.py` and verify files import under PYTHONPATH=src
- [ ] 1.2 Add `requirements.txt` (essentials) and `requirements-full.txt` (heavy) and verify both install cleanly in a fresh venv from the Tuna mirror
- [ ] 1.3 Add `GeoDataEngine.spec` (PyInstaller, stdlib+tkinter only) and verify `pyinstaller GeoDataEngine.spec` produces a runnable exe
- [ ] 1.4 Add launcher entry point `app/main.py` that loads config and starts the Tkinter root window; verify window opens

## 2. ROI handling

- [ ] 2.1 Implement `roi.load_roi(path, crs_override=None)` supporting GeoJSON and Shapefile (pyshp -> GeoJSON), defaulting to EPSG:4326 with warning when .prj missing; verify with sample/sample.geojson and a test .shp
- [ ] 2.2 Add CRS override field and display assumed CRS in the log; verify override is applied to a .shp without .prj
- [ ] 2.3 Add unit tests for roi loader (GeoJSON, Shapefile, invalid file, missing .prj) and verify pytest passes

## 3. Bootstrap environment

- [ ] 3.1 Implement first-run venv creation in app dir and pip install from requirements.txt via Tuna mirror with progress callback; verify venv is created and essentials importable
- [ ] 3.2 Implement "Enable full processing" that installs requirements-full.txt into the same venv and updates config.json mode; verify heavy imports (scipy, xarray) succeed after
- [ ] 3.3 Add idempotent re-run (skip if venv present) and mirror URL editability; verify second run does not reinstall
- [ ] 3.4 Add tests for bootstrap skip logic and config mode persistence; verify pytest passes

## 4. Search tab

- [ ] 4.1 Build Search tab UI: satellite selector, ROI file picker, date range, cloud threshold, min coverage ratio, sort selector, Search button; verify fields bind to state
- [ ] 4.2 Wire Search button to fetcher.search_scenes + full-coverage filter; populate table (id, date, cloud%, platform, path, row); verify results match CLI search for sample/sample.geojson
- [ ] 4.3 Implement row checkboxes and selected-count; verify selection persists across re-search
- [ ] 4.4 Add unit tests for search result mapping and coverage filtering; verify pytest passes

## 5. Download tab

- [ ] 5.1 Build Download tab: output dir picker, band info list, Download selected button, progress bar, scrolling log, cancel; verify UI renders
- [ ] 5.2 Wire download to fetcher.fetch_scenes for selected scenes, creating scenes/ output folder; verify files appear under scenes/ for sample/sample.geojson
- [ ] 5.3 Implement skip-already-downloaded and per-band log messages via worker thread + queue + after() polling; verify progress bar advances and log updates
- [ ] 5.4 Add integration test for download of one Landsat scene and verify MTL.json + bands exist

## 6. Indices tab

- [ ] 6.1 Build Indices tab: scene picker (single/batch), basic index checkboxes (NDVI, EVI, SAVI, NDWI, OPTRAM-Sentinel-only), METRIC preset selector (gated), Generate button; verify UI renders
- [ ] 6.2 Implement basic index generation using spectral.compute_spectral_index + rasterio I/O, writing to products/<index>/ with metadata under products/<index>/metadata/; verify products/ndvi/<scene>.tif created and readable for a downloaded scene
- [ ] 6.3 Implement METRIC preset execution (minimal/standard/full) when full mode enabled, writing OUTPUT_PRESETS products; verify standard preset produces expected files
- [ ] 6.4 Add tests for basic index generation and METRIC preset mapping; verify pytest passes

## 7. Settings tab and persistence

- [ ] 7.1 Build Settings tab: default output dir, date range, cloud threshold, min coverage ratio, mirror URL, venv status, Enable full processing button; verify fields bind
- [ ] 7.2 Implement config.json load/save in app dir and auto-restore on startup; verify settings persist across restart
- [ ] 7.3 Wire Enable full processing button to bootstrap heavy install and update status; verify status switches to Full after install

## 8. Help dialog

- [ ] 8.1 Draft help text: app usage, METRIC presets with product lists, basic indices with formulas (including OPTRAM); verify text renders in scrollable dialog
- [ ] 8.2 Wire Help button in Indices tab (and menu) to open dialog; verify dialog opens and scrolls

## 9. Integration and packaging

- [ ] 9.1 End-to-end smoke test: search + download one Landsat scene + generate NDVI; verify outputs under scenes/ and products/ndvi/ with metadata under products/ndvi/metadata/
- [ ] 9.2 Build exe with PyInstaller and smoke-test bootstrap on a clean folder; verify first-run creates venv and app launches
- [ ] 9.3 Write README section: install, first-run, mirror fallback, GitHub releases note; verify documented commands run as written
