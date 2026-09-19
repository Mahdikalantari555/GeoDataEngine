## Purpose

Complete all unchecked tasks across four pending OpenSpec changes so that each change is fully implemented, tested, and ready for archive: sentinel module exports (rsmetric), server entity router (geospatial-knowledge-layer), web modality toggle (unified-multimodal-retrieval), dashboard image search + benchmark completeness (olmoearth-production).

## ADDED Requirements

### Requirement: Sentinel module exports
The `data_engine.sentinel` package SHALL export `SentinelPipeline` and `SentinelFetcher` when the Sentinel asset root (`DATA_ENGINE_SENTINEL_ROOT`) points to a valid directory containing the copied source. When the root is absent or invalid (Linux environments), importing `data_engine.sentinel` SHALL raise `ImportError` with a clear message.

#### Scenario: Sentinel available on Windows
- **WHEN** `DATA_ENGINE_SENTINEL_ROOT` points to a directory containing `pipeline.py` and `config.py`
- **THEN** `from data_engine.sentinel import SentinelPipeline, SentinelFetcher` succeeds

#### Scenario: Sentinel unavailable on Linux
- **WHEN** `DATA_ENGINE_SENTINEL_ROOT` points to a non-existent path
- **THEN** importing `data_engine.sentinel` raises `ImportError("data_engine.sentinel is not available …")`

### Requirement: Server entity endpoints
The gateway SHALL expose two read-only entity endpoints. `GET /api/v1/entities?kind=` returns entities filtered by optional kind; `GET /api/v1/entities/{id}/relations` returns relation rows for a specific entity. Both return 404 when the workspace is closed or the id does not exist.

#### Scenario: List all entities
- **WHEN** `GET /api/v1/entities` is called with an open workspace containing entities
- **THEN** response is 200 with `{entities: [{id, name, kind, workspace_id, spatial_bbox, created_at}]}`

#### Scenario: Filter by kind
- **WHEN** `GET /api/v1/entities?kind=metric` is called
- **THEN** only entities with `kind == "metric"` are returned

#### Scenario: Entity relations
- **WHEN** `GET /api/v1/entities/{id}/relations` is called
- **THEN** response is 200 with `{relations: [{source_id, predicate, target_id, confidence, created_at}]}` or `{relations: []}` if none

#### Scenario: Closed workspace
- **WHEN** either endpoint is called without an open workspace
- **THEN** response is 409 `workspace_not_open`

### Requirement: Search modality toggle in UI
The Search page SHALL include a text/image/both modality selector alongside the existing mode tabs. The selector SHALL default to "text". When "image" or "both" is selected, each hit SHALL display a small modality badge (`text` / `image`) derived from `hit.metadata.modality`. Selecting a modality SHALL set `modalities` on the API request body.

#### Scenario: Toggle to both
- **WHEN** user clicks "both" modality button
- **THEN** search requests include `modalities: "both"` and image hits render with an "image" badge

#### Scenario: Default is text-only
- **WHEN** the search page loads
- **THEN** modalities defaults to `"text"` and no modality badge is shown on results

### Requirement: OLMoEarth benchmark reports full comparison
`scripts/benchmark_olmoearth_onnx.py` SHALL report mean cosine distance, per-sample table, torch latency (50 runs), ONNX latency (50 runs), and file size for both implementations. When torch is absent the script SHALL skip the torch benchmark and still run ONNX measurements.

#### Scenario: Full benchmark output
- **WHEN** `python scripts/benchmark_olmoearth_onnx.py --input <weights.pth> --output <dir>` runs with torch installed
- **THEN** output includes columns: `mean_cosine_distance`, `torch_latency_ms`, `onnx_latency_ms`, `torch_size_mb`, `onnx_size_mb`
