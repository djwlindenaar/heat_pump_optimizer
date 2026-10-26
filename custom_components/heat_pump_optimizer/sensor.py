from homeassistant.components.sensor import SensorEntity,SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
async def async_setup_entry(hass,entry,async_add_entities):
    c=entry.runtime_data
    async_add_entities([TargetPowerSensor(c,entry),ScheduleSensor(c,entry),CostSensor(c,entry)])
class Base(CoordinatorEntity,SensorEntity):
    _attr_has_entity_name=True
    def __init__(self,c,e): super().__init__(c); self._entry=e
class TargetPowerSensor(Base):
    _attr_name="Target electrical power"; _attr_native_unit_of_measurement="W"; _attr_device_class=SensorDeviceClass.POWER
    @property
    def unique_id(self): return f"{self._entry.entry_id}_target_power"
    @property
    def native_value(self): return self.coordinator.data["target_power_w"]
    @property
    def extra_state_attributes(self): return self.coordinator.data["current"]
class ScheduleSensor(Base):
    _attr_name="Schedule"
    @property
    def unique_id(self): return f"{self._entry.entry_id}_schedule"
    @property
    def native_value(self): return self.coordinator.data["forecast_hours"]
    @property
    def extra_state_attributes(self): return {"schedule":self.coordinator.data["schedule"]}
class CostSensor(Base):
    _attr_name="Forecast optimized cost"; _attr_native_unit_of_measurement="EUR"
    @property
    def unique_id(self): return f"{self._entry.entry_id}_cost"
    @property
    def native_value(self): return self.coordinator.data["total_cost_eur"]
