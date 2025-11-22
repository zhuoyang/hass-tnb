"""Tests for the restoration flag feature."""
import pytest
from datetime import datetime, timezone
from custom_components.tnb_rates.coordinator import TNBEnergyTracker


class TestRestorationFlag:
    """Test the _restored flag behavior."""

    def test_tracker_starts_not_restored(self, hass_mock):
        """Test that tracker starts with _restored=False."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=15, tariff_type="Time of Use")
        
        assert not tracker.is_restored()
        state = tracker.get_state()
        assert state["peak_kwh"] == 0.0
        assert state["offpeak_kwh"] == 0.0
        assert state["total_kwh"] == 0.0
        assert state["export_kwh"] == 0.0

    def test_mark_as_restored(self, hass_mock):
        """Test marking tracker as restored."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=15, tariff_type="Time of Use")
        
        assert not tracker.is_restored()
        tracker.mark_as_restored()
        assert tracker.is_restored()

    def test_restored_after_state_restoration(self, hass_mock):
        """Test restoration flow: set values then mark as restored."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=15, tariff_type="Time of Use")
        
        # Simulate state restoration
        tracker.set_peak_kwh(100.5)
        tracker.set_offpeak_kwh(50.3)
        tracker.set_export_kwh(10.0)
        
        # For ToU tariff, reconcile will recalculate total from peak + offpeak
        tracker.reconcile_tou_total()
        
        # Should still not be marked as restored yet
        assert not tracker.is_restored()
        
        # Mark as restored
        tracker.mark_as_restored()
        assert tracker.is_restored()
        
        # Verify values are preserved
        state = tracker.get_state()
        assert state["peak_kwh"] == 100.5
        assert state["offpeak_kwh"] == 50.3
        # For ToU, total = peak + offpeak
        assert abs(state["total_kwh"] - 150.8) < 0.01
        assert state["export_kwh"] == 10.0

    def test_restored_flag_persists_through_updates(self, hass_mock):
        """Test that _restored flag remains True after updates."""
        from decimal import Decimal
        tracker = TNBEnergyTracker(hass_mock, billing_day=15, tariff_type="Standard")
        
        # Mark as restored
        tracker.mark_as_restored()
        assert tracker.is_restored()
        
        # Process some updates (must use Decimal for internal processing)
        now = datetime(2025, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
        tracker._process_import_delta(Decimal("5.0"), now)
        
        # Should still be marked as restored
        assert tracker.is_restored()
        state = tracker.get_state()
        assert state["total_kwh"] == 5.0

    def test_fresh_install_workflow(self, hass_mock):
        """Test workflow for fresh install (no prior state)."""
        tracker = TNBEnergyTracker(hass_mock, billing_day=1, tariff_type="Time of Use")
        
        # On fresh install, sensors won't find prior state
        # So they'll immediately mark as restored with zero values
        assert not tracker.is_restored()
        tracker.mark_as_restored()
        assert tracker.is_restored()
        
        # Values should still be zero but now marked as valid
        state = tracker.get_state()
        assert state["peak_kwh"] == 0.0
        assert state["offpeak_kwh"] == 0.0
