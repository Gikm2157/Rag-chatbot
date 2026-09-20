import asyncio
import time
import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from db.redis_client import get_redis

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Limits how many requests a single IP can make per minute.

    How it works:
      - Every request gets a Redis key:  rate_limit:{ip}:{current_minute}
      - The key is incremented on each request (atomic — no race conditions)
      - TTL of 61s means Redis cleans it up automatically after the window passes
      - If the count exceeds max_requests, return 429 Too Many Requests

    Why per-minute windows?
      Using the current minute (Unix timestamp // 60) as part of the key means
      each minute starts a fresh counter with zero cost — no reset logic needed.
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def _increment(self, key: str) -> int:
        """Blocking Redis calls — run off the event loop via asyncio.to_thread."""
        redis = get_redis()
        count = redis.incr(key)  # increment and get new value atomically

        # set TTL only on the first request in this window
        # (avoids resetting TTL on every request, which would prevent expiry)
        if count == 1:
            redis.expire(key, self.window_seconds + 1)

        return count

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        window = int(time.time()) // self.window_seconds  # current time window
        key = f"rate_limit:{ip}:{window}"

        count = await asyncio.to_thread(self._increment, key)

        if count > self.max_requests:
            logger.warning("Rate limit exceeded for IP %s (%d requests)", ip, count)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "请求过于频繁",
                    "detail": f"每 {self.window_seconds} 秒最多请求 {self.max_requests} 次，请稍后重试。"
                }
            )

        return await call_next(request)
