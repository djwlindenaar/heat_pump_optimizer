"""Heat Pump Cost Optimizer integration."""
from __future__ import annotations
import math
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import CONF_COP_CORRECTION, CONF_COP_TABLE, CONF_NORDPOOL_BUY_ENTITY, CONF_NORDPOOL_ENTITY, CONF_NORDPOOL_FEED_IN_ENTITY, CONF_TEMP_FILTER_ALPHA, CONF_TEMP_FILTER_TIME_CONSTANT_HOURS, CONF_UPDATE_MINUTES, DEFAULTS, PLATFORMS
from .coordinator import HeatPumpOptimizerCoordinator
from .cop_model import format_cop_table

# Datasheet COP curve of the former datasheet x power-correction model, kept only to migrate entries.
_LEGACY_DATASHEET_T = [-7.0, -4.0, -2.0, 2.0, 7.0, 10.0, 15.0, 20.0]
_LEGACY_DATASHEET_COP = [3.61, 3.9, 4.09, 4.73, 5.24, 5.83, 6.37, 6.91]
_LEGACY_CORRECTION = '500:1.00\n750:0.98\n1000:0.96\n1500:0.93\n2000:0.90\n2500:0.87\n3000:0.84\n3500:0.81\n4000:0.78'

def _legacy_cop_table(correction_text):
    """Table equal to datasheet(T) x correction(P): a product of two piecewise-linear
    curves is bilinear on the grid of their breakpoints, so interpolation reproduces it."""
    points = sorted((float(p), float(c)) for p, c in (item.split(':') for item in correction_text.replace(',', '\n').splitlines() if item.strip()))
    cops = [[cop * c for _, c in points] for cop in _LEGACY_DATASHEET_COP]
    return format_cop_table(_LEGACY_DATASHEET_T, [p for p, _ in points], cops, decimals=3)

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
    if entry.minor_version < 3:
        # 1.3: the datasheet curve x power correction became one temperature x power COP table.
        options = dict(entry.options)
        correction = options.pop(CONF_COP_CORRECTION, None)
        if CONF_COP_TABLE not in options:
            options[CONF_COP_TABLE] = _legacy_cop_table(str(correction) if correction else _LEGACY_CORRECTION)
        hass.config_entries.async_update_entry(entry, options=options, minor_version=3)
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
