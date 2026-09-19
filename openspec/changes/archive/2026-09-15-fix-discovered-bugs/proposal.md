## Why

Static checks revealed an import break in `libs/data_engine/tests/test_planetary_computer_fetcher.py`, which imports `NoSceneFoundError`, `AuthenticationError`, `DownloadError`, `PartialDataError`, and `GeometryError` from `data_engine.io.planetary_computer_fetcher` — but that module defines no error classes, so the whole test module fails at collection. The error classes exist in `data_engine.io.errors` and are already re-exported by `data_engine.io`. The sample pipeline script (`scripts/compute_sample_indices.py`) also lacks unit tests with mocked STAC responses. Fixing the import path and adding those tests restores clean CI gates.

## What Changes

- Import the five I/O error classes (`NoSceneFoundError`, `AuthenticationError`, `DownloadError`, `PartialDataError`, `GeometryError`) in `test_planetary_computer_fetcher.py` from `data_engine.io.errors` (or the `data_engine.io` package) instead of `data_engine.io.planetary_computer_fetcher`, so the module collects instead of raising `ImportError`.
- Add unit tests for `scripts/compute_sample_indices.py` with mocked Planetary Computer STAC responses so Landsat and Sentinel paths exercise without network calls.
- Run ruff/mypy/lint gates on all touched code and verify existing tests continue to pass.

## Capabilities

### New Capabilities
- `data-engine-io-complete`: Define observable requirements for the `data_engine.io` package surface, ensuring all custom exception classes defined in `errors.py` are exported and reachable via the public module path used by downstream libraries and tests.
- `sample-script-testability`: Define observable requirements for the sample pipeline script, including deterministic unit tests with mocked satellite fetchers and verifiable CLI help output.

### Modified Capabilities
*(none — no existing spec behavior is changing; only library exports and new sample-script tests are added)*

## Impact

- **Modified files**: `libs/data_engine/src/data_engine/io/__init__.py`
- **New files**: `scripts/tests/test_compute_sample_indices.py`, `openspec/specs/data-engine-io-complete/spec.md`, `openspec/specs/sample-script-testability/spec.md`
- **Verified commands**:
  - `python -c "from data_engine.io import PartialDataError"`
  - `conda run -n geospatial pytest scripts/tests/test_compute_sample_indices.py -q`
  - `conda run -n geospatial ruff check libs/data_engine/src/data_engine/io __init__.py && conda run -n geospatial mypy --strict libs/data_engine/src/data_engine/io/__init__.py`
  - Full gate: `conda run -n geospatial pytest libs/data_engine/tests libs/geomemory/tests libs/geoagent/tests server/tests -q` plus `pnpm --prefix apps/web build`