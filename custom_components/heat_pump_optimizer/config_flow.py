from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import *

class HeatPumpOptimizerConfigFlow(config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=1
    async def async_step_user(self,user_input:dict[str,Any]|None=None)->FlowResult:
        if user_input is not None:
            await self.async_set_unique_id("primary")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Heat Pump Cost Optimizer",data=user_input)
        schema=vol.Schema({
            vol.Required(CONF_HEATING_ANALYTICS_ENTITY,default="sensor.heating_analytics_week_ahead_forecast"):str,
            vol.Required(CONF_ISOLATE_SENSOR,default="sensor.heating_water_energy"):str,
            vol.Required(CONF_NORDPOOL_ENTITY):str,
            vol.Optional(CONF_HORIZON_HOURS,default=DEFAULTS[CONF_HORIZON_HOURS]):vol.All(int,vol.Range(min=1,max=72)),
            vol.Optional(CONF_UPDATE_MINUTES,default=DEFAULTS[CONF_UPDATE_MINUTES]):vol.All(int,vol.Range(min=5,max=60)),
            vol.Optional(CONF_SLAB_MIN,default=DEFAULTS[CONF_SLAB_MIN]):vol.Coerce(float),
            vol.Optional(CONF_SLAB_MAX,default=DEFAULTS[CONF_SLAB_MAX]):vol.Coerce(float),
            vol.Optional(CONF_INITIAL_SLAB,default=DEFAULTS[CONF_INITIAL_SLAB]):vol.Coerce(float),
            vol.Optional(CONF_TERMINAL_RESERVE,default=DEFAULTS[CONF_TERMINAL_RESERVE]):vol.Coerce(float),
            vol.Optional(CONF_POWER_LEVELS,default=DEFAULTS[CONF_POWER_LEVELS]):str,
            vol.Optional(CONF_STARTUP_COST,default=DEFAULTS[CONF_STARTUP_COST]):vol.Coerce(float),
            vol.Optional(CONF_COP_CORRECTION,default=DEFAULTS[CONF_COP_CORRECTION]):str,
        })
        return self.async_show_form(step_id="user",data_schema=schema)
