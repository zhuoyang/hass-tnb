"""The TNB Rates integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_REMOTE_URL, CONF_BILLING_DAY, CONF_TARIFF_TYPE
from .coordinator import TNBRatesCoordinator, TNBEnergyTracker

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TNB Rates from a config entry."""
    
    remote_url = entry.options.get(CONF_REMOTE_URL, entry.data.get(CONF_REMOTE_URL))
    billing_day = entry.options.get(CONF_BILLING_DAY, entry.data.get(CONF_BILLING_DAY, 1))
    tariff_type = entry.data.get(CONF_TARIFF_TYPE)
    
    coordinator = TNBRatesCoordinator(hass, remote_url)
    
    # Create energy tracker with configuration
    coordinator.energy_tracker = TNBEnergyTracker(hass, billing_day, tariff_type)
    
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
