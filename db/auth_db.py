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
    """创建认证和部门表，并把旧员工归入默认部门。"""
    with _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS departments (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
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
        connection.execute(
            """
            INSERT OR IGNORE INTO departments (id, name, created_at)
            VALUES ('default', '默认部门', CURRENT_TIMESTAMP)
            """
        )
        connection.execute(
            "UPDATE users SET department_id = 'default' "
            "WHERE role = 'employee' AND department_id IS NULL"
        )


def get_department_by_id(department_id: str) -> dict | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM departments WHERE id = ?",
            (department_id,),
        ).fetchone()
    return dict(row) if row else None


def list_departments() -> list[dict]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM departments ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [dict(row) for row in rows]


def update_department(department_id: str, name: str) -> dict | None:
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE departments SET name = ? WHERE id = ?",
            (name, department_id),
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            "SELECT * FROM departments WHERE id = ?",
            (department_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_department(department_id: str) -> bool:
    with _connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM departments
            WHERE id = ? AND id != 'default'
              AND NOT EXISTS (
                  SELECT 1 FROM users WHERE users.department_id = departments.id
              )
            """,
            (department_id,),
        )
    return cursor.rowcount > 0


def create_department(*, department_id: str, name: str, created_at: str) -> dict:
    with _connection() as connection:
        connection.execute(
            "INSERT INTO departments (id, name, created_at) VALUES (?, ?, ?)",
            (department_id, name, created_at),
        )
    return get_department_by_id(department_id)  # type: ignore[return-value]


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


def list_employees() -> list[dict]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT users.*, departments.name AS department_name
            FROM users
            LEFT JOIN departments ON departments.id = users.department_id
            WHERE users.role = 'employee'
            ORDER BY users.username COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


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


def update_employee(
    *,
    user_id: str,
    username: str,
    department_id: str,
    password_hash: str | None = None,
) -> dict | None:
    with _connection() as connection:
        if password_hash is None:
            cursor = connection.execute(
                """
                UPDATE users SET username = ?, department_id = ?
                WHERE id = ? AND role = 'employee'
                """,
                (username, department_id, user_id),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE users SET username = ?, department_id = ?, password_hash = ?
                WHERE id = ? AND role = 'employee'
                """,
                (username, department_id, password_hash, user_id),
            )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            """
            SELECT users.*, departments.name AS department_name
            FROM users
            LEFT JOIN departments ON departments.id = users.department_id
            WHERE users.id = ? AND users.role = 'employee'
            """,
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def get_employee_department_id(user_id: str) -> str | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT department_id FROM users WHERE id = ? AND role = 'employee'",
            (user_id,),
        ).fetchone()
    return row["department_id"] if row else None


def delete_employee(user_id: str) -> bool:
    with _connection() as connection:
        cursor = connection.execute(
            "DELETE FROM users WHERE id = ? AND role = 'employee'",
            (user_id,),
        )
    return cursor.rowcount > 0


@lru_cache(maxsize=1)
def auth_db_ready() -> bool:
    """让应用启动时只执行一次表初始化。"""
    initialize_auth_db()
    return True
