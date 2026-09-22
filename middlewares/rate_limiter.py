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
    限制单个 IP 在一个时间窗口内可以发起的请求数量。

    工作方式：
      - 每个请求对应一个 Redis 键：rate_limit:{ip}:{current_window}
      - 每次请求都原子递增计数，避免并发竞争
      - TTL 到期后 Redis 自动清理该窗口的数据
      - 计数超过 max_requests 时返回 429

    将当前时间窗口编号作为键的一部分，每个新窗口都会自然使用新的计数器，
    不需要另外编写重置逻辑。
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def _increment(self, key: str) -> int:
        """Redis 调用是阻塞操作，通过 asyncio.to_thread 移出事件循环执行。"""
        redis = get_redis()
        count = redis.incr(key)  # 原子递增并取得新值

        # 只在当前窗口的第一次请求时设置 TTL，避免每次请求都重置 TTL 导致键无法过期。
        if count == 1:
            redis.expire(key, self.window_seconds + 1)

        return count

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        window = int(time.time()) // self.window_seconds  # 当前时间窗口编号
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
