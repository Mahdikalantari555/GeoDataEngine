## Why

`libs/data_engine` emits ~20 lines of debug-level log messages on every production run under the `INFO` level, tagged with `[ENERGY BALANCE DEBUG]`, `[METRIC DEBUG]`, and `DEBUG:` prefixes. These were left in during development and noise up production logs, making it harder to spot real warnings and errors.

## What Changes

- Demote all `logger.info()` calls carrying `DEBUG` or `[METRIC DEBUG]` / `EF DEBUG` tags to `logger.debug()`, so they remain visible when the data_engine logger is configured at DEBUG level but stay silent in default INFO-level deployments.
- Remove two accidental `logger.warning("DEBUG: ...")` calls in `product_organizer.py` that were originally debug-only instrumentation with no operational value.
- No behavior change, no API change, no new dependencies.

## Capabilities

### New Capabilities
- *(none — no spec-level behavior changes)*

### Modified Capabilities
- *(none — logging level is an implementation detail, not a user-facing contract)*

## Impact

- **Files modified**:
  - `libs/data_engine/src/data_engine/energy_balance/manager.py` (lines 165–207)
  - `libs/data_engine/src/data_engine/energy_balance/sensible_heat_flux.py` (line 653)
  - `libs/data_engine/src/data_engine/energy_balance/latent_heat_flux.py` (lines 393–396)
  - `libs/data_engine/src/data_engine/output/product_organizer.py` (lines 154–157)
- **No API change**: Gateway endpoints, SSE events, and client contracts are unaffected.
- **No new dependencies**.
- **No test impact**: Existing tests do not assert log levels for these paths.
