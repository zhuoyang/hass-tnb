
import pytest
import sys
from unittest.mock import MagicMock, AsyncMock

# Mock homeassistant modules
ha_mock = MagicMock()
sys.modules["homeassistant"] = ha_mock
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.sensor"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.event"] = MagicMock()
sys.modules["homeassistant.helpers.restore_state"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.util"] = MagicMock()

# Define mock base classes
class MockCoordinatorEntity:
    def __init__(self, coordinator): self.coordinator = coordinator
    async def async_added_to_hass(self): pass
    def async_write_ha_state(self): pass
    def async_on_remove(self, func): pass

class MockRestoreEntity:
    async def async_get_last_state(self): return None

class MockSensorEntity:
    _attr_has_entity_name = True
    _attr_name = "Test Sensor"
    entity_id = "sensor.test"

sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = MockCoordinatorEntity
sys.modules["homeassistant.helpers.restore_state"].RestoreEntity = MockRestoreEntity
sys.modules["homeassistant.components.sensor"].SensorEntity = MockSensorEntity

# Import components
from custom_components.tnb_rates.sensor import (
    TNBRatesPeakEnergySensor,
    TNBRatesOffpeakEnergySensor,
    TNBRatesTotalEnergySensor,
    TNBRatesExportEnergySensor
)
from custom_components.tnb_rates.coordinator import TNBEnergyTracker
from decimal import Decimal

@pytest.mark.asyncio
async def test_sensor_restoration():
    """Verify that sensors restore their state to the coordinator."""
    
    # Mock Coordinator
    hass = MagicMock()
    coordinator = MagicMock()
    coordinator.energy_tracker = TNBEnergyTracker(hass, 1, "tou")
    
    # Mock Config Entry
    config_entry = MagicMock()
    config_entry.data = {"import_sensor": "sensor.import"}
    config_entry.entry_id = "test_entry"
    
    # Test Peak Sensor Restoration
    peak_sensor = TNBRatesPeakEnergySensor(hass, coordinator, config_entry)
    last_state = MagicMock()
    last_state.state = "123.45"
    peak_sensor.async_get_last_state = AsyncMock(return_value=last_state)
    
    await peak_sensor.async_added_to_hass()
    
    assert coordinator.energy_tracker._peak_kwh == Decimal("123.45")
    print("Peak Sensor Restored Correctly")
    
    # Test Offpeak Sensor Restoration
    offpeak_sensor = TNBRatesOffpeakEnergySensor(hass, coordinator, config_entry)
    last_state.state = "678.90"
    offpeak_sensor.async_get_last_state = AsyncMock(return_value=last_state)
    
    await offpeak_sensor.async_added_to_hass()
    
    assert coordinator.energy_tracker._offpeak_kwh == Decimal("678.90")
    print("Offpeak Sensor Restored Correctly")

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test_sensor_restoration())
    print("All tests passed!")
