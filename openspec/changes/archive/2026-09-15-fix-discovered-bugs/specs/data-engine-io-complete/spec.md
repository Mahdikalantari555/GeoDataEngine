## Purpose

The `data_engine.io` package SHALL expose every custom I/O exception defined by the package so downstream modules and tests can import errors from the public module path without breaking package initialization.

## ADDED Requirements

### Requirement: Public I/O exception exports
The package SHALL export all exception classes defined in `data_engine.io.errors`, including `NoSceneFoundError`, `AuthenticationError`, `DownloadError`, `PartialDataError`, and `GeometryError`, from `data_engine.io`.

#### Scenario: Import PartialDataError from the public package path
- **WHEN** a downstream module imports `PartialDataError` from `data_engine.io`
- **THEN** the import succeeds and resolves to the exception class defined in `data_engine.io.errors`

#### Scenario: Import all I/O exceptions from the public package path
- **WHEN** a downstream module imports `NoSceneFoundError`, `AuthenticationError`, `DownloadError`, `PartialDataError`, and `GeometryError` from `data_engine.io`
- **THEN** every import succeeds without raising `ImportError`

### Requirement: Package initialization remains importable
The `data_engine.io` package SHALL remain importable even when optional satellite backends or external services are unavailable, as long as the required exception classes are defined.

#### Scenario: Import package without external services
- **WHEN** the runtime environment has no live Planetary Computer service
- **THEN** importing `data_engine.io` succeeds and exposes the public exception surface
