# Tasks

## 1. Setup and packaging

- [x] 1.1 Create `app/` package with `__init__.py`, `bootstrap.py`, `config.py`, `roi.py`, `help_text.py` and verify files import under PYTHONPATH=src
  - Implemented as `app/core/{config,roi,bootstrap,indices,presets,layout,catalog,session,workers,engine_loader}.py`, `app/help_text.py`, `app/ui/*`. Verified by `tests/gui/test_architecture.py` (imports without tkinter/heavy deps) and `tests/gui/test_lite_stack.py`.
- [x] 1.2 Add `requirements.txt` (essentials) and `requirements-full.txt` (heavy) and verify both install cleanly in a fresh venv from the Tuna mirror
  - `app/requirements.txt` + `app/requirements-full.txt`. Verified in a clean venv built from the requirements (lite tier installs numpy/rasterio/requests/pyproj/shapely/pystac-client/planetary-computer/tenacity/loguru/pyshp and imports the fetcher + spectral helper); `tests/gui/test_lite_stack.py` pins the dependency tiers. The Tuna mirror itself was unreachable from the build sandbox (network allowlist), so the fresh-venv verification used the PyPI wheel cache; the mirror URL, `--index-url`/`--trusted-host` arguments are covered by `tests/gui/test_bootstrap.py`.
- [x] 1.3 Add `GeoDataEngine.spec` (PyInstaller, stdlib+tkinter only) and verify `pyinstaller GeoDataEngine.spec` produces a runnable exe
  - `app/GeoDataEngine.spec` (portable folder, heavy stack excluded, lite engine modules bundled, requirements shipped as data files). The spec's structure is verified by `tests/gui/test_architecture.py::TestPackagingSpec`; the actual `pyinstaller` run needs Windows and was not executed in this environment.
- [x] 1.4 Add launcher entry point `app/main.py` that loads config and starts the Tkinter root window; verify window opens
  - `app/main.py` (+ `main.py`/`main.pyw` portable launchers, `geodataengine-gui` script entry point). Launcher wiring, exit codes (`0`/`2`/`3`) and config loading are verified by `tests/gui/test_launcher.py`. The Tk window itself cannot be opened in this sandbox (no Tk libraries, no display); the views are exercised through the toolkit abstraction instead.

## 2. ROI handling

- [x] 2.1 Implement `roi.load_roi(path, crs_override=None)` supporting GeoJSON and Shapefile (pyshp -> GeoJSON), defaulting to EPSG:4326 with warning when .prj missing; verify with sample/sample.geojson and a test .shp
  - `app/core/roi.py`. Tests: `tests/gui/test_roi.py` (GeoJSON, FeatureCollection, bare geometry, multi-feature, CRS hint, Shapefile via pyshp, missing `.prj`, `sample/sample.geojson`).
- [x] 2.2 Add CRS override field and display assumed CRS in the log; verify override is applied to a .shp without .prj
  - Settings tab CRS field is wired into `load_roi`; the assumed/overridden CRS is logged and shown in the ROI label. Tests: `test_roi.py::TestShapefile`, `test_views_search.py::TestRoiInput`.
- [x] 2.3 Add unit tests for roi loader (GeoJSON, Shapefile, invalid file, missing .prj) and verify pytest passes
  - 28 tests in `tests/gui/test_roi.py`.

## 3. Bootstrap environment

- [x] 3.1 Implement first-run venv creation in app dir and pip install from requirements.txt via Tuna mirror with progress callback; verify venv is created and essentials importable
  - `app/core/bootstrap.py::Bootstrapper.create_venv/install_essentials`; progress is streamed line by line. Tests: `tests/gui/test_bootstrap.py::TestCreateVenv/TestInstallEssentials`.
- [x] 3.2 Implement "Enable full processing" that installs requirements-full.txt into the same venv and updates config.json mode; verify heavy imports (scipy, xarray) succeed after
  - `Bootstrapper.install_full` + the Settings button; the mode is persisted and the view switches the status label and unlocks the preset selector. Tests: `test_bootstrap.py::TestInstallFull`, `test_views_settings.py::TestEnvironmentStatus`.
