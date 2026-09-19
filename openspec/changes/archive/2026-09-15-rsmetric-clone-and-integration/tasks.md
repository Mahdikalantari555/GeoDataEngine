# Tasks: rsmetric-clone-and-integration

- [x] Task 1: Clone and strip git
  - Acceptance: `libs/data_engine/.git` does not exist; `git status` from repo root lists `libs/data_engine/` as new untracked content.
  - Verify: `rm -rf libs/data_engine/.git && ls libs/data_engine/` shows package structure.
  - Files: none (new directory created)
  - Note: This task MUST be executed manually; automation is not part of the change.

- [x] Task 2: Rename package to data_engine + adopt src/ layout
  - Acceptance: `import data_engine` resolves from `libs/data_engine/src/data_engine/`; `from data_engine import DataCube, METRICPipeline` works; all internal imports updated (`metric_et.X` → `data_engine.X`); `pyproject.toml` uses `where = ["src"]`.
  - Verify: `conda run -n geospatial python -c "import data_engine; print(data_engine.__version__)"` prints `0.1.0`.
  - Files: all `*.py` under `libs/data_engine/src/data_engine/` (moved from root `data_engine/`); `pyproject.toml`; `README.md`

- [x] Task 3: Remove research scaffolding files
  - Acceptance: `Fetch_Data.py`, `Calculate_et.py`, `calculate_et_planetary.py`, `interpolate_et.py`, `run_metric_workflow.py`, `WORKFLOW_USAGE.md`, `scripts/`, `examples/`, `uv.lock`, `test_integration_config.py` are absent from `libs/data_engine/`.
  - Verify: `ls libs/data_engine/*.py libs/data_engine/*.md` lists only `README.md`.
  - Files: deleted files

- [x] Task 4: Rewrite pyproject.toml
  - Acceptance: `name = "data-engine"`, `requires-python = ">=3.10"`, `where = ["src"]`, `[project.scripts] data-engine`, `[optional-dependencies] rs` covers matplotlib/seaborn/cartopy/sentinelsat/scikit-learn.
  - Verify: `conda run -n geospatial pip install -e libs/data_engine` succeeds; `data-engine --help` shows click commands.
  - Files: `libs/data_engine/pyproject.toml`

- [x] Task 5: Add shared-core settings — SENTINEL_ROOT
  - Acceptance: `from data_engine.settings import SENTINEL_ROOT` returns a `pathlib.Path`; default value is `D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel`; overriding via `DATA_ENGINE_SENTINEL_ROOT` env var updates the path.
  - Verify: `conda run -n geospatial python -c "from data_engine.settings import SENTINEL_ROOT; assert 'ahmadi_data' in str(SENTINEL_ROOT)"` passes.
  - Files: `libs/data_engine/src/data_engine/settings.py` (new), `libs/data_engine/src/data_engine/__init__.py` (export)

- [x] Task 6: Promote shared core to top-level data_engine.*
  - Acceptance: All shared modules (`core`, `io`, `utils`, `surface`, `radiation`, `energy_balance`, `et`, `preprocess`, `output`, `validation`, `calibration`, `weather`, `settings`) are importable directly as `data_engine.<module>`. No `metric_et` import paths remain.
  - Verify: `conda run -n geospatial python -c "from data_engine.core import DataCube; from data_engine.surface import VegetationIndices; from data_engine.output import OutputWriter"` passes.
  - Files: directory reorganization under `libs/data_engine/src/data_engine/`

- [x] Task 7: Copy and fix sentinel module
  - Acceptance: `data_engine.sentinel` is importable; all `metric_et.*` references resolved to `data_engine.*`; `SentinelPipeline` and `SentinelFetcher` are accessible from top-level.
  - Verify: `conda run -n geospatial python -c "from data_engine.sentinel import SentinelPipeline, SentinelFetcher"` passes.
  - Sentinel unit tests in `libs/data_engine/tests/integration/test_sentinel_*.py` are present.
  - Caveat: sentinel integration tests reference Windows-style scene paths (`E:\RSGIS\...`); they may not execute on Linux without `DATA_ENGINE_SENTINEL_ROOT` pointing to valid assets. Tests with hardcoded Windows paths are marked `# skip-if-not-Windows` or refactored to use `SENTINEL_ROOT`.
  - Files: copied from `D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel/` → `libs/data_engine/src/data_engine/sentinel/`; import fixes applied

- [x] Task 8: Fix ruff/mypy violations introduced by rename and refactor
  - Acceptance: `conda run -n geospatial ruff check libs/data_engine/src` reports 0 errors; `mypy --strict libs/data_engine/src` reports 0 errors (or pre-existing errors documented and accepted).
  - Verify: same commands above return exit code 0.
  - Files: all touched `*.py` under `libs/data_engine/src/data_engine/`

- [x] Task 9: Add rs_compute_et tool to geoagent
  - Acceptance: `rs_compute_et` appears in `geoagent.registry.Registry.names()`. Calling it with a valid Landsat dir writes ET products and returns artifact refs + stats dict. `[rs]` extra missing yields structured error naming the extra.
  - Verify: `conda run -n geospatial python -c "from geoagent.registry import Registry; r=Registry(); print('rs_compute_et' in r.names())"` is True (after tool registration).
  - Files: `libs/geoagent/src/geoagent/tools/rs_tools.py` (new), `libs/geoagent/src/geoagent/__init__.py` (export), `libs/geoagent/pyproject.toml` (add `data-engine` to existing `[rs]` extra)

- [x] Task 10: Update geoagent pyproject.toml [rs] extra
  - Acceptance: `[project.optional-dependencies] rs = ["geolearn", "data-engine"]` present; base deps unchanged.
  - Verify: `conda run -n geospatial pip install -e libs/geoagent[rs]` installs geoagent, geolearn, and data_engine.
  - Files: `libs/geoagent/pyproject.toml`

- [x] Task 11: Gates
  - Acceptance: `libs/data_engine` passes its own pytest suite (both landsat and sentinel tests); geoagent tests pass; ruff clean across both libs.
  - Verify: `conda run -n geospatial pytest libs/data_engine/tests -q && conda run -n geospatial pytest libs/geoagent/tests -q && conda run -n geospatial ruff check libs/data_engine/src libs/geoagent/src`
  - Files: all above

Dependencies: 1→2→3→4 (sequential clone-work), 5 depends on 2, 6 depends on 2, 7 depends on 6+5, 8 depends on 6+7, 9 depends on 8, 10 independent (parallel with 9), all→11.
