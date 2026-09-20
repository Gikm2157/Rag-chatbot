import redis as _redis
from functools import lru_cache

from config import get_settings


@lru_cache
def get_redis() -> _redis.Redis:
    setting = get_settings()
    return _redis.Redis(
        host=setting.redis_host,
        port=setting.redis_port,
        password=setting.redis_password or None,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


# backward-compatible alias used by graph nodes
redis = get_redis()
