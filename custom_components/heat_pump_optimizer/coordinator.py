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
    async_refresh_heating_forecast,
    build_forecast_from_rows,
)
from .heating_forecast_cache import HeatingAnalyticsForecastCache
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
        self.heating_forecast_cache = HeatingAnalyticsForecastCache(hass)
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

    def _integrated_heat_loss_kwh(
        self,
        rows: list[dict],
        start: datetime,
        end: datetime,
    ) -> float:
        """Integrate cached hourly Heating Analytics demand over elapsed time."""
        if end <= start:
            return 0.0
        demand_by_hour = {row["datetime"]: float(row["kwh"]) for row in rows}
        total = 0.0
        cursor = start
        while cursor < end:
            hour_start = cursor.replace(minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)
            segment_end = min(end, hour_end)
            duration_hours = (segment_end - cursor).total_seconds() / 3600.0
            total += demand_by_hour.get(hour_start, 0.0) * duration_hours
            cursor = segment_end
        return total

    async def _update_slab_state(self, rows: list[dict]):
        if not self._loaded:
            await self.estimator.async_load()
            self._loaded = True
        if not rows:
            raise ValueError(
                "Heating Analytics cache contains no demand for slab estimator"
            )
        now = dt_util.utcnow()
        if self.estimator.state.last_update is None:
            elapsed_hours = 0.0
            heat_loss_kwh = 0.0
        else:
            previous_update = dt_util.parse_datetime(
                self.estimator.state.last_update
            )
            if previous_update is None:
                elapsed_hours = 0.0
                heat_loss_kwh = 0.0
            else:
                previous_update = previous_update.astimezone(now.tzinfo)
                elapsed_hours = max(
                    0.0, (now - previous_update).total_seconds() / 3600.0
                )
                heat_loss_kwh = self._integrated_heat_loss_kwh(
                    rows, previous_update, now
                )
        equilibrium_hours = int(self.opts[CONF_EQUILIBRIUM_HOURS])
        average_rows = rows[:equilibrium_hours]
        average_kw = sum(float(row["kwh"]) for row in average_rows) / max(
            1, len(average_rows)
        )
        return await self.estimator.async_update(
            heat_meter_kwh=self._sensor_float(CONF_HEAT_ENERGY_ENTITY),
            heat_loss_kwh=heat_loss_kwh,
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
            temp_correction_time_constant_hours=float(
                self.opts[CONF_TEMP_CORRECTION_TIME_CONSTANT_HOURS]
            ),
            elapsed_hours=elapsed_hours,
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
            horizon = int(self.opts[CONF_HORIZON_HOURS])
            days = max(1, (horizon + 23) // 24)
            heat_rows = await async_refresh_heating_forecast(
                self.hass,
                self.heating_forecast_cache,
                self.opts[CONF_HEATING_ANALYTICS_ENTITY],
                self.opts[CONF_ISOLATE_SENSOR],
                days,
            )
            slab = await self._update_slab_state(heat_rows)
            points = build_forecast_from_rows(
                self.hass,
                heat_rows,
                self.opts[CONF_NORDPOOL_BUY_ENTITY],
                self.opts[CONF_NORDPOOL_FEED_IN_ENTITY],
            )
            selected_points = []
            selected_hours = 0.0
            for point in points:
                if selected_hours >= horizon:
                    break
                selected_points.append(point)
                selected_hours += point.duration_hours
            points = selected_points

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
                    sum(row["duration_hours"] for row in local_schedule),
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
