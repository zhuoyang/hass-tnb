"""Pure calculation functions for TNB billing components."""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from .const import TARIFF_TOU

_LOGGER = logging.getLogger(__name__)


def select_tier(total_kwh: float, tiers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Select appropriate tier based on usage.
    
    Args:
        total_kwh: Total energy usage in kWh
        tiers: List of tier dictionaries with 'limit' key
        
    Returns:
        Selected tier dict, or None if no tiers provided
    """
    if not tiers:
        return None
        
    for tier in tiers:
        if total_kwh <= tier["limit"]:
            return tier
    
    # If usage exceeds all tiers, return the last tier
    return tiers[-1]


def is_peak_time(
    current_time: datetime,
    tou_config: Dict[str, Any]
) -> bool:
    """
    Determine if current time is peak or offpeak.
    
    Args:
        current_time: The datetime to check
        tou_config: ToU configuration dict with peak_start, peak_end, 
                   weekend_is_offpeak, public_holidays
                   
    Returns:
        True if peak time, False if offpeak
    """
    try:
        peak_start = datetime.strptime(
            tou_config.get("peak_start", "14:00"), "%H:%M"
        ).time()
        peak_end = datetime.strptime(
            tou_config.get("peak_end", "22:00"), "%H:%M"
        ).time()
        weekend_offpeak = tou_config.get("weekend_is_offpeak", True)
        
        is_weekend = current_time.weekday() >= 5
        
        # Check weekend first
        if weekend_offpeak and is_weekend:
            return False
            
        # Check public holiday
        public_holidays = tou_config.get("public_holidays", [])
        is_public_holiday = current_time.strftime("%Y-%m-%d") in public_holidays
        
        if is_public_holiday:
            return False
            
        # Check time range
        time_only = current_time.time()
        if peak_start <= time_only < peak_end:
            return True
        else:
            return False
            
    except Exception as err:
        _LOGGER.error("Error parsing ToU schedule, defaulting to Off-Peak: %s", err)
        return False


def calculate_energy_cost(
    peak_kwh: float,
    offpeak_kwh: float,
    total_kwh: float,
    tariff: Dict[str, Any],
    tariff_type: str
) -> Tuple[float, float, float, float]:
    """
    Calculate energy cost based on tier and tariff type.
    
    Args:
        peak_kwh: Peak period energy usage
        offpeak_kwh: Off-peak period energy usage
        total_kwh: Total energy usage
        tariff: Tariff configuration dict
        tariff_type: Either TARIFF_TOU or TARIFF_STANDARD
        
    Returns:
        Tuple of (energy_cost, peak_rate, offpeak_rate, rate)
        - For ToU: peak_rate and offpeak_rate are populated, rate is 0
        - For Standard: rate is populated, peak_rate and offpeak_rate are 0
    """
    energy_cost = 0.0
    peak_rate = 0.0
    offpeak_rate = 0.0
    rate = 0.0
    
    if tariff_type == TARIFF_TOU:
        tou_config = tariff.get("tou", {})
        tiers = tou_config.get("tiers", [])
        
        if not tiers:
            _LOGGER.error("No ToU tiers configured, defaulting to 0 rate")
            return (0.0, 0.0, 0.0, 0.0)
            
        selected_tier = select_tier(total_kwh, tiers)
        if not selected_tier:
            return (0.0, 0.0, 0.0, 0.0)
            
        peak_rate = selected_tier.get("peak_rate", 0)
        offpeak_rate = selected_tier.get("offpeak_rate", 0)
        energy_cost = (peak_kwh * (peak_rate / 100) + 
                      offpeak_kwh * (offpeak_rate / 100))
    else:
        # Standard Tariff
        tiers = tariff.get("tiers", [])
        if not tiers:
            _LOGGER.error("No tiers configured, defaulting to 0 rate")
            return (0.0, 0.0, 0.0, 0.0)
            
        selected_tier = select_tier(total_kwh, tiers)
        if not selected_tier:
            return (0.0, 0.0, 0.0, 0.0)
            
        rate = selected_tier.get("rate", 0)
        energy_cost = total_kwh * (rate / 100)
        
    return (energy_cost, peak_rate, offpeak_rate, rate)


def calculate_variable_charges(
    total_kwh: float,
    capacity_rate: float,
    network_rate: float
) -> float:
    """
    Calculate variable charges (capacity + network).
    
    Args:
        total_kwh: Total energy usage
        capacity_rate: Capacity rate in sen/kWh
        network_rate: Network rate in sen/kWh
        
    Returns:
        Total variable charges in RM
    """
    return total_kwh * ((capacity_rate + network_rate) / 100)


def calculate_retail_charge(
    total_kwh: float,
    retail_config: Dict[str, Any]
) -> float:
    """
    Calculate retail charge with waiver limit.
    
    Args:
        total_kwh: Total energy usage
        retail_config: Dict with 'retail' (charge amount) and 
                      'retail_waiver_limit' (threshold)
                      
    Returns:
        Retail charge in RM (0 if below waiver limit)
    """
    waiver_limit = retail_config.get("retail_waiver_limit", 600)
    retail_charge = retail_config.get("retail", 10.00)
    
    if total_kwh > waiver_limit:
        return retail_charge
    return 0.0


def calculate_afa_charge(
    total_kwh: float,
    afa_config: Dict[str, Any],
    current_month_key: str
) -> float:
    """
    Calculate AFA charge with monthly rate lookup.
    
    Args:
        total_kwh: Total energy usage
        afa_config: AFA configuration with 'waiver_limit', 'rates' (dict), 'rate' (fallback)
        current_month_key: Month key in format "YYYY-MM"
        
    Returns:
        AFA charge in RM
    """
    waiver_limit = afa_config.get("waiver_limit", 600)
    
    if total_kwh <= waiver_limit:
        return 0.0
        
    afa_rates = afa_config.get("rates", {})
    afa_rate = afa_rates.get(current_month_key, afa_config.get("rate", 0.0))
    
    return total_kwh * (afa_rate / 100)


def calculate_eei_rebate(
    total_kwh: float,
    eei_config: Dict[str, Any]
) -> float:
    """
    Calculate EEI rebate using tiered structure.
    
    Args:
        total_kwh: Total energy usage
        eei_config: EEI configuration with 'limit', 'tiers' (optional), 'rate' (fallback)
        
    Returns:
        EEI rebate in RM (negative value reduces bill)
    """
    limit = eei_config.get("limit", 1000)
    
    if total_kwh > limit:
        return 0.0
        
    eei_tiers = eei_config.get("tiers", [])
    
    if eei_tiers:
        selected_tier = select_tier(total_kwh, eei_tiers)
        if selected_tier:
            selected_eei_rate = selected_tier.get("rate", 0)
            return total_kwh * (selected_eei_rate / 100)
    
    # Fallback to single rate
    return total_kwh * (eei_config.get("rate", 0) / 100)


def calculate_kwtbb_tax(
    total_kwh: float,
    base_bill: float,
    kwtbb_config: Dict[str, Any]
) -> float:
    """
    Calculate KWTBB tax on base bill.
    
    Args:
        total_kwh: Total energy usage
        base_bill: Base bill amount before taxes
        kwtbb_config: KWTBB configuration with 'threshold' and 'rate'
        
    Returns:
        KWTBB tax in RM
    """
    threshold = kwtbb_config.get("threshold", 300)
    rate = kwtbb_config.get("rate", 1.6)
    
    if total_kwh > threshold:
        return base_bill * (rate / 100)
    return 0.0


def calculate_service_tax(
    total_kwh: float,
    base_bill: float,
    service_tax_config: Dict[str, Any]
) -> float:
    """
    Calculate service tax on usage above exemption limit.
    
    TNB applies service tax based on a usage threshold:
    - Usage ≤ exemption_limit (600 kWh): Charges are exempt (Tanpa ST)
    - Usage > exemption_limit: Charges for excess usage are taxable (Dengan ST)
    
    The bill calculates all charges on total usage, then splits them:
    - Non-taxable portion: charges proportional to first 600 kWh
    - Taxable portion: charges proportional to usage above 600 kWh
    
    Args:
        total_kwh: Total energy usage
        base_bill: Base bill amount before taxes (calculated on total usage)
        service_tax_config: Service tax configuration with 'exemption_limit' and 'rate'
        
    Returns:
        Service tax in RM
    """
    exemption_limit = service_tax_config.get("exemption_limit", 600)
    rate = service_tax_config.get("rate", 8.0)
    
    if total_kwh <= exemption_limit or total_kwh == 0:
        return 0.0
        
    # Calculate taxable portion: charges for usage above exemption limit
    # Taxable ratio = (excess usage) / (total usage)
    taxable_ratio = (total_kwh - exemption_limit) / total_kwh
    taxable_amount = base_bill * taxable_ratio
    
    return taxable_amount * (rate / 100)


def calculate_export_credit(
    peak_kwh: float,
    offpeak_kwh: float,
    total_kwh: float,
    export_kwh: float,
    peak_rate: float,
    offpeak_rate: float,
    variable_rate: float,
    tariff_type: str,
    rate: float = 0.0,
    eei_rate: float = 0.0
) -> Tuple[float, float, float, float]:
    """
    Calculate export credit using peak-first offset algorithm.
    
    Export energy offsets import in priority order:
    1. Peak energy (highest value)
    2. Off-peak energy
    3. Remaining export becomes excess
    
    For Non-ToU:
    1. Total energy
    2. Remaining export becomes excess
    
    Args:
        peak_kwh: Peak period import energy
        offpeak_kwh: Off-peak period import energy
        total_kwh: Total import energy (for non-ToU)
        export_kwh: Total export energy
        peak_rate: Peak energy rate (sen/kWh)
        offpeak_rate: Off-peak energy rate (sen/kWh)
        variable_rate: Variable charges rate (capacity + network, sen/kWh)
        tariff_type: Either TARIFF_TOU or TARIFF_STANDARD
        rate: Standard tariff rate (sen/kWh), used only if not ToU
        eei_rate: EEI rate (sen/kWh), typically negative. Added to rate to reduce credit.
        
    Returns:
        Tuple of (credit_value, matched_peak, matched_offpeak, excess_export)
        For non-ToU, matched_peak will contain the matched total amount for simplicity in return signature,
        or we could add a matched_total return. Let's use matched_peak + matched_offpeak = matched_total.
    """
    matched_peak = 0.0
    matched_offpeak = 0.0
    remaining_export = export_kwh
    
    if tariff_type == TARIFF_TOU:
        # Offset Peak First (highest value energy)
        if peak_kwh > 0:
            matched_peak = min(remaining_export, peak_kwh)
            remaining_export -= matched_peak
            
        # Offset Off-peak Second
        if offpeak_kwh > 0:
            matched_offpeak = min(remaining_export, offpeak_kwh)
            remaining_export -= matched_offpeak
            
        excess_export = remaining_export
        
        # Calculate Credit Value (energy rate + variable charges + eei_rate)
        # eei_rate is typically negative, so adding it reduces the credit
        credit_value = (
            matched_peak * ((peak_rate + variable_rate + eei_rate) / 100) +
            matched_offpeak * ((offpeak_rate + variable_rate + eei_rate) / 100)
        )
    else:
        # Standard Tariff
        matched_total = 0.0
        if total_kwh > 0:
            matched_total = min(remaining_export, total_kwh)
            remaining_export -= matched_total
            
        excess_export = remaining_export
        
        # For standard tariff, we can just return matched_total as matched_peak or split it?
        # The return signature expects matched_peak and matched_offpeak.
        # Let's just put it in matched_peak for now as a placeholder, or better, 
        # since the caller might use these values, we should be careful.
        # But looking at coordinator.py, it just logs them.
        # Let's assign to matched_peak to indicate "matched energy".
        matched_peak = matched_total
        
        credit_value = matched_total * ((rate + variable_rate + eei_rate) / 100)

    return (credit_value, matched_peak, matched_offpeak, excess_export)
