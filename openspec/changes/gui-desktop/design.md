# Design

## Context

GeoDataEngine exposes two fetchers (`PlanetaryComputerLandsatFetcher`, `SentinelPlanetaryComputerFetcher`) and `METRICPipeline`. Both fetchers already clip to ROI via HTTP range requests and return metadata dicts with `id`, `datetime`, `cloud_cover`, `platform`, `path`/`row` (Landsat), `bbox`, `geometry`. The spectral index module `_vendor/geospatial_core/spectral.py` is pure numpy. No GUI, no packaging, no bootstrap exists. See proposal.md for motivation.

Constraints: Windows only; restricted network in Iran → Tuna mirror; no admin rights assumed; friends must not manage Python manually.

## Goals / Non-Goals

**Goals:**
- Portable folder with one exe entry point; self-bootstrapping `.venv`.
- Search → select → download clipped scenes; generate basic indices (and METRIC presets when heavy deps enabled).
- ROI from GeoJSON or Shapefile (converted in memory).
- Per-scene progress + scrolling log; status bar.
- Session persistence via `config.json`.
- In-app help dialog.

**Non-Goals:**
- Image/preview rendering (metadata only).
- True single-file exe with first-run source extraction.
- macOS/Linux.
- Full METRIC by default (gated behind "Enable full processing").
- Offline wheelhouse (v2).
- Parallel multi-scene downloads (sequential for v1).

## Decisions

1. **GUI framework: Tkinter (stdlib) over Streamlit/PyQt**
   - Rationale: zero extra GUI dependency; PyInstaller-friendly; no browser/runtime.
   - Alternative: Streamlit — easier dev but requires browser + heavy packaging; rejected.

2. **Distribution: portable folder with one exe entry point (not single-file)**
   - Rationale: bootstrap needs `app/` source runnable by the venv python; single-file extraction adds fragility.
   - Alternative: true single exe extracting source on first run — deferred (v2 if demanded).

3. **Bootstrap: `uv`-free, stdlib `venv` + `pip` with Tuna mirror**
   - Rationale: no extra bootstrap binary; `python -m venv` + `pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple`; mirror editable in Settings.
   - Alternative: bundle `uv` for speed — deferred; revisit if first-run time unacceptable.

4. **Shapefile: convert to GeoJSON in memory via `pyshp` (pure Python)**
   - Rationale: avoids pulling geopandas/fiona into the lite stack; existing `_normalize_geometry` already accepts GeoJSON dicts.
   - Alternative: geopandas — rejected for lite; still used in full mode.

5. **Heavy deps: same `.venv`, installed on demand**
   - Rationale: single environment; "Enable full processing" button pip-installs `requirements-full.txt` into the existing venv; status tracked in `config.json`.

6. **Output layout: `scenes/` + `products/<product>/` + `metadata/`**
   - Rationale: user request; each product type gets its own folder (e.g. `products/ndvi/`) with a `metadata/` subfolder holding per-product JSON metadata (scene id, date, source bands, transform, CRS, params, timestamp).
   - Products are named `<scene_id>.tif` (or `<scene_id>_<product>.tif` when ambiguous).

7. **Progress: per-scene bar + scrolling log + status bar**
   - Rationale: user wants correct, visible progress; fetcher already logs per band; GUI mirrors via a queue polled by Tkinter `after()`.

8. **ROI coverage filter: reuse fetcher `_filter_full_coverage` + `min_coverage_ratio` param**
   - Rationale: already implemented and tested; expose `min_coverage_ratio` in Search tab.

## Risks / Trade-offs

- [Restricted network] → Tuna mirror default; mirror URL editable; README documents fallback direct link.
- [GitHub access in Iran] → publish zip on GitHub releases plus a domestic mirror link.
- [Antivirus on venv creation] → document expected; consider code signing later.
- [First-run duration 5–15 min] → clear progress dialog; warn before starting.
- [Shapefile without .prj] → assume WGS84/EPSG:4326; show warning; allow CRS override in Settings.
- [Heavy install partial failure] → re-run install button; pip is idempotent.
- [Tkinter threading] → all network/IO in worker thread; GUI updates via queue + `after()`.

## Migration Plan

New capability; no migration. Rollback = delete folder. Settings/config.json is forward-compatible (additive keys).

## Open Questions

- Help doc wording: draft from `OUTPUT_PRODUCTS`/`OUTPUT_PRESETS` and spectral module docstrings; user can edit later.
- Whether to ship a domestic mirror link alongside GitHub release — decide at release time.
