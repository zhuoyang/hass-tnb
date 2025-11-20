"""Tests for calculation functions in calculations.py module."""
import pytest
from datetime import datetime
from custom_components.tnb_rates.calculations import (
    calculate_energy_cost,
    calculate_variable_charges,
    calculate_retail_charge,
    calculate_afa_charge,
    calculate_eei_rebate,
    calculate_kwtbb_tax,
    calculate_service_tax,
    calculate_export_credit,
    select_tier,
    is_peak_time,
)
from custom_components.tnb_rates.const import TARIFF_TOU, TARIFF_STANDARD


class TestTierSelection:
    """Test tier selection logic."""
    
    def test_select_tier_exact_match(self):
        """Test tier selection when usage exactly matches tier limit."""
        tiers = [
            {"limit": 200, "rate": 21.80},
            {"limit": 1500, "rate": 33.40},
            {"limit": 999999, "rate": 51.60}
        ]
        tier = select_tier(200, tiers)
        assert tier["rate"] == 21.80
        
    def test_select_tier_between_limits(self):
        """Test tier selection when usage is between tier limits."""
        tiers = [
            {"limit": 200, "rate": 21.80},
            {"limit": 1500, "rate": 33.40},
            {"limit": 999999, "rate": 51.60}
        ]
        tier = select_tier(500, tiers)
        assert tier["rate"] == 33.40
        
    def test_select_tier_above_all_limits(self):
        """Test tier selection when usage exceeds all tiers."""
        tiers = [
            {"limit": 200, "rate": 21.80},
            {"limit": 1500, "rate": 33.40},
            {"limit": 999999, "rate": 51.60}
        ]
        tier = select_tier(2000000, tiers)
        assert tier["rate"] == 51.60  # Should use last tier
        
    def test_select_tier_no_tiers(self):
        """Test tier selection with empty tier list."""
        tier = select_tier(100, [])
        assert tier is None


class TestPeakOffpeakClassification:
    """Test peak/offpeak time classification."""
    
    def test_weekday_peak_hours(self):
        """Test that weekday peak hours (14:00-22:00) are detected."""
        tou_config = {
            "peak_start": "14:00",
            "peak_end": "22:00",
            "weekend_is_offpeak": True,
            "public_holidays": []
        }
        # Monday at 16:00
        test_time = datetime(2025, 1, 6, 16, 0, 0)
        assert is_peak_time(test_time, tou_config) is True
        
    def test_weekday_offpeak_hours(self):
        """Test that weekday offpeak hours are detected."""
        tou_config = {
            "peak_start": "14:00",
            "peak_end": "22:00",
            "weekend_is_offpeak": True,
            "public_holidays": []
        }
        # Monday at 10:00
        test_time = datetime(2025, 1, 6, 10, 0, 0)
        assert is_peak_time(test_time, tou_config) is False
        
    def test_weekend_offpeak(self):
        """Test that weekends are offpeak."""
        tou_config = {
            "peak_start": "14:00",
            "peak_end": "22:00",
            "weekend_is_offpeak": True,
            "public_holidays": []
        }
        # Saturday at 16:00 (would be peak on weekday)
        test_time = datetime(2025, 1, 4, 16, 0, 0)
        assert is_peak_time(test_time, tou_config) is False
        
    def test_public_holiday_offpeak(self):
        """Test that public holidays are offpeak."""
        tou_config = {
            "peak_start": "14:00",
            "peak_end": "22:00",
            "weekend_is_offpeak": True,
            "public_holidays": ["2025-01-01", "2025-05-01", "2025-12-25"]
        }
        # New Year at 16:00 (Wednesday, would be peak on normal weekday)
        test_time = datetime(2025, 1, 1, 16, 0, 0)
        assert is_peak_time(test_time, tou_config) is False
        
    def test_peak_boundary_start(self):
        """Test peak period start boundary."""
        tou_config = {
            "peak_start": "14:00",
            "peak_end": "22:00",
            "weekend_is_offpeak": True,
            "public_holidays": []
        }
        # Monday at exactly 14:00
        test_time = datetime(2025, 1, 6, 14, 0, 0)
        assert is_peak_time(test_time, tou_config) is True
        
    def test_peak_boundary_end(self):
        """Test peak period end boundary."""
        tou_config = {
            "peak_start": "14:00",
            "peak_end": "22:00",
            "weekend_is_offpeak": True,
            "public_holidays": []
        }
        # Monday at exactly 22:00 (should be offpeak, end is exclusive)
        test_time = datetime(2025, 1, 6, 22, 0, 0)
        assert is_peak_time(test_time, tou_config) is False