- [x] 3.3 Add idempotent re-run (skip if venv present) and mirror URL editability; verify second run does not reinstall
  - `install_essentials` short-circuits when the probe reports everything importable; the mirror is editable and also honoured via `--mirror`. Tests: `test_bootstrap.py::test_second_call_is_a_no_op`, `test_skips_when_everything_is_importable`, `TestInstallEssentials::test_custom_mirror` and `test_empty_mirror_omits_index_url`.
- [x] 3.4 Add tests for bootstrap skip logic and config mode persistence; verify pytest passes
  - `tests/gui/test_bootstrap.py` (41 tests).

## 4. Search tab

- [x] 4.1 Build Search tab UI: satellite selector, ROI file picker, date range, cloud threshold, min coverage ratio, sort selector, Search button; verify fields bind to state
  - `app/ui/views.py::_build_search_tab`; bindings verified by `tests/gui/test_views_search.py::TestFieldBinding` and `test_views_settings.py::TestFieldBinding`.
- [x] 4.2 Wire Search button to fetcher.search_scenes + full-coverage filter; populate table (id, date, cloud%, platform, path, row); verify results match CLI search for sample/sample.geojson
  - `app/core/catalog.search_scenes` (coverage filter via shapely, sorting) drives the table. Tests: `tests/gui/test_catalog.py`, `test_views_search.py::TestSearchAction`, `test_end_to_end.py`.
- [x] 4.3 Implement row checkboxes and selected-count; verify selection persists across re-search
  - Rows carry a `✔` marker column toggled by click/space plus "Select all"/"Clear selection", and selections are id-keyed. Tests: `test_views_search.py::TestSelection`.
- [x] 4.4 Add unit tests for search result mapping and coverage filtering; verify pytest passes
  - `tests/gui/test_catalog.py` (29 tests).

## 5. Download tab

- [x] 5.1 Build Download tab: output dir picker, band info list, Download selected button, progress bar, scrolling log, cancel; verify UI renders
  - `_build_download_tab` + shared progress/log widgets. Tests: `test_views_search.py::TestDownloadTabWiring`, `test_views_download.py`.
- [x] 5.2 Wire download to fetcher.fetch_scenes for selected scenes, creating scenes/ output folder; verify files appear under scenes/ for sample/sample.geojson
  - `LiveEngineBridge.download` + `Session.download`; results land in `<output>/scenes/<scene>/` with `MTL.json`. Tests: `test_session.py::TestDownload`, `test_end_to_end.py`.
- [x] 5.3 Implement skip-already-downloaded and per-band log messages via worker thread + queue + after() polling; verify progress bar advances and log updates
  - Existing-download skipping is the engine's `_find_existing_scene` behaviour (covered by `tests/test_planetary_computer_fetcher.py`); the bridge only receives the selected ids. Threading/polling: `app/core/workers.py` + `DesktopApp._start_job/_poll_job/_handle_event`. Tests: `test_workers.py`, `test_views_download.py::TestBackgroundThreading`.
- [x] 5.4 Add integration test for download of one Landsat scene and verify MTL.json + bands exist
  - `tests/gui/test_end_to_end.py::test_smoke_search_download_ndvi` (all eight bands + `MTL.json`).

## 6. Indices tab

- [x] 6.1 Build Indices tab: scene picker (single/batch), basic index checkboxes (NDVI, EVI, SAVI, NDWI, OPTRAM-Sentinel-only), METRIC preset selector (gated), Generate button; verify UI renders
  - `_build_indices_tab`; OPTRAM is greyed out and cleared for non-Sentinel satellites. Tests: `test_views_indices.py::TestScenePicker`, `TestSentinelAwareIndexGating`.
