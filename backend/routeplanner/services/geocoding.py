"""Place search via Photon (OpenStreetMap data, no API key)."""
from __future__ import annotations

import re

from ..conf import cfg
from ..domain.geo import Place
from ..validation import ValidationError
from .http import get_json

_COORDS = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


def _label(props: dict) -> str:
    name = props.get("name") or " ".join(p for p in (props.get("housenumber"), props.get("street")) if p)
    parts = [name, props.get("city"), props.get("state"), props.get("countrycode") or props.get("country")]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen) or "Unnamed place"


def search(query: str, limit: int = 6) -> list[Place]:
    """Free-text place search. "lat, lng" input is returned as-is."""
    match = _COORDS.match(query)
    if match:
        lat, lng = float(match.group(1)), float(match.group(2))
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return [Place(f"{lat:.4f}, {lng:.4f}", lat, lng)]

    data = get_json(
        cfg("GEOCODER_URL"),
        {"q": query, "limit": limit, "lang": "en"},
        service="Geocoder",
        cache_ttl=24 * 3600,
    )
    results: list[Place] = []
    labels: set[str] = set()
    for feature in data.get("features", []):
        try:
            lng, lat = feature["geometry"]["coordinates"][:2]
        except (KeyError, TypeError, ValueError):
            continue
        label = _label(feature.get("properties") or {})
        if label not in labels:
            labels.add(label)
            results.append(Place(label, float(lat), float(lng)))
    return results


def resolve(value: Place | str, field: str) -> Place:
    """Turn user input into a Place, geocoding free text to its best match."""
    if isinstance(value, Place):
        return value
    matches = search(value, limit=1)
    if not matches:
        raise ValidationError({field: f'No location found for "{value}".'})
    return matches[0]
