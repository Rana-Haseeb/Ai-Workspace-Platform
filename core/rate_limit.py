"""Per-client request throttling.

Added in Phase 9's security review, which found ``RATE_LIMIT_PER_MINUTE`` defined in
``core/config.py`` and documented in ``.env.example`` while **nothing read it**. A setting that
advertises a protection it does not provide is worse than no setting: anyone reading the
configuration reasonably concludes the login endpoint is defended against brute force, and it
was not.

**Two limits, because two threats.** A chat client legitimately makes many requests a minute, so
a limit strict enough to stop password guessing would break normal use. Authentication endpoints
therefore get their own, much tighter allowance.

**A fixed window, not a token bucket.** The window resets on the minute, which means a caller can
send up to twice the limit across a window boundary. That is a known and accepted property: the
threat here is thousands of guesses, not sixty, and a fixed window is small enough to read in one
sitting. A sliding window would be more correct and harder to verify.

**Scope, stated plainly.** Counters live in this process. With more than one worker each has its
own allowance, so the effective limit multiplies by the worker count. For the single-container
deployment this project targets that is exact; anything larger needs a shared store such as
Redis, and this module is deliberately small enough to swap.
"""
from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from core.config import settings
from core.logging import get_logger

log = get_logger("ratelimit")

WINDOW_SECONDS = 60

# Endpoints where a wrong answer is worth retrying — the brute-force surface.
AUTH_PATHS = ("/api/auth/login", "/api/auth/register")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window request counting, keyed by client address and bucket."""

    def __init__(self, app):
        super().__init__(app)
        # {(client, bucket): [window_started_at, count]}
        self._hits: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])

    def _client(self, request: Request) -> str:
        """Identify the caller.

        ``X-Forwarded-For`` is honoured because the deployment sits behind a proxy that
        terminates TLS — without it every request appears to come from the proxy and one user
        exhausts everybody's allowance. It is trusted only because the proxy is the sole route
        in; exposed directly, this header is caller-controlled and trivially spoofed.
        """
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _limit_for(self, path: str) -> tuple[str, int]:
        if path in AUTH_PATHS:
            return "auth", settings.auth_rate_limit_per_minute
        return "api", settings.rate_limit_per_minute

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Read the limit per request rather than caching it, so a test or a redeploy can change
        # the setting without rebuilding the application.
        bucket, limit = self._limit_for(path)

        # 0 disables the limiter. The test suite uses this: nearly every test would otherwise
        # spend its budget on setup and start failing for a reason it is not testing.
        if limit <= 0 or not path.startswith("/api/"):
            return await call_next(request)

        key = (self._client(request), bucket)
        now = time.monotonic()
        window = self._hits[key]

        if now - window[0] >= WINDOW_SECONDS:
            window[0], window[1] = now, 0

        window[1] += 1
        if window[1] > limit:
            retry_after = int(WINDOW_SECONDS - (now - window[0])) + 1
            log.warning("Rate limit hit: %s on %s (%d/%d)", key[0], bucket, window[1], limit)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(limit - window[1], 0))
        return response
