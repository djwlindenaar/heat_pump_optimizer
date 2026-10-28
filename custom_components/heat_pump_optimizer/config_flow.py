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

def _options_schema(current=None):
    c = {**DEFAULTS, **(current or {})}
    return vol.Schema({vol.Required(CONF_HORIZON_HOURS, default=c[CONF_HORIZON_HOURS]): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)), vol.Required(CONF_UPDATE_MINUTES, default=c[CONF_UPDATE_MINUTES]): vol.All(vol.Coerce(int), vol.Range(min=1)), vol.Required(CONF_SLAB_CAPACITY, default=c[CONF_SLAB_CAPACITY]): vol.All(vol.Coerce(float), vol.Range(min=0.1)), vol.Required(CONF_FLOOR_TRANSFER_KW_PER_K, default=c[CONF_FLOOR_TRANSFER_KW_PER_K]): vol.All(vol.Coerce(float), vol.Range(min=0.01)), vol.Required(CONF_TEMP_FILTER_ALPHA, default=c[CONF_TEMP_FILTER_ALPHA]): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)), vol.Required(CONF_TEMP_CORRECTION_ALPHA, default=c[CONF_TEMP_CORRECTION_ALPHA]): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)), vol.Required(CONF_EQUILIBRIUM_HOURS, default=c[CONF_EQUILIBRIUM_HOURS]): vol.All(vol.Coerce(int), vol.Range(min=1, max=72)), vol.Required(CONF_SLAB_MIN, default=c[CONF_SLAB_MIN]): vol.Coerce(float), vol.Required(CONF_SLAB_MAX, default=c[CONF_SLAB_MAX]): vol.Coerce(float), vol.Required(CONF_INITIAL_SLAB, default=c[CONF_INITIAL_SLAB]): vol.Coerce(float), vol.Required(CONF_TERMINAL_RESERVE, default=c[CONF_TERMINAL_RESERVE]): vol.Coerce(float), vol.Required(CONF_STARTUP_COST, default=c[CONF_STARTUP_COST]): vol.Coerce(float), vol.Required(CONF_STATE_STEP, default=c[CONF_STATE_STEP]): vol.Coerce(float)})
def _legacy_operating_points(current):
    levels = [int(value.strip()) for value in str(current.get(CONF_POWER_LEVELS, DEFAULTS[CONF_POWER_LEVELS])).split(',') if int(value.strip()) > 0]
    correction = {}
    for item in str(current.get(CONF_COP_CORRECTION, DEFAULTS[CONF_COP_CORRECTION])).split(','):
        power, factor = item.strip().split(':')
        correction[int(float(power))] = float(factor)
    return [{'power_w': power, 'cop_factor': correction.get(power, 1.0)} for power in levels]
def _operating_points(current):
    points = current.get(CONF_OPERATING_POINTS)
    if points:
        return [{'power_w': int(point['power_w']), 'cop_factor': float(point['cop_factor'])} for point in points]
    return _legacy_operating_points(current)
def _operating_points_schema(current):
    fields = {}
    for index, point in enumerate(_operating_points(current), start=1):
        fields[vol.Required(f'power_{index}_w', default=point['power_w'])] = vol.All(vol.Coerce(int), vol.Range(min=1))
        fields[vol.Required(f'cop_{index}_factor', default=point['cop_factor'])] = vol.All(vol.Coerce(float), vol.Range(min=0.01))
    return vol.Schema(fields)
def _points_from_input(user_input):
    indexes = sorted(int(key.split('_')[1]) for key in user_input if key.startswith('power_'))
    points = [{'power_w': int(user_input[f'power_{index}_w']), 'cop_factor': float(user_input[f'cop_{index}_factor'])} for index in indexes]
    points.sort(key=lambda point: point['power_w'])
    if len({point['power_w'] for point in points}) != len(points):
        raise vol.Invalid('duplicate_power')
    return points
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
        self._pending_options = None
    def _current(self):
        return {**DEFAULTS, **self._config_entry.data, **self._config_entry.options}
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self._pending_options = {**self._config_entry.options, **user_input}
            return await self.async_step_operating_points()
        return self.async_show_form(step_id='init', data_schema=_options_schema(self._current()))
    async def async_step_operating_points(self, user_input=None):
        current = {**self._current(), **(self._pending_options or {})}
        errors = {}
        if user_input is not None:
            try:
                points = _points_from_input(user_input)
            except (KeyError, TypeError, ValueError, vol.Invalid):
                errors['base'] = 'invalid_operating_points'
            else:
                options = {**(self._pending_options or self._config_entry.options)}
                options[CONF_OPERATING_POINTS] = points
                options[CONF_POWER_LEVELS] = '0,' + ','.join(str(point['power_w']) for point in points)
                options[CONF_COP_CORRECTION] = ','.join(f"{point['power_w']}:{point['cop_factor']}" for point in points)
                return self.async_create_entry(title='', data=options)
        return self.async_show_form(step_id='operating_points', data_schema=_operating_points_schema(current), errors=errors)
