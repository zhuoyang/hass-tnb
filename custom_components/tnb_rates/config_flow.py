"""Config flow for TNB Rates integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_IMPORT_SENSOR,
    CONF_EXPORT_SENSOR,
    CONF_BILLING_DAY,
    CONF_TARIFF_TYPE,
    CONF_REMOTE_URL,
    TARIFF_STANDARD,
    TARIFF_TOU,
    DEFAULT_REMOTE_URL,
)

_LOGGER = logging.getLogger(__name__)

class TNBRatesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TNB Rates."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_IMPORT_SENSOR]}_tnb")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input["name"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="TNB Bill"): str,
                    vol.Required(CONF_IMPORT_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                    ),
                    vol.Optional(CONF_EXPORT_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="energy")
                    ),
                    vol.Required(CONF_BILLING_DAY, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
                    vol.Required(CONF_TARIFF_TYPE, default=TARIFF_STANDARD): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[TARIFF_STANDARD, TARIFF_TOU],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(CONF_REMOTE_URL, default=DEFAULT_REMOTE_URL): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return TNBRatesOptionsFlowHandler(config_entry)


class TNBRatesOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REMOTE_URL,
                        default=self.config_entry.options.get(
                            CONF_REMOTE_URL, self.config_entry.data.get(CONF_REMOTE_URL, DEFAULT_REMOTE_URL)
                        ),
                    ): str,
                    vol.Required(
                        CONF_BILLING_DAY,
                        default=self.config_entry.options.get(
                            CONF_BILLING_DAY, self.config_entry.data.get(CONF_BILLING_DAY, 1)
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
                }
            ),
        )
