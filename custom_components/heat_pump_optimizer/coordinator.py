"""Data coordinator and scheduled activation of optimized setpoints."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import *
from .cop_model import COPModel
from .forecast import (
    INTERVALS_PER_HOUR,
    async_build_forecast,
    async_get_heating_demand,
)
from .optimizer import optimize
from .slab_state import SlabStateEstimator

_LOGGER = logging.getLogger(__name__)


class HeatPumpOptimizerCoordinator(DataUpdateCoordinator[dict]):
    """Optimize periodically and activate schedule rows at their exact timestamps."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.opts = {**DEFAULTS, **entry.data, **entry.options}
        legacy = self.opts.get(CONF_NORDPOOL_ENTITY, "")
        self.opts.setdefault(CONF_NORDPOOL_BUY_ENTITY, legacy)
        self.opts.setdefault(CONF_NORDPOOL_FEED_IN_ENTITY, legacy)

        self.estimator = SlabStateEstimator(
            hass,
            float(self.opts[CONF_INITIAL_SLAB]),
        )
        self._loaded = False
        self._cancel_schedule_timer: Callable[[], None] | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(
                minutes=int(self.opts[CONF_UPDATE_MINUTES])
            ),
        )

    def _sensor_float(self, key: str) -> float:
        state = self.hass.states.get(self.opts[key])
        if state is None:
            raise ValueError(f"Entity not found: {self.opts[key]}")
        return float(state.state)

    async def _update_slab_state(self):
        if not self._loaded:
            await self.estimator.async_load()
            self._loaded = True

        equilibrium_hours = int(self.opts[CONF_EQUILIBRIUM_HOURS])
        rows = await async_get_heating_demand(
            self.hass,
            self.opts[CONF_HEATING_ANALYTICS_ENTITY],
            self.opts[CONF_ISOLATE_SENSOR],
            max(1, (equilibrium_hours + 23) // 24),
        )
        if not rows:
            raise ValueError(
                "Heating Analytics returned no demand for slab estimator"
            )

        current_hour_kwh = rows[0][1]
        average_rows = rows[:equilibrium_hours]
        average_kw = sum(value for _, value in average_rows) / max(
            1,
            len(average_rows),
        )

        return await self.estimator.async_update(
            heat_meter_kwh=self._sensor_float(CONF_HEAT_ENERGY_ENTITY),
            heat_loss_kwh=current_hour_kwh / INTERVALS_PER_HOUR,
            slab_temperature_c=self._sensor_float(
                CONF_SLAB_TEMPERATURE_ENTITY
            ),
            room_temperature_c=self._sensor_float(
                CONF_ROOM_TEMPERATURE_ENTITY
            ),
            average_heat_loss_kw=average_kw,
            slab_capacity_kwh_per_k=float(self.opts[CONF_SLAB_CAPACITY]),
            floor_transfer_kw_per_k=float(
                self.opts[CONF_FLOOR_TRANSFER_KW_PER_K]
            ),
            temp_filter_alpha=float(self.opts[CONF_TEMP_FILTER_ALPHA]),
            temp_correction_alpha=float(
                self.opts[CONF_TEMP_CORRECTION_ALPHA]
            ),
            slab_min_kwh=float(self.opts[CONF_SLAB_MIN]),
            slab_max_kwh=float(self.opts[CONF_SLAB_MAX]),
        )

    def _cancel_schedule_activation(self) -> None:
        if self._cancel_schedule_timer is not None:
            self._cancel_schedule_timer()
            self._cancel_schedule_timer = None

    def _active_schedule_row(
        self,
        schedule: list[dict],
        now: datetime | None = None,
    ) -> dict:
        """Return the row whose interval contains now.

        If the schedule begins in the future, use its first row. If all timestamps
        have passed, keep the last row until a new optimization replaces it.
        """
        if not schedule:
            raise ValueError("Optimizer returned an empty schedule")

        now = now or dt_util.now()
        active = schedule[0]
        for row in schedule:
            if row["timestamp"] > now:
                break
            active = row
        return active

    def _next_schedule_timestamp(
        self,
        schedule: list[dict],
        now: datetime | None = None,
    ) -> datetime | None:
        now = now or dt_util.now()
        for row in schedule:
            if row["timestamp"] > now:
                return row["timestamp"]
        return None

    def _apply_active_schedule_row(self) -> None:
        """Update current/target values without rerunning the optimizer."""
        if not self.data:
            return

        schedule = self.data.get("schedule") or []
        if not schedule:
            return

        current = self._active_schedule_row(schedule)
        self.data["current"] = current
        self.data["target_power_w"] = current["target_electrical_power_w"]

    def _schedule_next_activation(self) -> None:
        """Arm a one-shot Home Assistant timer for the next schedule row."""
        self._cancel_schedule_activation()

        if not self.data:
            return
        schedule = self.data.get("schedule") or []
        next_timestamp = self._next_schedule_timestamp(schedule)
        if next_timestamp is None:
            return

        self._cancel_schedule_timer = async_track_point_in_time(
            self.hass,
            self._async_activate_schedule_row,
            next_timestamp,
        )

    async def _async_activate_schedule_row(self, now: datetime) -> None:
        """Activate the planned row at its timestamp and notify sensor entities."""
        self._cancel_schedule_timer = None
        self._apply_active_schedule_row()
        self.async_update_listeners()
        self._schedule_next_activation()

    async def _async_update_data(self) -> dict:
        try:
            slab = await self._update_slab_state()
            horizon = int(self.opts[CONF_HORIZON_HOURS])
            days = max(1, (horizon + 23) // 24)

            points = await async_build_forecast(
                self.hass,
                self.opts[CONF_HEATING_ANALYTICS_ENTITY],
                self.opts[CONF_ISOLATE_SENSOR],
                self.opts[CONF_NORDPOOL_BUY_ENTITY],
                self.opts[CONF_NORDPOOL_FEED_IN_ENTITY],
                days,
            )
            points = points[: horizon * INTERVALS_PER_HOUR]

            levels = [
                int(value.strip())
                for value in str(self.opts[CONF_POWER_LEVELS]).split(",")
            ]
            model = COPModel(str(self.opts[CONF_COP_CORRECTION]))

            schedule = await self.hass.async_add_executor_job(
                lambda: optimize(
                    points,
                    model,
                    power_levels_w=levels,
                    slab_min_kwh=float(self.opts[CONF_SLAB_MIN]),
                    slab_max_kwh=float(self.opts[CONF_SLAB_MAX]),
                    initial_slab_kwh=slab.energy_kwh,
                    terminal_reserve_kwh=float(
                        self.opts[CONF_TERMINAL_RESERVE]
                    ),
                    state_step_kwh=float(self.opts[CONF_STATE_STEP]),
                    startup_cost_eur=float(self.opts[CONF_STARTUP_COST]),
                )
            )

            local_schedule = [
                {
                    **row,
                    "timestamp": dt_util.as_local(row["timestamp"]),
                }
                for row in schedule
            ]
            current = self._active_schedule_row(local_schedule)

            return {
                "target_power_w": current["target_electrical_power_w"],
                "current": current,
                "schedule": local_schedule,
                "total_cost_eur": round(
                    sum(row["interval_cost_eur"] for row in local_schedule),
                    4,
                ),
                "forecast_hours": round(
                    len(local_schedule) / INTERVALS_PER_HOUR,
                    2,
                ),
                "forecast_intervals": len(local_schedule),
                "slab_state": slab,
            }
        except Exception as err:
            raise UpdateFailed(str(err)) from err

    def async_set_updated_data(self, data: dict) -> None:
        """Publish a new optimized schedule and arm its activation timer."""
        super().async_set_updated_data(data)
        self._schedule_next_activation()

    async def async_shutdown(self) -> None:
        """Cancel schedule activation when the config entry unloads."""
        self._cancel_schedule_activation()
        await super().async_shutdown()
