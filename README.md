# Heat Pump Cost Optimizer for Home Assistant

First functional custom integration for Heating Analytics + Nordpool + a power-controlled heat pump.

## Install
Copy `custom_components/heat_pump_optimizer` to `/config/custom_components/`, restart Home Assistant, then add **Heat Pump Cost Optimizer** in Settings > Devices & services.

## Inputs
- `heating_analytics.get_forecast`, with `isolate_sensor` set to the heat-pump energy sensor.
- Nordpool entity exposing `raw_today` and `raw_tomorrow`, each item containing `start` and `value`.
- Datasheet COP curve at LWT 30 C, corrected by a transparent configured power factor curve.

## Outputs
- `sensor.heat_pump_cost_optimizer_target_electrical_power`
- `sensor.heat_pump_cost_optimizer_schedule`
- `sensor.heat_pump_cost_optimizer_forecast_optimized_cost`
- `button.heat_pump_cost_optimizer_run_optimizer_now`

Use an HA automation to copy the target-power sensor into the number entity consumed by the existing heat-pump controller. Start in shadow mode.

## Important v0.1 assumptions
- Heating Analytics forecast intervals and Nordpool prices are hourly.
- Sell price equals buy price.
- PV is zero in v0.1.
- Slab state is relative and initialized from configuration on each solve. A later release must estimate actual slab state from delivered minus demanded heat.
- COP correction curve is editable in the config flow. It is not trained inside HA yet.
- This integration does not directly write to the heat-pump controller.
