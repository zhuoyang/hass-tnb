"""Tests for NEM balance functionality."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from custom_components.tnb_rates.coordinator import TNBEnergyTracker
from custom_components.tnb_rates.const import TARIFF_TOU, TARIFF_STANDARD


class TestNEMBalanceMonthlyReset:
    """Test NEM balance behavior during monthly billing cycle resets."""

    def test_nem_balance_accumulates_across_months(self, hass_mock):
        """Test that excess export carries forward through multiple months."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Start in March
        march_start = datetime(2025, 3, 1, 0, 0, 0)
        tracker._last_reset = march_start
        
        # Generate 100 kWh import, 150 kWh export in March
        tracker._total_kwh = Decimal("100.0")
        tracker._export_kwh = Decimal("150.0")
        
        # Trigger reset at start of April
        april_start = datetime(2025, 4, 1, 0, 0, 0)
        tracker._check_reset(april_start)
        
        # Should carry forward 50 kWh excess (150 - 100)
        assert tracker._nem_balance == Decimal("50.0")
        assert tracker._export_kwh == Decimal("0.0")  # Monthly counter reset
        assert tracker._total_kwh == Decimal("0.0")
        
        # Generate 80 kWh import, 120 kWh export in April
        tracker._total_kwh = Decimal("80.0")
        tracker._export_kwh = Decimal("120.0")
        
        # Trigger reset at start of May
        may_start = datetime(2025, 5, 1, 0, 0, 0)
        tracker._check_reset(may_start)
        
        # Should carry forward 50 + 40 = 90 kWh total
        assert tracker._nem_balance == Decimal("90.0")

    def test_nem_balance_with_no_excess_export(self, hass_mock):
        """Test that nem_balance stays the same when there's no excess."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Start with existing NEM balance
        tracker._nem_balance = Decimal("30.0")
        tracker._last_reset = datetime(2025, 3, 1, 0, 0, 0)
        
        # Generate 150 kWh import, 100 kWh export (no excess)
        tracker._total_kwh = Decimal("150.0")
        tracker._export_kwh = Decimal("100.0")
        
        # Reset
        tracker._check_reset(datetime(2025, 4, 1, 0, 0, 0))
        
        # NEM balance should remain at 30.0 (no new excess added)
        assert tracker._nem_balance == Decimal("30.0")

    def test_nem_balance_with_tou_tariff(self, hass_mock):
        """Test NEM balance calculation with Time of Use tariff."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=15, tariff_type=TARIFF_TOU)
        
        tracker._last_reset = datetime(2025, 3, 15, 0, 0, 0)
        
        # ToU: 60 peak + 40 offpeak = 100 total import, 180 export
        tracker._peak_kwh = Decimal("60.0")
        tracker._offpeak_kwh = Decimal("40.0")
        tracker._total_kwh = Decimal("100.0")
        tracker._export_kwh = Decimal("180.0")
        
        # Reset
        tracker._check_reset(datetime(2025, 4, 15, 0, 0, 0))
        
        # Should carry forward 80 kWh excess (180 - 100)
        assert tracker._nem_balance == Decimal("80.0")
        assert tracker._peak_kwh == Decimal("0.0")
        assert tracker._offpeak_kwh == Decimal("0.0")


