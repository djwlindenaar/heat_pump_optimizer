DOMAIN = "heat_pump_optimizer"
PLATFORMS = ["sensor", "button"]

CONF_HEATING_ANALYTICS_ENTITY = "heating_analytics_entity"
CONF_ISOLATE_SENSOR = "isolate_sensor"
CONF_NORDPOOL_ENTITY = "nordpool_entity"
CONF_CONTROL_ENTITY = "control_entity"
CONF_HORIZON_HOURS = "horizon_hours"
CONF_UPDATE_MINUTES = "update_minutes"
CONF_SLAB_CAPACITY = "slab_capacity_kwh_per_k"
CONF_SLAB_MIN = "slab_min_kwh"
CONF_SLAB_MAX = "slab_max_kwh"
CONF_INITIAL_SLAB = "initial_slab_kwh"
CONF_TERMINAL_RESERVE = "terminal_reserve_kwh"
CONF_POWER_LEVELS = "power_levels_w"
CONF_STARTUP_COST = "startup_cost_eur"
CONF_STATE_STEP = "state_step_kwh"
CONF_COP_CORRECTION = "cop_correction_curve"

DEFAULTS = {
    CONF_HORIZON_HOURS: 36,
    CONF_UPDATE_MINUTES: 15,
    CONF_SLAB_CAPACITY: 9.0,
    CONF_SLAB_MIN: -9.0,
    CONF_SLAB_MAX: 18.0,
    CONF_INITIAL_SLAB: 0.0,
    CONF_TERMINAL_RESERVE: 0.0,
    CONF_POWER_LEVELS: "0,500,750,1000,1250,1500,2000,2500,3000,3500,4000",
    CONF_STARTUP_COST: 0.03,
    CONF_STATE_STEP: 0.25,
    CONF_COP_CORRECTION: "500:1.00,750:0.98,1000:0.96,1500:0.93,2000:0.90,2500:0.87,3000:0.84,3500:0.81,4000:0.78",
}
