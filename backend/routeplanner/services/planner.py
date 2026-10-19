"""Builds a trip plan: routes -> checkpoints with ETAs -> weather -> risk -> recommendation."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import hos
from ..domain.geo import LatLng, Place, RouteProfile, checkpoint_miles, decimate, decimate_indices, haversine_mi
from ..domain.risk import Assessment, assess
from ..domain.scoring import (
    CRITERIA,
    ExposureInterval,
    RouteScore,
    exposure_intervals,
    explain,
    merge_intervals,
    rank_routes,
    score_route,
)
from ..validation import TripRequest, ValidationError
from . import routing, weather

PATH_POINTS_TARGET = 1500  # vertices per route sent to the browser


@dataclass
class Checkpoint:
    index: int
    mile: float
    lat: float
    lng: float
    drive_s: float
    eta: float
    sample: weather.WeatherSample | None = None
    assessment: Assessment | None = None


@dataclass
class RouteDraft:
    id: str
    geometry: routing.RouteGeometry
    profile: RouteProfile
    checkpoints: list[Checkpoint]
    duration_s: float
    intervals: list[ExposureInterval] = field(default_factory=list)


def plan_trip(req: TripRequest) -> dict:
    origin, destination = req.origin, req.destination
    assert isinstance(origin, Place) and isinstance(destination, Place), "places must be geocoded first"
    if haversine_mi(origin.latlng, destination.latlng) < 1:
        raise ValidationError({"destination": "Origin and destination are less than a mile apart."})

    departure = req.departure.timestamp()
    geometries = routing.fetch_routes(origin.latlng, destination.latlng)
    drafts = [_draft(chr(ord("A") + i), g, departure, req) for i, g in enumerate(geometries)]
    _attach_weather(drafts, req.load_lb, departure)

    scores: dict[str, RouteScore] = {}
    for draft in drafts:
        draft.intervals = exposure_intervals(
            [c.mile for c in draft.checkpoints], [c.assessment.level for c in draft.checkpoints]
        )
        scores[draft.id] = score_route(draft.id, draft.intervals, draft.duration_s)

    ranked = rank_routes(list(scores.values()))
    rank_of = {score.route_id: position for position, score in enumerate(ranked, start=1)}
    best = ranked[0]

    return {
        "origin": origin.as_dict(),
        "destination": destination.as_dict(),
        "departure": int(departure),
        "load_lb": req.load_lb,
        "interval_mi": req.interval_mi,
        "hos": req.hos,
        "routes": [
            _serialize_route(d, scores[d.id], rank_of[d.id], d.id == best.route_id, departure, req.hos)
            for d in drafts
        ],
        "recommendation": {
            "route_id": best.route_id,
            "reason": explain(ranked),
            "criteria": [c.label for c in CRITERIA],
            "warnings": _warnings(drafts, best, len(geometries)),
        },
        "sources": {"routing": "OSRM", "weather": "Open-Meteo", "geocoding": "Photon / OpenStreetMap"},
    }


def _draft(route_id: str, geometry: routing.RouteGeometry, departure: float, req: TripRequest) -> RouteDraft:
    profile = RouteProfile.from_segments(geometry.coords, geometry.seg_seconds)
    checkpoints = []
    for index, mile in enumerate(checkpoint_miles(profile.total_miles, req.interval_mi)):
        lat, lng, drive_s = profile.locate(mile)
        eta = departure + hos.elapsed_for_drive(drive_s, req.hos)
        checkpoints.append(Checkpoint(index, mile, lat, lng, drive_s, eta))
    duration = hos.elapsed_for_drive(profile.total_drive_s, req.hos)
    return RouteDraft(route_id, geometry, profile, checkpoints, duration)


def _attach_weather(drafts: list[RouteDraft], load_lb: float, departure: float) -> None:
    """One batched forecast lookup for every checkpoint, each read at its own ETA."""
    checkpoints = [c for d in drafts for c in d.checkpoints]
    last_eta = max(c.eta for c in checkpoints)
    series = weather.fetch_hourly([(c.lat, c.lng) for c in checkpoints], departure, last_eta + weather.HOUR_S)
    for checkpoint, forecast in zip(checkpoints, series):
        sample = forecast.sample(checkpoint.eta)
        checkpoint.sample = sample
        checkpoint.assessment = assess(
            weather.classification_wind(sample), sample.rain_in_hr, sample.snow_in_hr, load_lb
        )


def _warnings(drafts: list[RouteDraft], best: RouteScore, route_count: int) -> list[str]:
    warnings = []
    if best.no_travel_miles > 0:
        warnings.append(
            "Every route crosses No-Travel conditions at this departure time. "
            "Consider delaying the trip; use the forecast slider to find a safer window."
        )
    elif best.severe_miles > 0:
        warnings.append(f"Even the recommended route has {best.severe_miles:.0f} mi of Severe conditions.")
    if route_count < 3:
        warnings.append(f"Only {route_count} distinct route(s) exist between these points.")
    if any(c.sample and c.sample.missing for d in drafts for c in d.checkpoints):
        warnings.append("Forecast data was missing at some checkpoints; those values were treated as 0.")
    return warnings


def _round_path(points: list[LatLng]) -> list[list[float]]:
    return [[round(lat, 5), round(lng, 5)] for lat, lng in points]


def _timed_path(profile: RouteProfile, departure: float, hos_enabled: bool, spacing: float):
    """Simplified polyline plus the clock time the truck reaches each vertex.

    Rest stops are inserted as two identical points (arrive, leave), so the
    browser can interpolate the truck's position at any time without knowing
    the HOS rules.
    """
    events = hos.rest_events(profile.total_drive_s, hos_enabled)
    points: list[LatLng] = []
    times: list[float] = []
    next_event = 0
    for i in decimate_indices(profile.miles, spacing):
        drive_s = profile.drive_s[i]
        while next_event < len(events) and events[next_event].at_drive_s < drive_s:
            event = events[next_event]
            lat, lng, _ = profile.locate_drive_time(event.at_drive_s)
            arrive = departure + hos.elapsed_for_drive(event.at_drive_s, hos_enabled)
            points += [(lat, lng), (lat, lng)]
            times += [arrive, arrive + event.duration_s]
            next_event += 1
        points.append(profile.coords[i])
        times.append(departure + hos.elapsed_for_drive(drive_s, hos_enabled))
    return _round_path(points), [int(round(t)) for t in times]


def _serialize_route(
    draft: RouteDraft, score: RouteScore, rank: int, recommended: bool, departure: float, hos_enabled: bool
) -> dict:
    profile = draft.profile
    spacing = max(0.2, profile.total_miles / PATH_POINTS_TARGET)
    path, path_times = _timed_path(profile, departure, hos_enabled, spacing)

    rest_stops = []
    for event in hos.rest_events(profile.total_drive_s, hos_enabled):
        lat, lng, mile = profile.locate_drive_time(event.at_drive_s)
        start = departure + hos.elapsed_for_drive(event.at_drive_s, hos_enabled)
        rest_stops.append({
            "kind": event.kind,
            "mile": round(mile, 1),
            "lat": round(lat, 5),
            "lng": round(lng, 5),
            "start": int(start),
            "end": int(start + event.duration_s),
        })

    return {
        "id": draft.id,
        "name": f"Route {draft.id}",
        "roads": draft.geometry.roads,
        "distance_mi": round(profile.total_miles, 1),
        "drive_s": int(profile.total_drive_s),
        "duration_s": int(draft.duration_s),
        "departure": int(departure),
        "arrival": int(departure + draft.duration_s),
        "path": path,
        "path_times": path_times,
        "segments": [
            {
                "level": int(iv.level),
                "from_mile": round(iv.start_mi, 1),
                "to_mile": round(iv.end_mi, 1),
                "path": _round_path(decimate(profile.slice(iv.start_mi, iv.end_mi), spacing)),
            }
            for iv in merge_intervals(draft.intervals)
        ],
        "checkpoints": [_serialize_checkpoint(c) for c in draft.checkpoints],
        "rest_stops": rest_stops,
        "stats": {
            "miles_by_level": [round(m, 1) for m in score.miles_by_level],
            "no_travel_miles": round(score.no_travel_miles, 1),
            "severe_miles": round(score.severe_miles, 1),
            "high_miles": round(score.high_miles, 1),
            "avg_risk": round(score.avg_risk, 2),
            "max_level": int(score.max_level),
        },
        "rank": rank,
        "recommended": recommended,
    }


def _serialize_checkpoint(c: Checkpoint) -> dict:
    a = c.assessment
    return {
        "index": c.index,
        "mile": round(c.mile, 1),
        "lat": round(c.lat, 5),
        "lng": round(c.lng, 5),
        "eta": int(round(c.eta)),
        "weather": c.sample.as_dict(),
        "risk": {
            "level": int(a.level),
            "label": a.level.label,
            "wind": int(a.wind),
            "rain": int(a.rain),
            "snow": int(a.snow),
            "load_rule": None if a.load_rule is None else int(a.load_rule),
            "drivers": list(a.drivers),
        },
    }
