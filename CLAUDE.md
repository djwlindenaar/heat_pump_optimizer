# Notes for working on this repo

## Live instance
`/config/custom_components/heat_pump_optimizer` is a symlink into this repo's working tree, so Home Assistant runs whatever is checked out (including uncommitted edits) after a restart. Don't edit files while HA is restarting: it may import a half-edited module.

## Verifying a run after a restart, reload or options change
- Saving the options (or reconfiguring) reloads the entry, and setup immediately runs `async_config_entry_first_refresh`, i.e. a full optimization within ~2 s. No button press is needed.
- When checking that a change took effect, record the reference timestamp **before** triggering it, in the same command. A timestamp taken afterwards misses the run the trigger caused, and the next run (e.g. a manual button press) gets mistaken for it.
- Evidence of a run:
  - `.storage/heat_pump_optimizer.optimized_schedule` → `created` (UTC) of the last successful optimization.
  - Entity history: a reload shows all entities `unavailable`, then new values ~1–2 s later.
  - `binary_sensor.optimizer_problem`: `last_success` / `last_error`. Fallback runs (previous schedule kept) do not rewrite the stored plan.
- After an HA restart the first refresh usually runs before Heating Analytics is loaded (`Action heating_analytics.get_forecast not found`). That is expected: the coordinator serves the stored plan and the problem sensor is on until the next successful run.

## Changing options programmatically
Use the integration's options flow through the Supervisor API (`$SUPERVISOR_TOKEN`, `http://supervisor/core/api/config/config_entries/options/flow`). The form requires every field: build the submission from the form's defaults (the current stored values) and change only the intended keys. Diff against `.storage/core.config_entries` before submitting.

## Offline checks
`optimizer.py` and `cop_model.py` only depend on each other and can be run outside HA. A stored plan plus the Heating Analytics cache (`temp` per hour) is enough to rebuild the optimizer input and replay a run, e.g. to compare COP curves.
