## Purpose

The sample index computation script must be testable without network access, so its AOI parsing, date-window logic, and index dispatch can be verified deterministically in CI.

## ADDED Requirements

### Requirement: Sample script unit tests with mocked fetchers
The sample pipeline script SHALL ship with unit tests that mock the Landsat and Sentinel Planetary Computer fetchers, so Landsat and Sentinel index paths execute without network calls.

#### Scenario: Landsat path with mocked STAC response
- **WHEN** the unit test suite runs `scripts/tests/test_compute_sample_indices.py`
- **THEN** the Landsat path executes with mocked scenes and produces index outputs without any live STAC request

#### Scenario: Sentinel path with mocked STAC response
- **WHEN** the unit test suite runs `scripts/tests/test_compute_sample_indices.py`
- **THEN** the Sentinel path executes with mocked scenes and produces index outputs without any live STAC request

### Requirement: Script CLI surface stays testable
The sample pipeline script SHALL expose `parse_args` with `--input`, `--dates` (three values), `--sentinel` flag, and `--resolution`, so tests and users can invoke it without ad-hoc argument wrangling.

#### Scenario: Help output lists expected arguments
- **WHEN** `python scripts/compute_sample_indices.py --help` runs
- **THEN** the help text lists `--input`, `--dates`, `--sentinel`, and `--resolution`
