"""Atomic fixed-window limits for authenticated v1 API credentials."""

from __future__ import annotations

import time
from dataclasses import dataclass
from hashlib import sha256

from django.core.cache import cache

API_V1_RATE_LIMIT = 60
API_V1_RATE_WINDOW_SECONDS = 60


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


def consume_v1_rate_limit(api_key_id: str) -> RateLimitResult:
    """Consume one request using cache operations that are atomic in Redis."""
    now = int(time.time())
    window = now // API_V1_RATE_WINDOW_SECONDS
    credential_digest = sha256(api_key_id.encode()).hexdigest()[:24]
    cache_key = f"api:v1:key:{credential_digest}:{window}"
    timeout = API_V1_RATE_WINDOW_SECONDS + 1
    if cache.add(cache_key, 1, timeout=timeout):
        count = 1
    else:
        try:
            count = cache.incr(cache_key)
        except ValueError:
            # The key can expire between add and increment at a window boundary.
            if cache.add(cache_key, 1, timeout=timeout):
                count = 1
            else:
                count = cache.incr(cache_key)

    retry_after = max(1, API_V1_RATE_WINDOW_SECONDS - (now % API_V1_RATE_WINDOW_SECONDS))
    return RateLimitResult(
        allowed=count <= API_V1_RATE_LIMIT,
        limit=API_V1_RATE_LIMIT,
        remaining=max(0, API_V1_RATE_LIMIT - count),
        retry_after=retry_after,
    )
