"""Turns per-checkpoint risk into per-route exposure, then ranks routes.

Exposure: each checkpoint stands for the stretch of road that is closer to it
than to any other checkpoint (half-way to its neighbours). So with 25-mile
spacing a mid-route checkpoint covers 25 miles, and the route's miles add up
exactly to its length.

Ranking (from the brief), compared in order until one differs:
  0. fewest No-Travel miles      (added: No Travel is worse than Severe)
  1. fewest Severe miles
  2. fewest High miles
  3. lowest average risk         (distance-weighted, Low=0 ... No Travel=4)
  4. shortest travel time        (door to door, including required rest)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .risk import Risk


@dataclass(frozen=True)
class ExposureInterval:
    start_mi: float
    end_mi: float
    level: Risk

    @property
    def miles(self) -> float:
        return self.end_mi - self.start_mi


def exposure_intervals(marks: Sequence[float], levels: Sequence[Risk]) -> list[ExposureInterval]:
    if len(marks) != len(levels) or not marks:
        raise ValueError("Need one risk level per checkpoint.")
    n = len(marks)
    out: list[ExposureInterval] = []
    for i, (mile, level) in enumerate(zip(marks, levels)):
        start = marks[0] if i == 0 else (marks[i - 1] + mile) / 2
        end = marks[-1] if i == n - 1 else (mile + marks[i + 1]) / 2
        if end > start:
            out.append(ExposureInterval(start, end, Risk(level)))
    return out


def merge_intervals(intervals: Sequence[ExposureInterval]) -> list[ExposureInterval]:
    """Join neighbouring intervals that share a risk level (for drawing)."""
    merged: list[ExposureInterval] = []
    for iv in intervals:
        if merged and merged[-1].level == iv.level:
            merged[-1] = ExposureInterval(merged[-1].start_mi, iv.end_mi, iv.level)
        else:
            merged.append(iv)
    return merged


@dataclass(frozen=True)
class RouteScore:
    route_id: str
    miles_by_level: tuple[float, ...]  # indexed by Risk
    avg_risk: float
    duration_s: float

    @property
    def no_travel_miles(self) -> float:
        return self.miles_by_level[Risk.NO_TRAVEL]

    @property
    def severe_miles(self) -> float:
        return self.miles_by_level[Risk.SEVERE]

    @property
    def high_miles(self) -> float:
        return self.miles_by_level[Risk.HIGH]

    @property
    def max_level(self) -> Risk:
        for level in reversed(Risk):
            if self.miles_by_level[level] > 0:
                return level
        return Risk.LOW


def score_route(route_id: str, intervals: Sequence[ExposureInterval], duration_s: float) -> RouteScore:
    miles = [0.0] * len(Risk)
    weighted = total = 0.0
    for iv in intervals:
        miles[iv.level] += iv.miles
        weighted += int(iv.level) * iv.miles
        total += iv.miles
    return RouteScore(route_id, tuple(miles), weighted / total if total else 0.0, duration_s)


def _fmt_miles(v: float) -> str:
    return f"{v:,.0f} mi" if v >= 10 else f"{v:.1f} mi"


def _fmt_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    phrase: str  # completes "Route A has ..."
    value: Callable[[RouteScore], float]
    resolution: float  # differences smaller than this count as a tie
    fmt: Callable[[float], str]


CRITERIA: tuple[Criterion, ...] = (
    Criterion("no_travel_miles", "No-Travel miles", "fewer No-Travel miles", lambda s: s.no_travel_miles, 0.1, _fmt_miles),
    Criterion("severe_miles", "Severe miles", "fewer Severe-risk miles", lambda s: s.severe_miles, 0.1, _fmt_miles),
    Criterion("high_miles", "High miles", "fewer High-risk miles", lambda s: s.high_miles, 0.1, _fmt_miles),
    Criterion("avg_risk", "Average risk", "lower average risk", lambda s: s.avg_risk, 0.01, lambda v: f"{v:.2f}"),
    Criterion("duration_s", "Travel time", "shorter travel time", lambda s: s.duration_s, 60, _fmt_duration),
)


def _rounded(score: RouteScore, criterion: Criterion) -> int:
    return round(criterion.value(score) / criterion.resolution)


def rank_routes(scores: Sequence[RouteScore]) -> list[RouteScore]:
    return sorted(scores, key=lambda s: (tuple(_rounded(s, c) for c in CRITERIA), s.route_id))


def decisive_criterion(a: RouteScore, b: RouteScore) -> Criterion | None:
    for c in CRITERIA:
        if _rounded(a, c) != _rounded(b, c):
            return c
    return None


def explain(ranked: Sequence[RouteScore]) -> str:
    """One sentence saying why the top route beat each of the others."""
    best = ranked[0]
    if len(ranked) == 1:
        return f"Route {best.route_id} is the only distinct route found."
    parts = []
    for other in ranked[1:]:
        c = decisive_criterion(best, other)
        if c is None:
            parts.append(f"ties with Route {other.route_id} on every criterion")
        else:
            parts.append(
                f"{c.phrase} than Route {other.route_id} "
                f"({c.fmt(c.value(best))} vs {c.fmt(c.value(other))})"
            )
    return f"Route {best.route_id} has " + "; ".join(parts) + "."
