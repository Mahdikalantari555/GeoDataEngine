## Context

`test_planetary_computer_fetcher.py` imports five error classes from `data_engine.io.planetary_computer_fetcher`. That module defines fetchers only; errors live in `data_engine.io.errors` and re-export via `data_engine.io`. Result: `ImportError` at collection, whole module skipped. Sample script `scripts/compute_sample_indices.py` has argparse + Landsat/Sentinel paths but zero unit tests. See proposal Why.

## Goals / Non-Goals

**Goals:**
- Fix test import path, module collects green
- Mocked unit tests for sample script Landsat + Sentinel paths
- Ruff/mypy clean on touched files

**Non-Goals:**
- No fetcher refactor
- No live STAC calls in tests
- No new deps

## Decisions

### Import source: `data_engine.io.errors`
Import errors direct from `errors` module, not package `__init__`. Why: avoids package side-effects (`landsat_reader`, fetcher imports at `__init__`), precise, stable. Alternative `from data_engine.io import ...` works but pulls heavy imports.

### Sample tests mock at fetcher boundary
Patch `PlanetaryComputerLandsatFetcher` + `SentinelPlanetaryComputerFetcher` methods, not HTTP. Why: deterministic, no network, fast. Alternative VCR cassettes rejected — brittle binary payloads.

## Risks / Trade-offs

- `__init__` heavy imports remain → Mitigation: out of scope, noted only
- Mock drift from real STAC shape → Mitigation: assert minimal fields (`scene_id`, `directory`) used by script
