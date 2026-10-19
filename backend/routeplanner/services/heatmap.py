"""Weather heatmap along the trip corridor for the next 48 hours.

The corridor is every grid cell within HEATMAP_CORRIDOR_MI of any route. Grid
rows are evenly spaced in Web-Mercator y (not latitude) so the browser can
stretch the grid over the map as a single image without distortion. The cell
size grows until the corridor fits in HEATMAP_MAX_CELLS forecast points.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..conf import cfg
from ..domain.geo import MILES_PER_DEG_LAT, LatLng, haversine_mi, min_distance_mi
from ..domain.risk import assess
from ..validation import HeatmapRequest
from . import weather

MIN_CELL_MI = 6.0  # forecast models resolve a few km; finer cells add calls, not detail


@dataclass(frozen=True)
class CorridorGrid:
    south: float
    west: float
    north: float
    east: float
    rows: int
    cols: int
    cells: list[int]  # row-major indices (row 0 = north) of cells inside the corridor
    centers: list[LatLng]  # one per entry in `cells`


def _mercator_y(lat: float | np.ndarray):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def _inverse_mercator(y: np.ndarray) -> np.ndarray:
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def corridor_grid(paths: list[list[LatLng]], radius_mi: float, max_cells: int) -> CorridorGrid:
    points = np.array([p for path in paths for p in path], dtype=float)
    length_mi = sum(haversine_mi(a, b) for path in paths for a, b in zip(path, path[1:]))
    mean_lat = float(points[:, 0].mean())
    cos_lat = max(math.cos(math.radians(mean_lat)), 0.2)

    lat_pad = radius_mi / MILES_PER_DEG_LAT
    lng_pad = radius_mi / (MILES_PER_DEG_LAT * cos_lat)
    south = max(float(points[:, 0].min()) - lat_pad, -80.0)
    north = min(float(points[:, 0].max()) + lat_pad, 80.0)
    west = float(points[:, 1].min()) - lng_pad
    east = float(points[:, 1].max()) + lng_pad
    width_mi = (east - west) * MILES_PER_DEG_LAT * cos_lat
    height_mi = (north - south) * MILES_PER_DEG_LAT
    y_top, y_bottom = float(_mercator_y(north)), float(_mercator_y(south))

    cell_mi = max(MIN_CELL_MI, math.sqrt(max(length_mi, 1.0) * 2 * radius_mi / max_cells))
    for _ in range(25):
        cols = max(2, math.ceil(width_mi / cell_mi))
        rows = max(2, math.ceil(height_mi / cell_mi))
        lngs = west + (np.arange(cols) + 0.5) * (east - west) / cols
        lats = _inverse_mercator(y_top - (np.arange(rows) + 0.5) * (y_top - y_bottom) / rows)
        grid_lat, grid_lng = np.meshgrid(lats, lngs, indexing="ij")
        centers = np.column_stack((grid_lat.ravel(), grid_lng.ravel()))
        inside = min_distance_mi(centers, points) <= radius_mi
        if inside.sum() <= max_cells:
            break
        cell_mi *= 1.15

    cells = np.flatnonzero(inside)
    return CorridorGrid(
        south, west, north, east, rows, cols,
        cells=cells.tolist(),
        centers=[(round(float(lat), 4), round(float(lng), 4)) for lat, lng in centers[cells]],
    )


def build_heatmap(req: HeatmapRequest) -> dict:
    hours = cfg("HEATMAP_HOURS")
    radius = cfg("HEATMAP_CORRIDOR_MI")
    grid = corridor_grid(req.paths, radius, cfg("HEATMAP_MAX_CELLS"))

    start = weather.floor_hour(req.departure.timestamp())
    hour_stamps = [start + h * weather.HOUR_S for h in range(hours + 1)]
    series = weather.fetch_hourly(grid.centers, start, hour_stamps[-1])

    layers: dict[str, list[list[float]]] = {"risk": [], "wind": [], "rain": [], "snow": []}
    for ts in hour_stamps:
        samples = [s.sample(ts) for s in series]
        winds = [weather.classification_wind(x) for x in samples]
        layers["risk"].append(
            [int(assess(w, x.rain_in_hr, x.snow_in_hr, req.load_lb).level) for w, x in zip(winds, samples)]
        )
        layers["wind"].append([round(w, 1) for w in winds])
        layers["rain"].append([round(x.rain_in_hr, 3) for x in samples])
        layers["snow"].append([round(x.snow_in_hr, 3) for x in samples])

    return {
        "bounds": {"south": grid.south, "west": grid.west, "north": grid.north, "east": grid.east},
        "rows": grid.rows,
        "cols": grid.cols,
        "cells": grid.cells,
        "hours": hour_stamps,
        "layers": layers,
        "corridor_mi": radius,
        "load_lb": req.load_lb,
    }
