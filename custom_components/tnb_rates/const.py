"""Constants for the TNB Rates integration."""

DOMAIN = "tnb_rates"

# Configuration
CONF_IMPORT_SENSOR = "import_sensor"
CONF_EXPORT_SENSOR = "export_sensor"
CONF_BILLING_DAY = "billing_day"
CONF_TARIFF_TYPE = "tariff_type"
CONF_REMOTE_URL = "remote_url"

TARIFF_STANDARD = "Standard"
TARIFF_TOU = "Time of Use"

# Sensor reset detection threshold (kWh)
SENSOR_RESET_THRESHOLD = 10.0

# Default Remote URL
DEFAULT_REMOTE_URL = "https://raw.githubusercontent.com/zhuoyang/hass-tnb/main/rates.json"

# Services
SERVICE_SET_ENERGY_VALUES = "set_energy_values"
