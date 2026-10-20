"""Hourly forecasts from Open-Meteo, sampled at arbitrary times.

Open-Meteo semantics (which decide how a time is sampled):
  * wind speed / gusts / temperature are instantaneous at each hour
      -> linearly interpolated between the two surrounding hours
  * rain / showers / snowfall are totals over the PRECEDING hour
      -> the hour bucket that contains the time is used, i.e. the value
         stamped at the next full hour. That total is the rate in in/hr.
Rain = rain + showers (large-scale + convective), in inches.
Snowfall is converted to inches of snow per hour.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from django.core.cache import cache

from ..conf import cfg
from ..domain.geo import LatLng
from .http import UpstreamError, get_json

log = logging.getLogger(__name__)

HOUR_S = 3600
BATCH_SIZE = 50  # locations per Open-Meteo request
HOURLY_FIELDS = ("wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "temperature_2m", "weather_code")


def floor_hour(ts: float) -> int:
    return int(ts // HOUR_S * HOUR_S)


def ceil_hour(ts: float) -> int:
    return int(math.ceil(ts / HOUR_S) * HOUR_S)


@dataclass(frozen=True)
class WeatherSample:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    temp_f: float | None
    code: int | None
    missing: bool  # True if the forecast had no value here (treated as 0)

    def as_dict(self) -> dict:
        return {
            "wind_mph": round(self.wind_mph, 1),
            "gust_mph": round(self.gust_mph, 1),
            "rain_in_hr": round(self.rain_in_hr, 3),
            "snow_in_hr": round(self.snow_in_hr, 3),
            "temp_f": None if self.temp_f is None else round(self.temp_f, 1),
            "code": self.code,
            "missing": self.missing,
        }


def classification_wind(sample: WeatherSample) -> float:
    """The wind value fed into the risk table (sustained by default, see settings)."""
    return sample.gust_mph if cfg("WIND_METRIC") == "gust" else sample.wind_mph


def _interp(values: Sequence[float | None], i: int, t: float) -> tuple[float | None, bool]:
    a = values[i]
    b = values[i + 1] if i + 1 < len(values) else a
    if a is None and b is None:
        return None, True
    if a is None:
        return b, False
    if b is None:
        return a, False
    return a + (b - a) * t, False


@dataclass
class HourlySeries:
    times: list[int]  # unix seconds, one per hour
    wind: list[float | None]
    gust: list[float | None]
    rain: list[float | None]
    snow: list[float | None]
    temp: list[float | None]
    code: list[int | None]

    def sample(self, ts: float) -> WeatherSample:
        n = len(self.times)
        position = (ts - self.times[0]) / HOUR_S
        i = min(max(math.floor(position), 0), max(n - 2, 0))
        t = min(max(position - i, 0.0), 1.0) if n > 1 else 0.0
        bucket = min(max(math.ceil(position - 1e-9), 0), n - 1)

        wind, wind_missing = _interp(self.wind, i, t)
        gust, _ = _interp(self.gust, i, t)
        temp, _ = _interp(self.temp, i, t)
        rain, snow = self.rain[bucket], self.snow[bucket]
        out_of_range = position < -1 or position > n
        return WeatherSample(
            wind_mph=wind or 0.0,
            gust_mph=gust if gust is not None else (wind or 0.0),
            rain_in_hr=rain or 0.0,
            snow_in_hr=snow or 0.0,
            temp_f=temp,
            code=self.code[bucket],
            missing=wind_missing or rain is None or snow is None or out_of_range,
        )


OPEN_METEO_PAUSED_KEY = "weather:open-meteo-paused"
OPEN_METEO_PAUSE_S = 3600


def fetch_hourly(points: Sequence[LatLng], start_ts: float, end_ts: float) -> list[HourlySeries]:
    """One hourly series per input point covering [start_ts, end_ts].

    Open-Meteo is the primary source. Its free tier has a daily request cap
    that is counted per IP address, and cloud hosts share IPs between many
    apps, so when it refuses (429), errors or times out the request falls back
    to MET Norway. After a 429, Open-Meteo is skipped for an hour.
    """
    if not points:
        return []
    start, end = floor_hour(start_ts), ceil_hour(end_ts)
    if not cache.get(OPEN_METEO_PAUSED_KEY):
        try:
            return _fetch_open_meteo(points, start, end)
        except UpstreamError as exc:
            log.warning("Open-Meteo failed (%s); falling back to MET Norway", exc)
            if exc.status == 429:
                cache.set(OPEN_METEO_PAUSED_KEY, True, OPEN_METEO_PAUSE_S)
    return met_norway.fetch_hourly(points, start, end)


def _fetch_open_meteo(points: Sequence[LatLng], start: int, end: int) -> list[HourlySeries]:
    """Points within ~1 km of each other share a forecast (the model grid is
    coarser than that), which keeps the number of API calls down."""
    keys = [(round(lat, 2), round(lng, 2)) for lat, lng in points]
    unique = list(dict.fromkeys(keys))
    batches = [unique[i : i + BATCH_SIZE] for i in range(0, len(unique), BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=min(4, len(batches))) as pool:
        results = list(pool.map(lambda batch: _fetch_batch(batch, start, end), batches))
    by_key: dict[LatLng, HourlySeries] = {}
    for batch, series in zip(batches, results):
        by_key.update(zip(batch, series))
    return [by_key[key] for key in keys]


def _iso_hour(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _fetch_batch(batch: list[LatLng], start: int, end: int) -> list[HourlySeries]:
    params = {
        "latitude": ",".join(f"{lat:.2f}" for lat, _ in batch),
        "longitude": ",".join(f"{lng:.2f}" for _, lng in batch),
        "hourly": ",".join(HOURLY_FIELDS),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "temperature_unit": "fahrenheit",
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_hour": _iso_hour(start),
        "end_hour": _iso_hour(end),
    }
    data = get_json(cfg("OPEN_METEO_URL"), params, service="Weather (Open-Meteo)", cache_ttl=900)
    items = data if isinstance(data, list) else [data]
    if len(items) != len(batch):
        raise UpstreamError("Weather (Open-Meteo)", f"expected {len(batch)} locations, got {len(items)}")
    return [parse_location(item) for item in items]


_PRECIP_TO_INCH = {"inch": 1.0, "in": 1.0, "mm": 1 / 25.4, "cm": 1 / 2.54}
_SPEED_TO_MPH = {"mph": 1.0, "km/h": 0.621371, "m/s": 2.236936, "kn": 1.150779}


def parse_location(item: dict) -> HourlySeries:
    hourly = item.get("hourly") or {}
    units = item.get("hourly_units") or {}
    times = [int(t) for t in hourly.get("time", [])]
    if not times:
        raise UpstreamError("Weather (Open-Meteo)", "response contained no hourly data")

    def column(name: str, factors: dict[str, float]) -> list[float | None]:
        factor = factors.get(str(units.get(name, "")).lower(), 1.0)
        values = hourly.get(name) or [None] * len(times)
        return [None if v is None else float(v) * factor for v in values]

    rain = column("rain", _PRECIP_TO_INCH)
    showers = column("showers", _PRECIP_TO_INCH)
    temp_unit_f = "f" in str(units.get("temperature_2m", "°F")).lower()
    temps = column("temperature_2m", {})
    return HourlySeries(
        times=times,
        wind=column("wind_speed_10m", _SPEED_TO_MPH),
        gust=column("wind_gusts_10m", _SPEED_TO_MPH),
        rain=[None if r is None and s is None else (r or 0.0) + (s or 0.0) for r, s in zip(rain, showers)],
        snow=column("snowfall", _PRECIP_TO_INCH),
        temp=temps if temp_unit_f else [None if t is None else t * 9 / 5 + 32 for t in temps],
        code=[None if c is None else int(c) for c in (hourly.get("weather_code") or [None] * len(times))],
    )


# Imported last: met_norway builds HourlySeries objects defined above.
from . import met_norway  # noqa: E402
