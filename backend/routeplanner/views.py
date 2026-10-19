"""JSON API endpoints."""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from functools import wraps
from typing import Callable

from django.http import HttpRequest, JsonResponse

from .services import geocoding, heatmap, planner
from .services.http import UpstreamError
from .services.routing import NoRouteError
from .validation import ValidationError, parse_heatmap_request, parse_trip_request

log = logging.getLogger(__name__)


def _error(message: str, status: int, **extra) -> JsonResponse:
    return JsonResponse({"error": message, **extra}, status=status)


def api_view(method: str) -> Callable:
    """Restrict the HTTP method and map domain errors to clean JSON responses."""

    def decorator(view: Callable[[HttpRequest], dict]) -> Callable[[HttpRequest], JsonResponse]:
        @wraps(view)
        def wrapper(request: HttpRequest) -> JsonResponse:
            if request.method != method:
                return _error("Method not allowed.", 405)
            try:
                return JsonResponse(view(request))
            except ValidationError as exc:
                return _error("Please check the highlighted fields.", 400, fields=exc.errors)
            except NoRouteError as exc:
                return _error(str(exc), 422)
            except UpstreamError as exc:
                log.warning("Upstream failure: %s", exc)
                return _error(f"{exc.service} is unavailable right now ({exc.message}). Please try again.", 502)
            except Exception:  # noqa: BLE001 - last-resort guard, details go to the log
                log.exception("Unhandled error in %s", view.__name__)
                return _error("Unexpected server error.", 500)

        return wrapper

    return decorator


def _json_body(request: HttpRequest):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationError({"body": "Request body must be valid JSON."}) from exc


@api_view("GET")
def health(request: HttpRequest) -> dict:
    return {"status": "ok"}


@api_view("GET")
def geocode(request: HttpRequest) -> dict:
    query = request.GET.get("q", "").strip()
    if len(query) < 3:
        return {"results": []}
    return {"results": [p.as_dict() for p in geocoding.search(query[:200])]}


@api_view("POST")
def plan(request: HttpRequest) -> dict:
    trip = parse_trip_request(_json_body(request))
    trip = replace(
        trip,
        origin=geocoding.resolve(trip.origin, "origin"),
        destination=geocoding.resolve(trip.destination, "destination"),
    )
    return planner.plan_trip(trip)


@api_view("POST")
def heatmap_view(request: HttpRequest) -> dict:
    return heatmap.build_heatmap(parse_heatmap_request(_json_body(request)))
