## Context

`sample/sasmple.geojson` defines a small AOI polygon in Khuzestan, Iran (CRS84). data-engine already has `PlanetaryComputerLandsatFetcher.download_and_clip_bands()`, `SentinelPlanetaryComputerFetcher`, `METRICPipeline.run()` with output categories, and `VegetationIndices`. The missing piece is a single reproducible script that wires these together for 3 dates and writes clipped outputs to `sample/output/`.

## Goals / Non-Goals

**Goals:**
- One script that takes a GeoJSON AOI, 3 dates, and optional `--sentinel` flag and produces all available spectral/stress/ET products clipped to the AOI.
- OPTRAM soil-moisture proxy class for Sentinel-2 red/NIR bands.
- `sample/output/` gitignored; `sample/sasmple.geojson` remains tracked.

**Non-Goals:**
- No radiation, energy balance, or quality bands (excluded via `output_categories`).
- No full METRIC pipeline re-run when only Sentinel indices are requested.
- No live network download in unit tests — use mocked STAC responses.

## Decisions

### Output categories
**Decision**: Use `output_categories=["surface_props", "stress_indices", "spectral_indices"]` for Landsat runs. This excludes `et_core` (ETaDaily) — but the user explicitly asked for ETaDaily. So the effective list is `["et_core", "surface_props", "stress_indices", "spectral_indices"]`.

**Why**: The user wants ETaDaily plus all surface/stress/spectral indices, but explicitly excludes radiation and energy balance and quality bands.

### OPTRAM formula
**Decision**: Implement OPTRAM as a simplified soil-moisture proxy: `optram = sqrt(nir08 / red) * (1 - red / nir08)`, clipped to `[0, 1]`, computed per-pixel with NaN handling. This is a pragmatic approximation of the optical-path-length-adjusted reflectance model suitable for Sentinel-2 red/NIR bands.

**Why**: Full OPTRAM requires a wet-edge calibration curve; the simplified form is deterministic, dependency-free, and matches the library's existing index-style classes.

### Output directory
**Decision**: Write outputs to `<input-dir>/output/<scene_id>/` where `scene_id` comes from the STAC item's `id` field. Overwrite existing files.

**Why**: Keeps the workspace layout flat and predictable; avoids collisions between dates; idempotent.

## Risks / Trade-offs

- **Planetary Computer network availability**: Downloads require internet and may fail in offline environments. → Script logs warnings and continues with available scenes; unit tests mock network calls.
- **OPTRAM accuracy**: Simplified formula is not a full wet-edge calibrated OPTRAM. → Documented as a proxy; future work can add wet-edge calibration.
- **Large rasters**: 30m resolution over the AOI is manageable; Sentinel 10m may be heavier. → Default resolution 30m; allow `--resolution` override.

## Migration Plan

No migration needed. The script is additive. Outputs are written to a new gitignored directory.

## Open Questions

None.
