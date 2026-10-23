import logging

from fastapi import APIRouter, Depends, HTTPException

from dependencies.auth import get_current_user
from schemas.chat import ChatRequest, ChatResponse
from services.chat_service import conversation

logger = logging.getLogger(__name__)
router = APIRouter()

# 从 HTTP 请求头读取 x-user-id；如果没有提供，则使用anonymous作为默认用户 ID。
@router.post("/chat", response_model=ChatResponse, summary="知识库问答")
def chat_controller(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
):
    try:
        result = conversation(user_id=user["id"], q=request.q)
        logger.info("Chat response generated for user %s", user["id"])
        return {"status": "success", "data": result["answer"], "sources": result["sources"]}
    except Exception:
        logger.exception("Chat failed for user %s", user["id"])
        raise HTTPException(status_code=500, detail="生成回答失败")
