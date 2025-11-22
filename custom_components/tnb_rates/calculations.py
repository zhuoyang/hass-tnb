"""Pure calculation functions for TNB billing components."""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal

from .const import TARIFF_TOU

_LOGGER = logging.getLogger(__name__)


def select_tier(total_kwh: Decimal, tiers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Select appropriate tier based on usage.
    
    Args:
        total_kwh: Total energy usage in kWh (Decimal)
        tiers: List of tier dictionaries with 'limit' key
        
    Returns:
        Selected tier dict, or None if no tiers provided
    """
    if not tiers:
        return None
        
    for tier in tiers:
        # Ensure limit is Decimal for comparison
        limit = Decimal(str(tier["limit"]))
        if total_kwh <= limit:
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
    peak_kwh: Decimal,
    offpeak_kwh: Decimal,
    total_kwh: Decimal,
    tariff: Dict[str, Any],
    tariff_type: str
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
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
    """
    energy_cost = Decimal("0.0")
    peak_rate = Decimal("0.0")
    offpeak_rate = Decimal("0.0")
    rate = Decimal("0.0")
    
    if tariff_type == TARIFF_TOU:
        tou_config = tariff.get("tou", {})
        tiers = tou_config.get("tiers", [])
        
        if not tiers:
            _LOGGER.error("No ToU tiers configured, defaulting to 0 rate")
            return (Decimal("0.0"), Decimal("0.0"), Decimal("0.0"), Decimal("0.0"))
            
        selected_tier = select_tier(total_kwh, tiers)
        if not selected_tier:
            return (Decimal("0.0"), Decimal("0.0"), Decimal("0.0"), Decimal("0.0"))
            
        peak_rate = Decimal(str(selected_tier.get("peak_rate", 0)))
        offpeak_rate = Decimal(str(selected_tier.get("offpeak_rate", 0)))
        energy_cost = (peak_kwh * (peak_rate / 100) + 
                      offpeak_kwh * (offpeak_rate / 100))
    else:
        # Standard Tariff
        tiers = tariff.get("tiers", [])
        if not tiers:
            _LOGGER.error("No tiers configured, defaulting to 0 rate")
            return (Decimal("0.0"), Decimal("0.0"), Decimal("0.0"), Decimal("0.0"))
            
        selected_tier = select_tier(total_kwh, tiers)
        if not selected_tier:
            return (Decimal("0.0"), Decimal("0.0"), Decimal("0.0"), Decimal("0.0"))
            
        rate = Decimal(str(selected_tier.get("rate", 0)))
        energy_cost = total_kwh * (rate / 100)
        
    return (energy_cost, peak_rate, offpeak_rate, rate)


def calculate_variable_charges(
    total_kwh: Decimal,
    capacity_rate: float,
    network_rate: float
) -> Decimal:
    """
    Calculate variable charges (capacity + network).
    """
    cap_rate = Decimal(str(capacity_rate))
    net_rate = Decimal(str(network_rate))
    return total_kwh * ((cap_rate + net_rate) / 100)


def calculate_retail_charge(
    total_kwh: Decimal,
    retail_config: Dict[str, Any]
) -> Decimal:
    """
    Calculate retail charge with waiver limit.
    """
    waiver_limit = Decimal(str(retail_config.get("retail_waiver_limit", 600)))
    retail_charge = Decimal(str(retail_config.get("retail", 10.00)))
    
    if total_kwh > waiver_limit:
        return retail_charge
    return Decimal("0.0")


def calculate_afa_charge(
    total_kwh: Decimal,
    afa_config: Dict[str, Any],
    current_month_key: str
) -> Decimal:
    """
    Calculate AFA charge with monthly rate lookup.
    """
    waiver_limit = Decimal(str(afa_config.get("waiver_limit", 600)))
    
    if total_kwh <= waiver_limit:
        return Decimal("0.0")
        
    afa_rates = afa_config.get("rates", {})
    afa_rate_val = afa_rates.get(current_month_key, afa_config.get("rate", 0.0))
    afa_rate = Decimal(str(afa_rate_val))
    
    return total_kwh * (afa_rate / 100)


def calculate_eei_rebate(
    total_kwh: Decimal,
    eei_config: Dict[str, Any]
) -> Decimal:
    """
    Calculate EEI rebate using tiered structure.
    """
    limit = Decimal(str(eei_config.get("limit", 1000)))
    
    if total_kwh > limit:
        return Decimal("0.0")
        
    eei_tiers = eei_config.get("tiers", [])
    
    if eei_tiers:
        selected_tier = select_tier(total_kwh, eei_tiers)
        if selected_tier:
            selected_eei_rate = Decimal(str(selected_tier.get("rate", 0)))
            return total_kwh * (selected_eei_rate / 100)
    
    # Fallback to single rate
    return total_kwh * (Decimal(str(eei_config.get("rate", 0))) / 100)


def calculate_eei_export_rate(
    total_import_kwh: Decimal,
    eei_config: Dict[str, Any]
) -> Decimal:
    """
    Calculate EEI rate for export based on import usage.
    """
    if total_import_kwh <= 0:
        return Decimal("0.0")
        
    # Calculate the EEI rebate for import
    eei_rebate = calculate_eei_rebate(total_import_kwh, eei_config)
    
    # Convert rebate to rate: rebate = kwh * (rate/100), so rate = (rebate * 100) / kwh
    eei_rate = (eei_rebate * 100) / total_import_kwh
    
    return eei_rate


def calculate_kwtbb_tax(
    total_kwh: Decimal,
    base_bill: Decimal,
    kwtbb_config: Dict[str, Any]
) -> Decimal:
    """
    Calculate KWTBB tax on base bill.
    """
    threshold = Decimal(str(kwtbb_config.get("threshold", 300)))
    rate = Decimal(str(kwtbb_config.get("rate", 1.6)))
    
    if total_kwh > threshold:
        return base_bill * (rate / 100)
    return Decimal("0.0")


def calculate_service_tax(
    total_kwh: Decimal,
    base_bill: Decimal,
    service_tax_config: Dict[str, Any]
) -> Decimal:
    """
    Calculate service tax on usage above exemption limit.
    """
    exemption_limit = Decimal(str(service_tax_config.get("exemption_limit", 600)))
    rate = Decimal(str(service_tax_config.get("rate", 8.0)))
    
    if total_kwh <= exemption_limit or total_kwh == 0:
        return Decimal("0.0")
        
    # Calculate taxable portion: charges for usage above exemption limit
    # Taxable ratio = (excess usage) / (total usage)
    taxable_ratio = (total_kwh - exemption_limit) / total_kwh
    taxable_amount = base_bill * taxable_ratio
    
    return taxable_amount * (rate / 100)


def calculate_export_credit(
    peak_kwh: Decimal,
    offpeak_kwh: Decimal,
    total_kwh: Decimal,
    export_kwh: Decimal,
    peak_rate: Decimal,
    offpeak_rate: Decimal,
    variable_rate: float,
    tariff_type: str,
    rate: Decimal = Decimal("0.0"),
    eei_config: Optional[Dict[str, Any]] = None
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    Calculate export credit using peak-first offset algorithm.
    """
    matched_peak = Decimal("0.0")
    matched_offpeak = Decimal("0.0")
    remaining_export = export_kwh
    
    # Variable rate needs to be Decimal
    var_rate = Decimal(str(variable_rate))
    
    # Calculate EEI export rate based on import usage
    eei_rate = Decimal("0.0")
    if eei_config:
        total_import = peak_kwh + offpeak_kwh if tariff_type == TARIFF_TOU else total_kwh
        eei_rate = calculate_eei_export_rate(total_import, eei_config)
    
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
            matched_peak * ((peak_rate + var_rate + eei_rate) / 100) +
            matched_offpeak * ((offpeak_rate + var_rate + eei_rate) / 100)
        )
    else:
        # Standard Tariff
        matched_total = Decimal("0.0")
        if total_kwh > 0:
            matched_total = min(remaining_export, total_kwh)
            remaining_export -= matched_total
            
        excess_export = remaining_export
        matched_peak = matched_total
        
        credit_value = matched_total * ((rate + var_rate + eei_rate) / 100)

    return (credit_value, matched_peak, matched_offpeak, excess_export)
