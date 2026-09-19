## ADDED Requirements

### Requirement: Search modality toggle in UI
The Search page SHALL include a text/image/both modality selector alongside the existing mode tabs. The selector SHALL default to "text". When "image" or "both" is selected, each hit SHALL display a small modality badge (`text` / `image`) derived from `hit.metadata.modality`. Selecting a modality SHALL set `modalities` on the API request body.

#### Scenario: Toggle to both
- **WHEN** user clicks "both" modality button
- **THEN** search requests include `modalities: "both"` and image hits render with an "image" badge

#### Scenario: Default is text-only
- **WHEN** the search page loads
- **THEN** modalities defaults to `"text"` and no modality badge is shown on results

### Requirement: Settings page shows model download controls
The Settings page SHALL show a Vision Models section with a "Download OLMoEarth" button (enabled only when `offline==false` and no model is cached) and an Embedding section mirroring the existing ONNX model picker but with a "Download" button that enqueues `POST /api/v1/models/download` with progress tracking.

#### Scenario: Download button visible when needed
- **WHEN** workspace settings have `vision_path=null` and `offline=false`
- **THEN** the Settings page shows a "Download OLMoEarth (Nano v1.2)" button

#### Scenario: Download disabled when offline
- **WHEN** workspace `offline==true`
- **THEN** the download button is disabled with tooltip "Downloads require offline=false"
