## Heat Pump Cost Optimizer for Home Assistant

A Home Assistant custom integration that optimizes a power-controlled heat pump against 15-minute buying and feed-in prices while using a persistent floor-slab thermal-storage estimate.

### Inputs
- Heating Analytics hourly heat-demand forecast
- Separate Nordpool buying and feed-in price entities with quarter-hour timestamps
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

See [DESIGN.md](DESIGN.md) for equations, persistence, timing, and calibration details.
