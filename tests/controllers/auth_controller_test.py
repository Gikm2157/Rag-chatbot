from unittest.mock import patch


def test_chat_requires_login(app_client):
    """没有登录 Cookie 时，不能调用问答接口。"""
    from dependencies.auth import get_current_user
    from main import app

    override = app.dependency_overrides.pop(get_current_user)
    try:
        response = app_client.post("/api/v1/chat", json={"q": "测试问题"})
        docs_response = app_client.get("/api/v1/ingest/docs")
    finally:
        app.dependency_overrides[get_current_user] = override

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"
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
            "department_id": None,
        },
    ) as create_employee:
        response = app_client.post(
            "/api/v1/auth/users",
            json={"username": "new_employee", "password": "password123"},
        )

    assert response.status_code == 201
    assert response.json()["role"] == "employee"
    create_employee.assert_called_once_with("new_employee", "password123")


def test_employee_cannot_create_another_account(app_client, set_current_user):
    set_current_user(user_id="employee-1", role="employee")

    response = app_client.post(
        "/api/v1/auth/users",
        json={"username": "another_employee", "password": "password123"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "需要管理员权限"
