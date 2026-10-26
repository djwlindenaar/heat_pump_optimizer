"""Heat Pump Cost Optimizer integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_NORDPOOL_BUY_ENTITY,
    CONF_NORDPOOL_ENTITY,
    CONF_NORDPOOL_FEED_IN_ENTITY,
    PLATFORMS,
)
from .coordinator import HeatPumpOptimizerCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Heat Pump Cost Optimizer from a config entry."""
    coordinator = HeatPumpOptimizerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when data or options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the current schema."""
    if entry.version > 2:
        return False

    if entry.version == 1:
        data = dict(entry.data)
        legacy_entity = data.pop(CONF_NORDPOOL_ENTITY, "")
        data.setdefault(CONF_NORDPOOL_BUY_ENTITY, legacy_entity)
        data.setdefault(CONF_NORDPOOL_FEED_IN_ENTITY, legacy_entity)
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            version=2,
            minor_version=0,
        )

    return True