class TestEnergyCalculation:
    """Test energy cost calculations."""
    
    def test_tou_tier1_selection(self, tariff_a):
        """Test ToU tariff Tier 1 selection (≤1500 kWh)."""
        peak_kwh = 300.0
        offpeak_kwh = 500.0
        total_kwh = 800.0
        
        energy_cost, peak_rate, offpeak_rate, rate = calculate_energy_cost(
            peak_kwh, offpeak_kwh, total_kwh, tariff_a, TARIFF_TOU
        )
        
        # Should select Tier 1
        assert peak_rate > 0
        assert offpeak_rate > 0
        assert rate == 0  # Standard rate not used in ToU
        assert energy_cost > 0
        
    def test_tou_tier2_selection(self, tariff_a):
        """Test ToU tariff Tier 2 selection (>1500 kWh)."""
        peak_kwh = 800.0
        offpeak_kwh = 1000.0
        total_kwh = 1800.0
        
        energy_cost, peak_rate, offpeak_rate, rate = calculate_energy_cost(
            peak_kwh, offpeak_kwh, total_kwh, tariff_a, TARIFF_TOU
        )
        
        # Should select Tier 2 (higher rates)
        assert peak_rate > 0
        assert offpeak_rate > 0
        assert energy_cost > 0
        
    def test_standard_tariff_calculation(self, tariff_a):
        """Test standard tariff calculation."""
        total_kwh = 500.0
        
        energy_cost, peak_rate, offpeak_rate, rate = calculate_energy_cost(
            0, 0, total_kwh, tariff_a, TARIFF_STANDARD
        )
        
        # Standard tariff uses single rate
        assert rate > 0
        assert peak_rate == 0
        assert offpeak_rate == 0
        assert energy_cost > 0
        
    def test_zero_usage(self, tariff_a):
        """Test calculation with zero usage."""
        energy_cost, peak_rate, offpeak_rate, rate = calculate_energy_cost(
            0, 0, 0, tariff_a, TARIFF_STANDARD
        )
        
        assert energy_cost == 0.0


class TestVariableCharges:
    """Test variable charges calculation."""
    
    def test_variable_charges_calculation(self):
        """Test calculation of capacity + network charges."""
        total_kwh = 1000.0
        capacity_rate = 10.0  # sen/kWh
        network_rate = 5.0    # sen/kWh
        
        charges = calculate_variable_charges(total_kwh, capacity_rate, network_rate)
        
        # (1000 * 15) / 100 = 150 RM
        assert charges == pytest.approx(150.0, rel=1e-2)
        
    def test_variable_charges_zero_usage(self):
        """Test variable charges with zero usage."""
        charges = calculate_variable_charges(0, 10.0, 5.0)
        assert charges == 0.0


class TestRetailCharge:
    """Test retail charge calculation."""
    
    def test_retail_waiver_below_limit(self):
        """Test retail charge waived below limit."""
        retail_config = {
            "retail": 10.00,
            "retail_waiver_limit": 600
        }
        charge = calculate_retail_charge(500, retail_config)
        assert charge == 0.0
        
    def test_retail_charge_above_limit(self):
        """Test retail charge applied above limit."""
        retail_config = {
            "retail": 10.00,
            "retail_waiver_limit": 600
        }
        charge = calculate_retail_charge(700, retail_config)
        assert charge == 10.00
        
    def test_retail_charge_at_limit(self):
        """Test retail charge at exact limit."""
        retail_config = {
            "retail": 10.00,
            "retail_waiver_limit": 600
        }
        charge = calculate_retail_charge(600, retail_config)
        assert charge == 0.0  # At limit, not above


class TestAFACharge:
    """Test AFA charge calculation."""
    
    def test_afa_below_waiver_limit(self, afa_config):
        """Test AFA waived below limit."""
        charge = calculate_afa_charge(500, afa_config, "2025-01")
        assert charge == 0.0
        
    def test_afa_monthly_rate_lookup(self, afa_config):
        """Test AFA uses correct monthly rate."""
        charge = calculate_afa_charge(1000, afa_config, "2025-01")
        # Charge should be >= 0 (may be 0 if rate is 0 for that month)
        assert charge >= 0
        
    def test_afa_fallback_rate(self, afa_config):
        """Test AFA uses fallback rate when month not found."""
        charge = calculate_afa_charge(1000, afa_config, "2099-12")
        # Should use fallback rate
        assert charge >= 0


