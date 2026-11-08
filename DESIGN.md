# Heat Pump Cost Optimizer design

## Purpose
The integration optimizes a power-controlled heat pump against 15-minute buy/feed-in prices while treating the floor slab as thermal storage.

## Time resolution
Nordpool prices keep their 15-minute timestamps. EPEX Spot price rows use `start_time`, `end_time`, and `price_per_kwh`; hourly EPEX rows are expanded into four quarter-hours. Heating Analytics hourly heat demand is divided equally over four quarter-hours. Electrical energy for an interval is `power_kW * 0.25 h`.

## Persistent slab-state observer
The optimizer no longer resets slab charge on every solve. `SlabStateEstimator` persists its state with Home Assistant `Store`. The configured initial slab state is used only when no persisted state exists.

For every update the observer performs:

`E_integrated = E_previous + Q_measured_heat - Q_HeatingAnalytics`

The heat meter is assumed to be a monotonically increasing thermal-energy sensor in kWh. Its delta provides measured heat into the slab. Heating Analytics is the only available estimate of heat dissipated into the house; its hourly kWh is divided by four at 15-minute resolution.

## Temperature grounding
The slab temperature is deliberately not used as the primary state because it is delayed/noisy. It is exponentially filtered:

`T_filtered = alpha_filter*T_measured + (1-alpha_filter)*T_filtered_previous`, with `alpha_filter = 1 - exp(-elapsed_hours / temp_filter_time_constant_hours)`, so the filter strength does not depend on the refresh interval.

The storage zero point depends on the heating load. The estimated equilibrium slab temperature is:

`T_equilibrium = T_room + P_loss_average / K_floor`

where `P_loss_average` is the average Heating Analytics demand over the configured equilibrium period (default 24 h), and `K_floor` is the effective slab-to-room heat transfer coefficient in kW/K.

The temperature-derived reference energy is:

`E_temperature = C_slab * (T_filtered - T_equilibrium)`

The integrated state is only slowly pulled toward this reference:

`E_state = E_integrated + alpha_correction*(E_temperature - E_integrated)`

This makes energy accounting dominant over short periods while preventing long-term model drift. The result is not clipped to the configured slab minimum/maximum: those limits constrain the optimizer's plan, not the observed state. When the observed state lies outside the limits, the optimizer only allows transitions that move it back towards the allowed range.

## Optimizer coupling
The persisted observed `E_state` is supplied as `initial_slab_kwh` for every optimization run. Future slab trajectories still use the COP model and Heating Analytics forecast. Thus measured history initializes the optimizer, while predictions are used only forward in time.

## COP model
The COP is looked up in the `cop_table` option: the first row lists electrical powers (W), each further row an outdoor temperature (°C) followed by the COP at each power. The optimizer interpolates bilinearly between the grid points; temperatures and powers outside the table use the nearest edge, and the result is clamped to 1–8. A full temperature × power table is used instead of a temperature curve times one power-correction curve because the power dependence changes with temperature: in mild weather the lowest powers are the most efficient, while in frost the COP hardly depends on power below about 1.5 kW.

The default table was fitted to about 5,000 hours (Oct 2022 – Nov 2026) of one installation: the hourly heat-meter energy divided by the heat-pump electricity, against public hourly outdoor temperature (Open-Meteo). Only hours with the compressor running throughout, and in the hours before and after, were used, so the table describes steady running. Start-up and cycling losses, and the standby/pump consumption while the compressor is off, are not part of the COP; the start penalty covers the former. Measured data covered about −6…18 °C and 450…3,350 W; outside that range, values were extrapolated from the trend of the measured hours (grid points with little data were blended towards a temperature curve × power factor fit), so they are less reliable. Other installations should replace the table with their own data.

The optional `max_heat_kw` limits the heat output: in each interval, power levels whose predicted heat (power × COP) exceeds it are left out of the search, as the heat pump could not draw that power there. With the default table and 14 kW this removes e.g. 3,500 W above about 6 °C and 3,000 W above about 12 °C. The planned power of the current quarter is projected with its heat capped at the same limit.

