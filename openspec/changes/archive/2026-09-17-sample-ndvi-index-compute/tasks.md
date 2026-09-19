# Tasks: sample-ndvi-index-compute

## 1. OPTRAM surface index

- [x] 1.1 Create `libs/data_engine/src/data_engine/surface/optram.py` with `OPTRAM` class implementing `compute(cube) -> cube` that adds `optram` band; write test `libs/data_engine/tests/test_optram.py` covering valid computation, missing-band error, and NaN handling; verify: `conda run -n geospatial pytest libs/data_engine/tests/test_optram.py -q` → green.
- [x] 1.2 Export `OPTRAM` from `libs/data_engine/src/data_engine/surface/__init__.py`; verify: `conda run -n geospatial python -c "from data_engine.surface.optram import OPTRAM; print(OPTRAM)"` passes.

## 2. Sample compute script

- [x] 2.1 Write `scripts/compute_sample_indices.py` skeleton: argparse with `--input`, `--dates` (3x), `--sentinel` flag, `--resolution`; define `main()` that reads GeoJSON, extracts first polygon bounds, dispatches to Landsat/Sentinel paths; no network calls yet — stub functions only. Verify: `python scripts/compute_sample_indices.py --help` shows all expected arguments.
- [x] 2.2 Implement Landsat path: use `PlanetaryComputerLandsatFetcher.search_scenes(bbox, start_date, end_date)` for each date (±15 day window), download-and-clip to UTM via `download_and_clip_bands()`, run `METRICPipeline.run(roi_path=...)` with `output_categories=["et_core", "surface_props", "stress_indices", "spectral_indices"]`, save results to `<output_dir>/<scene_id>/`. Verify with mocked STAC responses in unit tests: `pytest scripts/tests/test_compute_sample_indices.py -q` → green.
- [x] 2.3 Implement Sentinel path: use `SentinelPlanetaryComputerFetcher` to search/download bands, run `VegetationIndices(compute_optram=True).compute(cube)`, write NDVI/SAVI/EVI/LAI/FVC/NDMI/MSI/OPTRAM as GeoTIFFs to `<output_dir>/<scene_id>-s2/` using `write_geotiff` from `data_engine.output.writer`. Verify: tests pass with mocked responses.
- [x] 2.4 Add robustness: log warning on missing scene, skip gracefully; overwrite output dir idempotently; print summary of produced files on completion.

## 3. Gitignore and wiring

- [x] 3.1 Add `sample/output/` to `.gitignore`; keep `sample/sasmple.geojson` tracked (it is not gitignored). Verify: `git status --short` does not list anything under `sample/output/`.
- [x] 3.2 Run `conda run -n geospatial ruff check libs/data_engine/src scripts/ && conda run -n geospatial mypy --strict libs/data_engine/src` — fix any new violations.

## 4. Full gate

- [x] 4.1 Run full test suite: `conda run -n geospatial pytest libs/data_engine/tests -q && conda run -n geospatial pytest server/tests -q && pnpm --prefix apps/web build` → clean.
- [x] 4.2 Update `tasks/todo.md`: add new section for `Sample Pipeline` with task checkboxes marked complete.

## Dependencies

1→2 (OPTRAM needed before script uses it), 2→3 (script must exist before adding to gitignore), 3→4.
