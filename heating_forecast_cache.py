"""Persistent cache for hourly Heating Analytics forecast rows."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

STORAGE_VERSION = 1
STORAGE_KEY = "heat_pump_optimizer.heating_analytics_forecast"


def _as_utc_hour(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = dt_util.parse_datetime(str(value))
        if result is None:
            raise ValueError(f"Cannot parse datetime: {value!r}")
    if result.tzinfo is None:
        result = result.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return result.astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


class HeatingAnalyticsForecastCache:
    """Merge fresh HA forecasts into a persistent hourly cache."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._rows: dict[datetime, dict[str, float]] = {}
        self._loaded = False

    async def async_load(self) -> None:
        if self._loaded:
            return
        data = await self._store.async_load() or {}
        rows = data.get("rows", {})
        for timestamp, row in rows.items():
            parsed = dt_util.parse_datetime(timestamp)
            if parsed is not None:
                self._rows[_as_utc_hour(parsed)] = {
                    "kwh": float(row["kwh"]),
                    "temp": float(row["temp"]),
                }
        self._loaded = True

    async def async_merge(self, rows: list[dict]) -> None:
        await self.async_load()
        current_hour = dt_util.utcnow().replace(
            minute=0,
            second=0,
            microsecond=0,
        )

        # Retain the cached current hour, but discard older hours.
        self._rows = {
            timestamp: row
            for timestamp, row in self._rows.items()
            if timestamp >= current_hour
        }

        # Fresh Heating Analytics data wins for every hour it returns.
        for row in rows:
            timestamp = _as_utc_hour(row["datetime"])
            if timestamp < current_hour:
                continue
            self._rows[timestamp] = {
                "kwh": float(row["kwh"]),
                "temp": float(row["temp"]),
            }

        await self._store.async_save(
            {
                "rows": {
                    timestamp.isoformat(): row
                    for timestamp, row in self._rows.items()
                }
            }
        )

    def rows(self) -> list[dict]:
        return [
            {
                "datetime": timestamp,
                "kwh": row["kwh"],
                "temp": row["temp"],
            }
            for timestamp, row in sorted(self._rows.items())
        ]
