# Design: data_engine — dual-domain remote-sensing library

## Architecture principle

**Shared infrastructure at the top level. Domain sub-packages beneath.**

The library is split by satellite type. Landsat and Sentinel are independent
processing domains — neither invokes the other — but both share the same
infrastructure (DataCube, I/O, validation, output writers, logging, surface
physics). By placing that infrastructure at the top-level `data_engine.*`
namespace, a bug-fix or optimization in the shared core applies to every
domain automatically.

```
libs/data_engine/
├── pyproject.toml            # name="data-engine", where=["src"]
├── README.md
└── src/
    └── data_engine/
        ├── __init__.py       # exports DataCube, METRICPipeline, SentinelPipeline
        ├── settings.py       # SENTINEL_ROOT (env-overridable, default: D:\...sentinel)
        │
        ├── core/             # DataCube, constants  (satellite-agnostic)
        ├── io/               # LandsatReader, MeteoReader, PlanetaryComputerFetcher
        ├── utils/            # exceptions, logger, retry, validation helpers
        ├── output/           # writer, product_organizer, visualization
        ├── preprocess/       # cloud_mask, resampling (generic routines)
        ├── surface/          # albedo, vegetation indices, emissivity, roughness
        ├── radiation/        # shortwave, longwave, net_radiation
        ├── energy_balance/   # soil, sensible, latent heat flux
        ├── et/               # instantaneous, daily, quality
        ├── calibration/      # DTCalibration, anchor_pixels
        ├── validation/       # integration, comprehensive
        ├── weather/          # met data fetcher
        ├── cli/              # interface.py (click CLI)
        │
        ├── landsat/          # thin METRIC ETa pipeline wrapper (Landsat-specific)
        │   ├── __init__.py   #   → export METRICPipeline
        │   └── pipeline.py   #   → delegates to data_engine.et, .energy_balance, ...
        │
        └── sentinel/         # Sentinel-2 processing (Sentinel-specific)
            ├── __init__.py   #   → export SentinelPipeline, SentinelFetcher
            ├── pipeline.py
            ├── fetcher.py
            ├── pc_fetcher.py
            ├── cloud_mask.py
            ├── optram.py
            ├── runner.py
            ├── app.py        # FastAPI wrapper (local dev only)
            └── config.py     # SENTINEL_COLLECTION, BAND_MAPPING, etc.
```

## Key design decisions

| Decision | Rationale |
|---|---|
| Package name `data_engine`, dir `data_engine/` | Lib serves two satellite domains; old `metric_et`/`rsmetric` no longer scopes the lib accurately |
| Shared physics at top-level (`surface/`, `radiation/`, `energy_balance/`, `et/`) | Both Landsat and Sentinel pipelines import `VegetationIndices`, `OutputWriter`, `DataCube` — keeping them shared avoids duplication |
| `landsat/` is a thin wrapper (not full ET math) | METRIC's ET math is in shared `data_engine.et/`; `landsat/pipeline.py` only orchestrates Landsat-specific IO → pipeline → output |
| Sentinel module copied (not built in-tree) | `D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel/` already works; copying + import fix is fastest path to working code |
| Top-level config module named `settings.py` | Avoids import name clash with `data_engine.sentinel.config` |
| Reuse existing geoagent `[rs]` extra | `libs/geoagent/pyproject.toml` already has `rs = ["geolearn"]`; adding `"data-engine"` expands scope to "remote-sensing processing libs" — documented |

## Rename strategy

- Package dir: `metric_et/` → `src/data_engine/`
- Top-level `__init__.py` exports all shared classes AND domain pipelines:
  ```python
  from data_engine.core import DataCube, constants
  from data_engine.io import LandsatReader, MeteoReader
  from data_engine.landsat import METRICPipeline
  from data_engine.sentinel import SentinelPipeline, SentinelFetcher
  ```
- Internal cross-module imports updated: `metric_et.X` → `data_engine.X` throughout.
  Landsat pipeline: `from metric_et.et...` → `from data_engine.et...`
  Sentinel pipeline: `from metric_et.core.DataCube` → `from data_engine.core import DataCube`

## Files removed (research scaffolding, not library code)

| File | Reason |
|---|---|
| `Fetch_Data.py` | Standalone script, replaced by `io.PlanetaryComputerFetcher` |
| `Calculate_et.py` | Duplicate of pipeline usage pattern |
| `calculate_et_planetary.py` | Same — legacy runner |
| `interpolate_et.py` | Ad-hoc interpolation, no unit tests |
| `run_metric_workflow.py` | Legacy wrapper around Pipeline |
| `WORKFLOW_USAGE.md` | Superseded by docstrings |
| `scripts/` | CI/dev scripts, not shipped with package |
| `examples/` | Exclude from initial migration |
| `uv.lock` | Use conda env + pip editable install |
| `test_integration_config.py` | ahmadi repo test, superseded by `data_engine/tests/` |

