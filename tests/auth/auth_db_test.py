import sqlite3
from types import SimpleNamespace

from db import auth_db


def test_initialize_auth_db_migrates_existing_employees_to_default_department(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "auth.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'employee')),
            department_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.executemany(
        "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("admin-1", "admin", "hash", "admin", None, "now"),
            ("employee-1", "employee", "hash", "employee", None, "now"),
        ],
    )
    connection.commit()
    connection.close()
    monkeypatch.setattr(
        auth_db,
        "get_settings",
        lambda: SimpleNamespace(auth_db_path=str(database_path)),
    )

    auth_db.initialize_auth_db()
    auth_db.initialize_auth_db()

    assert auth_db.get_department_by_id("default")["name"] == "默认部门"
    assert auth_db.get_user_by_id("employee-1")["department_id"] == "default"
    assert auth_db.get_user_by_id("admin-1")["department_id"] is None


def test_employee_department_changes_and_department_delete_guards(tmp_path, monkeypatch):
    database_path = tmp_path / "auth-crud.db"
    monkeypatch.setattr(
        auth_db,
        "get_settings",
        lambda: SimpleNamespace(auth_db_path=str(database_path)),
    )
    auth_db.initialize_auth_db()
    auth_db.create_department(department_id="sales", name="销售部", created_at="now")
    auth_db.create_user(
        user_id="employee-1",
        username="staff",
        password_hash="hash",
        role="employee",
        department_id="sales",
        created_at="now",
    )

    assert auth_db.delete_department("default") is False
    assert auth_db.delete_department("sales") is False
    assert auth_db.list_employees()[0]["department_name"] == "销售部"

    updated = auth_db.update_employee(
        user_id="employee-1",
        username="staff-renamed",
        department_id="default",
        password_hash="new-hash",
    )
    assert updated["username"] == "staff-renamed"
    assert updated["password_hash"] == "new-hash"
    assert auth_db.get_employee_department_id("employee-1") == "default"
    assert auth_db.delete_employee("employee-1") is True
    assert auth_db.delete_employee("employee-1") is False
    assert auth_db.delete_department("sales") is True
