"""Read Heating Analytics and Nordpool forecasts from Home Assistant."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from .optimizer import ForecastPoint
INTERVAL_MINUTES = 15
INTERVALS_PER_HOUR = 60 // INTERVAL_MINUTES

def _as_datetime(value: Any) -> datetime:
    """Return a timezone-aware datetime, preserving native datetime inputs."""
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = dt_util.parse_datetime(value)
        if result is None:
            raise ValueError(f'Cannot parse datetime: {value!r}')
    else:
        raise TypeError(f'Unsupported datetime type: {type(value).__name__}')
    if result.tzinfo is None:
        result = result.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return result

def _interval_key(value: Any) -> datetime:
    """Normalize a datetime-like value to the start of its UTC 15-minute interval."""
    value_dt = _as_datetime(value).astimezone(timezone.utc)
    minute = value_dt.minute // INTERVAL_MINUTES * INTERVAL_MINUTES
    return value_dt.replace(minute=minute, second=0, microsecond=0)

def _hour_start(value: Any) -> datetime:
    """Normalize an hourly Heating Analytics timestamp to its UTC hour start."""
    return _as_datetime(value).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)

def _extract_prices(state, label: str) -> dict[datetime, float]:
    rows = []
    for key in ('raw_today', 'raw_tomorrow'):
        rows.extend(state.attributes.get(key) or [])
    result = {}
    for row in rows:
        start = row.get('start') or row.get('start_time')
        value = row.get('value')
        if start is not None and value is not None:
            result[_interval_key(start)] = float(value)
    if not result:
        raise HomeAssistantError(f'{label} price entity must expose raw_today/raw_tomorrow with start and value fields')
    return result

async def async_build_forecast(hass: HomeAssistant, heating_entity: str, isolate_sensor: str, nordpool_buy_entity: str, nordpool_feed_in_entity: str, days: int) -> list[ForecastPoint]:
    response = await hass.services.async_call('heating_analytics', 'get_forecast', {'entity_id': heating_entity, 'days': days, 'isolate_sensor': isolate_sensor, 'human_readable': False}, blocking=True, return_response=True)
    heat_rows = response.get('forecast', [])
    buy_state = hass.states.get(nordpool_buy_entity)
    if buy_state is None:
        raise HomeAssistantError(f'Nordpool buying-price entity not found: {nordpool_buy_entity}')
    feed_in_state = hass.states.get(nordpool_feed_in_entity)
    if feed_in_state is None:
        raise HomeAssistantError(f'Nordpool feed-in-price entity not found: {nordpool_feed_in_entity}')
    buy_prices = _extract_prices(buy_state, 'Buying')
    feed_in_prices = _extract_prices(feed_in_state, 'Feed-in')
    points = []
    for row in heat_rows:
        demand = row.get('kwh')
        unit = (row.get('unit_breakdown') or {}).get(isolate_sensor) or {}
        if unit.get('net_kwh') is not None:
            demand = unit['net_kwh']
        if demand is None:
            continue
        quarter_demand = float(demand) / INTERVALS_PER_HOUR
        hour_start = _hour_start(row['datetime'])
        outdoor_c = float(row['temp'])
        for quarter in range(INTERVALS_PER_HOUR):
            key = hour_start + timedelta(minutes=quarter * INTERVAL_MINUTES)
            if key not in buy_prices or key not in feed_in_prices:
                continue
            points.append(ForecastPoint(timestamp=key, heat_demand_kwh=quarter_demand, outdoor_c=outdoor_c, buy_price=buy_prices[key], sell_price=feed_in_prices[key], pv_kwh=0.0))
    points.sort(key=lambda point: point.timestamp)
    if not points:
        raise HomeAssistantError('No overlapping Heating Analytics, buying-price, and feed-in-price 15-minute intervals')
    return points

async def async_get_heating_demand(hass: HomeAssistant, heating_entity: str, isolate_sensor: str, days: int=1) -> list[tuple[datetime, float]]:
    """Return hourly Heating Analytics demand as UTC timestamp/kWh rows."""
    response = await hass.services.async_call('heating_analytics', 'get_forecast', {'entity_id': heating_entity, 'days': days, 'isolate_sensor': isolate_sensor, 'human_readable': False}, blocking=True, return_response=True)
    result = []
    for row in response.get('forecast', []):
        demand = row.get('kwh')
        unit = (row.get('unit_breakdown') or {}).get(isolate_sensor) or {}
        if unit.get('net_kwh') is not None:
            demand = unit['net_kwh']
        if demand is not None:
            result.append((_hour_start(row['datetime']), float(demand)))
    return result
