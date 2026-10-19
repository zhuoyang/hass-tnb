"""The TNB Rates integration."""
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_REMOTE_URL,
    CONF_BILLING_DAY,
    CONF_TARIFF_TYPE,
    CONF_IMPORT_SENSOR,
    CONF_EXPORT_SENSOR,
    DEFAULT_REMOTE_URL,
    SERVICE_SET_ENERGY_VALUES,
    ATTR_CONFIG_ENTRY_ID,
)
from .coordinator import TNBRatesCoordinator, TNBEnergyTracker

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_ENERGY_VALUE = vol.All(vol.Coerce(float), vol.Range(min=0, max=100000))

SET_ENERGY_VALUES_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional("peak_kwh"): _ENERGY_VALUE,
        vol.Optional("offpeak_kwh"): _ENERGY_VALUE,
        vol.Optional("total_kwh"): _ENERGY_VALUE,
        vol.Optional("export_kwh"): _ENERGY_VALUE,
        vol.Optional("nem_balance_kwh"): _ENERGY_VALUE,
    }
)


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Set up the TNB Rates services."""

    async def handle_set_energy_values(call: ServiceCall):
        """Handle the set_energy_values service call."""
        coordinators = hass.data.get(DOMAIN, {})
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)

        if entry_id:
            if entry_id not in coordinators:
                raise ServiceValidationError(f"No loaded TNB Rates entry with id {entry_id}")
            targets = {entry_id: coordinators[entry_id]}
        elif len(coordinators) == 1:
            targets = coordinators
        else:
            raise ServiceValidationError(
                "Several TNB Rates entries are set up; choose one with config_entry_id"
            )

        for target_id, coordinator in targets.items():
            coordinator.energy_tracker.set_values(
                call.data.get("peak_kwh"),
                call.data.get("offpeak_kwh"),
                call.data.get("total_kwh"),
                call.data.get("export_kwh"),
                call.data.get("nem_balance_kwh"),
            )
            coordinator.async_update_listeners()
            _LOGGER.info("Energy values updated for entry %s", target_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ENERGY_VALUES,
        handle_set_energy_values,
        schema=SET_ENERGY_VALUES_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TNB Rates from a config entry."""

    remote_url = entry.options.get(CONF_REMOTE_URL, entry.data.get(CONF_REMOTE_URL, DEFAULT_REMOTE_URL))
    billing_day = entry.options.get(CONF_BILLING_DAY, entry.data.get(CONF_BILLING_DAY, 1))
    tariff_type = entry.data.get(CONF_TARIFF_TYPE)
    import_sensor = entry.data.get(CONF_IMPORT_SENSOR)
    export_sensor = entry.data.get(CONF_EXPORT_SENSOR)

    coordinator = TNBRatesCoordinator(hass, entry.entry_id, remote_url)

    # Create energy tracker with configuration
    coordinator.energy_tracker = TNBEnergyTracker(hass, billing_day, tariff_type)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Sensors restore their previous state while being added, so restoration
    # is complete once the platforms are set up (disabled sensors are skipped)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.energy_tracker.finish_restoration()

    # Set up state change listeners (only once per coordinator, not per sensor)
    coordinator.setup_listeners(import_sensor, export_sensor)
    coordinator.async_update_listeners()

    # Apply option changes (billing day, rates URL) without a restart
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Clean up listeners
        coordinator.remove_listeners()

    return unload_ok
