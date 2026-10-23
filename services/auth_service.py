import logging
import hashlib
from datetime import datetime, timezone
from functools import lru_cache

from config import get_settings
from db import auth_db
from db.redis_client import redis
from auth.security import create_session_token, hash_password, verify_password

logger = logging.getLogger(__name__)


def _session_key(token: str) -> str:
    """Redis 只保存会话令牌的摘要，避免令牌从 Redis 键名中直接泄露。"""
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"auth:session:{digest}"


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "department_id": user.get("department_id"),
    }


def ensure_admin_user() -> None:
    """使用环境变量创建初始管理员；已有同名用户不会被覆盖。"""
    setting = get_settings()
    if not setting.auth_admin_username or not setting.auth_admin_password:
        logger.warning(
            "AUTH_ADMIN_USERNAME/AUTH_ADMIN_PASSWORD 未配置，暂不创建初始管理员"
        )
        return

    username = setting.auth_admin_username.strip()
    if len(username) < 1 or len(setting.auth_admin_password) < 8:
        raise RuntimeError(
            "AUTH_ADMIN_USERNAME 不能为空，AUTH_ADMIN_PASSWORD 至少需要 8 位"
        )
    if auth_db.get_user_by_username(username):
        return

    auth_db.create_user(
        user_id=f"user-{create_session_token()[:16]}",
        username=username,
        password_hash=hash_password(setting.auth_admin_password),
        role="admin",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    logger.info("Created initial administrator account: %s", username)


def authenticate(username: str, password: str) -> dict | None:
    user = auth_db.get_user_by_username(username.strip())
    if not user or not verify_password(password, user["password_hash"]):
        return None
    return _public_user(user)


def create_employee(username: str, password: str) -> dict:
    user = auth_db.create_user(
        user_id=f"user-{create_session_token()[:16]}",
        username=username.strip(),
        password_hash=hash_password(password),
        role="employee",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return _public_user(user)


def create_session(user_id: str) -> str:
    setting = get_settings()
    token = create_session_token()
    redis.setex(
        _session_key(token),
        setting.auth_session_ttl_seconds,
        user_id,
    )
    return token


def get_user_from_session(token: str | None) -> dict | None:
    if not token:
        return None
    user_id = redis.get(_session_key(token))
    if not user_id:
        return None
    user = auth_db.get_user_by_id(user_id)
    return _public_user(user) if user else None


def delete_session(token: str | None) -> None:
    if token:
        redis.delete(_session_key(token))


@lru_cache(maxsize=1)
def initialize_auth() -> bool:
    auth_db.auth_db_ready()
    ensure_admin_user()
    return True
