"""The TNB Rates integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_REMOTE_URL,
    CONF_BILLING_DAY,
    CONF_TARIFF_TYPE,
    CONF_IMPORT_SENSOR,
    CONF_EXPORT_SENSOR,
)
from .coordinator import TNBRatesCoordinator, TNBEnergyTracker

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TNB Rates from a config entry."""
    
    remote_url = entry.options.get(CONF_REMOTE_URL, entry.data.get(CONF_REMOTE_URL))
    billing_day = entry.options.get(CONF_BILLING_DAY, entry.data.get(CONF_BILLING_DAY, 1))
    tariff_type = entry.data.get(CONF_TARIFF_TYPE)
    import_sensor = entry.data.get(CONF_IMPORT_SENSOR)
    export_sensor = entry.data.get(CONF_EXPORT_SENSOR)
    
    coordinator = TNBRatesCoordinator(hass, remote_url)
    
    # Create energy tracker with configuration
    coordinator.energy_tracker = TNBEnergyTracker(hass, billing_day, tariff_type)
    
    # Calculate expected sensor count for restoration coordination
    # Energy sensors: Total, Export, NEM Balance (always 3)
    # + Peak, Offpeak (if ToU) = 5 total for ToU, 3 for Standard
    from .const import TARIFF_TOU
    expected_sensors = 5 if tariff_type == TARIFF_TOU else 3
    coordinator.energy_tracker.set_expected_sensor_count(expected_sensors)
    
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Set up state change listeners (only once per coordinator, not per sensor)
    coordinator.setup_listeners(import_sensor, export_sensor)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Clean up listeners
        coordinator.remove_listeners()

    return unload_ok
