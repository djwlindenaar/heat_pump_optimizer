DOMAIN = 'heat_pump_optimizer'
PLATFORMS = ['sensor', 'binary_sensor', 'button']
CONF_HEATING_ANALYTICS_ENTITY = 'heating_analytics_entity'
CONF_ISOLATE_SENSOR = 'isolate_sensor'
CONF_NORDPOOL_BUY_ENTITY = 'nordpool_buy_entity'
CONF_NORDPOOL_FEED_IN_ENTITY = 'nordpool_feed_in_entity'
CONF_NORDPOOL_ENTITY = 'nordpool_entity'
CONF_FORECAST_SOLAR_ENTRIES = 'forecast_solar_entries'
CONF_OPEN_METEO_SOLAR_ENTITIES = 'open_meteo_solar_entities'
CONF_SOLAR_BASELOAD_W = 'solar_baseload_w'
CONF_HEAT_ENERGY_ENTITY = 'heat_energy_entity'
CONF_SLAB_TEMPERATURE_ENTITY = 'slab_temperature_entity'
CONF_ROOM_TEMPERATURE_ENTITY = 'room_temperature_entity'
CONF_HORIZON_HOURS = 'horizon_hours'
CONF_UPDATE_MINUTES = 'update_minutes'
CONF_SLAB_CAPACITY = 'slab_capacity_kwh_per_k'
CONF_SLAB_MIN = 'slab_min_kwh'
CONF_SLAB_MAX = 'slab_max_kwh'
CONF_INITIAL_SLAB = 'initial_slab_kwh'
CONF_TERMINAL_RESERVE = 'terminal_reserve_kwh'
CONF_POWER_LEVELS = 'power_levels_w'
CONF_STARTUP_COST = 'startup_cost_eur'
CONF_BOOTSTRAP_POWER_W = 'bootstrap_power_w'
CONF_STATE_STEP = 'state_step_kwh'
CONF_COP_CORRECTION = 'cop_correction_curve'  # legacy, migrated to the COP table
CONF_COP_TABLE = 'cop_table'
CONF_MAX_HEAT_KW = 'max_heat_kw'
CONF_FLOOR_TRANSFER_KW_PER_K = 'floor_transfer_kw_per_k'
CONF_TEMP_FILTER_ALPHA = 'temp_filter_alpha'  # legacy, migrated to the time constant
CONF_TEMP_FILTER_TIME_CONSTANT_HOURS = 'temp_filter_time_constant_hours'
CONF_TEMP_CORRECTION_ALPHA = 'temp_correction_alpha'
CONF_TEMP_CORRECTION_TIME_CONSTANT_HOURS = 'temp_correction_time_constant_hours'
CONF_EQUILIBRIUM_HOURS = 'equilibrium_hours'
# Fitted to measured steady-running hours (heat meter / electricity meter vs. outdoor temperature).
DEFAULT_COP_TABLE = '''W   500   650   800  1000  1250  1500  2000  2500  3000  3500  4000
 -8  3.30  3.42  3.31  3.10  2.99  2.90  2.70  2.59  2.52  2.46  2.41
 -4  3.61  3.69  3.57  3.34  3.23  3.14  2.97  2.86  2.77  2.70  2.65
  0  3.88  3.87  3.84  3.76  3.68  3.58  3.34  3.16  3.05  2.99  2.93
  4  4.48  4.74  4.73  4.46  4.27  4.11  3.84  3.68  3.58  3.51  3.43
  8  5.49  5.77  5.58  5.16  4.88  4.70  4.49  4.33  4.20  4.13  4.05
 12  6.77  6.70  6.34  5.96  5.80  5.58  5.20  5.04  4.88  4.80  4.71
 16  7.20  7.38  6.99  6.52  6.28  6.08  5.67  5.45  5.29  5.18  5.08
 20  7.39  7.67  7.41  6.95  6.71  6.50  6.06  5.80  5.64  5.52  5.41'''
DEFAULTS = {CONF_HORIZON_HOURS: 36, CONF_UPDATE_MINUTES: 15, CONF_SLAB_CAPACITY: 9.0, CONF_SLAB_MIN: -9.0, CONF_SLAB_MAX: 18.0, CONF_INITIAL_SLAB: 0.0, CONF_TERMINAL_RESERVE: 0.0, CONF_POWER_LEVELS: '0,500,750,1000,1250,1500,2000,2500,3000,3500,4000', CONF_STARTUP_COST: 0.03, CONF_BOOTSTRAP_POWER_W: 0, CONF_STATE_STEP: 0.25, CONF_COP_TABLE: DEFAULT_COP_TABLE, CONF_MAX_HEAT_KW: 0.0, CONF_FLOOR_TRANSFER_KW_PER_K: 1.3, CONF_TEMP_FILTER_TIME_CONSTANT_HOURS: 2.37, CONF_TEMP_CORRECTION_ALPHA: 0.01, CONF_TEMP_CORRECTION_TIME_CONSTANT_HOURS: 24.0, CONF_EQUILIBRIUM_HOURS: 24, CONF_FORECAST_SOLAR_ENTRIES: (), CONF_OPEN_METEO_SOLAR_ENTITIES: (), CONF_SOLAR_BASELOAD_W: 0.0}
