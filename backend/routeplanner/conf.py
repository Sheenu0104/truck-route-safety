from typing import Any

from django.conf import settings


def cfg(key: str) -> Any:
    """Read a value from the ROUTEPLANNER settings block."""
    return settings.ROUTEPLANNER[key]
