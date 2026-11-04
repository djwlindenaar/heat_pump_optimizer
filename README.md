## Heat Pump Cost Optimizer for Home Assistant

A Home Assistant custom integration that optimizes a power-controlled heat pump against 15-minute buying and feed-in prices while using a persistent floor-slab thermal-storage estimate.

### Inputs
- Heating Analytics hourly heat-demand forecast
- Buying and feed-in price entities with quarter-hour timestamps (Nordpool `raw_today`/`raw_tomorrow` and EPEX Spot `data` formats are supported)
- Optional Forecast.Solar configuration entries for one or more solar arrays
- Optional Open-Meteo Solar Forecast sensors for one or more solar arrays
- Optional fixed household electrical baseload (W), subtracted from forecast solar production
- Cumulative measured thermal energy delivered to the slab
- Slab temperature
- Comfort-temperature or room-setpoint entity
- Configurable electrical power levels and COP correction curve

### Operation
The persistent slab observer is updated from measured delivered heat, elapsed-time-integrated Heating Analytics demand, and slow temperature grounding. The current quarter's already-issued power is held fixed and projected to the next quarter boundary; optimization decisions begin at that boundary. A timed coordinator callback activates each later target at its timestamp.

### Outputs
- Target electrical power
- Quarter-hour schedule
- Forecast optimized cost
- Estimated slab energy and observer diagnostics
- Filtered slab temperature, equilibrium temperature, and temperature-reference energy

Use an automation to copy the target-power sensor into the number entity consumed by the heat-pump controller. Start in shadow mode and validate the observer and schedule before enabling closed-loop control.

For EPEX Spot, select the `sensor.epex_spot_data_total_price` entity as the buying-price entity. Its `data` attribute supplies forecast prices in €/kWh; the integration expands hourly prices into quarter-hour optimizer intervals when needed. If you do not have a separate feed-in price, select the same entity for that field.

To include solar production, configure Forecast.Solar entries, Open-Meteo Solar Forecast sensors, or both under the integration's options. For Open-Meteo, select one daily energy-production sensor for each solar installation. The optimizer automatically reads the related daily sensors on that device (today, tomorrow, and later days) and uses only forecast periods within the configured optimization horizon. It combines their `wh_period_15m` forecasts (falling back to `wh_period` where needed). Forecast.Solar hourly forecasts are also converted into quarter-hour estimates. Set the fixed household baseload in watts to reserve forecast production for typical household consumption; the optimizer subtracts this load from solar production in each interval. PV consumed by the heat pump is costed at the feed-in price (the revenue foregone by not exporting it), and additional electricity is costed at the buying price. Surplus PV is not credited. This is a fixed estimate, not a forecast of other household loads. With no solar forecasts selected, PV remains zero.

Each optimization keeps the already-issued power target fixed for the remainder of the current quarter and optimizes from the next quarter. The plan is persisted so a Home Assistant restart can recover that target. The configured bootstrap power is used only when no saved current-quarter plan is available.

See [DESIGN.md](DESIGN.md) for equations, persistence, timing, and calibration details.
