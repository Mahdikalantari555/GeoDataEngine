## Why

The thesis uses a standalone METRIC ETa implementation at `/home/asus/Projects/metric` (Landsat-only). It lives outside the GeoFoundation monorepo, so it cannot be consumed as a first-class library by GeoAgent tools. A parallel Sentinel-2 analysis path exists at
`D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel` but duplicates shared code (DataCube, OutputWriter, VegetationIndices, etc.) because the two domains are not yet unified under one package.

The METRIC algorithm is Landsat-specific. Rebranding the Landsat domain as `landsat` makes the separation of concerns explicit, and elevating shared utilities to the top-level `data_engine.*` namespace eliminates duplication across satellite domains.

## What Changes

1. Clone `https://github.com/Mahdikalantari555/metric` into `libs/data_engine/` and remove `.git` so it becomes a first-class monorepo submodule.
2. Rename the Python package from `metric_et` to `data_engine` (top-level importable as `import data_engine`). Adopt the monorepo `src/` layout: package lives at `libs/data_engine/src/data_engine/`. Promote shared modules (`core/`, `io/`, `utils/`, `surface/`, `radiation/`, `energy_balance/`, `et/`, `preprocess/`, `output/`, `validation/`, `calibration/`, `weather/`) to top-level `data_engine.*` packages — they are satellite-agnostic infrastructure used by both domains.
3. Extract the METRIC ETa pipeline into `data_engine.landsat` (formerly `metric_et.pipeline`). `METRICPipeline` is a thin wrapper that delegates to the shared core. Landsat-specific orchestration lives only in `data_engine.landsat.pipeline`.
4. Copy the Sentinel-2 module from `D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel/` into `data_engine.sentinel/`, fix all `metric_et.X` imports to `data_engine.X`, and ensure it references only the shared-core layer.
5. Remove research scaffolding from the clone (not needed as shipped library): `Fetch_Data.py`, `Calculate_et.py`, `calculate_et_planetary.py`, `interpolate_et.py`, `run_metric_workflow.py`, `WORKFLOW_USAGE.md`, `scripts/`, `examples/`, `uv.lock`, `test_integration_config.py`.
6. Rewrite `pyproject.toml`: `requires-python = ">=3.10"`, `where = ["src"]` to match monorepo convention, `name = "data-engine"`, align optional extras with monorepo convention (`[rs]` for heavy RS deps, matching geoagent's existing `[rs]` extra), update CLI script name from `metric-et` to `data-engine`.
7. Add `data_engine.settings` — a new top-level module with `SENTINEL_ROOT` (Path, defaults to `D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel`, env-overridable via `DATA_ENGINE_SENTINEL_ROOT`). Named `settings` to avoid name collision with `data_engine.sentinel.config` which holds Sentinel-specific constants like `SENTINEL_COLLECTION`.
8. Add `data_engine` to the existing `[rs]` extra in `libs/geoagent/pyproject.toml` (alongside the existing `geolearn` entry). This expands the semantic scope of `[rs]` from "geolearn only" to "remote-sensing processing libs". Document this in the design. Add a `rs_compute_et` tool wrapping `data_engine.landsat.METRICPipeline.run()`.
9. Run ruff/mypy on migrated code; fix any pre-existing violations without changing scientific logic.

## Capabilities

### New Capabilities
- `data-engine-library`: Clean monorepo library with renamed package, shared core promoted to top-level `data_engine.*` (src-layout), dual-domain sub-packages (`landsat/`, `sentinel/`), no git history bleed.
- `geoagent-rs-tool`: `rs_compute_et` tool in the GeoAgent registry — one call to run the full METRIC pipeline on a Landsat scene, outputs GeoTIFFs registered as tool artifacts.

### Modified Capabilities
- `gis-tools` (geoagent): The existing `geo_compute_indices` tool computes NDVI/EVI natively; the new `rs_compute_et` tool delegates to `data_engine.landsat.METRICPipeline` when the `[rs]` extra is installed. Both coexist — indices-first for simple calls, ET pipeline for energy-balance work. The `[rs]` extra in geoagent now also pulls in `data-engine`.

## Impact

- **New lib**: `libs/data_engine/` (cloned + renamed from external repo + sentinel module added).
- **GeoAgent tool**: `rs_compute_et` in `libs/geoagent/src/geoagent/tools/rs_tools.py`; registered under `[rs]` extra wiring.
- **API surface**: No server/router changes — `rs_compute_et` runs client-side via the tool registry threadpool.
- **Deps**: `data_engine` base dependencies (numpy/scipy/pandas/xarray/rasterio/geopandas/click/pyyaml/loguru/tqdm/requests) are required at install; RS-heavy deps (matplotlib/seaborn/cartopy/sentinelsat/scikit-learn) are in the `[rs]` extra. All RS-heavy imports are lazy in geoagent; no new top-level deps for base installs.
- **Risks**: Pre-existing code has minor style/mypy issues; must be fixed in migration step. Sentinel module originally imported from `metric_et.*` — all references must be updated to `data_engine.*`. Scientific logic preserved verbatim during rename. Sentinel integration tests reference Windows-style scene paths and may not run without path overrides on Linux.
