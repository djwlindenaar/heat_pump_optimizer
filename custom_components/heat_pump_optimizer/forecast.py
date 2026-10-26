"""Read Heating Analytics and Nordpool forecasts from Home Assistant."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .optimizer import ForecastPoint


def _as_datetime(value: Any) -> datetime:
    """Return a timezone-aware datetime, preserving native datetime inputs."""
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


def _hour_key(value: Any) -> datetime:
    """Normalize a datetime-like value to an exact UTC hour."""
    return _as_datetime(value).astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def _extract_prices(state, label: str) -> dict[datetime, float]:
    rows = []
    for key in ("raw_today", "raw_tomorrow"):
        rows.extend(state.attributes.get(key) or [])

    result = {}
    for row in rows:
        start = row.get("start") or row.get("start_time")
        value = row.get("value")
        if start is not None and value is not None:
            result[_hour_key(start)] = float(value)

    if not result:
        raise HomeAssistantError(
            f"{label} price entity must expose raw_today/raw_tomorrow "
            "with start and value fields"
        )
    return result


async def async_build_forecast(
    hass: HomeAssistant,
    heating_entity: str,
    isolate_sensor: str,
    nordpool_buy_entity: str,
    nordpool_feed_in_entity: str,
    days: int,
) -> list[ForecastPoint]:
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
    heat_rows = response.get("forecast", [])

    buy_state = hass.states.get(nordpool_buy_entity)
    if buy_state is None:
        raise HomeAssistantError(
            f"Nordpool buying-price entity not found: {nordpool_buy_entity}"
        )
    feed_in_state = hass.states.get(nordpool_feed_in_entity)
    if feed_in_state is None:
        raise HomeAssistantError(
            f"Nordpool feed-in-price entity not found: {nordpool_feed_in_entity}"
        )

    buy_prices = _extract_prices(buy_state, "Buying")
    feed_in_prices = _extract_prices(feed_in_state, "Feed-in")

    points = []
    for row in heat_rows:
        key = _hour_key(row["datetime"])
        if key not in buy_prices or key not in feed_in_prices:
            continue

        demand = row.get("kwh")
        unit = (row.get("unit_breakdown") or {}).get(isolate_sensor) or {}
        if unit.get("net_kwh") is not None:
            demand = unit["net_kwh"]
        if demand is None:
            continue

        points.append(
            ForecastPoint(
                timestamp=key,
                heat_demand_kwh=float(demand),
                outdoor_c=float(row["temp"]),
                buy_price=buy_prices[key],
                sell_price=feed_in_prices[key],
                pv_kwh=0.0,
            )
        )

    if not points:
        raise HomeAssistantError(
            "No overlapping Heating Analytics, buying-price, and feed-in-price hours"
        )
    return points
