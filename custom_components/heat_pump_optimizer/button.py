from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
async def async_setup_entry(hass,entry,async_add_entities): async_add_entities([RunButton(entry.runtime_data,entry)])
class RunButton(CoordinatorEntity,ButtonEntity):
    _attr_name="Run optimizer now"; _attr_has_entity_name=True
    def __init__(self,c,e): super().__init__(c); self._attr_unique_id=f"{e.entry_id}_run"
    async def async_press(self): await self.coordinator.async_request_refresh()
