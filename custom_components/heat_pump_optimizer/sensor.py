from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities([TargetPowerSensor(c, entry), ScheduleSensor(c, entry), CostSensor(c, entry), SlabEnergySensor(c, entry), SlabTempSensor(c, entry), EquilibriumTempSensor(c, entry), TempReferenceEnergySensor(c, entry)])

class Base(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, c, e):
        super().__init__(c)
        self._entry = e

    @property
    def available(self):
        return super().available and self.coordinator.data is not None

class TargetPowerSensor(Base):
    _attr_name = 'Target electrical power'
    _attr_native_unit_of_measurement = 'W'
    _attr_device_class = SensorDeviceClass.POWER

    @property
    def unique_id(self):
        return f'{self._entry.entry_id}_target_power'

    @property
    def native_value(self):
        return self.coordinator.data['target_power_w']

    @property
    def extra_state_attributes(self):
        return self.coordinator.data['current']

class ScheduleSensor(Base):
    _attr_name = 'Schedule'

    @property
    def unique_id(self):
        return f'{self._entry.entry_id}_schedule'

    @property
    def native_value(self):
        return self.coordinator.data['forecast_hours']

    @property
    def extra_state_attributes(self):
        return {'schedule': self.coordinator.data['schedule'], 'forecast_intervals': self.coordinator.data['forecast_intervals']}

class CostSensor(Base):
    _attr_name = 'Forecast optimized cost'
    _attr_native_unit_of_measurement = 'EUR'

    @property
    def unique_id(self):
        return f'{self._entry.entry_id}_cost'

    @property
    def native_value(self):
        return self.coordinator.data['total_cost_eur']

class SlabBase(Base):
    _attr_native_unit_of_measurement = 'kWh'

    @property
    def s(self):
        return self.coordinator.data['slab_state']

class SlabEnergySensor(SlabBase):
    _attr_name = 'Estimated slab energy'

    @property
    def unique_id(self):
        return f'{self._entry.entry_id}_slab_energy'

    @property
    def native_value(self):
        return round(self.s.energy_kwh, 3)

    @property
    def extra_state_attributes(self):
        return {'heat_in_kwh': self.s.last_heat_input_kwh, 'heat_loss_kwh': self.s.last_heat_loss_kwh, 'temperature_correction_kwh': self.s.last_temperature_correction_kwh, 'elapsed_hours': self.s.last_elapsed_hours, 'temperature_correction_alpha': self.s.last_temperature_correction_alpha, 'last_update': self.s.last_update}

class SlabTempSensor(Base):
    _attr_name = 'Filtered slab temperature'
    _attr_native_unit_of_measurement = '°C'
    _attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def unique_id(self):
        return f'{self._entry.entry_id}_filtered_slab_temperature'

    @property
    def native_value(self):
        return round(self.coordinator.data['slab_state'].filtered_temperature_c, 2)

class EquilibriumTempSensor(SlabTempSensor):
    _attr_name = 'Slab equilibrium temperature'

    @property
    def unique_id(self):
        return f'{self._entry.entry_id}_slab_equilibrium_temperature'

    @property
    def native_value(self):
        return round(self.coordinator.data['slab_state'].equilibrium_temperature_c, 2)

class TempReferenceEnergySensor(SlabBase):
    _attr_name = 'Slab temperature reference energy'

    @property
    def unique_id(self):
        return f'{self._entry.entry_id}_slab_temperature_reference_energy'

    @property
    def native_value(self):
        return round(self.s.temperature_reference_energy_kwh, 3)
