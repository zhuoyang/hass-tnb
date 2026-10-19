"""Sensor platform for TNB Rates."""
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_IMPORT_SENSOR,
    CONF_EXPORT_SENSOR,
    TARIFF_STANDARD,
    TARIFF_TOU,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the TNB Rates sensor."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Check tariff type
    tariff_type = config_entry.data.get("tariff_type", TARIFF_STANDARD)
    
    entities = [
        TNBRatesBillSensor(hass, coordinator, config_entry),
        TNBRatesImportCostSensor(hass, coordinator, config_entry),
        TNBRatesExportCreditSensor(hass, coordinator, config_entry),
        TNBRatesExcessExportSensor(hass, coordinator, config_entry),
        TNBRatesTotalEnergySensor(hass, coordinator, config_entry),
        TNBRatesExportEnergySensor(hass, coordinator, config_entry),
        TNBRatesNEMBalanceSensor(hass, coordinator, config_entry),
    ]
    
    # Add ToU specific sensors
    if tariff_type == TARIFF_TOU:
        entities.extend([
            TNBRatesPeakEnergySensor(hass, coordinator, config_entry),
            TNBRatesOffpeakEnergySensor(hass, coordinator, config_entry),
        ])
    
    async_add_entities(entities)


class TNBRatesBaseSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Base class for TNB Rates Sensors."""

    _attr_has_entity_name = True
    # Value starts again from zero each billing cycle (exposed via last_reset)
    _resets_each_cycle = True

    def __init__(self, hass, coordinator, config_entry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.hass = hass
        self.config_entry = config_entry
        
        self._import_sensor = config_entry.data[CONF_IMPORT_SENSOR]
        self._export_sensor = config_entry.data.get(CONF_EXPORT_SENSOR)

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
        
        # NOTE: State change listeners are now registered once in the coordinator,
        # not per-sensor. This prevents duplicate event processing that was causing
        # 6-8x overcounting of energy usage.
        # The coordinator.setup_listeners() is called from __init__.py

    @property
    def last_reset(self):
        """Return the start of the current billing cycle for long-term statistics."""
        if not self._resets_each_cycle or not self.coordinator.energy_tracker:
            return None
        return self.coordinator.energy_tracker.get_state()["last_reset"]

    def _get_components(self):
        """Get calculated cost components from coordinator."""
        return self.coordinator.get_components()


class TNBRatesBillSensor(TNBRatesBaseSensor):
    """Sensor for the Net Bill Amount."""
    
    _attr_name = "Bill"
    _attr_native_unit_of_measurement = "RM"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self):
        """Return the net bill value."""
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        components = self._get_components()
        return float(round(components.get("net_bill", 0.0), 2))

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {}
        components = self._get_components()
        
        attrs.update({
            "energy_cost": float(round(components.get("energy_cost", 0.0), 2)),
            "capacity_charge": float(round(components.get("capacity_charge", 0.0), 2)),
            "network_charge": float(round(components.get("network_charge", 0.0), 2)),
            "retail_charge": float(round(components.get("retail_charge", 0.0), 2)),
            "afa_cost": float(round(components.get("afa_cost", 0.0), 2)),
            "eei_rebate": float(round(components.get("eei_rebate", 0.0), 2)),
            "kwtbb_tax": float(round(components.get("kwtbb_tax", 0.0), 2)),
            "service_tax": float(round(components.get("service_tax", 0.0), 2)),
            "total_import_cost": float(round(components.get("import_cost", 0.0), 2)),
            "total_export_credit": float(round(components.get("export_credit", 0.0), 2)),
        })
        
        return attrs


class TNBRatesImportCostSensor(TNBRatesBaseSensor):
    """Sensor for the Gross Import Cost."""
    
    _attr_name = "Import Cost"
    _attr_native_unit_of_measurement = "RM"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self):
        """Return the gross import cost."""
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        components = self._get_components()
        return float(round(components.get("import_cost", 0.0), 2))


class TNBRatesExportCreditSensor(TNBRatesBaseSensor):
    """Sensor for the Export Credit Value."""
    
    _attr_name = "Export Credit"
    _attr_native_unit_of_measurement = "RM"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self):
        """Return the export credit value."""
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        components = self._get_components()
        return float(round(components.get("export_credit", 0.0), 2))


class TNBRatesExcessExportSensor(TNBRatesBaseSensor):
    """Sensor for Excess Export Energy."""
    
    _attr_name = "Excess Export"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    # No energy device class: it only allows total/total_increasing state classes
    _attr_state_class = SensorStateClass.MEASUREMENT  # Point-in-time measurement, not cumulative
    _resets_each_cycle = False

    @property
    def native_value(self):
        """Return the excess export energy."""
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        components = self._get_components()
        return float(round(components.get("excess_export_kwh", 0.0), 2))


class TNBRatesEnergySensor(TNBRatesBaseSensor):
    """Base class for Energy Sensors."""
    
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Restore state
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                val = float(last_state.state)
                self._restore_to_tracker(val)
            except (ValueError, TypeError):
                pass

            # Restore shared tracker state (only from Total Energy sensor to avoid duplicates)
            if isinstance(self, TNBRatesTotalEnergySensor) and last_state.attributes:
                self._restore_tracker_attributes(last_state.attributes)
        
        # The tracker is marked restored by __init__.py once all sensors are added

    def _restore_tracker_attributes(self, attributes):
        """Restore last_reset and meter baselines saved as state attributes."""
        tracker = self.coordinator.energy_tracker
        if not tracker:
            return
        
        last_reset_iso = attributes.get("last_reset_iso")
        if last_reset_iso:
            try:
                from datetime import datetime
                last_reset = datetime.fromisoformat(last_reset_iso)
                tracker.set_last_reset(last_reset)
                _LOGGER.info("Restored last_reset: %s", last_reset)
            except (ValueError, TypeError) as err:
                _LOGGER.warning("Failed to restore last_reset: %s", err)
        
        try:
            tracker.set_last_readings(
                attributes.get("last_import_reading"),
                attributes.get("last_export_reading"),
            )
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Failed to restore last meter readings: %s", err)

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        attrs = {}
        if self.coordinator.energy_tracker:
            state = self.coordinator.energy_tracker.get_state()
            # Add last_reset_iso for persistence
            if state.get("last_reset_iso"):
                attrs["last_reset_iso"] = state["last_reset_iso"]
        return attrs

    def _restore_to_tracker(self, value):
        """Restore value to tracker. To be implemented by subclasses."""
        pass


class TNBRatesPeakEnergySensor(TNBRatesEnergySensor):
    """Sensor for Peak Energy."""
    _attr_name = "Peak Energy"

    @property
    def native_value(self):
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        return self.coordinator.energy_tracker.get_state()["peak_kwh"]

    def _restore_to_tracker(self, value):
        if self.coordinator.energy_tracker:
            self.coordinator.energy_tracker.set_peak_kwh(value)


class TNBRatesOffpeakEnergySensor(TNBRatesEnergySensor):
    """Sensor for Off-peak Energy."""
    _attr_name = "Offpeak Energy"

    @property
    def native_value(self):
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        return self.coordinator.energy_tracker.get_state()["offpeak_kwh"]

    def _restore_to_tracker(self, value):
        if self.coordinator.energy_tracker:
            self.coordinator.energy_tracker.set_offpeak_kwh(value)


class TNBRatesTotalEnergySensor(TNBRatesEnergySensor):
    """Sensor for Total Energy."""
    _attr_name = "Total Energy"

    @property
    def native_value(self):
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        return self.coordinator.energy_tracker.get_state()["total_kwh"]

    @property
    def extra_state_attributes(self):
        """Return extra state attributes, including meter baselines for persistence."""
        attrs = super().extra_state_attributes or {}
        if self.coordinator.energy_tracker:
            state = self.coordinator.energy_tracker.get_state()
            for key in ("last_import_reading", "last_export_reading"):
                if state.get(key) is not None:
                    attrs[key] = state[key]
        return attrs

    def _restore_to_tracker(self, value):
        if self.coordinator.energy_tracker:
            self.coordinator.energy_tracker.set_total_kwh(value)


class TNBRatesExportEnergySensor(TNBRatesEnergySensor):
    """Sensor for Export Energy."""
    _attr_name = "Export Energy"

    @property
    def native_value(self):
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        return self.coordinator.energy_tracker.get_state()["export_kwh"]

    def _restore_to_tracker(self, value):
        if self.coordinator.energy_tracker:
            self.coordinator.energy_tracker.set_export_kwh(value)


class TNBRatesNEMBalanceSensor(TNBRatesEnergySensor):
    """Sensor for NEM Balance."""
    _attr_name = "NEM Balance"
    _resets_each_cycle = False  # Carries over between billing cycles

    @property
    def native_value(self):
        if not self.coordinator.energy_tracker:
            return None
        if not self.coordinator.energy_tracker.is_restored():
            return None
        return self.coordinator.energy_tracker.get_nem_balance_kwh()

    def _restore_to_tracker(self, value):
        if self.coordinator.energy_tracker:
            self.coordinator.energy_tracker.set_nem_balance_kwh(value)
