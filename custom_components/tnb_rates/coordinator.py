"""DataUpdateCoordinator for TNB Rates."""
import logging
import json
import aiohttp
import async_timeout
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DEFAULT_REMOTE_URL, TARIFF_TOU, SENSOR_RESET_THRESHOLD
from .calculations import (
    calculate_energy_cost,
    calculate_variable_charges,
    calculate_retail_charge,
    calculate_afa_charge,
    calculate_eei_rebate,
    calculate_kwtbb_tax,
    calculate_service_tax,
    calculate_export_credit,
    is_peak_time,
)

from decimal import Decimal

_LOGGER = logging.getLogger(__name__)


class TNBEnergyTracker:
    """Class to track energy import/export and calculate costs."""

    def __init__(self, hass: HomeAssistant, billing_day: int, tariff_type: str):
        """Initialize energy tracker."""
        self.hass = hass
        self._billing_day = max(1, min(28, billing_day))  # Validate billing day
        self._tariff_type = tariff_type
        
        # Energy counters (using Decimal for precision)
        self._peak_kwh = Decimal("0.0")
        self._offpeak_kwh = Decimal("0.0")
        self._total_kwh = Decimal("0.0")  # For non-ToU (Standard) tariff
        self._export_kwh = Decimal("0.0")
        self._last_reset = None
        
        # Restoration tracking (prevents showing zeros before state restoration)
        self._restored = False
        
        # Last known sensor states
        self._last_import_state = None
        self._last_export_state = None
        
        # Event deduplication tracking (prevents duplicate processing from multiple listeners)
        self._last_processed_import_time = None
        self._last_processed_export_time = None
        
        _LOGGER.info(
            "Energy tracker initialized: billing_day=%d, tariff=%s",
            self._billing_day,
            self._tariff_type
        )

    def restore_state(self, peak_kwh: float, offpeak_kwh: float, total_kwh: float, export_kwh: float, last_reset: datetime):
        """Restore state from persistent storage (Legacy method, kept for compatibility)."""
        # Validate restored values (reasonable limit: < 100,000 kWh per month)
        self._peak_kwh = Decimal(str(max(0, min(100000, peak_kwh))))
        self._offpeak_kwh = Decimal(str(max(0, min(100000, offpeak_kwh))))
        self._total_kwh = Decimal(str(max(0, min(100000, total_kwh))))
        self._export_kwh = Decimal(str(max(0, min(100000, export_kwh))))
        self._last_reset = last_reset
        
        # Migration logic for existing non-ToU users who have data in offpeak
        if self._tariff_type != TARIFF_TOU and self._offpeak_kwh > 0 and self._total_kwh == 0:
            _LOGGER.info("Migrating non-ToU data from offpeak (%.2f) to total", self._offpeak_kwh)
            self._total_kwh = self._offpeak_kwh
            self._offpeak_kwh = Decimal("0.0")
            
        _LOGGER.info(
            "Restored energy state: peak=%s, offpeak=%s, total=%s, export=%s",
            self._peak_kwh,
            self._offpeak_kwh,
            self._total_kwh,
            self._export_kwh
        )

    def set_peak_kwh(self, value: float):
        """Set peak kWh from restored sensor state."""
        self._peak_kwh = Decimal(str(value))
        # Note: Total is NOT automatically recalculated here to avoid race conditions
        # during state restoration. Total will be recalculated after all sensors restore.

    def set_offpeak_kwh(self, value: float):
        """Set offpeak kWh from restored sensor state."""
        self._offpeak_kwh = Decimal(str(value))
        # Note: Total is NOT automatically recalculated here to avoid race conditions
        # during state restoration. Total will be recalculated after all sensors restore.

    def set_total_kwh(self, value: float):
        """Set total kWh from restored sensor state."""
        self._total_kwh = Decimal(str(value))
        # For non-ToU mode, this is the authoritative value
        # For ToU mode, this will be recalculated from peak + offpeak after all sensors restore

    def set_export_kwh(self, value: float):
        """Set export kWh from restored sensor state."""
        self._export_kwh = Decimal(str(value))

    def set_last_reset(self, value: datetime):
        """Set last reset timestamp from restored sensor state."""
        self._last_reset = value

    def mark_as_restored(self):
        """Mark tracker as restored (called after state restoration completes)."""
        self._restored = True
        _LOGGER.info("Energy tracker marked as restored")

    def is_restored(self) -> bool:
        """Check if tracker has been restored from previous state."""
        return self._restored

    def reconcile_tou_total(self):
        """Recalculate total from peak + offpeak for ToU mode (call after all sensors restore)."""
        if self._tariff_type == TARIFF_TOU:
            calculated_total = self._peak_kwh + self._offpeak_kwh
            if self._total_kwh != calculated_total:
                _LOGGER.info(
                    "ToU total reconciliation: was %s, recalculated as %s (peak=%s + offpeak=%s)",
                    self._total_kwh, calculated_total, self._peak_kwh, self._offpeak_kwh
                )
                self._total_kwh = calculated_total

    @callback
    def handle_import_change(self, new_state, old_state, coordinator_data):
        """Handle changes in the import sensor."""
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        
        # Deduplicate events (prevents multiple sensors from processing same state change)
        if new_state.last_changed == self._last_processed_import_time:
            _LOGGER.debug("Skipping duplicate import event at %s", new_state.last_changed)
            return False
        self._last_processed_import_time = new_state.last_changed
            
        try:
            new_val = float(new_state.state)
            if old_state is None or old_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self._last_import_state = new_val
                return False
                
            old_val = float(old_state.state)
            
            # Detect sensor reset
            if new_val < old_val:
                if new_val < SENSOR_RESET_THRESHOLD:  # Likely a real reset
                    delta = new_val
                    _LOGGER.info("Import sensor reset detected: %s -> %s, delta=%.2f kWh", old_val, new_val, delta)
                else:
                    _LOGGER.warning("Unexpected decrease in import sensor: %s -> %s, ignoring", old_val, new_val)
                    delta = 0
            else:
                delta = new_val - old_val
                
            if delta > 0:
                self._process_import_delta(Decimal(str(delta)), coordinator_data)
                _LOGGER.debug("Import delta: %.2f kWh", delta)
                
            self._last_import_state = new_val
            return True
            
        except ValueError as err:
            _LOGGER.error("Error processing import state: %s", err)
            return False

    @callback
    def handle_export_change(self, new_state, old_state):
        """Handle changes in the export sensor."""
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        
        # Deduplicate events (prevents multiple sensors from processing same state change)
        if new_state.last_changed == self._last_processed_export_time:
            _LOGGER.debug("Skipping duplicate export event at %s", new_state.last_changed)
            return False
        self._last_processed_export_time = new_state.last_changed

        try:
            new_val = float(new_state.state)
            if old_state is None or old_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self._last_export_state = new_val
                return False
            
            old_val = float(old_state.state)
            
            # Detect sensor reset
            if new_val < old_val:
                if new_val < SENSOR_RESET_THRESHOLD:  # Likely a real reset
                    delta = new_val
                    _LOGGER.info("Export sensor reset detected: %s -> %s, delta=%.2f kWh", old_val, new_val, delta)
                else:
                    _LOGGER.warning("Unexpected decrease in export sensor: %s -> %s, ignoring", old_val, new_val)
                    delta = 0
            else:
                delta = new_val - old_val
                
            if delta > 0:
                self._check_reset()
                self._export_kwh += Decimal(str(delta))
                _LOGGER.debug("Export delta: %.2f kWh, total: %s kWh", delta, self._export_kwh)
                
            self._last_export_state = new_val
            return True
            
        except ValueError as err:
            _LOGGER.error("Error processing export state: %s", err)
            return False

    def _process_import_delta(self, delta: Decimal, coordinator_data, current_time=None):
        """Allocate delta to Peak, Off-Peak, or Total based on tariff and time."""
        self._check_reset(current_time)
        
        if delta <= 0:
            return

        # Handle Non-ToU (Standard)
        if self._tariff_type != TARIFF_TOU:
            self._total_kwh += delta
            _LOGGER.debug("Added %s kWh to total (total: %s kWh)", delta, self._total_kwh)
            return

        # Handle ToU
        is_peak = False
        if current_time is None:
            current_time = dt_util.now()
        tou_config = coordinator_data.get("tariff_a", {}).get("tou", {})
        
        is_peak = is_peak_time(current_time, tou_config)
        
        if is_peak:
            self._peak_kwh += delta
            _LOGGER.debug("Added %s kWh to peak (total: %s kWh)", delta, self._peak_kwh)
        else:
            self._offpeak_kwh += delta
            _LOGGER.debug("Added %s kWh to offpeak (total: %s kWh)", delta, self._offpeak_kwh)
        self._total_kwh = self._peak_kwh + self._offpeak_kwh

    def _check_reset(self, current_time=None):
        """Check if we need to reset for a new billing month."""
        if current_time is None:
            current_time = dt_util.now()
        
        if self._last_reset is None:
            self._last_reset = current_time
            return

        current_period_start = current_time.replace(day=self._billing_day, hour=0, minute=0, second=0, microsecond=0)
        if current_time.day < self._billing_day:
            if current_time.month == 1:
                current_period_start = current_period_start.replace(year=current_time.year-1, month=12)
            else:
                current_period_start = current_period_start.replace(month=current_time.month-1)
                
        if self._last_reset < current_period_start:
            _LOGGER.info(
                "Billing cycle reset. Previous totals: peak=%s, offpeak=%s, total=%s, export=%s",
                self._peak_kwh,
                self._offpeak_kwh,
                self._total_kwh,
                self._export_kwh
            )
            self._peak_kwh = Decimal("0.0")
            self._offpeak_kwh = Decimal("0.0")
            self._total_kwh = Decimal("0.0")
            self._export_kwh = Decimal("0.0")
            self._last_reset = current_time

    def get_state(self):
        """Get current energy state."""
        return {
            "peak_kwh": float(self._peak_kwh),
            "offpeak_kwh": float(self._offpeak_kwh),
            "total_kwh": float(self._total_kwh),
            "export_kwh": float(self._export_kwh),
            "last_reset": self._last_reset,
            "last_reset_iso": self._last_reset.isoformat() if self._last_reset else None,
        }

    def set_values(self, peak_kwh=None, offpeak_kwh=None, total_kwh=None, export_kwh=None):
        """Manually set energy values (for corrections)."""
        if peak_kwh is not None:
            self._peak_kwh = Decimal(str(max(0, min(100000, peak_kwh))))
        if offpeak_kwh is not None:
            self._offpeak_kwh = Decimal(str(max(0, min(100000, offpeak_kwh))))
        if total_kwh is not None:
            self._total_kwh = Decimal(str(max(0, min(100000, total_kwh))))
        if export_kwh is not None:
            self._export_kwh = Decimal(str(max(0, min(100000, export_kwh))))
        
        _LOGGER.info(
            "Manual override applied: peak=%s, offpeak=%s, total=%s, export=%s",
            self._peak_kwh,
            self._offpeak_kwh,
            self._total_kwh,
            self._export_kwh
        )

    def calculate_components(self, coordinator_data):
        """Calculate all cost components and return a dict."""
        if not coordinator_data:
            _LOGGER.warning("No coordinator data available for calculation")
            return {
                "import_cost": 0.0,
                "export_credit": 0.0,
                "excess_export_kwh": 0.0,
                "net_bill": 0.0
            }
            
        data = coordinator_data
        tariff = data.get("tariff_a", {})
        if not tariff:
            _LOGGER.error("Missing tariff_a configuration")
            return {
                "import_cost": 0.0,
                "export_credit": 0.0,
                "excess_export_kwh": 0.0,
                "net_bill": 0.0
            }
            
        charges = tariff.get("charges", {})
        afa = data.get("afa", {})
        eei = data.get("eei", {})
        tax_config = data.get("tax", {})
        
        # Calculate total import based on tariff type
        if self._tariff_type == TARIFF_TOU:
            total_import = self._peak_kwh + self._offpeak_kwh
        else:
            total_import = self._total_kwh
        
        # --- 1. Calculate Import Cost Components ---
        
        # Energy Charge
        energy_cost, peak_rate, offpeak_rate, rate = calculate_energy_cost(
            self._peak_kwh,
            self._offpeak_kwh,
            total_import,
            tariff,
            self._tariff_type
        )
        
        # Variable Charges (capacity + network)
        capacity_rate = Decimal(str(charges.get("capacity", 0)))
        network_rate = Decimal(str(charges.get("network", 0)))
        variable_rate = capacity_rate + network_rate
        
        capacity_charge = total_import * (capacity_rate / 100)
        network_charge = total_import * (network_rate / 100)
        total_variable_cost = capacity_charge + network_charge
        
        # Retail Charge
        retail_charge = calculate_retail_charge(total_import, charges)
        
        # AFA Charge
        current_month_key = dt_util.now().strftime("%Y-%m")
        afa_cost = calculate_afa_charge(total_import, afa, current_month_key)
        
        # EEI Rebate
        eei_rebate = calculate_eei_rebate(total_import, eei)
        
        # KWTBB Tax (calculated on energy-related charges only: Energy + Variable + EEI)
        # Excludes Retail and AFA charges
        kwtbb_base = energy_cost + total_variable_cost + eei_rebate
        kwtbb_cost = calculate_kwtbb_tax(
            total_import,
            kwtbb_base,
            tax_config.get("kwtbb", {})
        )
        
        # Base Bill (before taxes, includes all charges)
        base_bill_amount = energy_cost + total_variable_cost + retail_charge + afa_cost + eei_rebate
        
        # Service Tax
        service_tax_cost = calculate_service_tax(
            total_import,
            base_bill_amount,
            tax_config.get("service_tax", {})
        )
        
        # Total Import Cost
        total_import_cost = base_bill_amount + kwtbb_cost + service_tax_cost
        
        _LOGGER.debug(
            "Import cost breakdown: energy=%.2f, capacity=%.2f, network=%.2f, retail=%.2f, afa=%.2f, eei=%.2f, kwtbb=%.2f, service_tax=%.2f, total=%.2f",
            energy_cost, capacity_charge, network_charge, retail_charge, afa_cost, eei_rebate, kwtbb_cost, service_tax_cost, total_import_cost
        )
        
        # --- 2. Calculate Export Credit ---
        
        # Export credit calculation will determine EEI rate internally based on import usage
        credit_value, matched_peak, matched_offpeak, excess_export = calculate_export_credit(
            self._peak_kwh,
            self._offpeak_kwh,
            self._total_kwh,
            self._export_kwh,
            peak_rate,
            offpeak_rate,
            variable_rate,
            self._tariff_type,
            rate,
            eei
        )
        
        _LOGGER.debug(
            "Export credit: matched_peak=%.2f kWh, matched_offpeak=%.2f kWh, excess=%.2f kWh, credit=%.2f RM",
            matched_peak, matched_offpeak, excess_export, credit_value
        )
        
        return {
            "import_cost": total_import_cost,
            "energy_cost": energy_cost,
            "capacity_charge": capacity_charge,
            "network_charge": network_charge,
            "retail_charge": retail_charge,
            "afa_cost": afa_cost,
            "eei_rebate": eei_rebate,
            "kwtbb_tax": kwtbb_cost,
            "service_tax": service_tax_cost,
            "export_credit": credit_value,
            "excess_export_kwh": excess_export,
            "net_bill": max(total_import_cost - credit_value, Decimal("0.0"))
        }


