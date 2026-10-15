"""SYNTHETIC fixtures transcribed from booklet Tables 4.1 and Sections 4.3-4.4.

These are declared demonstration inputs, not Omani statistics. Partner codes
are fictional ("PARTNER_A" etc.) and must never be mapped to real countries.
"""

from datetime import date
from decimal import Decimal

from app.domain.quantities import GWH, MILLION_M3, OMR, TONNE, Measurement, Period

NATIONAL = "OM"
YEAR_1 = Period(date(2001, 1, 1), date(2001, 12, 31))  # abstract synthetic years
YEAR_2 = Period(date(2002, 1, 1), date(2002, 12, 31))
COMMODITY = "SYNTH_COMMODITY"


def m(value: str | None, unit, period=YEAR_2, commodity: str | None = None) -> Measurement:
    return Measurement(
        value=None if value is None else Decimal(value),
        unit=unit,
        period=period,
        coverage=NATIONAL,
        commodity=commodity,
    )


# Table 4.1 -------------------------------------------------------------
ELECTRICITY_GENERATION_Y1 = m("48000", GWH, YEAR_1)
ELECTRICITY_GENERATION_Y2 = m("50100", GWH, YEAR_2)
WATER_CONSUMPTION_Y1 = m("330", MILLION_M3, YEAR_1)
WATER_CONSUMPTION_Y2 = m("343", MILLION_M3, YEAR_2)

# Section 4.3 -----------------------------------------------------------
PRODUCTION = m("100000", TONNE, commodity=COMMODITY)
IMPORTS = m("80000", TONNE, commodity=COMMODITY)
EXPORTS = m("20000", TONNE, commodity=COMMODITY)
PARTNER_IMPORTS = {
    "PARTNER_A": m("48000", TONNE, commodity=COMMODITY),
    "PARTNER_B": m("20000", TONNE, commodity=COMMODITY),
    "PARTNER_C": m("12000", TONNE, commodity=COMMODITY),
}

# Section 4.4 -----------------------------------------------------------
IMPORT_VALUE = m("40000000", OMR, commodity=COMMODITY)
EXPORT_VALUE = m("12000000", OMR, commodity=COMMODITY)
