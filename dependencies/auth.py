from fastapi import Depends, HTTPException, Request, status

from config import get_settings
from services.auth_service import get_user_from_session


def get_current_user(
    request: Request,
) -> dict:
    cookie_name = get_settings().auth_session_cookie_name
    user = get_user_from_session(request.cookies.get(cookie_name))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """管理员权限依赖；先完成登录校验，再检查角色。"""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user