Entries created before the table existed are migrated to a table that reproduces their former datasheet curve × correction curve.

## Heat pump dynamics
The heat pump does not jump to a new power. The optimizer therefore separates the **target** (what the controller is asked for, `target_electrical_power_w`) from the **expected power** (the mean power the heat pump is predicted to draw in the interval, `expected_electrical_power_w`). Heat, COP, cost and slab energy are calculated from the expected power; the target is the decision.

The plant model (`PlantModel` in `optimizer.py`) gives the expected power of an interval from the previous interval's expected power, the run age and the target:

- Target 0: the heat pump stops within the interval (0 W).
- Start-up: in the n-th quarter after a start the mean power is `start_profile_w[n]`, whatever the target. The LG runs its own start-up: measured means were about 1.1 kW in the first quarter and 1.5 kW in the second, also for targets of 500–1000 W (Oct–Nov 2026).
- Running: the power moves towards the target by at most `ramp_up_w_per_quarter` up or `ramp_down_w_per_quarter` down per quarter (scaled for shorter intervals; 0 = no limit). Measured: about +1,000 W per quarter up (ES5 and boost), and 300–700 W per quarter down.

The DP state is (slab energy, on, expected power, run age). Expected power is part of the state only when the next interval depends on it (a ramp limit or the change penalty is set); its key resolution is 250 W, while the value itself is carried exactly. Several targets can lead to the same expected power when a ramp limit binds; the one closest to the expected power is chosen, so a large step down is planned as a staircase. During the start-up the target has no effect, so the plan asks for the power the run continues at. With an empty start profile and no ramp limits the optimizer reduces to the instantaneous model.

The current quarter starts from the measured state: the mean of `electrical_power_entity` over the previous quarter and the run age from `compressor_running_entity` (whole quarters since it turned on). Without these sensors the heat pump is assumed to be running steadily at the locked target. The expected power of the current quarter is the starting point of the optimization.

Two penalties keep the plan from flipping between almost equal options, which the heat pump cannot follow:

- `power_change_cost_eur_per_kw` per kW of change of the expected power while running (starts are covered by the start penalty, stops are free).
- `plan_change_cost_eur_per_kw` per kW that a target deviates from the previous plan, for intervals within `plan_change_hours`.

The penalties steer the search but are not part of the reported interval cost.

## Solar forecast and household baseload
One or more Forecast.Solar config entries and/or Open-Meteo Solar Forecast devices can be selected in the optimizer options. For each selected Open-Meteo device, the optimizer reads its daily energy sensors (today, tomorrow, and later days) and includes only periods overlapping the configured optimization horizon. It reads `wh_period_15m`, falling back to `wh_period`, and converts hourly forecast energies to quarter-hour optimizer intervals while preserving 15-minute data where available. Forecasts from multiple distinct arrays are summed. A fixed household baseload in watts is converted to interval energy and subtracted from the solar estimate; available PV is clipped at zero:

`PV_available = max(solar_forecast_kWh - baseload_W * interval_hours / 1000, 0)`

Only PV consumed by the heat pump is included in its running cost, valued at the feed-in price it could otherwise earn; any additional heat-pump electricity is valued at the buying price. Surplus PV is not credited, so the cost reflects the opportunity and grid-purchase costs of running the heat pump rather than net household energy revenue. The baseload is constant and does not model variable household consumption. When no solar forecasts are selected, the optimizer uses zero PV.

`HP_cost = min(HP_electricity, PV_available) * feed_in_price + max(HP_electricity - PV_available, 0) * buy_price`

## Inputs
- Heating Analytics forecast entity and isolated heating-energy sensor
- Buying-price entity (Nordpool or EPEX Spot)
- Feed-in-price entity (may be the same entity when no export price is available)
- Cumulative measured thermal energy delivered to the slab, kWh
- Slab temperature sensor, °C
- Room temperature sensor, °C
- Optional: heat-pump electrical power (W) and compressor-running sensor, for the measured starting state

