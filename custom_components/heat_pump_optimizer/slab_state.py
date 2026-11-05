"""Persistent slab thermal-state observer."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import logging
import math
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
STORAGE_VERSION = 1
STORAGE_KEY = 'heat_pump_optimizer.slab_state'
_LOGGER = logging.getLogger(__name__)

@dataclass
class SlabState:
    energy_kwh: float
    last_heat_meter_kwh: float | None = None
    last_update: str | None = None
    filtered_temperature_c: float | None = None
    equilibrium_temperature_c: float | None = None
    temperature_reference_energy_kwh: float | None = None
    last_heat_input_kwh: float = 0.0
    last_heat_loss_kwh: float = 0.0
    last_temperature_correction_kwh: float = 0.0
    last_elapsed_hours: float = 0.0
    last_temperature_correction_alpha: float = 0.0

class SlabStateEstimator:

    def __init__(self, hass: HomeAssistant, initial_kwh: float):
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.state = SlabState(energy_kwh=initial_kwh)

    async def async_load(self):
        data = await self._store.async_load()
        if data:
            self.state = SlabState(**data)

    async def async_save(self):
        await self._store.async_save(asdict(self.state))

    async def async_update(self, *, heat_meter_kwh: float, max_heat_input_kwh: float, heat_loss_kwh: float, slab_temperature_c: float, room_temperature_c: float, average_heat_loss_kw: float, slab_capacity_kwh_per_k: float, floor_transfer_kw_per_k: float, temp_filter_alpha: float, temp_correction_time_constant_hours: float, elapsed_hours: float) -> SlabState:
        s = self.state
        heat_in = 0.0
        if s.last_heat_meter_kwh is not None:
            delta = heat_meter_kwh - s.last_heat_meter_kwh
            if 0 <= delta <= max_heat_input_kwh:
                heat_in = delta
            else:
                # Meter reset or glitch: a drop to 0 followed by recovery would
                # otherwise count the whole meter reading as heat input.
                _LOGGER.warning('Ignoring implausible heat meter change of %.3f kWh (max %.3f kWh); re-baselining', delta, max_heat_input_kwh)
        filtered = slab_temperature_c if s.filtered_temperature_c is None else temp_filter_alpha * slab_temperature_c + (1 - temp_filter_alpha) * s.filtered_temperature_c
        equilibrium = room_temperature_c + average_heat_loss_kw / max(floor_transfer_kw_per_k, 0.001)
        temp_reference = slab_capacity_kwh_per_k * (filtered - equilibrium)
        integrated = s.energy_kwh + heat_in - heat_loss_kwh
        correction_alpha = 1.0 - math.exp(-max(elapsed_hours, 0.0) / max(temp_correction_time_constant_hours, 0.001))
        correction = correction_alpha * (temp_reference - integrated)
        # Not clipped to the slab limits: those constrain the plan, not the observed state.
        energy = integrated + correction
        self.state = SlabState(energy_kwh=energy, last_heat_meter_kwh=heat_meter_kwh, last_update=datetime.now(timezone.utc).isoformat(), filtered_temperature_c=filtered, equilibrium_temperature_c=equilibrium, temperature_reference_energy_kwh=temp_reference, last_heat_input_kwh=heat_in, last_heat_loss_kwh=heat_loss_kwh, last_temperature_correction_kwh=correction, last_elapsed_hours=elapsed_hours, last_temperature_correction_alpha=correction_alpha)
        await self.async_save()
        return self.state