class Testnem_balanceYearlyReset:
    """Test nem_balance behavior during yearly reset on January 1st."""

    def test_nem_balance_resets_on_jan_1st(self, hass_mock):
        """Test that nem_balance is discarded on January 1st yearly reset."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Start in December with accumulated nem_balance
        tracker._last_reset = datetime(2024, 12, 1, 0, 0, 0)
        tracker._nem_balance = Decimal("150.0")
        
        # Generate some excess in December
        tracker._total_kwh = Decimal("50.0")
        tracker._export_kwh = Decimal("100.0")  # 50 kWh excess
        
        # Trigger reset at Jan 1st
        jan_1st = datetime(2025, 1, 1, 0, 0, 0)
        tracker._check_reset(jan_1st)
        
        # nem_balance should be reset to 0
        assert tracker._nem_balance == Decimal("0.0")

    def test_nem_balance_continues_within_year(self, hass_mock):
        """Test that nem_balance accumulates normally within the same year."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Start in January after yearly reset
        tracker._last_reset = datetime(2025, 1, 1, 0, 0, 0)
        tracker._nem_balance = Decimal("0.0")
        
        # Generate excess in January
        tracker._total_kwh = Decimal("80.0")
        tracker._export_kwh = Decimal("120.0")
        
        # Reset to February
        tracker._check_reset(datetime(2025, 2, 1, 0, 0, 0))
        assert tracker._nem_balance == Decimal("40.0")
        
        # Continue to March
        tracker._total_kwh = Decimal("60.0")
        tracker._export_kwh = Decimal("90.0")
        tracker._check_reset(datetime(2025, 3, 1, 0, 0, 0))
        
        # Should have 40 + 30 = 70 kWh
        assert tracker._nem_balance == Decimal("70.0")

    def test_nem_balance_resets_with_mid_month_billing_day(self, hass_mock):
        """Test yearly reset when billing day is not 1st of month."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=15, tariff_type=TARIFF_STANDARD)
        
        # Last reset was Dec 15, 2024
        tracker._last_reset = datetime(2024, 12, 15, 0, 0, 0)
        tracker._nem_balance = Decimal("200.0")
        
        tracker._total_kwh = Decimal("50.0")
        tracker._export_kwh = Decimal("80.0")
        
        # Reset on Jan 15, 2025 (crosses Jan 1st)
        jan_15 = datetime(2025, 1, 15, 0, 0, 0)
        tracker._check_reset(jan_15)
        
        # Should discard nem_balance because we crossed Jan 1st
        assert tracker._nem_balance == Decimal("0.0")


class Testnem_balanceExportCredit:
    """Test that nem_balance is used in export credit calculations."""

    def test_nem_balance_used_in_export_credit_calculation(self, hass_mock, rates_data, tariff_a):
        """Test that nem_balance combines with current export for credit."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Set up nem_balance from previous period
        tracker._nem_balance = Decimal("50.0")
        
        # Current period: 100 import, 30 export
        tracker._total_kwh = Decimal("100.0")
        tracker._export_kwh = Decimal("30.0")
        
        # Calculate components
        coordinator_data = {"tariff_a": tariff_a, "rates": rates_data}
        components = tracker.calculate_components(coordinator_data)
        
        # With nem_balance: effective export = 30 + 50 = 80 kWh
        # Should offset 80 kWh of the 100 kWh import
        # Export credit should be > 0
        assert components["export_credit"] > Decimal("0.0")
        
        # Excess should be 0 (80 export < 100 import)
        assert components["excess_export_kwh"] == Decimal("0.0")

    def test_nem_balance_creates_excess_export(self, hass_mock, rates_data, tariff_a):
        """Test that nem_balance can create excess export."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Large nem_balance from previous periods
        tracker._nem_balance = Decimal("150.0")
        
        # Current period: 100 import, 20 export
        tracker._total_kwh = Decimal("100.0")
        tracker._export_kwh = Decimal("20.0")
        
        # Calculate components
        coordinator_data = {"tariff_a": tariff_a, "rates": rates_data}
        components = tracker.calculate_components(coordinator_data)
        
        # Effective export = 20 + 150 = 170 kWh
        # Import = 100 kWh
        # Excess = 170 - 100 = 70 kWh
        assert components["excess_export_kwh"] == Decimal("70.0")
        
        # Should have full import offset
        assert components["export_credit"] > Decimal("0.0")

    def test_nem_balance_with_tou_peak_first_offset(self, hass_mock, rates_data, tariff_a):
        """Test nem_balance uses peak-first offset in ToU tariff."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_TOU)
        
        # nem_balance from previous period
        tracker._nem_balance = Decimal("80.0")
        
        # Current period: 60 peak + 40 offpeak = 100 import, 30 export
        tracker._peak_kwh = Decimal("60.0")
        tracker._offpeak_kwh = Decimal("40.0")
        tracker._total_kwh = Decimal("100.0")
        tracker._export_kwh = Decimal("30.0")
        
        # Calculate components
        coordinator_data = {"tariff_a": tariff_a, "rates": rates_data}
        components = tracker.calculate_components(coordinator_data)
        
        # Effective export = 30 + 80 = 110 kWh
        # Should offset all 60 peak + 40 offpeak with 10 excess
        assert components["excess_export_kwh"] == Decimal("10.0")


