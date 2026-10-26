"""Read Heating Analytics and Nordpool forecasts from Home Assistant."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from .optimizer import ForecastPoint
import logging
_LOGGER = logging.getLogger(__name__)

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

def _extract_prices(state) -> dict[datetime,float]:
    attrs=state.attributes
    rows=[]
    for key in ("raw_today","raw_tomorrow"):
        rows.extend(attrs.get(key) or [])
    result={}
    for row in rows:
        start=row.get("start") or row.get("start_time")
        value=row.get("value")
        if start is not None and value is not None:
            result[_hour_key(start)]=float(value)
    # Some Nordpool versions expose a list under today/tomorrow without timestamps.
    if not result:
        for key in ("today","tomorrow"):
            values=attrs.get(key) or []
            # No safe timestamp reconstruction here; fail with a useful message.
            if values: raise HomeAssistantError("Nordpool entity must expose raw_today/raw_tomorrow with start and value fields")
    return result
async def async_build_forecast(hass: HomeAssistant, heating_entity: str, isolate_sensor: str,
                               nordpool_entity: str, days: int) -> list[ForecastPoint]:
    response=await hass.services.async_call(
        "heating_analytics","get_forecast",
        {"entity_id":heating_entity,"days":days,"isolate_sensor":isolate_sensor,"human_readable":False},
        blocking=True, return_response=True,
    )
    heat_rows = (
        response
        .get("forecast", [])
    )
    price_state=hass.states.get(nordpool_entity)
    if price_state is None: raise HomeAssistantError(f"Nordpool entity not found: {nordpool_entity}")
    prices=_extract_prices(price_state)
    points=[]
    for row in heat_rows:
        key=_hour_key(row["datetime"])
        if key not in prices: continue
        # isolate_sensor normally makes kwh the isolated requirement. Fall back to unit_breakdown.
        demand=row.get("kwh")
        unit=(row.get("unit_breakdown") or {}).get(isolate_sensor) or {}
        if unit.get("net_kwh") is not None: demand=unit["net_kwh"]
        if demand is None: continue
        price=prices[key]
        points.append(ForecastPoint(key,float(demand),float(row["temp"]),price,price,0.0))
    if not points:
        raise HomeAssistantError("No overlapping Heating Analytics and Nordpool forecast hours")
    return points