## Main calibration parameters
- `slab_capacity_kwh_per_k`, default 9.0 kWh/K
- `floor_transfer_kw_per_k`, default 1.3 kW/K
- `temp_filter_time_constant_hours`, default 2.37 h (equivalent to the former alpha 0.10 at 15-minute updates; existing entries are migrated from their alpha and update interval)
- `temp_correction_alpha`, default 0.01 per update
- `equilibrium_hours`, default 24 h
- `cop_table`, see COP model
- `max_heat_kw`, default 0 (no limit)
- `start_profile_w`, default `1100,1500`
- `ramp_up_w_per_quarter`, default 1000 W; `ramp_down_w_per_quarter`, default 600 W
- `power_change_cost_eur_per_kw`, default 0.005 EUR/kW; `plan_change_cost_eur_per_kw`, default 0.01 EUR/kW within `plan_change_hours`, default 1 h

The defaults for floor transfer and observer gains are starting values, not identified physical parameters. They should be calibrated from observed data.

## Persistence and restart behavior
Home Assistant storage records estimated energy, last heat-meter reading, filtered slab temperature and correction diagnostics. A restart therefore continues the previous estimate. If the cumulative heat meter resets, a negative delta is ignored for that update and the new reading becomes the baseline.

## Diagnostic entities
- Estimated slab energy
- Filtered slab temperature
- Slab equilibrium temperature
- Slab temperature reference energy

Estimated slab energy attributes expose last measured heat input, modeled heat loss, temperature correction and update timestamp.

## Limitations
- Heating Analytics is presently the sole heat-loss estimator; forecast error therefore appears as state-estimation error and is slowly corrected by temperature.
- The current heat-loss update uses the first returned Heating Analytics forecast hour as the present load proxy. If Heating Analytics later exposes a historical/current-demand API, that should replace this approximation.
- The observer assumes the heat energy entity measures cumulative thermal energy delivered to the slab.
- Temperature sensor delay is handled by filtering and weak correction, not an explicit transport-delay model.

## Persistent Heating Analytics forecast cache
Hourly Heating Analytics rows are persisted in Home Assistant storage. Fresh forecast rows replace cached values for their timestamps; older rows are retained until the observer integrates heat loss through the current time, then rows before the current UTC hour are pruned. This preserves the history needed to reconcile slab energy after a Home Assistant restart. The coordinator retrieves Heating Analytics only once per optimization update and shares the merged rows between the slab-state observer and future optimization.


### Time-aware state integration and partial current interval
The slab observer advances over the actual elapsed time since its persisted `last_update`. Heating Analytics hourly kWh is interpreted as average kW for that hour and integrated piecewise across any hour boundaries. Therefore observer behavior is independent of coordinator refresh frequency.

Temperature grounding uses a configurable time constant `temp_correction_time_constant_hours`. The effective update gain is `alpha = 1 - exp(-elapsed_hours / time_constant_hours)`, avoiding a correction strength that changes with polling interval.

The current-quarter target is fixed from the previously published schedule, persisted plan, or configured bootstrap power. Its remaining duration is between 0 and 0.25 hours. The coordinator projects the measured slab energy through that remainder using the fixed power and demand forecast. The optimizer starts at the next quarter boundary with that projected energy and the fixed power's on/off state; subsequent points are complete 15-minute intervals. Thus refreshes cannot alter the command mid-quarter. Future schedule rows are activated at their timestamps, never early.

After the first plan, the commanded power for the current quarter is locked across optimizer refreshes and persisted with the quarter timestamp. The observer's measured slab energy at refresh time is projected through the remaining part of that quarter using the locked power and forecast demand. Dynamic programming begins at the next quarter with that projected energy and the locked power's on/off state. If no saved row covers the current quarter, `bootstrap_power_w` supplies a fixed fallback command for that quarter; it defaults to 0 W.

The comfort-temperature input is the intended room setpoint used to define equilibrium slab temperature, not the instantaneous measured room temperature.