class Testnem_balancePersistence:
    """Test nem_balance state persistence and restoration."""

    def test_nem_balance_getter_setter(self, hass_mock):
        """Test get/set methods for NEM balance."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Set NEM balance
        tracker.set_nem_balance_kwh(75.5)
        
        # Get NEM balance
        assert tracker.get_nem_balance_kwh() == 75.5
        assert tracker._nem_balance == Decimal("75.5")

    def test_nem_balance_in_get_state(self, hass_mock):
        """Test that NEM balance is included in get_state()."""""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        tracker._nem_balance = Decimal("45.0")
        
        state = tracker.get_state()
        
        assert "nem_balance_kwh" in state
        assert state["nem_balance_kwh"] == 45.0

    def test_nem_balance_in_set_values(self, hass_mock):
        """Test manual setting of NEM balance via set_values()."""""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Manually set all values including NEM balance
        tracker.set_values(
            peak_kwh=50.0,
            offpeak_kwh=30.0,
            total_kwh=80.0,
            export_kwh=40.0,
            nem_balance_kwh=25.0
        )
        
        assert tracker._nem_balance == Decimal("25.0")
        assert tracker._peak_kwh == Decimal("50.0")

    def test_nem_balance_negative_values_rejected(self, hass_mock):
        """Test that negative NEM balance values are clamped to 0."""""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        tracker.set_nem_balance_kwh(-50.0)
        
        # Should be clamped to 0
        assert tracker.get_nem_balance_kwh() == 0.0


class TestNEMBalanceEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_no_export_no_nem_balance_change(self, hass_mock):
        """Test that no export doesn't affect NEM balance."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        tracker._nem_balance = Decimal("100.0")
        tracker._last_reset = datetime(2025, 3, 1, 0, 0, 0)
        
        # Only import, no export
        tracker._total_kwh = Decimal("200.0")
        tracker._export_kwh = Decimal("0.0")
        
        tracker._check_reset(datetime(2025, 4, 1, 0, 0, 0))
        
        # nem_balance unchanged (no new excess to add)
        assert tracker._nem_balance == Decimal("100.0")

    def test_first_reset_initializes_last_reset(self, hass_mock):
        """Test that first call to _check_reset initializes last_reset."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        assert tracker._last_reset is None
        
        current_time = datetime(2025, 3, 15, 10, 30, 0)
        tracker._check_reset(current_time)
        
        assert tracker._last_reset == current_time
        assert tracker._nem_balance == Decimal("0.0")

    def test_billing_day_28_boundary(self, hass_mock):
        """Test NEM balance with billing day at max (28th)."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=28, tariff_type=TARIFF_STANDARD)
        
        tracker._last_reset = datetime(2025, 2, 28, 0, 0, 0)
        tracker._total_kwh = Decimal("50.0")
        tracker._export_kwh = Decimal("100.0")
        
        # Reset to March 28
        tracker._check_reset(datetime(2025, 3, 28, 0, 0, 0))
        
        # Should carry 50 kWh
        assert tracker._nem_balance == Decimal("50.0")

    def test_nem_balance_reset_exactly_on_jan_1_midnight(self, hass_mock):
        """Test reset exactly at Jan 1 00:00:00."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        tracker._last_reset = datetime(2024, 12, 1, 0, 0, 0)
        tracker._nem_balance = Decimal("500.0")
        tracker._total_kwh = Decimal("100.0")
        tracker._export_kwh = Decimal("200.0")
        
        # Reset exactly at midnight
        jan_1_midnight = datetime(2025, 1, 1, 0, 0, 0)
        tracker._check_reset(jan_1_midnight)
        
        # NEM balance should be 0
        assert tracker._nem_balance == Decimal("0.0")

    def test_multiple_resets_within_year(self, hass_mock):
        """Test accumulation through multiple months within same year."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type=TARIFF_STANDARD)
        
        # Start in Feb
        tracker._last_reset = datetime(2025, 2, 1, 0, 0, 0)
        
        # February: 10 kWh excess
        tracker._total_kwh = Decimal("90.0")
        tracker._export_kwh = Decimal("100.0")
        tracker._check_reset(datetime(2025, 3, 1, 0, 0, 0))
        assert tracker._nem_balance == Decimal("10.0")
        
        # March: 20 kWh excess
        tracker._total_kwh = Decimal("80.0")
        tracker._export_kwh = Decimal("100.0")
        tracker._check_reset(datetime(2025, 4, 1, 0, 0, 0))
        assert tracker._nem_balance == Decimal("30.0")
        
        # April: 15 kWh excess
        tracker._total_kwh = Decimal("85.0")
        tracker._export_kwh = Decimal("100.0")
        tracker._check_reset(datetime(2025, 5, 1, 0, 0, 0))
        assert tracker._nem_balance == Decimal("45.0")
        
        # May: No excess (import > export)
        tracker._total_kwh = Decimal("100.0")
        tracker._export_kwh = Decimal("80.0")
        tracker._check_reset(datetime(2025, 6, 1, 0, 0, 0))
        assert tracker._nem_balance == Decimal("45.0")  # Unchanged


