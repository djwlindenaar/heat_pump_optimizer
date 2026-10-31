"""Read Heating Analytics and electricity prices from Home Assistant."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .heating_forecast_cache import HeatingAnalyticsForecastCache
from .optimizer import ForecastPoint

INTERVAL_MINUTES = 15
INTERVALS_PER_HOUR = 60 // INTERVAL_MINUTES


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


def _demand_from_row(row: dict, isolate_sensor: str) -> float | None:
    demand = row.get("kwh")
    unit = (row.get("unit_breakdown") or {}).get(isolate_sensor) or {}
    if unit.get("net_kwh") is not None:
        demand = unit["net_kwh"]
    return float(demand) if demand is not None else None


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
        demand = _demand_from_row(row, isolate_sensor)
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
