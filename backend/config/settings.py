"""Django settings for the Truck Route Safety backend.

The app is stateless: no database, an in-process cache for upstream API
responses, and (in production) the built React app served by WhiteNoise.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key")
DEBUG = _env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "*")
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "corsheaders",
    "routeplanner",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# No models, so no database.
DATABASES: dict = {}

USE_TZ = True
TIME_ZONE = "UTC"
USE_I18N = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "TIMEOUT": 900,
        "OPTIONS": {"MAX_ENTRIES": 2000},
    }
}

# Only needed when the front end is served from a different origin (e.g. Vercel).
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS", "")

# --- Front end ----------------------------------------------------------------
# In production the Docker build copies the Vite output here and WhiteNoise
# serves it from "/". During development Vite serves it and proxies /api.
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
STATIC_URL = "/static/"
if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST


def _immutable(path: str, url: str) -> bool:
    # Vite fingerprints everything under /assets/, so those can be cached forever.
    return url.startswith("/assets/")


WHITENOISE_IMMUTABLE_FILE_TEST = _immutable

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

# --- App configuration ----------------------------------------------------------
ROUTEPLANNER = {
    # Third-party services (all free, no API key required).
    "OSRM_BASE_URL": os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org"),
    "OPEN_METEO_URL": os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"),
    "GEOCODER_URL": os.environ.get("GEOCODER_URL", "https://photon.komoot.io/api/"),
    "USER_AGENT": os.environ.get("HTTP_USER_AGENT", "TruckRouteSafety/1.0"),
    "HTTP_TIMEOUT_S": float(os.environ.get("HTTP_TIMEOUT_S", "20")),
    # Routing
    "ROUTE_COUNT": 3,
    "TRUCK_MAX_SPEED_MPH": float(os.environ.get("TRUCK_MAX_SPEED_MPH", "65")),
    # Weather / risk
    "WIND_METRIC": os.environ.get("WIND_METRIC", "sustained"),  # "sustained" or "gust"
    "MAX_DEPARTURE_DAYS_AHEAD": 7,
    # Heatmap
    "HEATMAP_HOURS": 48,
    "HEATMAP_MAX_CELLS": int(os.environ.get("HEATMAP_MAX_CELLS", "350")),
    "HEATMAP_CORRIDOR_MI": float(os.environ.get("HEATMAP_CORRIDOR_MI", "40")),
}
