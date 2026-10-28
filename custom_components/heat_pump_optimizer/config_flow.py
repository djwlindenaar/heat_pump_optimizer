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
        return HeatPumpOptimizerOptionsFlow()

class HeatPumpOptimizerOptionsFlow(config_entries.OptionsFlowWithReload):
    def __init__(self):
        self._rows = None
        self._editing_index = None
        self._pending_options = None

    def _current(self):
        return {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}

    def _ensure_rows_loaded(self):
        if self._rows is not None:
            return
        current = self._current()
        configured = current.get(CONF_OPERATING_POINTS)
        if configured:
            self._rows = [
                {
                    'power_w': int(point['power_w']),
                    'cop_factor': float(point['cop_factor']),
                }
                for point in configured
            ]
        else:
            levels = [
                int(value.strip())
                for value in str(current[CONF_POWER_LEVELS]).split(',')
                if int(value.strip()) > 0
            ]
            correction = {}
            for item in str(current[CONF_COP_CORRECTION]).split(','):
                power, factor = item.strip().split(':')
                correction[int(float(power))] = float(factor)
            self._rows = [
                {
                    'power_w': power,
                    'cop_factor': correction.get(power, 1.0),
                }
                for power in levels
            ]
        self._rows.sort(key=lambda row: row['power_w'])

    def _overview_text(self):
        if not self._rows:
            return 'No operating points configured.'
        lines = ['| Power | COP factor |', '| ---: | ---: |']
        lines.extend(
            f"| {row['power_w']} W | {row['cop_factor']:.3f} |"
            for row in self._rows
        )
        return '\n'.join(lines)

    def _selection_options(self):
        options = [
            {'value': 'finish', 'label': 'Save and close'},
            {'value': 'add', 'label': 'Add operating point'},
        ]
        options.extend(
            {
                'value': f'edit:{index}',
                'label': (
                    f"Edit {row['power_w']} W / "
                    f"factor {row['cop_factor']:.3f}"
                ),
            }
            for index, row in enumerate(self._rows)
        )
        return options

    def _validate_rows(self):
        if len(self._rows) < 2:
            return 'not_enough_operating_points'
        powers = [int(row['power_w']) for row in self._rows]
        if any(power <= 0 for power in powers):
            return 'invalid_power'
        if len(powers) != len(set(powers)):
            return 'duplicate_power'
        if any(float(row['cop_factor']) <= 0 for row in self._rows):
            return 'invalid_cop_factor'
        return None

    def _save_options(self):
        validation_error = self._validate_rows()
        if validation_error is not None:
            return None, validation_error
        self._rows.sort(key=lambda row: row['power_w'])
        options = {
            **self.config_entry.options,
            **(self._pending_options or {}),
            CONF_OPERATING_POINTS: self._rows,
        }
        options[CONF_POWER_LEVELS] = '0,' + ','.join(
            str(row['power_w']) for row in self._rows
        )
        options[CONF_COP_CORRECTION] = ','.join(
            f"{row['power_w']}:{row['cop_factor']}"
            for row in self._rows
        )
        return options, None

    async def async_step_init(self, user_input=None):
        self._ensure_rows_loaded()
        if user_input is not None:
            self._pending_options = {
                **self.config_entry.options,
                **user_input,
            }
            return await self.async_step_operating_points()
        return self.async_show_form(
            step_id='init',
            data_schema=_options_schema(self._current()),
            last_step=False,
        )

    async def async_step_operating_points(self, user_input=None):
        self._ensure_rows_loaded()
        errors = {}
        if user_input is not None:
            selection = user_input.get('operating_point_action')
            if selection == 'finish':
                options, error = self._save_options()
                if error is None:
                    return self.async_create_entry(title='', data=options)
                errors['base'] = error
            elif selection == 'add':
                self._editing_index = None
                return await self.async_step_edit_operating_point()
            elif selection and selection.startswith('edit:'):
                self._editing_index = int(selection.split(':', 1)[1])
                return await self.async_step_edit_operating_point()

        return self.async_show_form(
            step_id='operating_points',
            data_schema=vol.Schema({
                vol.Required('operating_point_action', default='finish'):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=self._selection_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
            }),
            errors=errors,
            description_placeholders={
                'operating_points_table': self._overview_text(),
            },
        )

    async def async_step_edit_operating_point(self, user_input=None):
        is_new = self._editing_index is None
        current = (
            {'power_w': 500, 'cop_factor': 1.0}
            if is_new
            else self._rows[self._editing_index]
        )
        errors = {}
        if user_input is not None:
            action = user_input.get('row_action', 'save')
            if action == 'cancel':
                return await self.async_step_operating_points()
            if action == 'delete' and not is_new:
                del self._rows[self._editing_index]
                self._editing_index = None
                return await self.async_step_operating_points()

            power_w = int(user_input['power_w'])
            cop_factor = float(user_input['cop_factor'])
            duplicate = any(
                row['power_w'] == power_w and index != self._editing_index
                for index, row in enumerate(self._rows)
            )
            if duplicate:
                errors['power_w'] = 'duplicate_power'
            elif power_w <= 0:
                errors['power_w'] = 'invalid_power'
            elif cop_factor <= 0:
                errors['cop_factor'] = 'invalid_cop_factor'
            else:
                row = {'power_w': power_w, 'cop_factor': cop_factor}
                if is_new:
                    self._rows.append(row)
                else:
                    self._rows[self._editing_index] = row
                self._rows.sort(key=lambda item: item['power_w'])
                self._editing_index = None
                return await self.async_step_operating_points()

        action_options = [
            {'value': 'save', 'label': 'Save row'},
            {'value': 'cancel', 'label': 'Cancel'},
        ]
        if not is_new:
            action_options.append({'value': 'delete', 'label': 'Delete row'})

        return self.async_show_form(
            step_id='edit_operating_point',
            data_schema=vol.Schema({
                vol.Required('power_w', default=current['power_w']):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=10000,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement='W',
                        )
                    ),
                vol.Required('cop_factor', default=current['cop_factor']):
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.01,
                            max=2.0,
                            step=0.001,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                vol.Required('row_action', default='save'):
                    selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=action_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
            }),
            errors=errors,
            description_placeholders={
                'row_description': (
                    'Add a new operating point'
                    if is_new
                    else f"Edit operating point {self._editing_index + 1}"
                ),
            },
        )