class TestEEIRebate:
    """Test EEI rebate calculation."""
    
    def test_eei_tier_selection(self, eei_config):
        """Test EEI rebate tier selection."""
        rebate = calculate_eei_rebate(300, eei_config)
        assert rebate < 0  # Rebate is negative (reduces bill)
        
    def test_eei_above_limit(self, eei_config):
        """Test EEI rebate not applied above limit."""
        rebate = calculate_eei_rebate(1500, eei_config)
        assert rebate == 0.0
        
    def test_eei_at_limit(self, eei_config):
        """Test EEI rebate at exact limit."""
        limit = eei_config.get("limit", 1000)
        rebate = calculate_eei_rebate(limit, eei_config)
        assert rebate < 0  # Should still get rebate at limit


class TestKWTBBTax:
    """Test KWTBB tax calculation."""
    
    def test_kwtbb_below_threshold(self):
        """Test KWTBB not applied below threshold."""
        kwtbb_config = {"threshold": 300, "rate": 1.6}
        tax = calculate_kwtbb_tax(200, 100.0, kwtbb_config)
        assert tax == 0.0
        
    def test_kwtbb_at_threshold(self):
        """Test KWTBB at exact threshold."""
        kwtbb_config = {"threshold": 300, "rate": 1.6}
        tax = calculate_kwtbb_tax(300, 100.0, kwtbb_config)
        assert tax == 0.0  # At threshold, not above
        
    def test_kwtbb_above_threshold(self):
        """Test KWTBB applied above threshold."""
        kwtbb_config = {"threshold": 300, "rate": 1.6}
        base_bill = 100.0
        tax = calculate_kwtbb_tax(400, base_bill, kwtbb_config)
        # 100 * 1.6 / 100 = 1.6
        assert tax == pytest.approx(1.6, rel=1e-2)
        
    def test_kwtbb_with_zero_base_bill(self):
        """Test KWTBB with zero base bill."""
        kwtbb_config = {"threshold": 300, "rate": 1.6}
        tax = calculate_kwtbb_tax(400, 0.0, kwtbb_config)
        assert tax == 0.0


class TestServiceTax:
    """Test service tax calculation."""
    
    def test_service_tax_below_exemption(self):
        """Test service tax not applied below exemption."""
        service_tax_config = {"exemption_limit": 600, "rate": 8.0}
        tax = calculate_service_tax(500, 100.0, service_tax_config)
        assert tax == 0.0
        
    def test_service_tax_at_exemption(self):
        """Test service tax at exact exemption limit."""
        service_tax_config = {"exemption_limit": 600, "rate": 8.0}
        tax = calculate_service_tax(600, 100.0, service_tax_config)
        assert tax == 0.0  # At limit, not above
        
    def test_service_tax_above_exemption(self):
        """Test service tax applied above exemption."""
        service_tax_config = {"exemption_limit": 600, "rate": 8.0}
        base_bill = 100.0
        total_kwh = 900.0
        
        tax = calculate_service_tax(total_kwh, base_bill, service_tax_config)
        
        # Pro-rata: (900-600)/900 = 0.333... of bill is taxable
        # Taxable amount = 100 * 0.333... = 33.33...
        # Tax = 33.33... * 8 / 100 = 2.67
        assert tax > 0
        assert tax < base_bill  # Tax should be less than base bill
        
    def test_service_tax_pro_rata_calculation(self):
        """Test service tax pro-rata calculation accuracy."""
        service_tax_config = {"exemption_limit": 600, "rate": 8.0}
        base_bill = 200.0
        total_kwh = 800.0
        
        tax = calculate_service_tax(total_kwh, base_bill, service_tax_config)
        
        # (800-600)/800 = 0.25 taxable ratio
        # 200 * 0.25 = 50 taxable amount
        # 50 * 8 / 100 = 4.0
        assert tax == pytest.approx(4.0, rel=1e-2)


