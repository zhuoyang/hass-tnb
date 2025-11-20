"""Sensor platform for TNB Rates."""
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfEnergy,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_IMPORT_SENSOR,
    CONF_EXPORT_SENSOR,
    SERVICE_SET_ENERGY_VALUES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the TNB Rates sensor."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities([
        TNBRatesBillSensor(hass, coordinator, config_entry),
        TNBRatesImportCostSensor(hass, coordinator, config_entry),
        TNBRatesExportCreditSensor(hass, coordinator, config_entry),
        TNBRatesExcessExportSensor(hass, coordinator, config_entry),
    ])

    async def handle_set_energy_values(call):
        """Handle the set_energy_values service call."""
        peak_kwh = call.data.get("peak_kwh")
        offpeak_kwh = call.data.get("offpeak_kwh")
        export_kwh = call.data.get("export_kwh")
        
        # Get coordinator for all config entries and update
        for entry_id, coordinator_instance in hass.data[DOMAIN].items():
            if hasattr(coordinator_instance, 'energy_tracker') and coordinator_instance.energy_tracker:
                coordinator_instance.energy_tracker.set_values(peak_kwh, offpeak_kwh, export_kwh)
                coordinator_instance.async_update_listeners()
                _LOGGER.info("Energy values updated for entry %s", entry_id)
    
    # Register service (only once per domain)
    if not hass.services.has_service(DOMAIN, SERVICE_SET_ENERGY_VALUES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_ENERGY_VALUES,
            handle_set_energy_values,
        )


class TNBRatesBaseSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Base class for TNB Rates Sensors."""

    _attr_has_entity_name = True

    def __init__(self, hass, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        
        self._import_sensor = config_entry.data[CONF_IMPORT_SENSOR]
        self._export_sensor = config_entry.data.get(CONF_EXPORT_SENSOR)
        
        # Energy tracking is now handled by coordinator.energy_tracker
        self._state_restored = False

    @property
    def unique_id(self):
        """Return unique ID for this sensor."""
        return f"{self.config_entry.entry_id}_{self._attr_name.lower().replace(' ', '_')}"

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.config_entry.entry_id)},
            "name": "TNB Rates",
            "manufacturer": "TNB",
            "model": "Energy Cost Tracker",
        }

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Restore state to coordinator's energy tracker (only once from first sensor)
        if not self._state_restored and self.coordinator.energy_tracker:
            if (last_state := await self.async_get_last_state()) is not None:
                peak_kwh = float(last_state.attributes.get("current_month_peak_kwh", 0))
                offpeak_kwh = float(last_state.attributes.get("current_month_offpeak_kwh", 0))
                export_kwh = float(last_state.attributes.get("current_month_export_kwh", 0))
                last_reset = None
                if last_reset_str := last_state.attributes.get("last_reset"):
                    last_reset = dt_util.parse_datetime(last_reset_str)
                
                if last_reset:
                    self.coordinator.energy_tracker.restore_state(
                        peak_kwh, offpeak_kwh, export_kwh, last_reset
                    )
                    self._state_restored = True
                    _LOGGER.info("State restored from %s", self.entity_id)

        # Listen to source sensors (coordinator handles the logic)
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._import_sensor], self._handle_import_change
            )
        )
        
        if self._export_sensor:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._export_sensor], self._handle_export_change
                )
            )

    @callback
    def _handle_import_change(self, event):
        """Handle changes in the import sensor - delegate to coordinator."""
        if not self.coordinator.energy_tracker:
            return
            
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        
        if self.coordinator.energy_tracker.handle_import_change(
            new_state, old_state, self.coordinator.data
        ):
            # State changed, update all sensors
            self.async_write_ha_state()

    @callback
    def _handle_export_change(self, event):
        """Handle changes in the export sensor - delegate to coordinator."""
        if not self.coordinator.energy_tracker:
            return
            
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        
        if self.coordinator.energy_tracker.handle_export_change(new_state, old_state):
            # State changed, update all sensors
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.energy_tracker:
            return {}
            
        state = self.coordinator.energy_tracker.get_state()
        return {
            "current_month_peak_kwh": round(state["peak_kwh"], 2),
            "current_month_offpeak_kwh": round(state["offpeak_kwh"], 2),
            "current_month_export_kwh": round(state["export_kwh"], 2),
            "last_reset": state["last_reset"].isoformat() if state["last_reset"] else None,
        }

    def _get_components(self):
        """Get calculated cost components from coordinator."""
        if not self.coordinator.energy_tracker:
            return {
                "import_cost": 0.0,
                "export_credit": 0.0,
                "excess_export_kwh": 0.0,
                "net_bill": 0.0
            }
        return self.coordinator.energy_tracker.calculate_components(self.coordinator.data)


class TNBRatesBillSensor(TNBRatesBaseSensor):
    """Sensor for the Net Bill Amount."""
    
    _attr_name = "Bill"
    _attr_native_unit_of_measurement = "RM"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self):
        """Return the net bill value."""
        components = self._get_components()
        return round(components.get("net_bill", 0.0), 2)


class TNBRatesImportCostSensor(TNBRatesBaseSensor):
    """Sensor for the Gross Import Cost."""
    
    _attr_name = "Import Cost"
    _attr_native_unit_of_measurement = "RM"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self):
        """Return the gross import cost."""
        components = self._get_components()
        return round(components.get("import_cost", 0.0), 2)


class TNBRatesExportCreditSensor(TNBRatesBaseSensor):
    """Sensor for the Export Credit Value."""
    
    _attr_name = "Export Credit"
    _attr_native_unit_of_measurement = "RM"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self):
        """Return the export credit value."""
        components = self._get_components()
        return round(components.get("export_credit", 0.0), 2)


class TNBRatesExcessExportSensor(TNBRatesBaseSensor):
    """Sensor for Excess Export Energy."""
    
    _attr_name = "Excess Export"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT  # Point-in-time measurement, not cumulative

    @property
    def native_value(self):
        """Return the excess export energy."""
        components = self._get_components()
        return round(components.get("excess_export_kwh", 0.0), 2)
