"""Public connector API consumed by collection workers and administration."""

from typing import Any

from .base import Connector, NormalizedObservation
from .registry import registry
from .security import ConnectorError, limiter

__all__ = ["Connector", "ConnectorError", "NormalizedObservation", "configure_rate_limiter", "registry"]


def configure_rate_limiter(redis_client: Any) -> None:
    """Use shared Redis permits in worker processes; passing None enables local fallback."""
    limiter.redis = redis_client
