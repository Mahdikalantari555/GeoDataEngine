## Why

Four OpenSpec changes were implemented by compose but left incomplete — sentinel stubs unexported, server entity routes absent, web modality toggle missing, benchmark scope incomplete. Additionally, the system has no mechanism to auto-download the default embedding (ONNX MiniLM) or vision (OLMoEarth Nano v1.2) models when `embedding_path` / `vision_path` are unset and no cached copy exists, causing cold-start failures on fresh workspaces.

## What Changes

1. **rsmetric-clone-and-integration** — complete Tasks 7, 8, 11: export `SentinelPipeline`/`SentinelFetcher` from `data_engine.sentinel`, add integration tests, fix ruff violations, clean mypy errors.
2. **geospatial-knowledge-layer** — complete Task 7: add `server/src/geofront_api/routers/entities.py` with `GET /api/v1/entities?kind=` and `GET /api/v1/entities/{id}/relations`, wire into `main.py`, add `server/tests/test_entities.py`.
3. **unified-multimodal-retrieval** — complete Task 5: add text/image/both modality toggle to SearchPage with per-hit modality badges; add unit + integration tests (Task 6).
4. **olmoearth-production-and-onnx-spike** — complete Task A3 (image-search dashboard page), complete Task B3 (torch-vs-ONNX latency + size comparison); mark Task A3 as skipped if `apps/dashboard` does not exist in this repo variant.
5. **model-auto-download** (new): when `vision_path` is None/unset and no weights exist at HF cache, auto-download OLMoEarth Nano v1.2 weights from HuggingFace into the workspace project folder or `~/.cache/huggingface/hub`. When `embedding_path` is None and no ONNX model is cached, auto-download `Xenova/all-MiniLM-L6-v2` on first search/build. Report download status in doctor. Add web UI controls.

## Capabilities

### New Capabilities
- `pending-changes-completion`: Finish all unchecked tasks across the four pending openspec changes (sentinel exports, server entities router, web modality toggle, benchmark completion, missing tests).
- `model-auto-download`: Auto-download OLMoEarth vision weights and ONNX text embedding models from HuggingFace when paths are empty and no local copy exists; persist to workspace project folder or HF cache; expose status via doctor + settings UI.

### Modified Capabilities
- `gateway-server`: extends `/doctor` response with `vision_model_available` flag; adds `GET /api/v1/models/vision/download` endpoint for vision model auto-download.
- `web-app`: adds modality toggle to search page; adds vision model download section to Settings page.

## Impact

- **New files**: `server/src/geofront_api/routers/entities.py`, `server/tests/test_entities.py`, `apps/web/src/features/search/SearchModalityToggle.tsx`, `libs/geomemory/src/geomemory/embeddings/vision_downloader.py`
- **Modified files**: `server/src/geofront_api/main.py` (router wiring), `server/src/geofront_api/routers/models.py` (vision download endpoint), `apps/web/src/features/search/SearchPage.tsx` (modality toggle), `apps/web/src/features/workspace/SettingsPage.tsx` (vision model controls), `libs/geomemory/src/geomemory/embeddings/factory.py` (auto-download trigger), `libs/data_engine/src/data_engine/sentinel/__init__.py`, `apps/web/src/api/knowledge.ts` (no changes needed — already present)
- **Tests**: `server/tests/test_entities.py`, `libs/geomemory/tests/unit/test_vision_downloader.py`, `libs/geomemory/tests/integration/test_multimodal_search.py`, `server/tests/test_search_modalities.py`, `libs/geoagent/tests/test_rs_tools.py` (ruff fixes may touch)
- **Deps**: no new hard deps; uses existing `huggingface-hub` and `torch` (already optional `[vision]`)
