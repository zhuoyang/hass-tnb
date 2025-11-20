# Project Overview

This project is a Home Assistant custom component for tracking TNB (Tenaga Nasional Berhad) electricity rates and calculating bills.

## Project Structure

```
j:\tnb-ha\
├── custom_components\
│   └── tnb_rates\          # The integration source code
│       ├── __init__.py
│       ├── calculations.py # Core calculation logic
│       ├── config_flow.py  # Configuration flow
│       ├── const.py        # Constants
│       ├── coordinator.py  # Data update coordinator & Energy Tracker
│       ├── sensor.py       # Sensor entities
│       └── ...
├── tests\                  # Test suite
│   ├── conftest.py         # Pytest fixtures and mocks
│   ├── test_calculations.py# Unit tests for calculations
│   └── test_energy_tracker.py # Tests for energy tracking logic
├── rates.json              # Tariff rates and configuration
├── pytest.ini              # Pytest configuration
└── ...
```

## Testing

This project uses `pytest` for testing.

### How to Run Tests

To run all tests:
```bash
pytest
```

To run a specific test file:
```bash
pytest tests/test_calculations.py
```

To run a specific test function:
```bash
pytest tests/test_calculations.py::TestEnergyCalculation::test_tou_tier1_selection
```

### How to Write Tests

1.  **Location**: Place new tests in the `tests/` directory. File names should start with `test_`.
2.  **Fixtures**: Use fixtures defined in `tests/conftest.py`.
    -   `hass_mock`: Mocks the Home Assistant instance.
    -   `rates_data`: Loads the `rates.json` file.
    -   `tariff_a`, `tou_config`, `afa_config`, etc.: Provide specific sections of the rates configuration.
3.  **Mocking**: Home Assistant modules are mocked in `conftest.py` to allow testing without a running HA instance.
4.  **Structure**: Group related tests into classes (e.g., `class TestEnergyCalculation:`).

### Example Test

```python
def test_example_calculation(tariff_a):
    """Test a simple calculation using the tariff_a fixture."""
    # Setup
    usage = 100
    
    # Execute
    result = some_calculation_function(usage, tariff_a)
    
    # Verify
    assert result == expected_value
```

## Key Components

-   **`calculations.py`**: Contains pure functions for calculating costs, taxes, and rebates. This is the easiest part to test as it doesn't depend on Home Assistant state.
-   **`coordinator.py`**: Handles data fetching and state management (`TNBEnergyTracker`).
-   **`sensor.py`**: Defines the sensors that expose data to Home Assistant.