class TestExportCredit:
    """Test export credit calculation."""
    
    def test_peak_first_offset(self):
        """Test that peak energy is offset before offpeak."""
        peak_kwh = 100.0
        offpeak_kwh = 200.0
        total_kwh = 300.0
        export_kwh = 150.0
        peak_rate = 50.0
        offpeak_rate = 30.0
        variable_rate = 15.0
        
        credit, matched_peak, matched_offpeak, excess = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            peak_rate, offpeak_rate, variable_rate,
            TARIFF_TOU
        )
        
        # Should offset all peak (100) first, then 50 from offpeak
        assert matched_peak == 100.0
        assert matched_offpeak == 50.0
        assert excess == 0.0
        assert credit > 0
        
    def test_partial_export(self):
        """Test export less than total import."""
        peak_kwh = 100.0
        offpeak_kwh = 200.0
        total_kwh = 300.0
        export_kwh = 50.0
        peak_rate = 50.0
        offpeak_rate = 30.0
        variable_rate = 15.0
        
        credit, matched_peak, matched_offpeak, excess = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            peak_rate, offpeak_rate, variable_rate,
            TARIFF_TOU
        )
        
        # Should offset 50 from peak only
        assert matched_peak == 50.0
        assert matched_offpeak == 0.0
        assert excess == 0.0
        
    def test_excess_export(self):
        """Test export greater than total import."""
        peak_kwh = 100.0
        offpeak_kwh = 200.0
        total_kwh = 300.0
        export_kwh = 400.0
        peak_rate = 50.0
        offpeak_rate = 30.0
        variable_rate = 15.0
        
        credit, matched_peak, matched_offpeak, excess = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            peak_rate, offpeak_rate, variable_rate,
            TARIFF_TOU
        )
        
        # Should offset all import, 100 excess
        assert matched_peak == 100.0
        assert matched_offpeak == 200.0
        assert excess == 100.0
        
    def test_export_credit_value_tou(self):
        """Test export credit value calculation for ToU."""
        peak_kwh = 100.0
        offpeak_kwh = 0.0
        total_kwh = 100.0
        export_kwh = 100.0
        peak_rate = 40.0  # sen/kWh
        offpeak_rate = 20.0
        variable_rate = 10.0  # sen/kWh
        
        credit, _, _, _ = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            peak_rate, offpeak_rate, variable_rate,
            TARIFF_TOU
        )
        
        # Credit = 100 * (40 + 10) / 100 = 50 RM
        assert credit == pytest.approx(50.0, rel=1e-2)
        
    def test_export_credit_value_standard(self):
        """Test export credit value calculation for standard tariff."""
        peak_kwh = 0.0
        offpeak_kwh = 0.0
        total_kwh = 100.0
        export_kwh = 100.0
        rate = 30.0  # sen/kWh
        variable_rate = 10.0  # sen/kWh
        
        credit, matched_peak, matched_offpeak, excess = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            0, 0, variable_rate,
            TARIFF_STANDARD, rate
        )
        
        # Credit = 100 * (30 + 10) / 100 = 40 RM
        assert credit == pytest.approx(40.0, rel=1e-2)
        assert matched_peak == 100.0 # matched_peak holds total matched for standard
        assert excess == 0.0
        
    def test_zero_export(self):
        """Test with no export energy."""
        credit, matched_peak, matched_offpeak, excess = calculate_export_credit(
            100.0, 200.0, 300.0, 0.0,
            50.0, 30.0, 15.0,
            TARIFF_TOU
        )
        
        assert matched_peak == 0.0
        assert matched_offpeak == 0.0
        assert excess == 0.0
        assert credit == 0.0

    def test_non_tou_export_partial(self):
        """Test Non-ToU export credit with partial offset."""
        peak_kwh = 0.0
        offpeak_kwh = 0.0
        total_kwh = 500.0
        export_kwh = 200.0
        rate = 21.8  # sen/kWh
        variable_rate = 15.0
        
        credit, matched_peak, matched_offpeak, excess = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            0, 0, variable_rate,
            TARIFF_STANDARD, rate
        )
        
        assert matched_peak == 200.0 # matched_peak holds total matched
        assert excess == 0.0
        # Credit = 200 * (21.8 + 15.0) / 100 = 73.6 RM
        assert credit == pytest.approx(73.6, rel=1e-2)

    def test_non_tou_export_excess(self):
        """Test Non-ToU export credit with excess."""
        peak_kwh = 0.0
        offpeak_kwh = 0.0
        total_kwh = 200.0
        export_kwh = 300.0
        rate = 21.8
        variable_rate = 15.0
        
        credit, matched_peak, matched_offpeak, excess = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            0, 0, variable_rate,
            TARIFF_STANDARD, rate
        )
        
        assert matched_peak == 200.0
        assert excess == 100.0
        # Credit = 200 * (21.8 + 15.0) / 100 = 73.6 RM
        assert credit == pytest.approx(73.6, rel=1e-2)

    def test_export_credit_with_eei_deduction_tou(self):
        """Test that EEI rate is deducted from export credit for ToU tariff."""
        peak_kwh = 100.0
        offpeak_kwh = 200.0
        total_kwh = 300.0
        export_kwh = 150.0
        peak_rate = 50.0  # sen/kWh
        offpeak_rate = 30.0  # sen/kWh
        variable_rate = 15.0  # sen/kWh
        eei_rate = -5.0  # -5 sen/kWh (negative rebate, reduces credit)
        
        # Calculate without EEI
        credit_no_eei, _, _, _ = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            peak_rate, offpeak_rate, variable_rate,
            TARIFF_TOU, 0, 0.0
        )
        
        # Calculate with EEI
        credit_with_eei, matched_peak, matched_offpeak, excess = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            peak_rate, offpeak_rate, variable_rate,
            TARIFF_TOU, 0, eei_rate
        )
        
        # Should offset all peak (100) first, then 50 from offpeak
        assert matched_peak == 100.0
        assert matched_offpeak == 50.0
        assert excess == 0.0
        
        # Credit without EEI = 100*(50+15)/100 + 50*(30+15)/100 = 65 + 22.5 = 87.5
        assert credit_no_eei == pytest.approx(87.5, rel=1e-2)
        
        # Credit with EEI = 100*(50+15-5)/100 + 50*(30+15-5)/100 = 60 + 20 = 80
        assert credit_with_eei == pytest.approx(80.0, rel=1e-2)
        
        # EEI should reduce credit by RM 7.5
        assert credit_with_eei < credit_no_eei
        assert (credit_no_eei - credit_with_eei) == pytest.approx(7.5, rel=1e-2)

    def test_export_credit_with_eei_deduction_standard(self):
        """Test that EEI rate is deducted from export credit for standard tariff."""
        peak_kwh = 0.0
        offpeak_kwh = 0.0
        total_kwh = 500.0
        export_kwh = 200.0
        rate = 30.0  # sen/kWh
        variable_rate = 17.4  # sen/kWh (4.55 + 12.85)
        eei_rate = -10.0  # -10 sen/kWh (negative rebate)
        
        # Calculate without EEI
        credit_no_eei, _, _, _ = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            0, 0, variable_rate,
            TARIFF_STANDARD, rate, 0.0
        )
        
        # Calculate with EEI
        credit_with_eei, matched_peak, _, excess = calculate_export_credit(
            peak_kwh, offpeak_kwh, total_kwh, export_kwh,
            0, 0, variable_rate,
            TARIFF_STANDARD, rate, eei_rate
        )
        
        assert matched_peak == 200.0  # matched_peak holds total matched for standard
        assert excess == 0.0
        
        # Credit without EEI = 200 * (30 + 17.4) / 100 = 94.8 RM
        assert credit_no_eei == pytest.approx(94.8, rel=1e-2)
        
        # Credit with EEI = 200 * (30 + 17.4 - 10) / 100 = 74.8 RM
        assert credit_with_eei == pytest.approx(74.8, rel=1e-2)
        
        # EEI should reduce credit by RM 20.0
        assert credit_with_eei < credit_no_eei
        assert (credit_no_eei - credit_with_eei) == pytest.approx(20.0, rel=1e-2)



