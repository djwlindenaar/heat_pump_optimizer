from __future__ import annotations
from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from .const import *
from .cop_model import COPModel
from .forecast import INTERVALS_PER_HOUR, async_build_forecast, async_get_heating_demand
from .optimizer import optimize
from .slab_state import SlabStateEstimator
_LOGGER = logging.getLogger(__name__)

class HeatPumpOptimizerCoordinator(DataUpdateCoordinator[dict]):

    def __init__(self, hass, entry):
        self.entry = entry
        self.opts = {**DEFAULTS, **entry.data, **entry.options}
        legacy = self.opts.get(CONF_NORDPOOL_ENTITY, '')
        self.opts.setdefault(CONF_NORDPOOL_BUY_ENTITY, legacy)
        self.opts.setdefault(CONF_NORDPOOL_FEED_IN_ENTITY, legacy)
        self.estimator = SlabStateEstimator(hass, float(self.opts[CONF_INITIAL_SLAB]))
        self._loaded = False
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(minutes=int(self.opts[CONF_UPDATE_MINUTES])))

    def _sensor_float(self, key):
        state = self.hass.states.get(self.opts[key])
        if state is None:
            raise ValueError(f'Entity not found: {self.opts[key]}')
        return float(state.state)

    async def _update_slab_state(self):
        if not self._loaded:
            await self.estimator.async_load()
            self._loaded = True
        rows = await async_get_heating_demand(self.hass, self.opts[CONF_HEATING_ANALYTICS_ENTITY], self.opts[CONF_ISOLATE_SENSOR], max(1, (int(self.opts[CONF_EQUILIBRIUM_HOURS]) + 23) // 24))
        if not rows:
            raise ValueError('Heating Analytics returned no demand for slab estimator')
        current_hour_kwh = rows[0][1]
        average_kw = sum((v for _, v in rows[:int(self.opts[CONF_EQUILIBRIUM_HOURS])])) / max(1, min(len(rows), int(self.opts[CONF_EQUILIBRIUM_HOURS])))
        return await self.estimator.async_update(heat_meter_kwh=self._sensor_float(CONF_HEAT_ENERGY_ENTITY), heat_loss_kwh=current_hour_kwh / INTERVALS_PER_HOUR, slab_temperature_c=self._sensor_float(CONF_SLAB_TEMPERATURE_ENTITY), room_temperature_c=self._sensor_float(CONF_ROOM_TEMPERATURE_ENTITY), average_heat_loss_kw=average_kw, slab_capacity_kwh_per_k=float(self.opts[CONF_SLAB_CAPACITY]), floor_transfer_kw_per_k=float(self.opts[CONF_FLOOR_TRANSFER_KW_PER_K]), temp_filter_alpha=float(self.opts[CONF_TEMP_FILTER_ALPHA]), temp_correction_alpha=float(self.opts[CONF_TEMP_CORRECTION_ALPHA]), slab_min_kwh=float(self.opts[CONF_SLAB_MIN]), slab_max_kwh=float(self.opts[CONF_SLAB_MAX]))

    async def _async_update_data(self):
        try:
            slab = await self._update_slab_state()
            horizon = int(self.opts[CONF_HORIZON_HOURS])
            days = max(1, (horizon + 23) // 24)
            points = await async_build_forecast(self.hass, self.opts[CONF_HEATING_ANALYTICS_ENTITY], self.opts[CONF_ISOLATE_SENSOR], self.opts[CONF_NORDPOOL_BUY_ENTITY], self.opts[CONF_NORDPOOL_FEED_IN_ENTITY], days)
            points = points[:horizon * INTERVALS_PER_HOUR]
            levels = [int(v.strip()) for v in str(self.opts[CONF_POWER_LEVELS]).split(',')]
            model = COPModel(str(self.opts[CONF_COP_CORRECTION]))
            schedule = await self.hass.async_add_executor_job(lambda: optimize(points, model, power_levels_w=levels, slab_min_kwh=float(self.opts[CONF_SLAB_MIN]), slab_max_kwh=float(self.opts[CONF_SLAB_MAX]), initial_slab_kwh=slab.energy_kwh, terminal_reserve_kwh=float(self.opts[CONF_TERMINAL_RESERVE]), state_step_kwh=float(self.opts[CONF_STATE_STEP]), startup_cost_eur=float(self.opts[CONF_STARTUP_COST])))
            local_schedule = [
                {
                    **row,
                    'timestamp': dt_util.as_local(row['timestamp']),
                }
                for row in schedule
            ]
            first = local_schedule[0]
            return {
                'target_power_w': first['target_electrical_power_w'],
                'current': first,
                'schedule': local_schedule,
                'total_cost_eur': round(
                    sum(r['interval_cost_eur'] for r in local_schedule), 4
                ),
                'forecast_hours': round(
                    len(local_schedule) / INTERVALS_PER_HOUR, 2
                ),
                'forecast_intervals': len(local_schedule),
                'slab_state': slab,
            }
        except Exception as err:
            raise UpdateFailed(str(err)) from err
