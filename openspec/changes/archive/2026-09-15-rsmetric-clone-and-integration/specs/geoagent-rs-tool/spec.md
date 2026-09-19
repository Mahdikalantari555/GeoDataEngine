## ADDED Requirements

### Requirement: Tool registration
`rs_compute_et` SHALL be registered in the geoagent `Registry` under the `[rs]`
extra. When `[rs]` is not installed, calling the tool returns a structured
error naming the required extra — never an uncaught ImportError.

The `[rs]` extra in `libs/geoagent/pyproject.toml` is expanded from its original
scope (`["geolearn"]`) to `["geolearn", "data-engine"]`. This is intentional:
both libraries provide remote-sensing processing capabilities and the `[rs]`
extra now means "remote-sensing processing dependencies" for geoagent.

#### Scenario: Missing extra
- **WHEN** `rs_compute_et` is called without data_engine installed
- **THEN** result is `status=validation_error` with message containing "install geoagent[rs]"

### Requirement: rs_compute_et contract
`rs_compute_et(landsat_dir, output_dir, config?)` SHALL call
`data_engine.landsat.METRICPipeline(config=config or {}).run(landsat_dir, meteo_data=[], output_dir=output_dir)`
and return a `ToolResult` with:
- `artifacts`: list of `ArtifactRef` for each output GeoTIFF (ET_daily, ETrF, LE, H, Rn, G, dT)
- `value`: compact summary `{ET_daily_mean, ET_daily_std, ETrF_mean, quality}` where missing values indicate pipeline failure

#### Scenario: Valid scene
- **WHEN** landsat_dir contains a valid Landsat L2 scene with MTL.json
- **THEN** output GeoTIFFs are written; artifacts list contains 7 paths; value has numeric means

#### Scenario: Missing input
- **WHEN** landsat_dir does not exist
- **THEN** status=failed with error describing the missing directory

### Requirement: Artifact discipline
Every output file SHALL be registered as an artifact (path + sha256) by the
registry wrapper; tools return paths + stats only, never raw numpy arrays.

#### Scenario: Artifact output
- **WHEN** `rs_compute_et` completes successfully
- **THEN** every output GeoTIFF appears in `artifacts` with `path` and `sha256` fields

### Requirement: Timeout
Tool timeout SHALL be 600 s (pipeline can take minutes on large scenes).

#### Scenario: Timeout configured
- **WHEN** the tool definition is inspected
- **THEN** `timeout_s == 600.0`

### Requirement: Sandbox
`landsat_dir` and `output_dir` SHALL resolve within sandbox roots (workspace dir
by default).

#### Scenario: Relative path resolution
- **WHEN** `landsat_dir` or `output_dir` is passed as a relative path
- **THEN** it resolves relative to the workspace directory
