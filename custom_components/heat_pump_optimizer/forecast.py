"""Read Heating Analytics and electricity prices from Home Assistant."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .heating_forecast_cache import HeatingAnalyticsForecastCache
from .optimizer import ForecastPoint

INTERVAL_MINUTES = 15
INTERVALS_PER_HOUR = 60 // INTERVAL_MINUTES
OPEN_METEO_SOLAR_PLATFORM = "open_meteo_solar_forecast"
OPEN_METEO_DAILY_ENERGY_SUFFIXES = (
    "_energy_production_today",
    "_energy_production_tomorrow",
    *(f"_energy_production_d{day}" for day in range(2, 8)),
)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = dt_util.parse_datetime(value)
        if result is None:
            raise ValueError(f"Cannot parse datetime: {value!r}")
    else:
        raise TypeError(f"Unsupported datetime type: {type(value).__name__}")
    if result.tzinfo is None:
        result = result.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return result


def _interval_key(value: Any) -> datetime:
    value_dt = _as_datetime(value).astimezone(timezone.utc)
    minute = value_dt.minute // INTERVAL_MINUTES * INTERVAL_MINUTES
    return value_dt.replace(minute=minute, second=0, microsecond=0)


def _hour_start(value: Any) -> datetime:
    return _as_datetime(value).astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def _extract_prices(state, label: str) -> dict[datetime, float]:
    attributes = state.attributes
    epex_rows = attributes.get("data")
    if epex_rows is not None:
        unit = attributes.get("unit_of_measurement")
        if unit != "€/kWh":
            raise HomeAssistantError(
                f"{label} EPEX price entity must use €/kWh; got {unit!r}"
            )
        rows = epex_rows or []
    else:
        rows = []
        for key in ("raw_today", "raw_tomorrow"):
            rows.extend(attributes.get(key) or [])

    result = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        start = row.get("start") or row.get("start_time")
        value = row.get("value")
        if value is None:
            value = row.get("price_per_kwh")
        if start is None or value is None:
            continue

        price = float(value)
        if not math.isfinite(price):
            raise HomeAssistantError(f"{label} price must be a finite number")

        start_dt = _as_datetime(start).astimezone(timezone.utc)
        end = row.get("end") or row.get("end_time")
        if end is None:
            interval_starts = [_interval_key(start_dt)]
        else:
            end_dt = _as_datetime(end).astimezone(timezone.utc)
            if (
                start_dt.second
                or start_dt.microsecond
                or start_dt.minute % INTERVAL_MINUTES
                or end_dt.second
                or end_dt.microsecond
                or end_dt.minute % INTERVAL_MINUTES
                or end_dt <= start_dt
            ):
                raise HomeAssistantError(
                    f"{label} price interval must have aligned, increasing "
                    "15-minute timestamps"
                )
            duration_seconds = (end_dt - start_dt).total_seconds()
            if duration_seconds % (INTERVAL_MINUTES * 60):
                raise HomeAssistantError(
                    f"{label} price interval duration must be a multiple of "
                    "15 minutes"
                )
            interval_count = int(duration_seconds // (INTERVAL_MINUTES * 60))
            interval_starts = [
                start_dt + timedelta(minutes=index * INTERVAL_MINUTES)
                for index in range(interval_count)
            ]

        for interval_start in interval_starts:
            result[interval_start] = price

    if not result:
        raise HomeAssistantError(
            f"{label} price entity must expose data with start_time, "
            "end_time, and price_per_kwh, or raw_today/raw_tomorrow with "
            "start and value fields"
        )
    return result


def _demand_from_row(row: dict) -> float | None:
    """Return the service's demand, which already reflects isolation."""
    demand = row.get("kwh")
    return float(demand) if demand is not None else None


def _open_meteo_daily_entity_ids(
    hass: HomeAssistant,
    selected_entity_ids: list[str],
) -> set[str]:
    """Resolve selected Open-Meteo sensors to all daily sensors on their device."""
    registry = er.async_get(hass)
    entity_ids = set(selected_entity_ids)
    for selected_entity_id in selected_entity_ids:
        selected = registry.async_get(selected_entity_id)
        if (
            selected is None
            or selected.platform != OPEN_METEO_SOLAR_PLATFORM
            or selected.device_id is None
        ):
            continue
        for sibling in er.async_entries_for_device(registry, selected.device_id):
            if (
                sibling.platform == OPEN_METEO_SOLAR_PLATFORM
                and sibling.unique_id.endswith(OPEN_METEO_DAILY_ENERGY_SUFFIXES)
            ):
                entity_ids.add(sibling.entity_id)
    return entity_ids


