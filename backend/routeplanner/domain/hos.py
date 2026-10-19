"""Simplified U.S. hours-of-service (HOS) model for property-carrying drivers.

Used to turn "hours of driving" into a realistic clock-time ETA:
  * a 30-minute break once 8 hours of driving have accumulated in a shift
  * 10 consecutive hours off duty after 11 hours of driving
The 14-hour on-duty window and the 60/70-hour weekly limits are not modelled
(an 11h drive + 30 min break always fits inside 14h).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SHIFT_DRIVE_S = 11 * 3600
BREAK_AFTER_S = 8 * 3600
BREAK_S = 30 * 60
REST_S = 10 * 3600


@dataclass(frozen=True)
class RestEvent:
    at_drive_s: float  # cumulative driving time when the stop starts
    duration_s: float
    kind: str


def elapsed_for_drive(drive_s: float, enabled: bool = True) -> float:
    """Wall-clock seconds since departure after `drive_s` seconds of driving.

    At an exact break boundary the stop has not started yet, i.e. the truck
    has just arrived at the stop location.
    """
    if not enabled or drive_s <= 0:
        return max(drive_s, 0.0)
    shifts_done = max(0, math.ceil(drive_s / SHIFT_DRIVE_S - 1e-9) - 1)
    into_shift = drive_s - shifts_done * SHIFT_DRIVE_S
    extra = shifts_done * (BREAK_S + REST_S)
    if into_shift > BREAK_AFTER_S:
        extra += BREAK_S
    return drive_s + extra


def rest_events(total_drive_s: float, enabled: bool = True) -> list[RestEvent]:
    """Every break or rest the driver takes before reaching the destination."""
    if not enabled:
        return []
    events: list[RestEvent] = []
    shift = 0
    while True:
        start = shift * SHIFT_DRIVE_S
        if start + BREAK_AFTER_S >= total_drive_s - 1e-9:
            break
        events.append(RestEvent(start + BREAK_AFTER_S, BREAK_S, "30-min break"))
        if start + SHIFT_DRIVE_S >= total_drive_s - 1e-9:
            break
        events.append(RestEvent(start + SHIFT_DRIVE_S, REST_S, "10-hr rest"))
        shift += 1
    return events
