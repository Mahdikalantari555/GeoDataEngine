## Purpose

Auto-download OLMoEarth vision weights and ONNX text embedding models from HuggingFace when configured paths are empty or models are missing from the cache, so fresh workspaces become usable without manual model setup. Status is reported via doctor and Settings UI.

## ADDED Requirements

### Requirement: Auto-download vision model on first use
When `build_vision_embedder(settings)` is called with `vision_path=None` or a path that does not contain `weights.pth`, AND `offline==false`, AND the OLMoEarth Nano v1.2 checkpoint is not present in the HF cache, the system SHALL download `allenai/OlmoEarth-v1_2-Nano` weights to `workspace/project_folder/models/vision/` (or `~/.cache/huggingface/hub` as fallback) and set `settings.vision_path` to the downloaded location. On subsequent calls the cached model SHALL be reused without re-downloading.

#### Scenario: First search with no vision model
- **WHEN** workspace has `vision_path=null` and `offline=false` and OLMoEarth weights are absent from HF cache
- **THEN** first call to `build_vision_embedder` downloads weights and returns an `OlmoEarthVisionEmbedder` pointing to the downloaded path

#### Scenario: Offline with no model
- **WHEN** `vision_path=null` and `offline=true` and no cached weights exist
- **THEN** `build_vision_embedder` returns `PlaceholderVisionEmbedder` (no error, graceful degradation)

#### Scenario: Reuse cached model
- **WHEN** OLMoEarth weights exist at `~/.cache/huggingface/hub/models--allenai--OlmoEarth-v1_2-Nano/snapshots/<sha>/weights.pth`
- **THEN** `build_vision_embedder` loads directly from cache without network access

### Requirement: Auto-download text embedding model on first use
When `build_text_embedder(settings)` is called with no local ONNX model found in any hub root (including workspace `embedding_path`, env `GEOMEMORY_EMBEDDING_ROOT`, and `~/.cache/huggingface`), AND `offline==false`, the system SHALL auto-download `Xenova/all-MiniLM-L6-v2` ONNX weights via `EmbeddingModelHub.download()` and the embedder SHALL resolve to the downloaded directory.

#### Scenario: First embed call with no cached model
- **WHEN** `embedding_path=null`, `offline=false`, and no ONNX MiniLM snapshot exists
- **THEN** `build_text_embedder` triggers a download and subsequent searches use the cached model

#### Scenario: Offline guard for text embedding
- **WHEN** `offline=true` and no ONNX model is cached
- **THEN** `build_text_embedder` returns `HashingTextEmbedder` and searches fall back to n-gram hashing

### Requirement: Doctor reports model availability
`GET /api/v1/doctor` SHALL include `diagnostics.vision.model_available` (bool) and `diagnostics.embedding.model_available` (bool). When a model was auto-downloaded during the session, `diagnostics.vision.download_status` SHALL be `"downloaded"` instead of `"missing"`.

#### Scenario: Doctor after cold-start download
- **WHEN** a vision model was auto-downloaded in the current session
- **THEN** `diagnostics.vision.model_available == true` and `diagnostics.vision.download_status == "downloaded"`

### Requirement: Settings page shows model download controls
The Settings page SHALL show a Vision Models section with a "Download OLMoEarth" button (enabled only when `offline==false` and no model is cached) and an Embedding section mirroring the existing ONNX model picker but with a "Download" button that enqueues `POST /api/v1/models/download` with progress tracking.

#### Scenario: Download button visible when needed
- **WHEN** workspace settings have `vision_path=null` and `offline=false`
- **THEN** the Settings page shows a "Download OLMoEarth (Nano v1.2)" button

#### Scenario: Download disabled when offline
- **WHEN** workspace `offline==true`
- **THEN** the download button is disabled with tooltip "Downloads require offline=false"
