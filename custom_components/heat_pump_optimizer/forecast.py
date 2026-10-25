"""Read Heating Analytics and Nordpool forecasts from Home Assistant."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from .optimizer import ForecastPoint

import logging

_LOGGER = logging.getLogger(__name__)

def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def _hour_key(value: str) -> int:
    dt = (
        _dt(value)
        .astimezone()
        .replace(
            minute=0,
            second=0,
            microsecond=0,
        )
    )

    return int(dt.timestamp())

def _extract_prices(state) -> dict[str,float]:
    attrs=state.attributes
    rows=[]
    for key in ("raw_today","raw_tomorrow"):
        rows.extend(attrs.get(key) or [])
    result={}
    for row in rows:
        start=row.get("start") or row.get("start_time")
        value=row.get("value")
        if start is not None and value is not None:
            result[_hour_key(str(start))]=float(value)
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
