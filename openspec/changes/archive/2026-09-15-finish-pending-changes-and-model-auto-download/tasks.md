# Tasks: finish-pending-changes-and-model-auto-download

## 1. Sentinel module exports (rsmetric Task 7)

- [x] 1.1 Copy sentinel source files into `libs/data_engine/src/data_engine/sentinel/` and update `__init__.py` to export `SentinelPipeline` and `SentinelFetcher`; verify import when `DATA_ENGINE_SENTINEL_ROOT` is valid: `conda run -n geospatial python -c "from data_engine.sentinel import SentinelPipeline, SentinelFetcher"` passes when env var set.
- [x] 1.2 Add sentinel stub that raises `ImportError` when root is absent; add `libs/data_engine/tests/integration/test_sentinel_stub.py` asserting the ImportError path; verify: `conda run -n geospatial pytest libs/data_engine/tests/integration/test_sentinel_stub.py -q`.

## 2. Ruff/mypy fixes (rsmetric Task 8)

- [x] 2.1 Run `conda run -n geospatial ruff check libs/data_engine/src --fix` and commit all auto-fixes; re-run `ruff check libs/data_engine/src` → exit 0.
- [x] 2.2 Fix any remaining mypy errors in `libs/data_engine/src/cli/interface.py` (type annotations for Collection usage); verify: `conda run -n geospatial mypy --strict libs/data_engine/src` exit 0.

## 3. Server entity router (geospatial-knowledge-layer Task 7)

- [x] 3.1 Write `server/tests/test_entities.py` (red): define test functions for `GET /api/v1/entities`, `GET /api/v1/entities?kind=metric`, `GET /api/v1/entities/{id}/relations`, closed-workspace 409, and missing-entity 404. All calls reference unimplemented routes so they return 404 currently.
- [x] 3.2 Create `server/src/geofront_api/routers/entities.py` with two endpoints using `Workspace.traverse()` internally for relations; mount in `server/src/geofront_api/main.py`; re-run `pytest server/tests/test_entities.py -q` → green.
- [x] 3.3 Regenerate web API client: `cd apps/web && pnpm gen:api` then `pnpm build` → no type errors.

## 4. Search modality toggle (unified-multimodal-retrieval Task 5)

- [x] 4.1 Write `apps/web/src/features/search/SearchModalityToggle.test.tsx` (red): assert default modalities is "text", click "image" sets state, each modality renders correct label.
- [x] 4.2 Create `apps/web/src/features/search/SearchModalityToggle.tsx` component wired to `useSearch` hook's `modalities` field; integrate into `SearchPage.tsx` control bar; update `HitCard` to render modality badge from `hit.metadata.modality`; verify `pnpm test` passes for SearchPage.
- [x] 4.3 Update i18n keys in `apps/web/src/i18n/en.json` and `fa.json` (`search.modalities.*`, `search.hits.modality.*`).

## 5. Missing integration tests (unified-multimodal-retrieval Task 6)

- [x] 5.1 Write `libs/geomemory/tests/unit/test_image_backend.py`: assert `ImageRetrievalBackend.search()` returns empty list for empty index, returns hits with `metadata.modality="image"` for populated index, respects `top_k`.
- [x] 5.2 Write `libs/geomemory/tests/integration/test_multimodal_search.py`: assert search with `modalities="both"` fuses text + image hits via RRF; search with `modalities="image"` skips text backends.
- [x] 5.3 Write `server/tests/test_search_modalities.py`: assert `POST /api/v1/search` accepts `modalities` param and forwards to workspace; assert `POST /api/v1/ask` also accepts it.
- [x] 5.4 Verify gates: `conda run -n geospatial pytest libs/geomemory/tests libs/geoagent/tests server/tests -q` (known geomemory failure excluded), `pnpm --prefix apps/web build` → clean.

## 6. OLMoEarth benchmark completion (olmoearth Task B3)

- [x] 6.1 Extend `scripts/benchmark_olmoearth_onnx.py` to measure torch latency (50 runs) alongside ONNX latency and output both in the comparison table; skip torch section gracefully when `import torch` fails.
- [x] 6.2 Add file size reporting (torch `weights.pth` vs exported `.onnx`) to the benchmark output table.
- [x] 6.3 Verify: `python scripts/benchmark_olmoearth_onnx.py --help` shows `--input` and `--output`; script exits 1 on missing input, exits 0 on success with comparison table printed.

## 7. Vision model auto-download library (model-auto-download)

