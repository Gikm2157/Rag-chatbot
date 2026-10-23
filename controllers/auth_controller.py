import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from config import get_settings
from dependencies.auth import get_current_user, require_admin
from schemas.auth import (
    CreateDepartmentRequest,
    CreateEmployeeRequest,
    DepartmentResponse,
    LoginRequest,
    LoginResponse,
    UserResponse,
    UpdateEmployeeRequest,
)
from db import auth_db
from db.redis_client import redis
from services.auth_service import (
    authenticate,
    create_department,
    create_employee,
    create_session,
    delete_session,
    delete_employee,
    update_employee,
)

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=LoginResponse, summary="用户登录")
def login(request: LoginRequest, response: Response):
    user = authenticate(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    setting = get_settings()
    token = create_session(user["id"])
    response.set_cookie(
        key=setting.auth_session_cookie_name,
        value=token,
        max_age=setting.auth_session_ttl_seconds,
        httponly=True,
        secure=setting.auth_cookie_secure,
        samesite="lax",
    )
    return {"status": "success", "user": user}


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="管理员创建员工账号",
    dependencies=[Depends(require_admin)],
)
def add_employee(request: CreateEmployeeRequest):
    if not auth_db.get_department_by_id(request.department_id):
        raise HTTPException(status_code=404, detail="部门不存在")
    try:
        return create_employee(
            request.username,
            request.password,
            request.department_id,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在") from exc


@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="管理员查看员工列表",
    dependencies=[Depends(require_admin)],
)
def employees():
    return auth_db.list_employees()


@router.put(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="管理员修改员工账号",
    dependencies=[Depends(require_admin)],
)
def edit_employee(user_id: str, request: UpdateEmployeeRequest):
    if not auth_db.get_department_by_id(request.department_id):
        raise HTTPException(status_code=404, detail="部门不存在")
    try:
        user = update_employee(
            user_id,
            request.username,
            request.department_id,
            request.password,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    if not user:
        raise HTTPException(status_code=404, detail="员工账号不存在")
    return user


@router.delete(
    "/users/{user_id}",
    summary="管理员删除员工账号",
    dependencies=[Depends(require_admin)],
)
def remove_employee(user_id: str):
    if not delete_employee(user_id):
        raise HTTPException(status_code=404, detail="员工账号不存在")
    return {"status": "deleted", "user_id": user_id}


@router.get(
    "/departments",
    response_model=list[DepartmentResponse],
    summary="管理员查看部门列表",
    dependencies=[Depends(require_admin)],
)
def departments():
    return auth_db.list_departments()


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="管理员创建部门",
    dependencies=[Depends(require_admin)],
)
def add_department(request: CreateDepartmentRequest):
    try:
        return create_department(request.name)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="部门名称已存在") from exc


@router.put(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    summary="管理员修改部门名称",
    dependencies=[Depends(require_admin)],
)
def edit_department(department_id: str, request: CreateDepartmentRequest):
    try:
        department = auth_db.update_department(department_id, request.name)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="部门名称已存在") from exc
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在")
    return department


@router.delete(
    "/departments/{department_id}",
    summary="管理员删除部门",
    dependencies=[Depends(require_admin)],
)
def remove_department(department_id: str):
    if department_id == "default":
        raise HTTPException(status_code=409, detail="默认部门不可删除")
    if not auth_db.get_department_by_id(department_id):
        raise HTTPException(status_code=404, detail="部门不存在")
    for doc_id in redis.smembers("ingest:doc_ids"):
        status = redis.hgetall(f"ingest_status:{doc_id}")
        if status.get("department_id", "default") == department_id:
            raise HTTPException(status_code=409, detail="该部门仍有关联文档，请先删除或迁移文档")
    if not auth_db.delete_department(department_id):
        raise HTTPException(status_code=409, detail="该部门仍有关联员工，不能删除")
    return {"status": "deleted", "department_id": department_id}


@router.get("/me", response_model=UserResponse, summary="查看当前登录用户")
def me(
    user: dict = Depends(get_current_user),
):
    return user


@router.post("/logout", summary="退出登录")
def logout(
    response: Response,
    request: Request,
):
    setting = get_settings()
    delete_session(request.cookies.get(setting.auth_session_cookie_name))
    response.delete_cookie(setting.auth_session_cookie_name)
    return {"status": "success"}
