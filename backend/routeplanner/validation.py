"""Request parsing and validation for the API. Pure: no network calls."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .conf import cfg
from .domain.geo import LatLng, Place

ALLOWED_INTERVALS_MI = (10, 25, 50)
MAX_LOAD_LB = 200_000
MAX_HEATMAP_POINTS = 6000


class ValidationError(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


@dataclass(frozen=True)
class TripRequest:
    origin: Place | str  # a free-text query is geocoded before planning
    destination: Place | str
    departure: datetime
    load_lb: float
    interval_mi: int
    hos: bool = True


@dataclass(frozen=True)
class HeatmapRequest:
    paths: list[list[LatLng]]
    departure: datetime
    load_lb: float


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _valid_latlng(lat: float | None, lng: float | None) -> bool:
    return lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180


def _place(value: Any, field: str, errors: dict[str, str]) -> Place | str | None:
    if isinstance(value, str):
        text = value.strip()
        if len(text) < 2:
            errors[field] = "Enter a location."
            return None
        return text[:200]
    if isinstance(value, dict):
        lat, lng = _number(value.get("lat")), _number(value.get("lng"))
        if not _valid_latlng(lat, lng):
            errors[field] = "Location coordinates are invalid."
            return None
        label = str(value.get("label") or f"{lat:.4f}, {lng:.4f}")[:200]
        return Place(label, lat, lng)
    errors[field] = "Enter a location."
    return None


def _departure(value: Any, errors: dict[str, str]) -> datetime | None:
    if not isinstance(value, str):
        errors["departure"] = "Departure time is required."
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        errors["departure"] = "Departure must be an ISO 8601 date-time."
        return None
    if parsed.tzinfo is None:
        errors["departure"] = "Departure must include a time zone offset."
        return None
    now = datetime.now(timezone.utc)
    max_days = cfg("MAX_DEPARTURE_DAYS_AHEAD")
    if parsed < now - timedelta(hours=2):
        errors["departure"] = "Departure can't be in the past."
    elif parsed > now + timedelta(days=max_days):
        errors["departure"] = f"Departure must be within the next {max_days} days (forecast range)."
    return parsed


def _load(value: Any, errors: dict[str, str]) -> float | None:
    load = _number(value)
    if load is None or not 0 <= load <= MAX_LOAD_LB:
        errors["load_lb"] = f"Load weight must be between 0 and {MAX_LOAD_LB:,} lb."
        return None
    return load


def parse_trip_request(data: Any) -> TripRequest:
    if not isinstance(data, dict):
        raise ValidationError({"body": "Expected a JSON object."})
    errors: dict[str, str] = {}
    origin = _place(data.get("origin"), "origin", errors)
    destination = _place(data.get("destination"), "destination", errors)
    departure = _departure(data.get("departure"), errors)
    load = _load(data.get("load_lb"), errors)

    interval = data.get("interval_mi", 25)
    if interval not in ALLOWED_INTERVALS_MI:
        errors["interval_mi"] = "Checkpoint spacing must be 10, 25 or 50 miles."

    hos = data.get("hos", True)
    if not isinstance(hos, bool):
        errors["hos"] = "hos must be true or false."

    if errors:
        raise ValidationError(errors)
    return TripRequest(origin, destination, departure, load, int(interval), hos)


def parse_heatmap_request(data: Any) -> HeatmapRequest:
    if not isinstance(data, dict):
        raise ValidationError({"body": "Expected a JSON object."})
    errors: dict[str, str] = {}
    paths: list[list[LatLng]] = []
    raw_paths = data.get("paths")
    if not isinstance(raw_paths, list) or not 1 <= len(raw_paths) <= 5:
        errors["paths"] = "Provide between 1 and 5 route paths."
    else:
        for raw in raw_paths:
            path: list[LatLng] = []
            for point in raw if isinstance(raw, list) else []:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    lat, lng = _number(point[0]), _number(point[1])
                    if _valid_latlng(lat, lng):
                        path.append((lat, lng))
            if len(path) < 2:
                errors["paths"] = "Each path needs at least two valid [lat, lng] points."
                break
            paths.append(path)
        if sum(len(p) for p in paths) > MAX_HEATMAP_POINTS:
            errors["paths"] = f"Paths may contain at most {MAX_HEATMAP_POINTS} points in total."
    departure = _departure(data.get("departure"), errors)
    load = _load(data.get("load_lb"), errors)
    if errors:
        raise ValidationError(errors)
    return HeatmapRequest(paths, departure, load)
