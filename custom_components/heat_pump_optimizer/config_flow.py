from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import *


class HeatPumpOptimizerConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:

        if user_input is not None:
            await self.async_set_unique_id(
                "primary"
            )

            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="Heat Pump Cost Optimizer",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(),
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

            await self.hass.config_entries.async_reload(
                entry.entry_id
            )

            return self.async_abort(
                reason="reconfigure_successful"
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(
                entry.data
            ),
        )

    def _schema(
        self,
        current=None,
    ):

        current = current or {}

        return vol.Schema(
            {
                vol.Required(
                    CONF_HEATING_ANALYTICS_ENTITY,
                    default=current.get(
                        CONF_HEATING_ANALYTICS_ENTITY,
                        "sensor.heating_analytics_week_ahead_forecast",
                    ),
                ): str,

                vol.Required(
                    CONF_ISOLATE_SENSOR,
                    default=current.get(
                        CONF_ISOLATE_SENSOR,
                        "sensor.heating_water_energy",
                    ),
                ): str,

                vol.Required(
                    CONF_NORDPOOL_ENTITY,
                    default=current.get(
                        CONF_NORDPOOL_ENTITY,
                        "",
                    ),
                ): str,

                vol.Optional(
                    CONF_HORIZON_HOURS,
                    default=current.get(
                        CONF_HORIZON_HOURS,
                        DEFAULTS[CONF_HORIZON_HOURS],
                    ),
                ): vol.Coerce(int),

                vol.Optional(
                    CONF_SLAB_MIN,
                    default=current.get(
                        CONF_SLAB_MIN,
                        DEFAULTS[CONF_SLAB_MIN],
                    ),
                ): vol.Coerce(float),

                vol.Optional(
                    CONF_SLAB_MAX,
                    default=current.get(
                        CONF_SLAB_MAX,
                        DEFAULTS[CONF_SLAB_MAX],
                    ),
                ): vol.Coerce(float),

                vol.Optional(
                    CONF_INITIAL_SLAB,
                    default=current.get(
                        CONF_INITIAL_SLAB,
                        DEFAULTS[CONF_INITIAL_SLAB],
                    ),
                ): vol.Coerce(float),

                vol.Optional(
                    CONF_TERMINAL_RESERVE,
                    default=current.get(
                        CONF_TERMINAL_RESERVE,
                        DEFAULTS[CONF_TERMINAL_RESERVE],
                    ),
                ): vol.Coerce(float),

                vol.Optional(
                    CONF_POWER_LEVELS,
                    default=current.get(
                        CONF_POWER_LEVELS,
                        DEFAULTS[CONF_POWER_LEVELS],
                    ),
                ): str,

                vol.Optional(
                    CONF_COP_CORRECTION,
                    default=current.get(
                        CONF_COP_CORRECTION,
                        DEFAULTS[CONF_COP_CORRECTION],
                    ),
                ): str,
            }
        )
