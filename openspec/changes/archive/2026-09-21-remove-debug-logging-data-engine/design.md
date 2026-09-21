## Context

The `data_engine` library computes ETa (evapotranspiration) using the METRIC method. During development, numerous diagnostic prints were added as `logger.info("[* DEBUG]* ...")` calls to trace energy-balance residual values, calibration coefficients, and flux components. These were never promoted to proper debug-level logging or removed before production use.

Affected call sites:
- `energy_balance/manager.py:165-207` — 10 `logger.info("[ENERGY BALANCE DEBUG] ...")` calls covering Rn, G, H, LE, EF, ET_inst, and residuals
- `energy_balance/sensible_heat_flux.py:653` — 1 `logger.info("METRIC DEBUG: ...")` call
- `energy_balance/latent_heat_flux.py:393-396` — 4 `logger.debug("EF DEBUG: ...")` calls (correct level already, keep as-is)
- `output/product_organizer.py:154-157` — 2 `logger.warning("DEBUG: ...")` calls (wrong level — should be removed, not downgraded)

Note: `latent_heat_flux.py` already uses `logger.debug` — those lines are correct and need no change. The other three files use `logger.info` or `logger.warning` incorrectly.

## Goals / Non-Goals

**Goals:**
- Demote all debug diagnostic `logger.info()` calls to `logger.debug()` so they are silent by default.
- Remove the two stray `logger.warning("DEBUG: ...")` calls in `product_organizer.py` that serve no operational purpose.
- Preserve the diagnostic value: engineers who set `logging.getLogger('data_engine').setLevel(DEBUG)` still see everything.

**Non-Goals:**
- Restructuring the logging architecture (already handled by `observability-and-error-reporting`).
- Adding log filtering or sampling logic.
- Changing any computational behavior.

## Decisions

### D1: Demote to `logger.debug()`, do not delete
**Choice**: Replace `logger.info("[* DEBUG]* ...")` with `logger.debug(...)` keeping the same message content.
**Rationale**: These are legitimate diagnostic outputs for production troubleshooting. Deleting them would lose valuable traceability. Demoting to DEBUG level preserves them for developers while silencing them in default deployments.

### D2: Delete `product_organizer.py` debug warnings entirely
**Choice**: Remove lines 154–157 in `product_organizer.py`.
**Rationale**: Unlike the energy-balance diagnostics, these two `logger.warning` calls are one-shot checks ("does .tif exist?", "how many .tif files?") that add no ongoing diagnostic value. They appear to have been left as temporary debug scaffolding.

### D3: Leave `latent_heat_flux.py` unchanged
**Choice**: Lines 393–396 already use `logger.debug()` correctly.
**Rationale**: No action needed.

## Risks / Trade-offs

- **[Risk] Debug traces disappear from default log output** → Mitigation: The messages move to DEBUG level, which is standard practice. Anyone who needs them can configure the logger; the messages are fully preserved.
- **[Risk] Deleting `product_organizer.py` lines removes useful one-shot info** → Mitigation: The operations those lines checked (`.tif` existence and count) are already observable through file-system inspection; the warnings were ad-hoc and non-structured.

## Migration Plan

1. In `manager.py`: replace each `logger.info(f"[ENERGY BALANCE DEBUG] ...")` with `logger.debug(...)`.
2. In `sensible_heat_flux.py`: replace `logger.info("METRIC DEBUG: ...")` with `logger.debug(...)`.
3. In `product_organizer.py`: remove lines 154–157 entirely.
4. Run `conda run -n geospatial ruff check libs/data_engine/src` to confirm no violations.
5. Run `pytest libs/data_engine/tests -q` to verify no regressions.
