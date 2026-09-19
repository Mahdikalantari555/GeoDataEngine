## ADDED Requirements

### Requirement: Package identity
The top-level importable package SHALL be `data_engine` (not `metric_et`). The
public API entry point is:
```python
from data_engine import DataCube, METRICPipeline, SentinelPipeline
```
Version is `0.1.0`. Python ≥3.10. Package uses the monorepo `src/` layout
(`libs/data_engine/src/data_engine/`).

#### Scenario: Import check
- **WHEN** `import data_engine` runs
- **THEN** `DataCube`, `METRICPipeline`, and `SentinelPipeline` are accessible; no `metric_et` namespace exists

### Requirement: Domain separation
The library SHALL expose two independent domain sub-packages:
- `data_engine.landsat` — wraps the full METRIC ETa pipeline (Landsat-specific)
- `data_engine.sentinel` — processes Sentinel-2 scenes (Sentinel-specific)

Neither domain SHALL import from the other's sub-package. Both MAY import
from shared top-level modules (`data_engine.core`, `data_engine.surface`, etc.).

#### Scenario: No cross-domain coupling
- **WHEN** `data_engine.landsat` is imported
- **THEN** `data_engine.sentinel` symbols are NOT loaded into memory

#### Scenario: Shared core independence
- **WHEN** a bug is fixed in `data_engine.surface.vegetation`
- **THEN** both `data_engine.landsat` and `data_engine.sentinel` benefit automatically

### Requirement: Shared physics modules
The following modules SHALL remain at the top-level `data_engine.*` namespace (not
nested under a domain sub-package) because they are shared between domains:
`core`, `io`, `utils`, `surface`, `radiation`, `energy_balance`, `et`,
`preprocess`, `output`, `validation`, `calibration`, `weather`, `settings`.
Only the pipeline orchestration logic differs per domain.

#### Scenario: Shared modules importable
- **WHEN** `from data_engine import core, io, utils, surface, radiation, energy_balance, et, preprocess, output, validation, calibration, weather, settings` runs
- **THEN** all imports succeed without error

### Requirement: Core classes preserved
`DataCube`, `constants`, and all shared pipeline-stage classes SHALL be
preserved with unchanged signatures. Scientific behavior is not altered by migration.

#### Scenario: DataCube round-trip
- **WHEN** a band is added and retrieved via `DataCube().add('ndvi', arr).get('ndvi')`
- **THEN** the returned array is identical to the input

### Requirement: Sentinel root config
`data_engine.settings.SENTINEL_ROOT` SHALL be a `Path` object pointing to the
Sentinel-2 asset directory. The default value SHALL be
`D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel`, overridable via the
`DATA_ENGINE_SENTINEL_ROOT` environment variable.

#### Scenario: Env override
- **WHEN** `DATA_ENGINE_SENTINEL_ROOT=/mnt/d/RS/...` is set before import
- **THEN** `data_engine.settings.SENTINEL_ROOT` reflects the env value

### Requirement: CLI entry point
The `data-engine` CLI command SHALL be registered and callable (`data-engine --help`).
Existing click groups are preserved; command names are unchanged.

#### Scenario: CLI help
- **WHEN** `data-engine --help` runs
- **THEN** the command prints usage for `data-engine` and lists available subcommands

### Requirement: Test suite preserved
All existing pytest tests under `data_engine/tests/` SHALL pass after migration.
Sentinel integration tests (copied from ahmadi repo) SHALL also be included and
pass — note: these tests may reference Windows-style scene paths and require
`DATA_ENGINE_SENTINEL_ROOT` to point to valid test assets on the host.
No test logic is altered.

#### Scenario: Full test suite
- **WHEN** `pytest libs/data_engine/tests -q` runs
- **THEN** all tests pass (or pre-existing failures are documented)

### Requirement: Documentation
README.md SHALL reference the monorepo path (`libs/data_engine/`) and list only
the shipped library files. Legacy workflow docs (`WORKFLOW_USAGE.md`, etc.)
are excluded.

#### Scenario: README content
- **WHEN** `libs/data_engine/README.md` is read
- **THEN** it references `libs/data_engine/` and does not mention removed scaffolding files
