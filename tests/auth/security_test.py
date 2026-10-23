import hashlib
from types import SimpleNamespace
from unittest.mock import patch

from auth.security import hash_password, verify_password
from services.auth_service import (
    create_session,
    delete_employee,
    delete_session,
    get_user_from_session,
    update_employee,
)


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("wrong password", first)


def test_malformed_password_hash_is_rejected():
    assert not verify_password("anything", "not-a-valid-hash")


def test_session_token_is_stored_as_a_hash(fake_redis):
    setting = SimpleNamespace(auth_session_ttl_seconds=300)
    with patch("services.auth_service.redis", fake_redis), patch(
        "services.auth_service.get_settings", return_value=setting
    ):
        token = create_session("user-1")

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert fake_redis.get(f"auth:session:{digest}") == "user-1"
    assert fake_redis.get(f"auth:session:{token}") is None


def test_invalidated_session_no_longer_resolves(fake_redis):
    user = {
        "id": "user-1",
        "username": "employee",
        "password_hash": "must-not-leak",
        "role": "employee",
        "department_id": None,
    }
    with patch("services.auth_service.redis", fake_redis), patch(
        "services.auth_service.auth_db.get_user_by_id", return_value=user
    ):
        token = create_session("user-1")
        assert get_user_from_session(token) == {
            "id": "user-1",
            "username": "employee",
            "role": "employee",
            "department_id": None,
        }
        delete_session(token)
        assert get_user_from_session(token) is None


def test_session_user_includes_department_name():
    user = {
        "id": "user-1",
        "username": "employee",
        "role": "employee",
        "department_id": "sales",
    }
    with patch("services.auth_service.auth_db.get_department_by_id", return_value={"name": "销售部"}):
        from services.auth_service import _public_user

        assert _public_user(user)["department_name"] == "销售部"


def test_moving_employee_clears_previous_department_memory(fake_redis):
    updated_user = {
        "id": "user-1",
        "username": "employee",
        "role": "employee",
        "department_id": "hr",
        "department_name": "人事部",
    }
    fake_redis.set("user-1", "previous department conversation")
    with patch("services.auth_service.redis", fake_redis), patch(
        "services.auth_service.auth_db.get_employee_department_id", return_value="sales"
    ), patch("services.auth_service.auth_db.update_employee", return_value=updated_user):
        user = update_employee("user-1", "employee", "hr", None)

    assert user["department_name"] == "人事部"
    assert fake_redis.get("user-1") is None


def test_deleting_employee_clears_chat_memory(fake_redis):
    fake_redis.set("user-1", "private conversation")
    with patch("services.auth_service.redis", fake_redis), patch(
        "services.auth_service.auth_db.delete_employee", return_value=True
    ):
        assert delete_employee("user-1") is True

    assert fake_redis.get("user-1") is None
