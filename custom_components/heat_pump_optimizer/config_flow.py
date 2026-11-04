from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from .const import *

def _es():
    return selector.EntitySelector(selector.EntitySelectorConfig(domain='sensor'))

def _connection_schema(current=None):
    current = current or {}
    legacy = current.get(CONF_NORDPOOL_ENTITY, '')
    return vol.Schema({vol.Required(CONF_HEATING_ANALYTICS_ENTITY, default=current.get(CONF_HEATING_ANALYTICS_ENTITY, 'sensor.heating_analytics_week_ahead_forecast')): _es(), vol.Required(CONF_ISOLATE_SENSOR, default=current.get(CONF_ISOLATE_SENSOR, 'sensor.heating_water_energy')): _es(), vol.Required(CONF_NORDPOOL_BUY_ENTITY, default=current.get(CONF_NORDPOOL_BUY_ENTITY, legacy)): _es(), vol.Required(CONF_NORDPOOL_FEED_IN_ENTITY, default=current.get(CONF_NORDPOOL_FEED_IN_ENTITY, current.get(CONF_NORDPOOL_BUY_ENTITY, legacy))): _es(), vol.Required(CONF_HEAT_ENERGY_ENTITY, default=current.get(CONF_HEAT_ENERGY_ENTITY, '')): _es(), vol.Required(CONF_SLAB_TEMPERATURE_ENTITY, default=current.get(CONF_SLAB_TEMPERATURE_ENTITY, '')): _es(), vol.Required(CONF_ROOM_TEMPERATURE_ENTITY, default=current.get(CONF_ROOM_TEMPERATURE_ENTITY, '')): _es()})

def _options_schema(current=None, solar_options=None):
    c = {**DEFAULTS, **(current or {})}
    solar_entries = c[CONF_FORECAST_SOLAR_ENTRIES]
    if isinstance(solar_entries, str):
        solar_entries = [solar_entries] if solar_entries else []
    else:
        solar_entries = list(solar_entries)
    open_meteo_entities = c[CONF_OPEN_METEO_SOLAR_ENTITIES]
    if isinstance(open_meteo_entities, str):
        open_meteo_entities = [open_meteo_entities] if open_meteo_entities else []
    else:
        open_meteo_entities = list(open_meteo_entities)
    return vol.Schema(
        {
            vol.Required(
                CONF_FORECAST_SOLAR_ENTRIES,
                default=solar_entries,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=solar_options or [],
                    multiple=True,
                )
            ),
            vol.Required(
                CONF_OPEN_METEO_SOLAR_ENTITIES,
                default=open_meteo_entities,
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    integration="open_meteo_solar_forecast",
                    multiple=True,
                )
            ),
            vol.Required(
                CONF_SOLAR_BASELOAD_W,
                default=c[CONF_SOLAR_BASELOAD_W],
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Required(
                CONF_HORIZON_HOURS,
                default=c[CONF_HORIZON_HOURS],
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
            vol.Required(
                CONF_UPDATE_MINUTES,
                default=c[CONF_UPDATE_MINUTES],
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Required(
                CONF_SLAB_CAPACITY,
                default=c[CONF_SLAB_CAPACITY],
            ): vol.All(vol.Coerce(float), vol.Range(min=0.1)),
            vol.Required(
                CONF_FLOOR_TRANSFER_KW_PER_K,
                default=c[CONF_FLOOR_TRANSFER_KW_PER_K],
            ): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
            vol.Required(
                CONF_TEMP_FILTER_ALPHA,
                default=c[CONF_TEMP_FILTER_ALPHA],
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
            vol.Required(
                CONF_TEMP_CORRECTION_TIME_CONSTANT_HOURS,
                default=c[CONF_TEMP_CORRECTION_TIME_CONSTANT_HOURS],
            ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=720)),
            vol.Required(
                CONF_EQUILIBRIUM_HOURS,
                default=c[CONF_EQUILIBRIUM_HOURS],
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=72)),
            vol.Required(
                CONF_SLAB_MIN,
                default=c[CONF_SLAB_MIN],
            ): vol.Coerce(float),
            vol.Required(
                CONF_SLAB_MAX,
                default=c[CONF_SLAB_MAX],
            ): vol.Coerce(float),
            vol.Required(
                CONF_INITIAL_SLAB,
                default=c[CONF_INITIAL_SLAB],
            ): vol.Coerce(float),
            vol.Required(
                CONF_TERMINAL_RESERVE,
                default=c[CONF_TERMINAL_RESERVE],
            ): vol.Coerce(float),
            vol.Required(
                CONF_POWER_LEVELS,
                default=c[CONF_POWER_LEVELS],
            ): str,
            vol.Required(
                CONF_STARTUP_COST,
                default=c[CONF_STARTUP_COST],
            ): vol.Coerce(float),
            vol.Required(
                CONF_BOOTSTRAP_POWER_W,
                default=c[CONF_BOOTSTRAP_POWER_W],
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Required(
                CONF_STATE_STEP,
                default=c[CONF_STATE_STEP],
            ): vol.Coerce(float),
            vol.Required(
                CONF_COP_CORRECTION,
                default=c[CONF_COP_CORRECTION],
            ): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )

class HeatPumpOptimizerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id('primary')
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title='Heat Pump Cost Optimizer', data=user_input)
        return self.async_show_form(step_id='user', data_schema=_connection_schema())

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            self.hass.config_entries.async_update_entry(entry, data=user_input)
            return self.async_abort(reason='reconfigure_successful')
        return self.async_show_form(step_id='reconfigure', data_schema=_connection_schema(dict(entry.data)))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HeatPumpOptimizerOptionsFlow(config_entry)

class HeatPumpOptimizerOptionsFlow(config_entries.OptionsFlow):

    def __init__(self, config_entry):
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title='', data=user_input)
        solar_options = [
            {"value": entry.entry_id, "label": entry.title}
            for entry in self.hass.config_entries.async_entries("forecast_solar")
        ]
        return self.async_show_form(
            step_id='init',
            data_schema=_options_schema(
                {**self._config_entry.data, **self._config_entry.options},
                solar_options,
            ),
        )
