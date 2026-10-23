import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from config import get_settings
from dependencies.auth import get_current_user, require_admin
from schemas.auth import CreateEmployeeRequest, LoginRequest, LoginResponse, UserResponse
from services.auth_service import (
    authenticate,
    create_employee,
    create_session,
    delete_session,
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
    try:
        return create_employee(request.username, request.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在") from exc


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
