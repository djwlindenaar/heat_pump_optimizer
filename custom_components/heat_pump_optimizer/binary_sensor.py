from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OptimizerProblemSensor(entry.runtime_data, entry)])

class OptimizerProblemSensor(CoordinatorEntity, BinarySensorEntity):
    """On while the last optimization failed, even if a previous schedule is still served."""
    _attr_name = 'Optimizer problem'
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, c, e):
        super().__init__(c)
        self._attr_unique_id = f'{e.entry_id}_optimizer_problem'

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return not self.coordinator.last_update_success or bool((self.coordinator.data or {}).get('last_error'))

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        error = data.get('last_error')
        if not self.coordinator.last_update_success and self.coordinator.last_exception is not None:
            error = str(self.coordinator.last_exception)
        return {'last_error': error, 'last_success': data.get('last_success')}
