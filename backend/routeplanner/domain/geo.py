"""Pure geometry helpers (no I/O). Coordinates are (lat, lng) in degrees."""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import Sequence

import numpy as np

EARTH_RADIUS_MI = 3958.7613
MILES_PER_DEG_LAT = 69.055

LatLng = tuple[float, float]


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lng: float

    @property
    def latlng(self) -> LatLng:
        return (self.lat, self.lng)

    def as_dict(self) -> dict:
        return {"label": self.label, "lat": self.lat, "lng": self.lng}


def haversine_mi(a: LatLng, b: LatLng) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def _bracket(axis: Sequence[float], value: float) -> tuple[int, float]:
    """Index i and fraction t such that value sits t of the way from axis[i] to axis[i+1]."""
    n = len(axis)
    if value <= axis[0]:
        return 0, 0.0
    if value >= axis[-1]:
        return n - 2, 1.0
    i = min(bisect_right(axis, value) - 1, n - 2)
    span = axis[i + 1] - axis[i]
    return i, ((value - axis[i]) / span if span > 0 else 0.0)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


@dataclass
class RouteProfile:
    """A polyline annotated with cumulative distance and driving time at every vertex."""

    coords: list[LatLng]
    miles: list[float]
    drive_s: list[float]

    @classmethod
    def from_segments(cls, coords: Sequence[LatLng], seg_seconds: Sequence[float]) -> "RouteProfile":
        if len(coords) < 2:
            raise ValueError("A route needs at least two coordinates.")
        if len(seg_seconds) != len(coords) - 1:
            raise ValueError("seg_seconds needs exactly one entry per segment.")
        miles, drive = [0.0], [0.0]
        for i in range(1, len(coords)):
            miles.append(miles[-1] + haversine_mi(coords[i - 1], coords[i]))
            drive.append(drive[-1] + max(0.0, seg_seconds[i - 1]))
        return cls(list(coords), miles, drive)

    @property
    def total_miles(self) -> float:
        return self.miles[-1]

    @property
    def total_drive_s(self) -> float:
        return self.drive_s[-1]

    def locate(self, mile: float) -> tuple[float, float, float]:
        """(lat, lng, drive_s) at a distance along the route."""
        i, t = _bracket(self.miles, mile)
        (la, lna), (lb, lnb) = self.coords[i], self.coords[i + 1]
        return _lerp(la, lb, t), _lerp(lna, lnb, t), _lerp(self.drive_s[i], self.drive_s[i + 1], t)

    def locate_drive_time(self, drive_s: float) -> tuple[float, float, float]:
        """(lat, lng, mile) after driving for `drive_s` seconds."""
        i, t = _bracket(self.drive_s, drive_s)
        (la, lna), (lb, lnb) = self.coords[i], self.coords[i + 1]
        return _lerp(la, lb, t), _lerp(lna, lnb, t), _lerp(self.miles[i], self.miles[i + 1], t)

    def slice(self, from_mile: float, to_mile: float) -> list[LatLng]:
        """Sub-polyline between two distances, with interpolated end points."""
        start = self.locate(from_mile)[:2]
        end = self.locate(to_mile)[:2]
        lo = bisect_right(self.miles, from_mile)
        hi = bisect_left(self.miles, to_mile)
        return [start, *self.coords[lo:hi], end]


def checkpoint_miles(total_miles: float, interval_mi: float) -> list[float]:
    """Distances of checkpoints: the origin, every `interval_mi`, and the destination."""
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")
    marks = [0.0]
    k = 1
    while k * interval_mi < total_miles - 1e-6:
        marks.append(k * interval_mi)
        k += 1
    if total_miles > 0:
        marks.append(total_miles)
    return marks


def decimate_indices(miles: Sequence[float], min_spacing_mi: float) -> list[int]:
    """Vertex indices at least `min_spacing_mi` apart (always keeps first and last)."""
    if len(miles) <= 2:
        return list(range(len(miles)))
    keep, last = [0], miles[0]
    for i in range(1, len(miles) - 1):
        if miles[i] - last >= min_spacing_mi:
            keep.append(i)
            last = miles[i]
    keep.append(len(miles) - 1)
    return keep


def decimate(points: Sequence[LatLng], min_spacing_mi: float) -> list[LatLng]:
    if len(points) <= 2:
        return list(points)
    out = [points[0]]
    for p in points[1:-1]:
        if haversine_mi(out[-1], p) >= min_spacing_mi:
            out.append(p)
    out.append(points[-1])
    return out


def _unit_vectors(latlng: np.ndarray) -> np.ndarray:
    lat = np.radians(latlng[:, 0])
    lng = np.radians(latlng[:, 1])
    return np.column_stack((np.cos(lat) * np.cos(lng), np.cos(lat) * np.sin(lng), np.sin(lat)))


def min_distance_mi(queries: Sequence[LatLng] | np.ndarray, targets: Sequence[LatLng] | np.ndarray) -> np.ndarray:
    """Great-circle distance from every query point to its nearest target point."""
    q = _unit_vectors(np.asarray(queries, dtype=float))
    t = _unit_vectors(np.asarray(targets, dtype=float))
    out = np.empty(len(q))
    chunk = max(1, 1_500_000 // max(len(t), 1))
    for start in range(0, len(q), chunk):
        block = q[start : start + chunk]
        chord2 = ((block[:, None, :] - t[None, :, :]) ** 2).sum(axis=2).min(axis=1)
        out[start : start + chunk] = 2 * EARTH_RADIUS_MI * np.arcsin(np.clip(np.sqrt(chord2) / 2, 0, 1))
    return out


def overlap_fraction(a: Sequence[LatLng], b: Sequence[LatLng], tolerance_mi: float = 0.5) -> float:
    """Share of polyline `a` (by sampled length) lying within `tolerance_mi` of polyline `b`."""
    samples = decimate(a, 2.0)
    reference = decimate(b, 0.5)
    distances = min_distance_mi(samples, reference)
    return float((distances <= tolerance_mi).mean())
