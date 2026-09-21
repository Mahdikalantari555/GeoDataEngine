## 1. Demote energy_balance manager debug logs

- [x] 1.1 In `libs/data_engine/src/data_engine/energy_balance/manager.py`, locate lines 165–207 (all `logger.info(f"[ENERGY BALANCE DEBUG] ...")` calls) and replace `logger.info(` with `logger.debug(` on each line
- [x] 1.2 Verify: running `grep -n "ENERGY BALANCE DEBUG" libs/data_engine/src/data_engine/energy_balance/manager.py` returns zero matches
- [x] 1.3 Verify: running `grep -n "logger\.debug.*ENERGY BALANCE DEBUG" libs/data_engine/src/data_engine/energy_balance/manager.py` returns all 10 lines

## 2. Demote sensible_heat_flux debug log

- [x] 2.1 In `libs/data_engine/src/data_engine/energy_balance/sensible_heat_flux.py:653`, replace `logger.info(f"METRIC DEBUG: ...")` with `logger.debug(f"METRIC DEBUG: ...")`
- [x] 2.2 Verify: `grep -n "METRIC DEBUG" libs/data_engine/src/data_engine/energy_balance/sensible_heat_flux.py` returns the line with `logger.debug`

## 3. Remove product_organizer debug warnings

- [x] 3.1 In `libs/data_engine/src/data_engine/output/product_organizer.py`, remove lines 154–157 entirely (the two `logger.warning("DEBUG: ...")` calls)
- [x] 3.2 Verify: `grep -rn "DEBUG:" libs/data_engine/src/data_engine/output/product_organizer.py` returns zero matches

## 4. Verification

- [x] 4.1 Run `conda run -n geospatial ruff check libs/data_engine/src` — expect clean
- [x] 4.2 Run `conda run -n geospatial pytest libs/data_engine/tests -q` — expect all existing tests pass
- [x] 4.3 Confirm no remaining `logger.info` calls in `libs/data_engine/src/data_engine/energy_balance/` contain "DEBUG" in the message
- [x] 4.4 Update `tasks/todo.md` checkboxes to reflect completion status
