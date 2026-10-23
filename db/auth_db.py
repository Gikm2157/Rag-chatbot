"""SQLite 用户数据访问层。

当前用户规模较小，SQLite 足以满足单机工作室部署；通过这个独立访问层，
以后迁移 PostgreSQL 或引入 ORM 时不会把 SQL 散落在控制器中。
"""

import os
import sqlite3
from contextlib import contextmanager
from functools import lru_cache

from config import get_settings


def _connect() -> sqlite3.Connection:
    setting = get_settings()
    directory = os.path.dirname(os.path.abspath(setting.auth_db_path))
    os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(setting.auth_db_path)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _connection():
    """提供会自动关闭的 SQLite 连接，避免文件句柄和数据库锁泄漏。"""
    connection = _connect()
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def initialize_auth_db() -> None:
    """创建认证所需的表；重复启动不会覆盖已有用户。"""
    with _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'employee')),
                department_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def get_user_by_username(username: str) -> dict | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def create_user(
    *,
    user_id: str,
    username: str,
    password_hash: str,
    role: str,
    department_id: str | None = None,
    created_at: str,
) -> dict:
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO users (id, username, password_hash, role, department_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, password_hash, role, department_id, created_at),
        )
    return get_user_by_id(user_id)  # type: ignore[return-value]


@lru_cache(maxsize=1)
def auth_db_ready() -> bool:
    """让应用启动时只执行一次表初始化。"""
    initialize_auth_db()
    return True