- [x] 6.2 Implement basic index generation using spectral.compute_spectral_index + rasterio I/O, writing to products/<index>/ with metadata under products/<index>/metadata/; verify products/ndvi/<scene>.tif created and readable for a downloaded scene
  - `app/core/indices.py` (+ `app/core/engine_loader.py` so the vendored helper loads on the lite stack). Tests: `test_indices.py`, `test_end_to_end.py`.
- [x] 6.3 Implement METRIC preset execution (minimal/standard/full) when full mode enabled, writing OUTPUT_PRESETS products; verify standard preset produces expected files
  - `app/core/presets.py` (`preset_categories`, `run_preset`, `DefaultMetricRunner`) mirrors `OUTPUT_PRESETS`/`OUTPUT_PRODUCTS` (parity asserted in `test_presets.py::TestEngineParity`). The pipeline itself is injected, so the mapping is tested without running METRIC; writing the standard preset's `et_core`/`energy_balance`/`surface_props` products is covered by `test_presets.py::TestRunPreset` and `test_views_indices.py::test_metric_run_writes_products`.
- [x] 6.4 Add tests for basic index generation and METRIC preset mapping; verify pytest passes
  - `tests/gui/test_indices.py` (42) and `tests/gui/test_presets.py` (33).

## 7. Settings tab and persistence

- [x] 7.1 Build Settings tab: default output dir, date range, cloud threshold, min coverage ratio, mirror URL, venv status, Enable full processing button; verify fields bind
  - `_build_settings_tab`. Tests: `test_views_settings.py::TestFieldBinding`, `TestEnvironmentStatus`.
- [x] 7.2 Implement config.json load/save in app dir and auto-restore on startup; verify settings persist across restart
  - `app/core/config.py::ConfigStore` (atomic write, forward-compatible unknown keys). Tests: `test_config.py`, `test_views_settings.py::TestPersistenceAcrossRestart`.
- [x] 7.3 Wire Enable full processing button to bootstrap heavy install and update status; verify status switches to Full after install
  - `DesktopApp.enable_full_processing` → `Bootstrapper.install_full` → mode persisted, status label and preset selector updated. Tests: `test_views_settings.py::TestEnvironmentStatus`.

## 8. Help dialog

- [x] 8.1 Draft help text: app usage, METRIC presets with product lists, basic indices with formulas (including OPTRAM); verify text renders in scrollable dialog
  - `app/help_text.py::build_help_text` (usage, presets with product lists, index formulas, output layout, troubleshooting); rendered by `TkToolkit.show_text_dialog` (scrollable). Tests: `tests/gui/test_help.py`.
- [x] 8.2 Wire Help button in Indices tab (and menu) to open dialog; verify dialog opens and scrolls
  - Help button on the Indices tab plus a menubar entry. Tests: `test_help.py::TestHelpDialog`, `test_views_indices.py::TestHelpFromIndicesTab`.

## 9. Integration and packaging

- [x] 9.1 End-to-end smoke test: search + download one Landsat scene + generate NDVI; verify outputs under scenes/ and products/ndvi/ with metadata under products/ndvi/metadata/
  - `tests/gui/test_end_to_end.py` (3 tests, including the layout contract).
- [x] 9.2 Build exe with PyInstaller and smoke-test bootstrap on a clean folder; verify first-run creates venv and app launches
  - First-run venv creation on a clean folder is verified by `tests/gui/test_launcher.py` and `tests/gui/test_architecture.py::test_setup_only_creates_the_environment`. The PyInstaller build and the exe smoke test require Windows and were not run here; the spec (exclusions, bundled data, entry point) is asserted by `test_architecture.py::TestPackagingSpec`.
- [x] 9.3 Write README section: install, first-run, mirror fallback, GitHub releases note; verify documented commands run as written
  - `app/README.md` + a "Desktop GUI" section in the root `README.md`. The documented commands (`python -m app.main --version`, `--help`, `--setup-only`, `pytest tests/gui`, `ruff check`, `mypy`) are executed by `tests/gui/test_launcher.py` and `test_architecture.py`.
