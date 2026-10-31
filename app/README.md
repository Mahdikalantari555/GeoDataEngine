# GeoDataEngine Desktop

A small Tkinter desktop app on top of the `data_engine` scientific engine. It
lets non-CLI users search the Microsoft Planetary Computer STAC catalog,
download ROI-clipped Landsat 8/9 and Sentinel-2 scenes, compute spectral
indices, and (optionally) run the METRIC ETa presets.

- **Search** — STAC search for Landsat 8/9 and Sentinel-2; only scenes that
  cover the region of interest are listed.
- **Download** — every required band of a selected scene, clipped to the ROI,
  into `<output>/scenes/<scene>/` with an `MTL.json`.
- **Indices** — NDVI, EVI, SAVI, NDWI on the light stack, plus OPTRAM for
  Sentinel-2; METRIC presets (`minimal`/`standard`/`full`) once full processing
  is enabled.
- **Settings** — output folder, mirror URL, CRS override, environment status.

## Requirements

- Python 3.10+ with Tk (`python3-tk` on Debian/Ubuntu, included in the Windows
  and macOS installers).
- Network access to the Planetary Computer STAC API
  (`https://planetarycomputer.microsoft.com/api/stac/v1`).

The app installs its own dependencies into `.venv` next to it on first run:

| tier | file | adds |
| --- | --- | --- |
| essentials ("lite") | `app/requirements.txt` | numpy, rasterio, requests, pyproj, shapely, pystac-client, planetary-computer, tenacity, loguru, pyshp |
| full processing | `app/requirements-full.txt` | `-r requirements.txt` + stackstac, scipy, pandas, xarray, rioxarray, geopandas, fiona, matplotlib, click, pyyaml, tqdm |

## Run from a source checkout

```bash
git clone <repo> && cd GeoDataEngine
pip install -e .                       # installs the engine (heavy stack)
python -m app.main                     # or: python main.py
```

Running from the checkout reuses the interpreter's environment; the engine is
found under `src/` automatically. `--no-bootstrap` skips the environment check:

```bash
python -m app.main --no-bootstrap
python -m app.main --setup-only        # only create .venv + install essentials
python -m app.main --version
```

### Troubleshooting a missing Tk

```
error: Tkinter is not available in this Python installation.
```

Install the Tk bindings — `sudo apt install python3-tk` (Debian/Ubuntu) or use
the official python.org build on Windows — and start the app again. The CLI
(`data-engine ...`) never needs Tk.

## First run

1. The launcher loads (or creates) `config.json` next to the app.
2. If `.venv` is missing, it prints progress while running
   `python -m venv .venv` followed by
   `pip install --index-url <mirror> -r requirements.txt`.
3. The window opens in **Lite** mode. Expect 5–15 minutes for the first run
   (antivirus software makes venv creation slower); later runs skip the
   install.

Press **Enable full processing** in *Settings* to install
`requirements-full.txt` into the same `.venv` and unlock the METRIC presets.

### Mirror fallback

The default `pip` index is the Tuna mirror
(`https://pypi.tuna.tsinghua.edu.cn/simple`). If it is unreachable, set the
mirror field in *Settings* to `https://pypi.org/simple`, or leave it empty to
use pip's default, then press **Save settings**. `--mirror <url>` does the same
for a single run. When a mirror is configured the app also passes
`--trusted-host` automatically.

## Packaging (Windows)

```bash
pip install pyinstaller
pyinstaller app/GeoDataEngine.spec
```

This produces the portable folder `dist/GeoDataEngine/`:

```
GeoDataEngine/
  GeoDataEngine.exe
  requirements.txt
  requirements-full.txt
  config.json          (created on first run)
  .venv/               (created on first run)
```

The build bundles only the GUI (stdlib + tkinter) and the lite engine modules;
the scientific stack is installed into `.venv` at run time, which keeps the
download small and lets pip pick the right wheels for the user's machine.

A frozen executable cannot create a virtual environment by itself, so a
portable interpreter must sit next to it:

- place `python/python.exe` in `dist/GeoDataEngine/`, **or**
- set `GEODATAENGINE_PYTHON=C:\path\to\python.exe`.

Distribution: zip `dist/GeoDataEngine/` and attach it to a GitHub release
(`gh release create v0.1.0 dist/GeoDataEngine.zip`). If GitHub is not
reachable for your users, mirror that zip on a domestic host and document the
link in the release notes.

## Output layout

```
<output>/
  scenes/
    landsat_20240601_166_038/       Landsat bands + MTL.json
    sentinel_20240601/              Sentinel-2 bands + MTL.json
  products/
    ndvi/
      <scene-id>.tif                generated raster
      metadata/<scene-id>.json      provenance + statistics
    optram/ … savi/ … ndwi/ … evi/
    ETaDaily/ … (METRIC products)   <scene-id>.tif + metadata/<scene-id>.json
```

Every product folder follows the same contract: rasters at the top level,
per-product JSON metadata in `metadata/`. The metadata records the scene id,
date, source bands, CRS, transform, statistics, formula, parameters and a UTC
timestamp.

## Development

```bash
pip install -e ".[dev]"
pytest tests/gui               # GUI + core suite (no Tk, no network)
ruff check app tests/gui
mypy app --ignore-missing-imports
```

Design notes:

- `app/core` is toolkit-free and heavy-dependency-free, so it is fully unit
  testable; `app/ui` holds the Tkinter views.
- The views are written against `app/ui/toolkit.py`; `TkToolkit` renders real
  widgets and `FakeToolkit` (`app/ui/fake.py`) lets the tests drive every tab
  without a display server.
- Engine imports go through `app/core/engine_loader.py`, which can load a
  lite-stack module file directly when the full `data_engine` package imports
  (the engine's top-level `__init__` needs the scientific stack).
- `pyshp` converts Shapefiles to GeoJSON in memory, so the lite stack needs no
  fiona/geopandas.
