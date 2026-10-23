from unittest.mock import patch


def test_chat_requires_login(app_client):
    """没有登录 Cookie 时，不能调用问答接口。"""
    from dependencies.auth import get_current_user
    from main import app

    override = app.dependency_overrides.pop(get_current_user)
    try:
        response = app_client.post("/api/v1/chat", json={"q": "测试问题"})
        stream_response = app_client.post("/api/v1/chat/stream", json={"q": "测试问题"})
        docs_response = app_client.get("/api/v1/ingest/docs")
    finally:
        app.dependency_overrides[get_current_user] = override

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"
    assert stream_response.status_code == 401
    assert stream_response.json()["detail"] == "请先登录"
    assert docs_response.status_code == 401


def test_untrusted_browser_origin_cannot_make_write_request(app_client):
    response = app_client.post(
        "/api/v1/chat",
        headers={"Origin": "https://untrusted.example"},
        json={"q": "测试问题"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "请求来源不受信任"


def test_employee_can_read_but_cannot_manage_documents(
    app_client, set_current_user, mock_vs
):
    """员工可以查看文档列表，但上传和删除属于管理员操作。"""
    set_current_user(user_id="employee-1", role="employee")

    list_response = app_client.get("/api/v1/ingest/docs")
    upload_response = app_client.post(
        "/api/v1/ingest/upload",
        data={"file_name": "policy"},
        files={"file": ("policy.pdf", b"%PDF-test", "application/pdf")},
    )
    delete_response = app_client.delete("/api/v1/ingest/policy")

    assert list_response.status_code == 200
    assert upload_response.status_code == 403
    assert delete_response.status_code == 403
    mock_vs._collection.delete.assert_not_called()


def test_admin_can_create_employee_account(app_client):
    """管理员可以创建员工账号，创建接口不允许普通用户使用。"""
    with patch(
        "controllers.auth_controller.create_employee",
        return_value={
            "id": "employee-1",
            "username": "new_employee",
            "role": "employee",
                "department_id": "default",
        },
    ) as create_employee:
        response = app_client.post(
            "/api/v1/auth/users",
            json={"username": "new_employee", "password": "password123", "department_id": "default"},
        )

    assert response.status_code == 201
    assert response.json()["role"] == "employee"
    create_employee.assert_called_once_with("new_employee", "password123", "default")


def test_employee_cannot_create_another_account(app_client, set_current_user):
    set_current_user(user_id="employee-1", role="employee")

    response = app_client.post(
        "/api/v1/auth/users",
        json={"username": "another_employee", "password": "password123", "department_id": "default"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "需要管理员权限"


def test_admin_cannot_create_employee_in_unknown_department(app_client):
    with patch("controllers.auth_controller.auth_db.get_department_by_id", return_value=None):
        response = app_client.post(
            "/api/v1/auth/users",
            json={
                "username": "new_employee",
                "password": "password123",
                "department_id": "missing-department",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "部门不存在"


def test_admin_can_create_department(app_client):
    with patch(
        "controllers.auth_controller.create_department",
        return_value={"id": "dept-sales", "name": "销售部"},
    ) as create_department:
        response = app_client.post("/api/v1/auth/departments", json={"name": "销售部"})

    assert response.status_code == 201
    assert response.json() == {"id": "dept-sales", "name": "销售部"}
    create_department.assert_called_once_with("销售部")


def test_employee_cannot_list_departments(app_client, set_current_user):
    set_current_user(user_id="employee-1", role="employee", department_id="default")

    response = app_client.get("/api/v1/auth/departments")

    assert response.status_code == 403


def test_admin_can_list_employee_accounts(app_client):
    employees = [{
        "id": "employee-1",
        "username": "staff",
        "role": "employee",
        "department_id": "sales",
        "department_name": "销售部",
    }]
    with patch("controllers.auth_controller.auth_db.list_employees", return_value=employees):
        response = app_client.get("/api/v1/auth/users")

    assert response.status_code == 200
    assert response.json()[0]["department_name"] == "销售部"


def test_employee_cannot_manage_employee_accounts(app_client, set_current_user):
    set_current_user(user_id="employee-1", role="employee", department_id="default")

    listed = app_client.get("/api/v1/auth/users")
    updated = app_client.put(
        "/api/v1/auth/users/employee-2",
        json={"username": "staff", "department_id": "default"},
    )
    deleted = app_client.delete("/api/v1/auth/users/employee-2")

    assert [listed.status_code, updated.status_code, deleted.status_code] == [403, 403, 403]


def test_admin_can_update_employee_account(app_client):
    with patch(
        "controllers.auth_controller.update_employee",
        return_value={
            "id": "employee-1",
            "username": "staff-renamed",
            "role": "employee",
            "department_id": "default",
            "department_name": "默认部门",
        },
    ) as update:
        response = app_client.put(
            "/api/v1/auth/users/employee-1",
            json={"username": "staff-renamed", "department_id": "default"},
        )

    assert response.status_code == 200
    assert response.json()["username"] == "staff-renamed"
    update.assert_called_once_with("employee-1", "staff-renamed", "default", None)


def test_admin_can_delete_employee_account(app_client):
    with patch("controllers.auth_controller.delete_employee", return_value=True) as delete:
        response = app_client.delete("/api/v1/auth/users/employee-1")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "user_id": "employee-1"}
    delete.assert_called_once_with("employee-1")


def test_admin_can_update_department_name(app_client):
    with patch(
        "controllers.auth_controller.auth_db.update_department",
        return_value={"id": "dept-sales", "name": "销售运营部"},
    ) as update:
        response = app_client.put(
            "/api/v1/auth/departments/dept-sales",
            json={"name": "销售运营部"},
        )

    assert response.status_code == 200
    assert response.json() == {"id": "dept-sales", "name": "销售运营部"}
    update.assert_called_once_with("dept-sales", "销售运营部")


def test_default_department_cannot_be_deleted(app_client):
    response = app_client.delete("/api/v1/auth/departments/default")

    assert response.status_code == 409
    assert response.json()["detail"] == "默认部门不可删除"


def test_department_with_documents_cannot_be_deleted(app_client, fake_redis):
    fake_redis.sadd("ingest:doc_ids", "sales-guide")
    fake_redis.hset(
        "ingest_status:sales-guide",
        mapping={"status": "done", "department_id": "dept-sales"},
    )

    response = app_client.delete("/api/v1/auth/departments/dept-sales")

    assert response.status_code == 409
    assert "关联文档" in response.json()["detail"]


def test_department_with_employees_cannot_be_deleted(app_client):
    with patch(
        "controllers.auth_controller.auth_db.get_department_by_id",
        return_value={"id": "dept-sales", "name": "销售部"},
    ), patch("controllers.auth_controller.auth_db.delete_department", return_value=False):
        response = app_client.delete("/api/v1/auth/departments/dept-sales")

    assert response.status_code == 409
    assert response.json()["detail"] == "该部门仍有关联员工，不能删除"


def test_admin_can_delete_empty_department(app_client):
    with patch(
        "controllers.auth_controller.auth_db.get_department_by_id",
        return_value={"id": "dept-sales", "name": "销售部"},
    ), patch("controllers.auth_controller.auth_db.delete_department", return_value=True):
        response = app_client.delete("/api/v1/auth/departments/dept-sales")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "department_id": "dept-sales"}
