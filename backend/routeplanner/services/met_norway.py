"""Fallback forecasts from MET Norway's Locationforecast API (free, global, no key).

Used when Open-Meteo is unavailable. MET Norway's terms ask for:
  * an identifying User-Agent with contact details
  * coordinates with at most 4 decimals
  * one location per request, and caching of responses
so nearby points share one request, and points are snapped to a coarser grid
until there are at most MAX_REQUESTS distinct locations.

Data semantics (mapped onto HourlySeries, see weather.py):
  * wind_speed / wind_speed_of_gust (m/s) and air_temperature (°C) are
    instantaneous -> interpolated onto the hour stamps
  * next_1_hours.precipitation_amount (mm) covers [t, t+1h) -> the bucket
    stamped t+1h. Beyond ~2.5 days only next_6_hours exists; its amount is
    spread evenly over the six hourly buckets.
  * MET gives total precipitation only. It is split into rain or snow using
    the period's symbol code ("snow", "sleet") or, failing that, temperature.
    Snow depth uses Open-Meteo's own conversion: 1 mm water = 0.7 cm snow.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Sequence

import numpy as np
from django.conf import settings

from ..domain.geo import LatLng
from .http import get_json
from .weather import HOUR_S, HourlySeries

MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
MAX_REQUESTS = 150
GRID_STEPS_DEG = (0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
MPS_TO_MPH = 2.236936
MM_TO_IN = 1 / 25.4
SNOW_CM_PER_MM = 0.7
SNOW_TEMP_C = 0.5  # with no symbol, precipitation at or below this is snow
DEFAULT_USER_AGENT = "TruckRouteSafety/1.0 (+https://github.com/Sheenu0104/truck-route-safety)"


def _user_agent() -> str:
    return settings.ROUTEPLANNER.get("MET_USER_AGENT") or DEFAULT_USER_AGENT


def snap(points: Sequence[LatLng], max_locations: int = MAX_REQUESTS) -> list[LatLng]:
    """Each point's request location: the finest grid that needs <= max_locations requests."""
    for step in GRID_STEPS_DEG:
        keys = [(round(round(lat / step) * step, 4), round(round(lng / step) * step, 4)) for lat, lng in points]
        if len(set(keys)) <= max_locations:
            return keys
    return keys


def fetch_hourly(points: Sequence[LatLng], start: int, end: int) -> list[HourlySeries]:
    keys = snap(points)
    unique = list(dict.fromkeys(keys))

    def load(key: LatLng) -> HourlySeries:
        data = get_json(
            MET_URL,
            {"lat": f"{key[0]:.4f}", "lon": f"{key[1]:.4f}"},
            service="Weather (MET Norway)",
            cache_ttl=1800,
            headers={"User-Agent": _user_agent()},
        )
        return parse(data, start, end)

    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        series = dict(zip(unique, pool.map(load, unique)))
    return [series[key] for key in keys]


def _unix(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _is_snow(symbol: str | None, temp_c: float | None) -> float:
    """Share of precipitation that falls as snow (0, 0.5 or 1)."""
    symbol = (symbol or "").lower()
    if "snow" in symbol:
        return 1.0
    if "sleet" in symbol:
        return 0.5
    if symbol:
        return 0.0
    return 1.0 if temp_c is not None and temp_c <= SNOW_TEMP_C else 0.0


def parse(data: dict, start: int, end: int) -> HourlySeries:
    timeseries = (data.get("properties") or {}).get("timeseries") or []
    inst_t, wind, gust, temp = [], [], [], []
    buckets: dict[int, tuple[float, str | None]] = {}  # bucket end hour -> (mm in that hour, symbol)

    for entry in timeseries:
        t = int(_unix(entry["time"]))
        block = entry.get("data") or {}
        details = (block.get("instant") or {}).get("details") or {}
        if "wind_speed" in details:
            inst_t.append(t)
            wind.append(details["wind_speed"] * MPS_TO_MPH)
            gust.append(details.get("wind_speed_of_gust", details["wind_speed"]) * MPS_TO_MPH)
            temp.append(details.get("air_temperature", np.nan))
        if "next_1_hours" in block:
            period = block["next_1_hours"]
            amount = (period.get("details") or {}).get("precipitation_amount")
            if amount is not None:
                buckets[t + HOUR_S] = (float(amount), (period.get("summary") or {}).get("symbol_code"))
        elif "next_6_hours" in block:
            period = block["next_6_hours"]
            amount = (period.get("details") or {}).get("precipitation_amount")
            if amount is not None:
                for k in range(1, 7):
                    buckets.setdefault(t + k * HOUR_S, (float(amount) / 6, (period.get("summary") or {}).get("symbol_code")))

    hours = list(range(start, end + HOUR_S, HOUR_S))
    if not inst_t:
        empty = [None] * len(hours)
        return HourlySeries(hours, empty, empty, empty, empty, empty, empty)

    def interp(values: list[float]) -> list[float | None]:
        out = np.interp(hours, inst_t, values, left=np.nan, right=np.nan)
        return [None if np.isnan(v) else float(v) for v in out]

    wind_h, gust_h, temp_c = interp(wind), interp(gust), interp(temp)
    rain_h: list[float | None] = []
    snow_h: list[float | None] = []
    for h, t_c in zip(hours, temp_c):
        bucket = buckets.get(h)
        if bucket is None:
            rain_h.append(None)
            snow_h.append(None)
            continue
        mm, symbol = bucket
        snow_share = _is_snow(symbol, t_c)
        rain_h.append(mm * (1 - snow_share) * MM_TO_IN)
        snow_h.append(mm * snow_share * SNOW_CM_PER_MM / 2.54)

    return HourlySeries(
        times=hours,
        wind=wind_h,
        gust=gust_h,
        rain=rain_h,
        snow=snow_h,
        temp=[None if c is None else c * 9 / 5 + 32 for c in temp_c],
        code=[None] * len(hours),
    )
