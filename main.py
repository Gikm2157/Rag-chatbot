import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from controllers.chat_controller import router as chat_router
from controllers.ingest_controller import router as ingest_router
from middlewares.logging_setup import setup_logging
from middlewares.rate_limiter import RateLimitMiddleware
from db.redis_client import get_redis
from db.vector import get_vectorstore

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

# this defines a special function that FastAPI runs around the app lifecycle:

# Code before yield → startup
# Code after yield → shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_redis().ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.error("Redis connection failed: %s", e)

    try:
        get_vectorstore().similarity_search("health", k=1)
        logger.info("ChromaDB connected")
    except Exception as e:
        logger.error("ChromaDB connection failed: %s", e)
    # anything want to start before app start here are the above functions that will be called before the app starts, such as database connections and redis.
    yield
    # after shutown, you can do some instruction here if needed.
    logger.info("Shutting down...")

app = FastAPI(
    title="企业知识库客服 API",
    description="提供 PDF 文档导入、知识库管理和智能问答接口。",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")

# This is a custom exception handler for validation errors. When a request fails validation, it will return a structured JSON response with details about which fields failed and why.
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "请求参数校验失败", "details": errors})

# This is a generic exception handler that catches any unhandled exceptions in the application. It logs the error and returns a generic 500 Internal Server Error response to the client, without exposing sensitive details about the error. Note:- not validations errors, those are handled by the above handler. This is for any other unhandled exceptions that may occur in the application.
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "服务器内部错误"})


@app.get("/health", summary="服务健康检查")
def health_check():
    return {"status": "ok"}


@app.get("/", summary="服务运行状态")
def home():
    return {"message": "企业知识库客服正在运行"}
