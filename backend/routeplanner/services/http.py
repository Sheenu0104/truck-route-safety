"""Shared HTTP client for third-party APIs: retries, timeouts and response caching."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Any

import requests
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..conf import cfg

log = logging.getLogger(__name__)


class UpstreamError(Exception):
    """A third-party API failed or returned something unusable."""

    def __init__(self, service: str, message: str, payload: Any = None, status: int | None = None):
        super().__init__(f"{service}: {message}")
        self.service = service
        self.message = message
        self.payload = payload
        self.status = status


_session: requests.Session | None = None
_session_lock = threading.Lock()


def _get_session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            session = requests.Session()
            retry = Retry(
                total=2,
                backoff_factor=0.6,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            session.headers["User-Agent"] = cfg("USER_AGENT")
            _session = session
        return _session


def get_json(
    url: str,
    params: dict[str, Any],
    *,
    service: str,
    cache_ttl: int | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """GET a JSON document, caching successful responses for `cache_ttl` seconds."""
    key = None
    if cache_ttl:
        raw = url + "?" + json.dumps(params, sort_keys=True, default=str)
        key = "http:" + hashlib.sha256(raw.encode()).hexdigest()
        cached = cache.get(key)
        if cached is not None:
            return cached

    try:
        response = _get_session().get(url, params=params, headers=headers, timeout=cfg("HTTP_TIMEOUT_S"))
    except requests.RequestException as exc:
        log.warning("%s request failed: %s", service, exc)
        raise UpstreamError(service, f"request failed ({exc.__class__.__name__})") from exc

    try:
        data = response.json()
    except ValueError:
        data = None

    if response.status_code >= 400:
        reason = None
        if isinstance(data, dict):
            reason = data.get("reason") or data.get("message") or data.get("error")
        raise UpstreamError(
            service, f"HTTP {response.status_code}: {reason or response.reason}", payload=data, status=response.status_code
        )
    if data is None:
        raise UpstreamError(service, "response was not valid JSON")

    if key:
        cache.set(key, data, cache_ttl)
    return data