## Sentinel module origin

Copied from `D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel/`
(with import-path fixes). The module contents are preserved:

| Original file | Role in new layout |
|---|---|
| `pipeline.py` | `SentinelPipeline` — end-to-end Sentinel-2 processing |
| `fetcher.py` | `SentinelImageFetcher` — high-level STAC downloader |
| `pc_fetcher.py` | `SentinelPlanetaryComputerFetcher` — raw Planetary Computer client |
| `cloud_mask.py` | `SentinelCloudMasker` — SCL-based masking |
| `optram.py` | `STRCalculator` + OPTRAM soil-moisture proxy |
| `runner.py` | Batch-scene orchestrator |
| `app.py` | FastAPI wrapper (kept for local dev) |
| `config.py` | Band mappings, product names |
| `errors.py` | Sentinel-specific exceptions |
| `conftest.py` | pytest fixtures |
| `test_*.py` | Unit tests (moved to `tests/integration/`) |

## Sentinel root path

```python
# data_engine/settings.py
from pathlib import Path
import os

SENTINEL_ROOT = Path(
    os.environ.get(
        "DATA_ENGINE_SENTINEL_ROOT",
        r"D:\RS\Projects\ahmadi_data\ahmadi_data-master\sentinel",
    )
)
```

`data_engine.sentinel` reads `SENTINEL_ROOT` to locate test assets and scene
directories. On Linux / non-Windows environments the env var MUST be set to a
valid path before running tests.

## pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "data-engine"
version = "0.1.0"
description = "Remote-sensing data engine: Landsat (METRIC ETa) and Sentinel-2 processing"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [{name = "GeoFoundation"}]
keywords = ["evapotranspiration", "landsat", "sentinel", "remote-sensing", "energy-balance"]

dependencies = [
    "numpy>=1.24",
    "scipy>=1.10",
    "pandas>=2.0",
    "xarray>=2023.1",
    "rasterio>=1.3",
    "rioxarray>=0.14",
    "geopandas>=0.14",
    "click>=8.1",
    "pyyaml>=6.0",
    "loguru>=0.7",
    "tqdm>=4.65",
    "requests>=2.28",
]

[project.optional-dependencies]
rs = [
    "matplotlib>=3.7",
    "seaborn>=0.12",
    "cartopy>=0.22",
    "sentinelsat>=1.1",
    "scikit-learn>=1.3",
]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]

[project.scripts]
data-engine = "data_engine.cli.interface:cli"

[tool.setuptools.packages.find]
where = ["src"]
```

## GeoAgent integration

`libs/geoagent/pyproject.toml` existing `[rs]` extra:
```toml
[project.optional-dependencies]
rs = ["geolearn", "data-engine"]   # expanded scope: RS processing libs
```

`rs_compute_et` tool definition:

```python
ToolDefinition(
    name="rs_compute_et",
    description=(
        "Run the full METRIC ETa pipeline on a Landsat Collection 2 Level-2 "
        "scene directory. Requires [rs] extra. Writes ET_daily.tif, ETrF.tif, "
        "LE.tif, H.tif, Rn.tif, G.tif, dT.tif to output_dir."
    ),
    params={
        "type": "object",
        "properties": {
            "landsat_dir": {"type": "string", "description": "Path to Landsat scene dir"},
            "output_dir": {"type": "string"},
            "config": {"type": "object", "description": "Optional METRIC config override"},
        },
        "required": ["landsat_dir", "output_dir"],
    },
    timeout_s=600.0,
    cacheable=False,
)
```

Returns: `{"artifacts": [...], "stats": {"ET_daily_mean": float, "ETrF_mean": float}}`

## Execution flow

```
GeoAgent → rs_compute_et(args)
           → data_engine.landsat.METRICPipeline(config=config).run(landsat_dir, meteo_data, output_dir)
           → registers each output tif as ArtifactRef(path, sha256)
           → returns compact summary
```

```
data_engine.sentinel.SentinelPipeline.run(scene_dir, output_dir, roi_path)
           → imports data_engine.core.DataCube
           → imports data_engine.surface.vegetation.VegetationIndices
           → imports data_engine.output.writer.OutputWriter
           → writes index products as GeoTIFFs
```

No domain calls the other's pipeline. They share only the top-level modules.
