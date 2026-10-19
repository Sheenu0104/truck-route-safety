"""Route options from an OSRM server, with speeds adjusted for a loaded truck.

OSRM returns at most one or two alternatives, and often none on long trips.
When it returns fewer than three distinct routes, extra candidates are made by
routing through a via point offset sideways from the fastest route; a candidate
is kept only if it is meaningfully different and not absurdly slow.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterator

from ..conf import cfg
from ..domain.geo import MILES_PER_DEG_LAT, LatLng, RouteProfile, haversine_mi, overlap_fraction
from .http import UpstreamError, get_json

log = logging.getLogger(__name__)

NO_ROUTE_CODES = {"NoRoute", "NoSegment", "NoMatch"}
MAX_DETOUR_RATIO = 1.8  # alternatives slower than 1.8x the fastest are not useful
MAX_OVERLAP = 0.8  # a route sharing >80% of its length with another is a duplicate


class NoRouteError(Exception):
    pass


@dataclass
class RouteGeometry:
    coords: list[LatLng]
    seg_seconds: list[float]  # truck driving time for each segment of `coords`
    roads: str  # main roads, e.g. "I 70, I 15"
    via: LatLng | None = None

    @property
    def drive_s(self) -> float:
        return sum(self.seg_seconds)


def fetch_routes(origin: LatLng, destination: LatLng, count: int | None = None) -> list[RouteGeometry]:
    """Up to `count` distinct routes, fastest first."""
    count = count or cfg("ROUTE_COUNT")
    routes = _distinct(_request([origin, destination], alternatives=count - 1))
    if not routes:
        raise NoRouteError("No drivable route was found between these locations.")
    if len(routes) < count:
        routes = _add_detour_alternatives(routes, origin, destination, count)
    routes.sort(key=lambda r: r.drive_s)
    return routes[:count]


def _distinct(routes: list[RouteGeometry]) -> list[RouteGeometry]:
    accepted: list[RouteGeometry] = []
    for route in sorted(routes, key=lambda r: r.drive_s):
        if _is_distinct(route, accepted):
            accepted.append(route)
    return accepted


def _is_distinct(candidate: RouteGeometry, accepted: list[RouteGeometry]) -> bool:
    return all(overlap_fraction(candidate.coords, other.coords) <= MAX_OVERLAP for other in accepted)


def _add_detour_alternatives(
    routes: list[RouteGeometry], origin: LatLng, destination: LatLng, count: int
) -> list[RouteGeometry]:
    fastest = min(r.drive_s for r in routes)

    def attempt(via: LatLng) -> RouteGeometry | None:
        try:
            found = _request([origin, via, destination], alternatives=0)
        except (UpstreamError, NoRouteError) as exc:
            log.info("Detour via %s failed: %s", via, exc)
            return None
        if not found:
            return None
        found[0].via = via
        return found[0]

    with ThreadPoolExecutor(max_workers=3) as pool:
        candidates = list(pool.map(attempt, _via_points(routes[0], origin, destination)))

    for candidate in candidates:
        if len(routes) >= count:
            break
        if candidate is None or candidate.drive_s > fastest * MAX_DETOUR_RATIO:
            continue
        if _is_distinct(candidate, routes):
            routes.append(candidate)
    return routes


def _via_points(route: RouteGeometry, origin: LatLng, destination: LatLng) -> Iterator[LatLng]:
    """Points pushed sideways from the fastest route, perpendicular to the trip direction."""
    profile = RouteProfile.from_segments(route.coords, route.seg_seconds)
    total = profile.total_miles
    offset_mi = min(max(total * 0.12, 8.0), 120.0)
    kx = max(math.cos(math.radians((origin[0] + destination[0]) / 2)), 0.2)
    dx = (destination[1] - origin[1]) * kx
    dy = destination[0] - origin[0]
    norm = math.hypot(dx, dy) or 1.0
    px, py = -dy / norm, dx / norm  # unit vector perpendicular to the direction of travel
    for fraction, scale in ((0.5, 1.0), (0.5, -1.0), (0.35, 1.0), (0.65, -1.0), (0.5, 2.0), (0.5, -2.0)):
        lat, lng, _ = profile.locate(total * fraction)
        degrees = offset_mi * scale / MILES_PER_DEG_LAT
        yield (lat + py * degrees, lng + px * degrees / kx)


def _request(points: list[LatLng], alternatives: int) -> list[RouteGeometry]:
    coords = ";".join(f"{lng:.5f},{lat:.5f}" for lat, lng in points)
    url = f"{cfg('OSRM_BASE_URL').rstrip('/')}/route/v1/driving/{coords}"
    params = {
        "alternatives": str(alternatives) if alternatives > 0 else "false",
        "steps": "true",
        "geometries": "geojson",
        "overview": "false",
    }
    try:
        data = get_json(url, params, service="Routing (OSRM)", cache_ttl=3600)
    except UpstreamError as exc:
        if isinstance(exc.payload, dict) and exc.payload.get("code") in NO_ROUTE_CODES:
            raise NoRouteError("No drivable route was found between these locations.") from exc
        raise

    code = data.get("code")
    if code in NO_ROUTE_CODES:
        raise NoRouteError("No drivable route was found between these locations.")
    if code != "Ok":
        raise UpstreamError("Routing (OSRM)", data.get("message") or f"unexpected response code {code!r}")
    return [route for route in (_parse_route(raw) for raw in data.get("routes", [])) if route]


def _truck_seconds(car_seconds: float, miles: float, max_mph: float) -> float:
    """OSRM's car timing, but never faster than the truck speed cap."""
    return max(float(car_seconds or 0.0), miles / max_mph * 3600)


def _parse_route(raw: dict) -> RouteGeometry | None:
    """Flatten OSRM legs/steps into one polyline with per-segment driving time."""
    max_mph = cfg("TRUCK_MAX_SPEED_MPH")
    coords: list[LatLng] = []
    seconds: list[float] = []
    for leg in raw.get("legs", []):
        for step in leg.get("steps", []):
            points = [(lat, lng) for lng, lat in (step.get("geometry") or {}).get("coordinates", [])]
            if len(points) < 2:
                continue
            seg_miles = [haversine_mi(points[k - 1], points[k]) for k in range(1, len(points))]
            step_miles = sum(seg_miles)
            if step_miles <= 0:
                continue
            step_seconds = _truck_seconds(step.get("duration", 0.0), step_miles, max_mph)
            if not coords:
                coords.append(points[0])
            elif coords[-1] != points[0]:
                coords.append(points[0])
                seconds.append(0.0)
            for point, miles in zip(points[1:], seg_miles):
                coords.append(point)
                seconds.append(step_seconds * miles / step_miles)
    if len(coords) < 2:
        return None
    roads = [
        name.strip()
        for leg in raw.get("legs", [])
        for name in (leg.get("summary") or "").split(",")
        if name.strip()
    ]
    return RouteGeometry(coords, seconds, ", ".join(dict.fromkeys(roads)))
