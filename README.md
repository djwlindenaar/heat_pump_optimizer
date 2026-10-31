## Heat Pump Cost Optimizer for Home Assistant

A Home Assistant custom integration that optimizes a power-controlled heat pump against 15-minute buying and feed-in prices while using a persistent floor-slab thermal-storage estimate.

### Inputs
- Heating Analytics hourly heat-demand forecast
- Buying and feed-in price entities with quarter-hour timestamps (Nordpool `raw_today`/`raw_tomorrow` and EPEX Spot `data` formats are supported)
- Cumulative measured thermal energy delivered to the slab
- Slab temperature
- Comfort-temperature or room-setpoint entity
- Configurable electrical power levels and COP correction curve

### Operation
The persistent slab observer is updated from measured delivered heat, elapsed-time-integrated Heating Analytics demand, and slow temperature grounding. Every optimization starts from this updated physical state. The first forecast interval represents only the remaining part of the current quarter; later intervals are complete 15-minute periods. A timed coordinator callback activates each scheduled target at its timestamp.

### Outputs
- Target electrical power
- Quarter-hour schedule
- Forecast optimized cost
- Estimated slab energy and observer diagnostics
- Filtered slab temperature, equilibrium temperature, and temperature-reference energy

Use an automation to copy the target-power sensor into the number entity consumed by the heat-pump controller. Start in shadow mode and validate the observer and schedule before enabling closed-loop control.

For EPEX Spot, select the `sensor.epex_spot_data_total_price` entity as the buying-price entity. Its `data` attribute supplies forecast prices in €/kWh; the integration expands hourly prices into quarter-hour optimizer intervals when needed. If you do not have a separate feed-in price, select the same entity for that field. Feed-in prices currently have no effect because PV production is not modeled.

See [DESIGN.md](DESIGN.md) for equations, persistence, timing, and calibration details.
