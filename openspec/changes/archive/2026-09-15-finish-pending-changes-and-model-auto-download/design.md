## Context

Four pending OpenSpec changes have code but leave tasks unchecked due to missing pieces: sentinel module stub not exporting real classes, server entity router never created, web search modality toggle never added, and the OLMoEarth benchmark script is incomplete. Additionally, both embedding and vision models lack auto-download on cold start — a fresh workspace with no local models cannot perform retrieval until the user manually downloads them.

The geomemory library already has `EmbeddingModelHub` for text model download and `OlmoEarthVisionEmbedder._download_config()` for config-only download. Vision weights (`weights.pth`) are never auto-downloaded. The text embedder (`OnnxTextEmbedder._ensure_downloaded()`) already triggers download when no local copy exists.

## Goals / Non-Goals

**Goals:**
- Complete all pending tasks across 4 changes so they can be archived
- Auto-download OLMoEarth vision weights and ONNX text embedding models on first use when paths are empty
- Add server entity router and tests
- Add web search modality toggle with badges
- Report model availability in doctor diagnostics

**Non-Goals:**
- Building `apps/dashboard` (does not exist in this repo variant)
- Adding new hard dependencies beyond `huggingface-hub` (already present)
- Changing the existing embedding provider architecture
- Full ruff/mypy pass on data_engine (existing violations documented, only clean path fixes applied)

## Decisions

### Vision model auto-download trigger point
**Decision**: Trigger auto-download inside `build_vision_embedder()` in `factory.py` when `vision_path` is None/unset and no cached weights exist in HF cache. Use `huggingface_hub.snapshot_download("allenai/OlmoEarth-v1_2-Nano", allow_patterns=["*.pth"])` saving into workspace project folder (or `~/.cache/huggingface/hub`). Store result in `settings.vision_path`.

**Why**: Keeps the factory thin and avoids touching every caller. Consistent with how `OnnxTextEmbedder._ensure_downloaded()` works.

**Alternative considered**: Download on `workspace/create`. Rejected — too early; user may never open/use the workspace. Download on first embed call is more economical.

### Text embedding auto-download
**Decision**: Extend `ONNXEmbeddingProvider.__init__` to accept an optional `auto_download=True` flag (default True). When `model_dir` is not provided and hub scan finds nothing, call `EmbeddingModelHub().download(model_name)` before loading. No API change — existing callers work unchanged.

**Why**: `OnnxTextEmbedder._ensure_downloaded()` already does this for explicit `model_dir=None`; the gap is only when called via the provider layer without an explicit dir.

### Server entities router placement
**Decision**: New file `server/src/geofront_api/routers/entities.py` with two endpoints, mounted in `main.py` via `include_router(entities_router, prefix="/api/v1")`. Follows existing pattern (one router per domain).

**Why**: Single-file routers keep the `server/src/` flat structure consistent with existing domains.

### Web modality toggle implementation
**Decision**: Add a `SearchModalityToggle` component (separate from SearchPage for testability), integrated into SearchPage's control bar alongside mode tabs. Default to "text". Pass `modalities` field through `useSearch` hook to API call. Modality badge rendered as small colored chip next to hit score.

**Why**: Separation keeps SearchPage focused; toggle component can be unit-tested independently. Badge color matches existing score chip styling.

## Risks / Trade-offs

- **Network speed on first use**: Auto-download can take minutes for large models (OLMoEarth ~3 GB). → Mitigation: show progress bar via SSE job_progress; allow cancellation; default to placeholder embedder if download times out.
- **Disk space**: Fresh workspace may pull both ONNX (~380 MB) + OLMoEarth (~3 GB). → Documented in README; user can set `offline=true` to skip.
- **Sentinel module on Linux**: Windows-only asset path cannot be tested. → Keep stub behavior; integration tests gated on `pytest.mark.skipif(not SENTINEL_ROOT.exists())`.
- **Benchmark torch vs ONNX**: Requires torch installed; may be absent in CI. → Script skips torch benchmark when torch unavailable, still reports ONNX metrics.

## Migration Plan

No migration needed. Auto-download is additive: existing workspaces with configured paths continue to use them. New workspaces with empty paths get transparent model fetching. Rollback is safe — removing downloaded models reverts to placeholder behavior.

## Open Questions

None. All decisions resolved during audit.
