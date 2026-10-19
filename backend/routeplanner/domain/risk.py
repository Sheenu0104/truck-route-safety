"""Weather + load risk classification, exactly as specified in the brief.

Band edges: each band's lower bound is inclusive. Where the brief writes the
top band with ">" (rain > 1.00 in/hr, snow > 3.0 in/hr) the value at the edge
stays in the band below, so 1.00 in/hr of rain is Severe and 1.01 is No Travel.

    Condition  Low      Moderate    High        Severe      No Travel
    Wind       <25      25-34       35-44       45-54       >=55 mph
    Rain       <0.10    0.10-0.25   0.25-0.50   0.50-1.00   >1.00 in/hr
    Snow       <0.5     0.5-1.0     1.0-2.0     2.0-3.0     >3.0 in/hr

Load rules raise (never lower) the result:
    wind >= 55 mph                         -> No Travel (any load)
    wind 45-54 mph and load > 30,000 lb    -> No Travel
    wind 35-44 mph and load > 40,000 lb    -> Severe
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    Risk.LOW: "Low",
    Risk.MODERATE: "Moderate",
    Risk.HIGH: "High",
    Risk.SEVERE: "Severe",
    Risk.NO_TRAVEL: "No Travel",
}

NO_TRAVEL_LOAD_LB = 30_000  # applies in the 45-54 mph band
SEVERE_LOAD_LB = 40_000  # applies in the 35-44 mph band


def classify_wind(mph: float) -> Risk:
    if mph >= 55:
        return Risk.NO_TRAVEL
    if mph >= 45:
        return Risk.SEVERE
    if mph >= 35:
        return Risk.HIGH
    if mph >= 25:
        return Risk.MODERATE
    return Risk.LOW


def classify_rain(in_per_hr: float) -> Risk:
    if in_per_hr > 1.00:
        return Risk.NO_TRAVEL
    if in_per_hr >= 0.50:
        return Risk.SEVERE
    if in_per_hr >= 0.25:
        return Risk.HIGH
    if in_per_hr >= 0.10:
        return Risk.MODERATE
    return Risk.LOW


def classify_snow(in_per_hr: float) -> Risk:
    if in_per_hr > 3.0:
        return Risk.NO_TRAVEL
    if in_per_hr >= 2.0:
        return Risk.SEVERE
    if in_per_hr >= 1.0:
        return Risk.HIGH
    if in_per_hr >= 0.5:
        return Risk.MODERATE
    return Risk.LOW


def load_rule(wind_mph: float, load_lb: float) -> Risk | None:
    """Minimum risk level imposed by wind + load, or None if no load rule applies."""
    if wind_mph >= 55:
        return Risk.NO_TRAVEL
    if 45 <= wind_mph < 55 and load_lb > NO_TRAVEL_LOAD_LB:
        return Risk.NO_TRAVEL
    if 35 <= wind_mph < 45 and load_lb > SEVERE_LOAD_LB:
        return Risk.SEVERE
    return None


@dataclass(frozen=True)
class Assessment:
    level: Risk
    wind: Risk
    rain: Risk
    snow: Risk
    load_rule: Risk | None
    drivers: tuple[str, ...]  # human-readable reasons for `level`


def assess(wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    """Overall risk = the worst of wind, rain, snow and any load rule."""
    wind = classify_wind(wind_mph)
    rain = classify_rain(rain_in_hr)
    snow = classify_snow(snow_in_hr)
    floor = load_rule(wind_mph, load_lb)
    weather_level = max(wind, rain, snow)
    level = max(weather_level, floor) if floor is not None else weather_level

    drivers: list[str] = []
    if level > Risk.LOW:
        if wind == level:
            drivers.append(f"Wind {wind_mph:.0f} mph")
        if rain == level:
            drivers.append(f"Rain {rain_in_hr:.2f} in/hr")
        if snow == level:
            drivers.append(f"Snow {snow_in_hr:.2f} in/hr")
        if floor is not None and floor == level and floor > weather_level:
            drivers.append(f"Wind {wind_mph:.0f} mph with {load_lb:,.0f} lb load")

    return Assessment(level, wind, rain, snow, floor, tuple(drivers))
