"""Synthetic routes and forecasts so the pipeline can be tested without network access."""
from __future__ import annotations

from routeplanner.services.routing import RouteGeometry
from routeplanner.services.weather import HourlySeries

HOUR = 3600


def straight_route(start, end, hours: float, steps: int = 200, roads: str = "I 80") -> RouteGeometry:
    coords = [
        (start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps)
        for i in range(steps + 1)
    ]
    return RouteGeometry(coords, [hours * HOUR / steps] * steps, roads)


def bent_route(start, end, bend, hours: float, roads: str) -> RouteGeometry:
    first = straight_route(start, bend, hours / 2, 100, roads)
    second = straight_route(bend, end, hours / 2, 100, roads)
    return RouteGeometry(first.coords + second.coords[1:], first.seg_seconds + second.seg_seconds, roads)


def series(start_ts: int, hours: int, wind=5.0, rain=0.0, snow=0.0) -> HourlySeries:
    n = hours + 1
    return HourlySeries(
        times=[start_ts + h * HOUR for h in range(n)],
        wind=[wind] * n,
        gust=[wind * 1.3] * n,
        rain=[rain] * n,
        snow=[snow] * n,
        temp=[40.0] * n,
        code=[0] * n,
    )


def storm_north_of(lat_threshold: float, **storm):
    """fake fetch_hourly: calm weather, except a storm at latitudes above the threshold."""

    def fetch(points, start_ts, end_ts):
        start = int(start_ts // HOUR * HOUR)
        hours = int((end_ts - start) // HOUR) + 2
        return [series(start, hours, **(storm if lat > lat_threshold else {})) for lat, _ in points]

    return fetch