async def async_refresh_heating_forecast(
    hass: HomeAssistant,
    cache: HeatingAnalyticsForecastCache,
    heating_entity: str,
    isolate_sensor: str,
    days: int,
) -> list[dict]:
    """Retrieve HA once, merge into cache, and return merged hourly rows."""
    response = await hass.services.async_call(
        "heating_analytics",
        "get_forecast",
        {
            "entity_id": heating_entity,
            "days": days,
            "isolate_sensor": isolate_sensor,
            "human_readable": False,
        },
        blocking=True,
        return_response=True,
    )
    fresh_rows = []
    for row in response.get("forecast", []):
        demand = _demand_from_row(row)
        temp = row.get("temp")
        if demand is None or temp is None:
            continue
        fresh_rows.append(
            {
                "datetime": _hour_start(row["datetime"]),
                "kwh": demand,
                "temp": float(temp),
            }
        )
    await cache.async_merge(fresh_rows)
    return cache.rows()


def build_forecast_from_rows(
    hass: HomeAssistant,
    heat_rows: list[dict],
    buy_price_entity: str,
    feed_in_price_entity: str,
) -> list[ForecastPoint]:
    """Expand cached hourly HA rows to quarter-hour optimizer points."""
    buy_state = hass.states.get(buy_price_entity)
    if buy_state is None:
        raise HomeAssistantError(
            f"Buying-price entity not found: {buy_price_entity}"
        )
    feed_in_state = hass.states.get(feed_in_price_entity)
    if feed_in_state is None:
        raise HomeAssistantError(
            f"Feed-in-price entity not found: {feed_in_price_entity}"
        )
    buy_prices = _extract_prices(buy_state, "Buying")
    feed_in_prices = _extract_prices(feed_in_state, "Feed-in")

    # Only include the current or future 15-minute interval. This keeps a cached
    # current-hour row useful after Heating Analytics stops returning that hour.
    now = dt_util.utcnow()
    first_interval = now.replace(
        minute=now.minute // INTERVAL_MINUTES * INTERVAL_MINUTES,
        second=0,
        microsecond=0,
    )

    points = []
    for row in heat_rows:
        hourly_demand_kwh = float(row["kwh"])
        hour_start = _hour_start(row["datetime"])
        outdoor_c = float(row["temp"])
        for quarter in range(INTERVALS_PER_HOUR):
            key = hour_start + timedelta(minutes=quarter * INTERVAL_MINUTES)
            if key < first_interval:
                continue
            if key not in buy_prices or key not in feed_in_prices:
                continue
            interval_end = key + timedelta(minutes=INTERVAL_MINUTES)
            interval_start = max(now, key)
            duration_hours = (
                interval_end - interval_start
            ).total_seconds() / 3600.0
            if duration_hours <= 0:
                continue
            points.append(
                ForecastPoint(
                    timestamp=key,
                    duration_hours=duration_hours,
                    heat_demand_kwh=hourly_demand_kwh * duration_hours,
                    outdoor_c=outdoor_c,
                    buy_price=buy_prices[key],
                    sell_price=feed_in_prices[key],
                    pv_kwh=0.0,
                )
            )
    points.sort(key=lambda point: point.timestamp)
    if not points:
        raise HomeAssistantError(
            "No overlapping cached Heating Analytics, buying-price, and "
            "feed-in-price 15-minute intervals"
        )
    return points


