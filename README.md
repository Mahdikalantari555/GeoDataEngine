# Data Engine — Remote Sensing & Energy Balance Pipeline

`data_engine` is the scientific remote sensing processing engine of the GeoFoundation platform. It provides automated processing pipelines for Landsat (METRIC evapotranspiration model) and Sentinel-2 imagery, including surface radiation balance, aerodynamic roughness, and energy flux estimation.

## Capabilities

- **METRIC ETa Pipeline**: Full implementation of Mapping Evapotranspiration with Internalized Calibration (Allen et al., 2007) for Landsat 4-9 imagery.
- **Surface Properties & Radiation Balance**:
  - Albedo, NDVI, SAVI, EVI, NDWI calculation.
  - Surface emissivity and roughness length ($z_{0m}$) modeling.
  - Shortwave and longwave net radiation ($R_n$).
- **Energy Balance & Turbulent Fluxes**:
  - Soil heat flux ($G$).
  - Sensible heat flux ($H$) with aerodynamic resistance and CIMEC iteration.
  - Latent heat flux ($\lambda ET$) and actual evapotranspiration ($ET_a$, $ET_r F$).
- **Automated Anchor Pixel Selection**:
  - Cold pixel (well-watered alfalfa/crop reference) and hot pixel (dry bare agricultural soil).
- **Sentinel-2 Processing**:
  - Scene querying, tile downloads, multi-band preprocessing, and vegetation index timeseries.

## Architecture

```text
src/data_engine/
  core/            DataCube abstraction, physical constants, quality control
  io/              Landsat and meteorological data readers (GeoTIFF, NetCDF, CSV)
  preprocess/      Cloud/shadow masking, nodata handling, radiometric calibration
  surface/         Vegetation indices (NDVI, SAVI), albedo, emissivity, roughness
  radiation/       Net radiation, shortwave and longwave components
  energy_balance/  Soil, sensible, and latent heat fluxes
  calibration/     Anchor pixel selection (hot/cold) and dT calibration
  et/              Daily and instantaneous ET calculation, reference ET fraction
  landsat/         Landsat-specific METRIC pipeline orchestrator
  sentinel/        Sentinel-2 querying, processing, and pipeline
  weather/         Meteorological data interpolation and fetchers
  validation/      Energy balance closure and flux sanity checks
  cli/             Click CLI command interface (`data-engine`)

app/                 Tkinter desktop GUI (search / download / indices / settings)
  core/              toolkit-free logic: config, ROI, indices, presets, bootstrap
  ui/                Tkinter views plus the testable toolkit abstraction
```

## Installation

Run in the **`geospatial` conda environment**:

```bash
conda run -n geospatial pip install -e libs/data_engine
```

Optional extras:
```bash
pip install -e ".[gui]"   # pyshp, for the desktop GUI's Shapefile support
pip install -e ".[rs]"    # plotting, cartopy, sentinelsat
pip install -e ".[dev]"   # pytest, pytest-cov
```

## Python API Usage

```python
from data_engine.io import LandsatReader, MeteoReader
from data_engine.pipeline import METRICPipeline

# Initialize METRIC pipeline with configuration and area of interest
pipeline = METRICPipeline(
    config={"elevation": 1200.0, "latitude": 29.5},
    roi_path="path/to/aoi.geojson",
)

# Run end-to-end processing on a Landsat scene
results = pipeline.run(
    landsat_dir="path/to/LC08_L1TP_...",
    meteo_path="path/to/hourly_meteo.csv",
    output_dir="output/metric/",
)

print(f"ETa calculated. Mean daily ET: {results['et_24h'].mean():.2f} mm/day")
```

## CLI Usage

```bash
# Run METRIC ETa pipeline from terminal
data-engine run-metric \
  --scene-dir /path/to/LC08_scene/ \
  --weather /path/to/weather.csv \
  --output /path/to/output/ \
  --roi /path/to/field.geojson
```


## Desktop GUI

`app/` provides a Tkinter desktop app for users who do not want a terminal:
STAC search over Planetary Computer, ROI-clipped downloads, spectral indices
and optional METRIC presets, with a self-bootstrapping `.venv`.

```bash
python -m app.main            # first run creates .venv and installs essentials
python -m app.main --version  # print the version
python -m app.main --help     # all launcher flags
```

See [`app/README.md`](app/README.md) for the first-run flow, the mirror
fallback, the portable-folder packaging (`pyinstaller app/GeoDataEngine.spec`)
and the output layout. The GUI reuses the engine's fetchers and vendored
spectral helpers and never requires a conda environment.

## Invariants & Design Principles

1. **Independent scientific engine**: `data_engine` never imports `geomemory`, `geoagent`, or server layers.
2. **Numeric stability**: All band math guards against division by zero and propagates nodata masks explicitly.
3. **Pure processing**: Functional or DataCube-based operations without side effects on source raster files.
