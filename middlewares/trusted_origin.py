"""限制携带 Cookie 的浏览器写请求来源，降低跨站请求伪造风险。"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings


class TrustedOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.allowed_origins = set(get_settings().cors_origins)

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        is_write = request.method in {"POST", "PUT", "PATCH", "DELETE"}

        # CLI/服务端请求通常不带 Origin；浏览器写请求必须来自明确配置的前端源。
        # 不接受通配符，避免把带 Cookie 的接口开放给任意网站发起。
        if is_write and origin and origin not in self.allowed_origins:
            return JSONResponse(
                status_code=403,
                content={"detail": "请求来源不受信任"},
            )

        return await call_next(request)
