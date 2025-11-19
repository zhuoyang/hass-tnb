"""Pytest configuration and fixtures for TNB Rates tests."""
import sys
from unittest.mock import MagicMock

# Mock homeassistant modules before any imports
sys.modules['homeassistant'] = MagicMock()
sys.modules['homeassistant.core'] = MagicMock()
sys.modules['homeassistant.const'] = MagicMock()
sys.modules['homeassistant.config_entries'] = MagicMock()
sys.modules['homeassistant.helpers'] = MagicMock()
sys.modules['homeassistant.helpers.update_coordinator'] = MagicMock()
sys.modules['homeassistant.helpers.entity'] = MagicMock()
sys.modules['homeassistant.helpers.entity_platform'] = MagicMock()
sys.modules['homeassistant.util'] = MagicMock()
sys.modules['homeassistant.util.dt'] = MagicMock()

# Define actual constants that tests need
from homeassistant import const as ha_const
ha_const.STATE_UNAVAILABLE = "unavailable"
ha_const.STATE_UNKNOWN = "unknown"

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock


@pytest.fixture
def rates_data():
    """Load production rates data for testing."""
    rates_path = Path(__file__).parent.parent / "rates.json"
    with open(rates_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def coordinator_data(rates_data):
    """Provide coordinator data structure for tests."""
    return rates_data


@pytest.fixture
def tariff_a(rates_data):
    """Provide tariff_a configuration."""
    return rates_data.get("tariff_a", {})


@pytest.fixture
def tou_config(tariff_a):
    """Provide Time-of-Use configuration."""
    return tariff_a.get("tou", {})


@pytest.fixture
def standard_tariff_config(tariff_a):
    """Provide Standard tariff tiers configuration."""
    return {
        "tiers": tariff_a.get("tiers", []),
        "charges": tariff_a.get("charges", {})
    }


@pytest.fixture
def afa_config(rates_data):
    """Provide AFA configuration."""
    return rates_data.get("afa", {})


@pytest.fixture
def eei_config(rates_data):
    """Provide EEI configuration."""
    return rates_data.get("eei", {})


@pytest.fixture
def tax_config(rates_data):
    """Provide tax configuration."""
    return rates_data.get("tax", {})


@pytest.fixture
def hass_mock():
    """Provide a mock Home Assistant instance."""
    hass = Mock()
    hass.states = {}
    return hass


@pytest.fixture
def energy_tracker(hass_mock):
    """Provide a TNBEnergyTracker instance for testing."""
    from custom_components.tnb_rates.coordinator import TNBEnergyTracker
    return TNBEnergyTracker(hass_mock, billing_day=1, tariff_type="Standard")


@pytest.fixture
def energy_tracker_tou(hass_mock):
    """Provide a TNBEnergyTracker instance with ToU tariff for testing."""
    from custom_components.tnb_rates.coordinator import TNBEnergyTracker
    return TNBEnergyTracker(hass_mock, billing_day=1, tariff_type="Time of Use")


class MockState:
    """Mock Home Assistant state object."""
    
    def __init__(self, state_value):
        """Initialize mock state."""
        self.state = str(state_value)


@pytest.fixture
def mock_state_factory():
    """Factory for creating mock state objects."""
    return MockState
