"""Heat Pump Cost Optimizer integration."""
from __future__ import annotations
import math
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import CONF_NORDPOOL_BUY_ENTITY, CONF_NORDPOOL_ENTITY, CONF_NORDPOOL_FEED_IN_ENTITY, CONF_TEMP_FILTER_ALPHA, CONF_TEMP_FILTER_TIME_CONSTANT_HOURS, CONF_UPDATE_MINUTES, DEFAULTS, PLATFORMS
from .coordinator import HeatPumpOptimizerCoordinator

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version > 1:
        return False
    if entry.minor_version < 2:
        # 1.2: the per-refresh temperature filter alpha became a time constant.
        # Convert it so that the filter behaves the same at the configured refresh rate.
        options = dict(entry.options)
        alpha = options.pop(CONF_TEMP_FILTER_ALPHA, None)
        if alpha is not None and CONF_TEMP_FILTER_TIME_CONSTANT_HOURS not in options:
            update_hours = float(options.get(CONF_UPDATE_MINUTES, DEFAULTS[CONF_UPDATE_MINUTES])) / 60.0
            alpha = float(alpha)
            if alpha >= 1:
                time_constant = 0.01
            elif alpha <= 0:
                time_constant = 720.0
            else:
                time_constant = min(720.0, max(0.01, update_hours / -math.log(1.0 - alpha)))
            options[CONF_TEMP_FILTER_TIME_CONSTANT_HOURS] = round(time_constant, 2)
        hass.config_entries.async_update_entry(entry, options=options, minor_version=2)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = HeatPumpOptimizerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True

async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
