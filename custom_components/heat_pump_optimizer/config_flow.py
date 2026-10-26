from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import *


def _entity_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    )


def _connection_schema(current: dict[str, Any] | None = None) -> vol.Schema:
    current = current or {}
    legacy_nordpool = current.get(CONF_NORDPOOL_ENTITY, "")
    return vol.Schema(
        {
            vol.Required(
                CONF_HEATING_ANALYTICS_ENTITY,
                default=current.get(
                    CONF_HEATING_ANALYTICS_ENTITY,
                    "sensor.heating_analytics_week_ahead_forecast",
                ),
            ): _entity_selector(),
            vol.Required(
                CONF_ISOLATE_SENSOR,
                default=current.get(
                    CONF_ISOLATE_SENSOR,
                    "sensor.heating_water_energy",
                ),
            ): _entity_selector(),
            vol.Required(
                CONF_NORDPOOL_BUY_ENTITY,
                default=current.get(CONF_NORDPOOL_BUY_ENTITY, legacy_nordpool),
            ): _entity_selector(),
            vol.Required(
                CONF_NORDPOOL_FEED_IN_ENTITY,
                default=current.get(
                    CONF_NORDPOOL_FEED_IN_ENTITY,
                    current.get(CONF_NORDPOOL_BUY_ENTITY, legacy_nordpool),
                ),
            ): _entity_selector(),
        }
    )


def _options_schema(current: dict[str, Any] | None = None) -> vol.Schema:
    current = {**DEFAULTS, **(current or {})}
    return vol.Schema(
        {
            vol.Required(
                CONF_HORIZON_HOURS,
                default=current[CONF_HORIZON_HOURS],
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
            vol.Required(
                CONF_UPDATE_MINUTES,
                default=current[CONF_UPDATE_MINUTES],
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
            vol.Required(
                CONF_SLAB_MIN,
                default=current[CONF_SLAB_MIN],
            ): vol.Coerce(float),
            vol.Required(
                CONF_SLAB_MAX,
                default=current[CONF_SLAB_MAX],
            ): vol.Coerce(float),
            vol.Required(
                CONF_INITIAL_SLAB,
                default=current[CONF_INITIAL_SLAB],
            ): vol.Coerce(float),
            vol.Required(
                CONF_TERMINAL_RESERVE,
                default=current[CONF_TERMINAL_RESERVE],
            ): vol.Coerce(float),
            vol.Required(
                CONF_POWER_LEVELS,
                default=current[CONF_POWER_LEVELS],
            ): str,
            vol.Required(
                CONF_STARTUP_COST,
                default=current[CONF_STARTUP_COST],
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Required(
                CONF_STATE_STEP,
                default=current[CONF_STATE_STEP],
            ): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
            vol.Required(
                CONF_COP_CORRECTION,
                default=current[CONF_COP_CORRECTION],
            ): str,
        }
    )


def _validate_options(values: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    slab_min = values[CONF_SLAB_MIN]
    slab_max = values[CONF_SLAB_MAX]
    initial = values[CONF_INITIAL_SLAB]
    reserve = values[CONF_TERMINAL_RESERVE]

    if slab_min >= slab_max:
        errors[CONF_SLAB_MAX] = "slab_max_not_above_min"
    if not slab_min <= initial <= slab_max:
        errors[CONF_INITIAL_SLAB] = "initial_slab_out_of_range"
    if not slab_min <= reserve <= slab_max:
        errors[CONF_TERMINAL_RESERVE] = "terminal_reserve_out_of_range"

    try:
        levels = [int(value.strip()) for value in values[CONF_POWER_LEVELS].split(",")]
        if not levels or any(value < 0 for value in levels):
            raise ValueError
    except ValueError:
        errors[CONF_POWER_LEVELS] = "invalid_power_levels"

    try:
        points = []
        for item in values[CONF_COP_CORRECTION].split(","):
            power, factor = item.strip().split(":")
            points.append((float(power), float(factor)))
        if len(points) < 2 or any(power <= 0 or factor <= 0 for power, factor in points):
            raise ValueError
    except (TypeError, ValueError):
        errors[CONF_COP_CORRECTION] = "invalid_cop_curve"

    return errors


class HeatPumpOptimizerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        if user_input is not None:
            await self.async_set_unique_id("primary")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Heat Pump Cost Optimizer",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(),
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                entry,
                data=user_input,
            )
            return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(dict(entry.data)),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return HeatPumpOptimizerOptionsFlow(config_entry)




class HeatPumpOptimizerOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_options(user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)

        current = {
            **DEFAULTS,
            **self._config_entry.data,
            **self._config_entry.options,
        }
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(user_input or current),
            errors=errors,
        )