async def async_apply_solar_forecasts(
    hass: HomeAssistant,
    points: list[ForecastPoint],
    config_entry_ids: list[str],
    baseload_w: float,
    open_meteo_entities: list[str] | None = None,
    horizon_hours: int | None = None,
) -> list[ForecastPoint]:
    """Apply solar forecasts after accounting for household electrical load."""
    open_meteo_entities = open_meteo_entities or []
    if not config_entry_ids and not open_meteo_entities:
        return points
    if not math.isfinite(baseload_w) or baseload_w < 0:
        raise HomeAssistantError(
            "Solar household baseload must be a finite, non-negative number"
        )

    start = points[0].timestamp.replace(minute=0, second=0, microsecond=0)
    end = points[-1].timestamp + timedelta(
        hours=points[-1].duration_hours
    )
    forecast_end = (
        min(
            end,
            points[0].timestamp + timedelta(hours=horizon_hours),
        )
        if horizon_hours is not None
        else end
    )
    solar_periods: dict[tuple[datetime, timedelta], float] = {}
    for config_entry_id in config_entry_ids:
        response = await hass.services.async_call(
            "forecast_solar",
            "get_forecast",
            {
                "config_entry": config_entry_id,
                "start": start.isoformat(),
                "end": forecast_end.isoformat(),
                "resolution": "hourly",
            },
            blocking=True,
            return_response=True,
        )
        if not isinstance(response, dict) or not isinstance(
            response.get("wh_period"), dict
        ):
            raise HomeAssistantError(
                "Forecast.Solar get_forecast response must contain a "
                "wh_period mapping"
            )
        for timestamp, value in response["wh_period"].items():
            period_start = _as_datetime(timestamp).astimezone(timezone.utc)
            energy_wh = float(value)
            if not math.isfinite(energy_wh) or energy_wh < 0:
                raise HomeAssistantError(
                    "Forecast.Solar period energy must be a finite, "
                    "non-negative number"
                )
            period_key = (period_start, timedelta(hours=1))
            solar_periods[period_key] = (
                solar_periods.get(period_key, 0.0) + energy_wh / 1000.0
            )

    selected_entity_ids = set(open_meteo_entities)
    entity_ids = _open_meteo_daily_entity_ids(
        hass,
        open_meteo_entities,
    )
    window_start = points[0].timestamp.astimezone(timezone.utc)
    window_end = forecast_end.astimezone(timezone.utc)
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None:
            if entity_id in selected_entity_ids:
                raise HomeAssistantError(
                    f"Open-Meteo Solar Forecast entity not found: {entity_id}"
                )
            continue
        wh_period_15m = state.attributes.get("wh_period_15m")
        wh_period = state.attributes.get("wh_period")
        if isinstance(wh_period_15m, Mapping) and wh_period_15m:
            period_data = wh_period_15m
            period_duration = timedelta(minutes=15)
        elif isinstance(wh_period, Mapping) and wh_period:
            period_data = wh_period
            period_duration = timedelta(hours=1)
        else:
            if entity_id in selected_entity_ids:
                raise HomeAssistantError(
                    f"Open-Meteo Solar Forecast entity {entity_id} must expose "
                    "wh_period_15m or wh_period forecast attributes"
                )
            continue
        for timestamp, value in period_data.items():
            period_start = _as_datetime(timestamp).astimezone(timezone.utc)
            period_end = period_start + period_duration
            if period_start >= window_end or period_end <= window_start:
                continue
            energy_wh = float(value)
            if not math.isfinite(energy_wh) or energy_wh < 0:
                raise HomeAssistantError(
                    f"Open-Meteo Solar Forecast energy for {entity_id} must "
                    "be a finite, non-negative number"
                )
            period_key = (period_start, period_duration)
            solar_periods[period_key] = (
                solar_periods.get(period_key, 0.0) + energy_wh / 1000.0
            )

    solar_points = []
    for point in points:
        interval_start = point.timestamp.astimezone(timezone.utc)
        interval_end = interval_start + timedelta(
            hours=point.duration_hours
        )
        solar_kwh = 0.0
        for (period_start, period_duration), period_energy_kwh in (
            solar_periods.items()
        ):
            overlap_start = max(interval_start, period_start)
            overlap_end = min(
                interval_end,
                period_start + period_duration,
            )
            if overlap_end > overlap_start:
                overlap_hours = (
                    overlap_end - overlap_start
                ).total_seconds() / 3600.0
                period_hours = period_duration.total_seconds() / 3600.0
                solar_kwh += period_energy_kwh * overlap_hours / period_hours
        solar_kwh -= baseload_w / 1000.0 * point.duration_hours
        solar_points.append(replace(point, pv_kwh=max(solar_kwh, 0.0)))
    return solar_points