- [x] 7.1 Write `libs/geomemory/tests/unit/test_vision_downloader.py` (red): test `download_vision_model(settings)` returns path to downloaded weights when HF cache is empty and offline=false; returns existing cached path when already present; returns `None` when offline=true.
- [x] 7.2 Create `libs/geomemory/src/geomemory/embeddings/vision_downloader.py` with `download_vision_model(settings: WorkspaceSettings) -> str | None` using `huggingface_hub.snapshot_download("allenai/OlmoEarth-v1_2-Nano", allow_patterns=["weights.pth"])` saving to `<workspace_dir>/models/vision/` or `~/.cache/huggingface/hub`; return path on success, `None` on offline/missing.
- [x] 7.3 Wire into `build_vision_embedder()` in `factory.py`: when `vision_path` is None and offline=false, call `download_vision_model()`, set on settings, return `OlmoEarthVisionEmbedder(path)`.
- [x] 7.4 Verify: `conda run -n geospatial pytest libs/geomemory/tests/unit/test_vision_downloader.py -q` → green.

## 8. Text embedding auto-download fix (model-auto-download)

- [x] 8.1 Write `libs/geomemory/tests/unit/test_embedding_auto_download.py` (red): test that `ONNXEmbeddingProvider` without explicit `model_dir` triggers hub download when no local copy exists; verify `download_with_progress` callback receives progress events.
- [x] 8.2 Extend `ONNXEmbeddingProvider.__init__` to accept `auto_download: bool = True`; when `model_dir` is None and hub scan finds nothing, call `self.download_with_progress()` before returning.
- [x] 8.3 Verify: `conda run -n geospatial pytest libs/geomemory/tests/unit/test_provider.py libs/geomemory/tests/unit/test_embedding_auto_download.py -q` → green.

## 9. Doctor diagnostics extension

- [x] 9.1 Write `server/tests/test_doctor_models.py` (red): assert `GET /api/v1/doctor` includes `diagnostics.vision.model_available` and `diagnostics.embedding.model_available` fields.
- [x] 9.2 Update `server/src/geofront_api/routers/doctor.py` to report `vision: {model_available, download_status}` and `embedding: {model_available}` based on current workspace settings and model status.
- [x] 9.3 Verify: `conda run -n geospatial pytest server/tests/test_doctor_models.py -q` → green.

## 10. Vision download endpoint (model-auto-download server)

- [x] 10.1 Write `server/tests/test_vision_download.py` (red): assert `POST /api/v1/models/vision/download` returns 202 with job_id when offline=false and vision_path=None; returns 503 when offline=true.
- [x] 10.2 Add endpoint to `server/src/geofront_api/routers/models.py`: enqueue background job calling `download_vision_model(workspace.settings)`, update `workspace.settings.vision_path` on completion, expose via `GET /jobs/{id}`.
- [x] 10.3 Verify: `conda run -n geospatial pytest server/tests/test_vision_download.py -q` → green.

## 11. Settings page model download UI (web-app)

- [x] 11.1 Add Vision Models section to `apps/web/src/features/workspace/SettingsPage.tsx`: show "Download OLMoEarth" button when `settings.vision_path` is null and `offline==false`; disable button with tooltip when offline.
- [x] 11.2 Wire button to `POST /api/v1/models/vision/download` and show job progress via `useJobPoll` hook (or reuse existing job progress pattern from Index page).
- [x] 11.3 Verify: `pnpm build && pnpm test` → clean.

## 12. Full gate verification

- [x] 12.1 Run full test suite: `conda run -n geospatial pytest libs/geomemory/tests libs/geoagent/tests server/tests -q` (expected: known geomemory failure for abstention test excluded; all others green).
- [x] 12.2 Run lint: `conda run -n geospatial ruff check libs/data_engine/src libs/geoagent/src libs/geomemory/src server/src && conda run -n geospatial mypy --strict libs/geomemory/src libs/geoagent/src server/src`.
- [x] 12.3 Run web checks: `pnpm --prefix apps/web build && pnpm --prefix apps/web lint`.
- [x] 12.4 Update `tasks/todo.md`: mark all tasks under M7 (polish) or new section as complete; tick all 4 pending change task files (rsmetric, geospatial-knowledge-layer, unified-multimodal-retrieval, olmoearth-production).

## Dependencies

1→2 (sequential), 3 (independent), 4→5 (tests depend on feature), 6 (independent), 7→8 (library layer), 8→9 (doctor reads model status), 9→10 (endpoint uses library), 10→11 (UI consumes endpoint), all→12 (final gate).