class TNBRatesCoordinator(DataUpdateCoordinator):
    """Class to manage fetching TNB Rates data."""

    def __init__(self, hass: HomeAssistant, remote_url: str):
        """Initialize."""
        self.remote_url = remote_url
        self.energy_tracker = None  # Will be set by __init__.py after config is loaded
        self._listener_removers = []  # Track listener cleanup functions
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=12),
        )

    def setup_listeners(self, import_sensor: str, export_sensor: str = None):
        """Set up state change listeners for import/export sensors."""
        from homeassistant.helpers.event import async_track_state_change_event
        
        @callback
        def handle_import_change(event):
            """Handle import sensor state changes."""
            if not self.energy_tracker:
                return
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            if self.energy_tracker.handle_import_change(new_state, old_state, self.data):
                # Notify all coordinator listeners to update
                self.async_update_listeners()
        
        @callback
        def handle_export_change(event):
            """Handle export sensor state changes."""
            if not self.energy_tracker:
                return
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            if self.energy_tracker.handle_export_change(new_state, old_state):
                # Notify all coordinator listeners to update
                self.async_update_listeners()
        
        # Register listeners (only once per coordinator)
        self._listener_removers.append(
            async_track_state_change_event(self.hass, [import_sensor], handle_import_change)
        )
        _LOGGER.info("Registered import sensor listener: %s", import_sensor)
        
        if export_sensor:
            self._listener_removers.append(
                async_track_state_change_event(self.hass, [export_sensor], handle_export_change)
            )
            _LOGGER.info("Registered export sensor listener: %s", export_sensor)

    def remove_listeners(self):
        """Remove all state change listeners."""
        for remover in self._listener_removers:
            remover()
        self._listener_removers.clear()
        _LOGGER.info("Removed all sensor listeners")

    async def _async_update_data(self):
        """Fetch data from remote JSON."""
        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.remote_url) as response:
                        if response.status != 200:
                            raise UpdateFailed(f"Error fetching rates: {response.status}")
                        data = await response.json(content_type=None)
                        _LOGGER.debug("Successfully fetched rates data from %s", self.remote_url)
                        return data
                        
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