class TestRealBillVerification:
    """Test calculations against real TNB bill from January 2025."""
    
    def test_bill_january_2025(self):
        """
        Verify calculations against actual TNB bill with NEM export.
        
        Import (Gross) usage:
        - Peak usage: 160 kWh
        - Off-peak usage: 798 kWh
        - Total gross import: 958 kWh
        
        Export data (from Kredit NEM):
        - Peak export: 160 kWh (credit: RM45.63 @ RM0.2852/kWh)
        - Off-peak export: 344 kWh (credit: RM84.04 @ RM0.2443/kWh)
        - Total export: 504 kWh
        
        Expected import charges (before NEM offset):
        - Peak energy: RM 45.63 (160 kWh @ RM0.2852/kWh)
        - Off-peak energy: RM 194.95 (798 kWh @ RM0.2443/kWh)
        - Total energy: RM 240.58
        - Capacity: RM 43.59 (958 kWh @ RM0.0455/kWh)
        - Network: RM 123.10 (958 kWh @ RM0.1285/kWh)
        - AFA rebate: -RM 62.27 (958 kWh @ -RM0.065/kWh)
        - Retail: RM 10.00
        - EEI rebate (import): -RM 4.79 (958 kWh @ -RM0.005/kWh)
        - Base bill: RM 350.21 (before tax)
        - Service Tax (8%): RM 10.78
        - KWTBB (1.6%): RM 6.44
        - Total before NEM: RM 367.43
        
        NEM Export Credits:
        - Peak energy credit: RM 45.63 (160 kWh @ RM0.2852/kWh)
        - Off-peak energy credit: RM 84.04 (344 kWh @ RM0.2443/kWh)
        - Capacity credit: RM 22.93 (504 kWh @ RM0.0455/kWh)
        - Network credit: RM 64.76 (504 kWh @ RM0.1285/kWh)
        - Subtotal NEM credit: RM 217.36
        - Pelarasan Insentif (EEI deduction): +RM 2.52 (504 kWh @ RM0.005/kWh)
        - Net NEM credit: RM 214.84
        
        Final bill: RM 367.43 - RM 214.84 = RM 152.59
        """
        # Import usage data
        peak_kwh = 160.0
        offpeak_kwh = 798.0
        total_kwh = 958.0
        
        # Export data
        export_kwh = 504.0
        export_peak_kwh = 160.0  # Matched all peak import
        export_offpeak_kwh = 344.0  # Matched 344 out of 798 offpeak
        
        # Tariff configuration (E1 Enhanced ToU for 901-1500 kWh tier)
        tariff = {
            "tou": {
                "tiers": [
                    {"limit": 200, "peak_rate": 28.52, "offpeak_rate": 24.43},
                    {"limit": 900, "peak_rate": 28.52, "offpeak_rate": 24.43},
                    {"limit": 1500, "peak_rate": 28.52, "offpeak_rate": 24.43},
                    {"limit": 999999, "peak_rate": 28.52, "offpeak_rate": 24.43}
                ]
            },
            "capacity_rate": 4.55,
            "network_rate": 12.85,
            "retail": 10.00,
            "retail_waiver_limit": 600,
        }
        
        afa_config = {
            "waiver_limit": 600,
            "rates": {
                "2025-01": -6.5,  # -6.5 sen/kWh = -RM0.065/kWh (rebate)
            },
            "rate": 0.0,
        }
        
        eei_config = {
            "limit": 1000,
            "rate": -0.5,  # -0.5 sen/kWh = -RM0.005/kWh
        }
        
        service_tax_config = {
            "exemption_limit": 600,
            "rate": 8.0,
        }
        
        kwtbb_config = {
            "threshold": 300,
            "rate": 1.6,
        }
        
        # === IMPORT COST CALCULATION ===
        
        # Step 1: Energy cost
        energy_cost, peak_rate, offpeak_rate, _ = calculate_energy_cost(
            peak_kwh, offpeak_kwh, total_kwh, tariff, TARIFF_TOU
        )
        
        # Verify individual components
        peak_energy_cost = peak_kwh * (peak_rate / 100)
        offpeak_energy_cost = offpeak_kwh * (offpeak_rate / 100)
        
        assert peak_rate == 28.52
        assert offpeak_rate == 24.43
        assert peak_energy_cost == pytest.approx(45.63, rel=1e-2)
        assert offpeak_energy_cost == pytest.approx(194.95, rel=1e-2)
        assert energy_cost == pytest.approx(240.58, rel=1e-2)
        
        # Step 2: Variable charges
        capacity_charge = total_kwh * (tariff["capacity_rate"] / 100)
        network_charge = total_kwh * (tariff["network_rate"] / 100)
        variable_charges = calculate_variable_charges(
            total_kwh, tariff["capacity_rate"], tariff["network_rate"]
        )
        
        assert capacity_charge == pytest.approx(43.59, rel=1e-2)
        assert network_charge == pytest.approx(123.10, rel=1e-2)
        assert variable_charges == pytest.approx(166.69, rel=1e-2)
        
        # Step 3: AFA rebate
        afa_charge = calculate_afa_charge(total_kwh, afa_config, "2025-01")
        assert afa_charge == pytest.approx(-62.27, abs=0.02)
        
        # Step 4: Retail charge
        retail_charge = calculate_retail_charge(total_kwh, tariff)
        assert retail_charge == pytest.approx(10.00, rel=1e-2)
        
        # Step 5: EEI rebate (for import)
        eei_rebate_import = calculate_eei_rebate(total_kwh, eei_config)
        assert eei_rebate_import == pytest.approx(-4.79, rel=1e-2)
        
        # Step 6: Base bill (before tax)
        base_bill = energy_cost + variable_charges + afa_charge + retail_charge + eei_rebate_import
        assert base_bill == pytest.approx(350.21, abs=0.02)
        
        # Step 7: KWTBB tax (1.6%)
        kwtbb_base = energy_cost + variable_charges + eei_rebate_import
        kwtbb_tax = calculate_kwtbb_tax(total_kwh, kwtbb_base, kwtbb_config)
        assert kwtbb_tax == pytest.approx(6.44, abs=0.01)
        
        # Step 8: Service tax (8% on taxable portion)
        service_tax = calculate_service_tax(total_kwh, base_bill, service_tax_config)
        assert service_tax == pytest.approx(10.78, abs=0.5)
        
        # Step 9: Total bill before NEM credits
        total_before_nem = base_bill + service_tax + kwtbb_tax
        assert total_before_nem == pytest.approx(367.43, abs=0.5)
        
        # === NEM EXPORT CREDIT CALCULATION ===
        
        # Calculate EEI rate for export
        eei_export_rebate = calculate_eei_rebate(export_kwh, eei_config)
        eei_export_rate = 0.0
        if export_kwh > 0:
            eei_export_rate = (eei_export_rebate * 100) / export_kwh
        
        # EEI deduction (Pelarasan Insentif)
        # This is the absolute value of the EEI rebate for export (positive charge)
        pelarasan_insentif = abs(eei_export_rebate)
        assert pelarasan_insentif == pytest.approx(2.52, abs=0.02)
        
        # Calculate export credit
        variable_rate = tariff["capacity_rate"] + tariff["network_rate"]
        credit_value, matched_peak, matched_offpeak, excess_export = calculate_export_credit(
            peak_kwh,
            offpeak_kwh,
            total_kwh,
            export_kwh,
            peak_rate,
            offpeak_rate,
            variable_rate,
            TARIFF_TOU,
            0.0,
            eei_export_rate
        )
        
        # Verify export matching (peak-first algorithm)
        assert matched_peak == 160.0  # All peak import offset
        assert matched_offpeak == 344.0  # 344 out of 798 offpeak offset
        assert excess_export == 0.0  # No excess export
        
        # Verify individual export credit components
        peak_export_credit = export_peak_kwh * (peak_rate / 100)
        offpeak_export_credit = export_offpeak_kwh * (offpeak_rate / 100)
        capacity_export_credit = export_kwh * (tariff["capacity_rate"] / 100)
        network_export_credit = export_kwh * (tariff["network_rate"] / 100)
        
        assert peak_export_credit == pytest.approx(45.63, abs=0.02)
        assert offpeak_export_credit == pytest.approx(84.04, abs=0.02)
        assert capacity_export_credit == pytest.approx(22.93, abs=0.02)
        assert network_export_credit == pytest.approx(64.76, abs=0.02)
        
        # Total credit before EEI deduction
        total_credit_before_eei = (peak_export_credit + offpeak_export_credit + 
                                   capacity_export_credit + network_export_credit)
        assert total_credit_before_eei == pytest.approx(217.36, abs=0.1)
        
        # Net credit after EEI deduction
        net_nem_credit = credit_value
        assert net_nem_credit == pytest.approx(214.84, abs=0.1)
        
        # Verify the credit matches: total_credit_before_eei - pelarasan_insentif
        assert net_nem_credit == pytest.approx(total_credit_before_eei - pelarasan_insentif, abs=0.1)
        
        # Step 10: Final bill
        final_bill = total_before_nem - net_nem_credit
        assert final_bill == pytest.approx(152.59, abs=0.5)

