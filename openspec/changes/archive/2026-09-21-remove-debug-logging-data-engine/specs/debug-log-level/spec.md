## Purpose

Debug-level diagnostic log messages that were left at INFO or WARNING level during development SHALL be demoted to DEBUG so they remain visible when explicitly enabled but stay silent in default deployments.

## ADDED Requirements

### Requirement: Debug logs use correct level

All diagnostic log calls tagged with `DEBUG` in their message (e.g., `[ENERGY BALANCE DEBUG]`, `[METRIC DEBUG]`, `EF DEBUG`) SHALL use `logger.debug()` as the log level.

#### Scenario: Energy balance diagnostics are DEBUG-level
- **WHEN** an ETa computation runs in a default INFO-level deployment
- **THEN** no `[ENERGY BALANCE DEBUG]` lines appear in stdout

#### Scenario: Debug logs remain accessible
- **WHEN** the data_engine logger is configured at DEBUG level (`logging.getLogger('data_engine').setLevel(logging.DEBUG)`)
- **THEN** all energy-balance diagnostic messages appear as before

#### Scenario: Product organizer debug scaffolding removed
- **WHEN** `product_organizer.py` runs
- **THEN** no `DEBUG:` prefixed warning messages are emitted
