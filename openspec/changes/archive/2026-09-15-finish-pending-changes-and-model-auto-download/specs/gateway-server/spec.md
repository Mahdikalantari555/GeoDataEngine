## ADDED Requirements

### Requirement: Entity endpoints
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

### Requirement: Vision model download endpoint
`POST /api/v1/models/vision/download` SHALL enqueue a background job (`202 {job_id}`) that downloads OLMoEarth Nano v1.2 weights from HuggingFace into the workspace project folder (or `~/.cache/huggingface/hub` fallback) when `vision_path` is unset. Progress is exposed via `GET /api/v1/jobs/{id}` and `job_progress` SSE. When `offline==true`, it returns `503 vision_unavailable` with hint.

#### Scenario: Vision download job
- **WHEN** `POST /api/v1/models/vision/download` is called with an open workspace and `offline=false`
- **THEN** response is 202 with a job id that transitions to `done` with `vision_path` set to the downloaded weights path

#### Scenario: Vision download offline guard
- **WHEN** `POST /api/v1/models/vision/download` is called with `offline=true`
- **THEN** response is 503 `vision_unavailable` with `detail.offline=true` and `detail.hint="set offline=false or pre-download"`

### Requirement: Doctor reports model availability
`GET /api/v1/doctor` diagnostics SHALL include `vision: {model_available: bool, download_status: "downloaded"|"missing"|"downloading"}` and `embedding: {model_available: bool}`. When a model was auto-downloaded during the session, `download_status` SHALL be `"downloaded"`.

#### Scenario: Doctor after cold-start download
- **WHEN** a vision model was auto-downloaded in the current session
- **THEN** `diagnostics.vision.model_available == true` and `diagnostics.vision.download_status == "downloaded"`
