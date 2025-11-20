# TNB Rates for Home Assistant

A custom component for Home Assistant that tracks electricity costs in Malaysia using Tenaga Nasional Berhad (TNB) tariff rates. It supports both Standard (Tariff A) and Time of Use (ToU) tariffs, handles solar export, and provides a detailed breakdown of your electricity bill.

## Features

*   **Real-time Cost Tracking**: Calculates your estimated monthly bill based on your energy sensor readings.
*   **Tariff Support**:
    *   **Standard (Tariff A)**: Tiered pricing blocks.
    *   **Time of Use (ToU)**: Peak and Off-Peak rates.
*   **Solar Export Support**: Tracks exported energy and calculates potential savings or net costs.
*   **Detailed Cost Breakdown**:
    *   **Energy Charge**: Cost of electricity consumed (split by Peak/Off-Peak for ToU).
    *   **Service Tax (SST)**: Automatically calculates 8% tax for usage above 600kWh.
    *   **KWTBB (RE Fund)**: Calculates the 1.6% Renewable Energy Fund contribution.
    *   **AFA**: Calculates the Automatic Fuel Adjustment, rates is set in rates.json file and will be updated regularly.
    *   **Minimum Charge**: Enforces the minimum monthly charge (RM 3.00).
*   **Configurable Billing Cycle**: Set the day of the month your bill resets.
*   **Remote Rates Update**: Fetches the latest tariff rates from a remote JSON file, ensuring your rates are always up to date without needing to update the component code.
*   **Manual Correction**: Service to manually set accumulated energy values if needed.

## Installation

### HACS (Recommended)

1.  Open HACS in Home Assistant.
2.  Go to "Integrations".
3.  Click the three dots in the top right corner and select "Custom repositories".
4.  Add the URL of this repository.
5.  Select "Integration" as the category.
6.  Click "Add" and then install "TNB Rates".
7.  Restart Home Assistant.

### Manual Installation

1.  Download the `custom_components/tnb_rates` folder from this repository.
2.  Copy the folder to your Home Assistant `config/custom_components/` directory.
3.  Restart Home Assistant.

## Configuration

1.  Go to **Settings** > **Devices & Services**.
2.  Click **+ ADD INTEGRATION** in the bottom right.
3.  Search for **TNB Rates**.
4.  Follow the configuration flow:
    *   **Name**: Give your sensor a name (e.g., "TNB Bill").
    *   **Import Sensor**: Select your total energy import sensor (kWh). This should be an increasing counter (total_increasing).
    *   **Export Sensor** (Optional): Select your total energy export sensor (kWh) if you have solar.
    *   **Billing Day**: The day of the month your TNB bill cycle starts (e.g., 1 for the 1st of the month).
    *   **Tariff Type**: Select "Standard" or "Time of Use".
    *   **Remote URL**: The URL to the `rates.json` file. You can leave the default or point to your own if you want to customize rates.

## Usage

Once configured, a new sensor (e.g., `sensor.tnb_bill`) will be created. This sensor's state represents the **Total Bill Amount** (RM).

### Attributes

The sensor provides detailed attributes for your dashboard:
*   `energy_cost`: Total cost of energy consumed.
*   `peak_cost` / `offpeak_cost`: Breakdown for ToU.
*   `export_credit`: Value of exported energy.
*   `tax_total`: Total tax (Service Tax + KWTBB).
*   `final_bill`: The final bill amount.
*   `current_tier`: The current pricing tier you are in (for Standard tariff).

### Services

#### `tnb_rates.set_energy_values`
Allows you to manually override the accumulated energy values for the current billing cycle. This is useful if the sensor gets out of sync or you need to correct it based on your actual bill.

**Parameters:**
*   `peak_kwh`: (Optional) Accumulated Peak Energy (kWh).
*   `offpeak_kwh`: (Optional) Accumulated Off-Peak Energy (kWh).
*   `export_kwh`: (Optional) Accumulated Export Energy (kWh).

## License

[MIT License](LICENSE)
