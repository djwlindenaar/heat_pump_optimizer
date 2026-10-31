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

`T_filtered = alpha_filter*T_measured + (1-alpha_filter)*T_filtered_previous`

The storage zero point depends on the heating load. The estimated equilibrium slab temperature is:

`T_equilibrium = T_room + P_loss_average / K_floor`

where `P_loss_average` is the average Heating Analytics demand over the configured equilibrium period (default 24 h), and `K_floor` is the effective slab-to-room heat transfer coefficient in kW/K.

The temperature-derived reference energy is:

`E_temperature = C_slab * (T_filtered - T_equilibrium)`

The integrated state is only slowly pulled toward this reference:

`E_state = E_integrated + alpha_correction*(E_temperature - E_integrated)`

The result is clipped to configured slab minimum/maximum limits. This makes energy accounting dominant over short periods while preventing long-term model drift.

## Optimizer coupling
The persisted observed `E_state` is supplied as `initial_slab_kwh` for every optimization run. Future slab trajectories still use the COP model and Heating Analytics forecast. Thus measured history initializes the optimizer, while predictions are used only forward in time.

## Inputs
- Heating Analytics forecast entity and isolated heating-energy sensor
- Buying-price entity (Nordpool or EPEX Spot)
- Feed-in-price entity (may be the same entity when no export price is available)
- Cumulative measured thermal energy delivered to the slab, kWh
- Slab temperature sensor, °C
- Room temperature sensor, °C

## Main calibration parameters
- `slab_capacity_kwh_per_k`, default 9.0 kWh/K
- `floor_transfer_kw_per_k`, default 1.3 kW/K
- `temp_filter_alpha`, default 0.10 per update
- `temp_correction_alpha`, default 0.01 per update
- `equilibrium_hours`, default 24 h

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
Hourly Heating Analytics rows are persisted in Home Assistant storage. On every coordinator refresh, hours before the current UTC hour are removed and every newly returned hour replaces the cached value for that timestamp. If Heating Analytics no longer returns the current hour, its last forecast remains cached and supplies the remaining 15-minute intervals of that hour. The coordinator retrieves Heating Analytics only once per optimization update and shares the merged rows between the slab-state observer and future optimization. On a first-ever startup inside an hour, no historical current-hour forecast exists; slab heat-loss subtraction is therefore zero for that update, while optimization starts as soon as a cached/current forecast interval is available.


### Time-aware state integration and partial current interval
The slab observer advances over the actual elapsed time since its persisted `last_update`. Heating Analytics hourly kWh is interpreted as average kW for that hour and integrated piecewise across any hour boundaries. Therefore observer behavior is independent of coordinator refresh frequency.

Temperature grounding uses a configurable time constant `temp_correction_time_constant_hours`. The effective update gain is `alpha = 1 - exp(-elapsed_hours / time_constant_hours)`, avoiding a correction strength that changes with polling interval.

The optimizer includes the current quarter. Its first point starts at the current time and ends on the next quarter boundary, so its `duration_hours` is between 0 and 0.25. Later points use 0.25 hours. Heating demand, electric energy, produced heat, and cost all scale with the point duration. A new optimization may therefore change the target immediately during the current quarter; the next observer update uses measured delivered heat, not the previous prediction.

The comfort-temperature input is the intended room setpoint used to define equilibrium slab temperature, not the instantaneous measured room temperature.
